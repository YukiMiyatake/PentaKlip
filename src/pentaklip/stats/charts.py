"""Build chart specs from aggregated stats + display settings (separate from aggregation)."""

from __future__ import annotations

from typing import Any

from pentaklip.stats.catalog import SERIES_STAT_KEYS, STAT_LABELS, Position, StatKey
from pentaklip.stats.display import DisplaySettings, default_display_settings
from pentaklip.stats.models import (
    AggregatedReplayStats,
    ChartBundle,
    ChartSeries,
    ChartSpec,
    PlayerPositionAggregate,
)

_COMPARE_SKIP = {
    StatKey.CHAMPION,
    StatKey.TEAM,
    StatKey.IS_DEAD,
}

_POSITION_ORDER = [
    Position.TOP,
    Position.JUNGLE,
    Position.MIDDLE,
    Position.BOTTOM,
    Position.UTILITY,
    Position.UNKNOWN,
]


def _as_number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _table_chart_for_position(
    position: Position,
    players: list[PlayerPositionAggregate],
    columns: list[StatKey],
) -> ChartSpec:
    col_names = [STAT_LABELS.get(c, c.value) for c in columns]
    rows: list[dict] = []
    for player in players:
        row: dict = {
            "player_id": player.player_id,
            "position": player.position.value,
        }
        for key in columns:
            row[STAT_LABELS.get(key, key.value)] = player.scalars.get(key.value)
        rows.append(row)
    return ChartSpec(
        chart_id=f"table-{position.value}",
        chart_type="table",
        title=f"{position.value} stats",
        position=position,
        columns=["player_id", *col_names],
        rows=rows,
    )


def _lane_compare_chart(
    position: Position,
    players: list[PlayerPositionAggregate],
    columns: list[StatKey],
) -> ChartSpec | None:
    """
    LCK-style per-lane comparison: one row per scalar metric, bars per player.

    Rows carry ``value_i`` / ``player_i`` / ``team_i`` for the viewer.
    """
    if not players:
        return None
    ordered = sorted(
        players,
        key=lambda p: (str(p.team or "~"), p.player_id.casefold()),
    )
    series = [
        ChartSeries(
            key="player",
            label=player.player_id,
            player_id=player.player_id,
            position=position,
            value=player.team,
        )
        for player in ordered
    ]
    rows: list[dict[str, Any]] = []
    for key in columns:
        if key in _COMPARE_SKIP:
            continue
        nums = [_as_number(p.scalars.get(key.value)) for p in ordered]
        if all(v is None for v in nums):
            continue
        present = [v for v in nums if v is not None]
        peak = max(abs(v) for v in present) if present else 1.0
        if peak <= 0:
            peak = 1.0
        row: dict[str, Any] = {
            "stat_key": key.value,
            "stat": STAT_LABELS.get(key, key.value),
            "max": peak,
            "player_count": len(ordered),
        }
        for index, player in enumerate(ordered):
            row[f"player_{index}"] = player.player_id
            row[f"team_{index}"] = player.team
            row[f"champion_{index}"] = player.champion_name
            row[f"value_{index}"] = nums[index]
        rows.append(row)
    if not rows:
        return None
    return ChartSpec(
        chart_id=f"lane-compare-{position.value}",
        chart_type="lane_compare",
        title=f"{position.value} · Player comparison",
        position=position,
        series=series,
        columns=["stat"],
        rows=rows,
    )


def _line_charts_for_player(
    player: PlayerPositionAggregate,
    series_keys: list[StatKey],
) -> list[ChartSpec]:
    charts: list[ChartSpec] = []
    for key in series_keys:
        points = player.series.get(key.value, [])
        if not points and key not in SERIES_STAT_KEYS:
            continue
        if not points:
            continue
        label = STAT_LABELS.get(key, key.value)
        charts.append(
            ChartSpec(
                chart_id=f"line-{player.player_id}-{player.position.value}-{key.value}",
                chart_type="line",
                title=f"{player.player_id} ({player.position.value}) — {label}",
                position=player.position,
                series=[
                    ChartSeries(
                        key=key,
                        label=label,
                        player_id=player.player_id,
                        position=player.position,
                        points=points,
                    )
                ],
            )
        )
    return charts


def build_charts(
    aggregated: AggregatedReplayStats,
    display: DisplaySettings | None = None,
) -> ChartBundle:
    """
    Convert aggregates into UI-ready chart/table specs.

    Does not recompute stats; only filters/shapes using display settings.
    Emits LCK-style lane comparison bars from table keys, plus optional lines.
    """
    settings = display or default_display_settings()
    charts: list[ChartSpec] = []

    by_pos: dict[Position, list[PlayerPositionAggregate]] = {}
    for player in aggregated.players:
        by_pos.setdefault(player.position, []).append(player)

    applied: dict[str, list[str]] = {}
    for position in _POSITION_ORDER:
        players = by_pos.get(position) or []
        if not players:
            continue
        table_keys = settings.table_by_position.get(position) or []
        chart_keys = settings.charts_by_position.get(position) or []
        applied[position.value] = [
            *[f"table:{k.value}" for k in table_keys],
            *[f"compare:{k.value}" for k in table_keys],
            *[f"chart:{k.value}" for k in chart_keys],
        ]
        if table_keys:
            charts.append(_table_chart_for_position(position, players, table_keys))
            compare = _lane_compare_chart(position, players, table_keys)
            if compare is not None:
                charts.append(compare)
        for player in players:
            charts.extend(_line_charts_for_player(player, chart_keys))

    return ChartBundle(charts=charts, display_settings_applied=applied)
