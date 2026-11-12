"""Build chart specs from aggregated stats + display settings (separate from aggregation)."""

from __future__ import annotations

from typing import Any

from pentaklip.stats.catalog import (
    LCK_RADAR_STAT_KEYS,
    OCR_RADAR_STAT_KEYS,
    SERIES_STAT_KEYS,
    SIGNED_RADAR_STAT_KEYS,
    STAT_LABELS,
    Position,
    StatKey,
    position_label,
)
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

# Lower value is better on radar (inverted when normalizing).
_RADAR_LOWER_BETTER = {
    StatKey.DEATHS,
}

# Cap axes so radar stays readable; allow more room for jungle objectives.
_RADAR_MAX_AXES = 8

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
        title=f"{position_label(position)} stats",
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
        title=f"{position_label(position)} · Player comparison",
        position=position,
        series=series,
        columns=["stat"],
        rows=rows,
    )


def _radar_axis_keys(
    columns: list[StatKey],
    *,
    players: list[PlayerPositionAggregate] | None = None,
) -> list[StatKey]:
    """Prefer LCK octagon order; drop OCR damage axes when no DPM/DMG% data."""
    usable = [k for k in columns if k not in _COMPARE_SKIP and k not in SERIES_STAT_KEYS]
    preferred = [k for k in LCK_RADAR_STAT_KEYS if k in usable]
    has_damage = False
    if players is not None:
        has_damage = any(
            p.scalars.get(StatKey.DPM.value) is not None
            or p.scalars.get(StatKey.DAMAGE_SHARE.value) is not None
            for p in players
        )
        if not has_damage:
            preferred = [k for k in preferred if k not in OCR_RADAR_STAT_KEYS]
    rest = [k for k in usable if k not in preferred]
    if not has_damage:
        rest = [k for k in rest if k not in OCR_RADAR_STAT_KEYS]
    return [*preferred, *rest][:_RADAR_MAX_AXES]


def _mean_scalar(players: list[PlayerPositionAggregate], key: StatKey) -> float | None:
    vals = [_as_number(p.scalars.get(key.value)) for p in players]
    present = [v for v in vals if v is not None]
    if not present:
        return None
    return sum(present) / len(present)


def _baseline_for_radar(
    focus: PlayerPositionAggregate,
    players: list[PlayerPositionAggregate],
    axes: list[StatKey],
    *,
    all_players: list[PlayerPositionAggregate] | None = None,
) -> tuple[str, dict[str, float | None]]:
    """Dashed baseline is always an average (never a named 1v1 opponent)."""
    # Prefer mean of everyone on this lane (stable role average across the set).
    if len(players) >= 2:
        return "レーン平均", {k.value: _mean_scalar(players, k) for k in axes}

    # Single player on the lane → fall back to match-wide average.
    pool = [
        p
        for p in (all_players or players)
        if p.player_id != focus.player_id
    ]
    if pool:
        return "全体平均", {k.value: _mean_scalar(pool, k) for k in axes}
    return "平均", {k.value: None for k in axes}


def _normalize_radar_value(
    value: float | None,
    peak: float,
    *,
    lower_is_better: bool,
    signed: bool = False,
) -> float | None:
    if value is None or peak <= 0:
        return None
    if signed:
        # Map [-peak, +peak] → [0, 1] so even (0) sits at the center ring.
        return max(0.0, min(1.0, (value + peak) / (2.0 * peak)))
    ratio = max(0.0, min(1.0, abs(value) / peak))
    return (1.0 - ratio) if lower_is_better else ratio


def _radar_charts_for_position(
    position: Position,
    players: list[PlayerPositionAggregate],
    columns: list[StatKey],
    *,
    all_players: list[PlayerPositionAggregate] | None = None,
) -> list[ChartSpec]:
    """
    LCK-style radar (pentagon/hexagon): filled polygon = player, dashed = average.

    Each row is one axis with raw + normalized values for Recharts RadarChart.
    """
    axes = _radar_axis_keys(columns, players=players)
    if len(axes) < 3 or not players:
        return []

    charts: list[ChartSpec] = []
    for focus in sorted(players, key=lambda p: p.player_id.casefold()):
        baseline_label, baseline_vals = _baseline_for_radar(
            focus, players, axes, all_players=all_players
        )
        rows: list[dict[str, Any]] = []
        for key in axes:
            player_v = _as_number(focus.scalars.get(key.value))
            baseline_v = baseline_vals.get(key.value)
            present = [v for v in (player_v, baseline_v) if v is not None]
            if not present:
                continue
            peak = max(abs(v) for v in present)
            if peak <= 0:
                peak = 1.0
            lower = key in _RADAR_LOWER_BETTER
            signed = key in SIGNED_RADAR_STAT_KEYS
            rows.append(
                {
                    "stat_key": key.value,
                    "axis": STAT_LABELS.get(key, key.value),
                    "player": player_v,
                    "baseline": baseline_v,
                    "player_norm": _normalize_radar_value(
                        player_v,
                        peak,
                        lower_is_better=lower,
                        signed=signed,
                    ),
                    "baseline_norm": _normalize_radar_value(
                        baseline_v,
                        peak,
                        lower_is_better=lower,
                        signed=signed,
                    ),
                    "max": peak,
                    "lower_is_better": lower,
                    "signed": signed,
                }
            )
        if len(rows) < 3:
            continue
        charts.append(
            ChartSpec(
                chart_id=f"radar-{position.value}-{focus.player_id}",
                chart_type="radar",
                title=f"{position_label(position)} · {focus.player_id}",
                position=position,
                series=[
                    ChartSeries(
                        key="player",
                        label=focus.player_id,
                        player_id=focus.player_id,
                        position=position,
                        value=focus.team,
                    ),
                    ChartSeries(
                        key="baseline",
                        label=baseline_label,
                        player_id=baseline_label,
                        position=position,
                        value="dashed",
                    ),
                ],
                columns=["axis", "player", "baseline"],
                rows=rows,
            )
        )
    return charts


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
                title=f"{player.player_id} ({position_label(player.position)}) — {label}",
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
    Emits LCK-style lane comparison bars, radar polygons, plus optional lines.
    """
    settings = display or default_display_settings()
    charts: list[ChartSpec] = []

    by_pos: dict[Position, list[PlayerPositionAggregate]] = {}
    for player in aggregated.players:
        by_pos.setdefault(player.position, []).append(player)

    all_players = list(aggregated.players)
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
            *[f"radar:{k.value}" for k in _radar_axis_keys(table_keys)],
            *[f"chart:{k.value}" for k in chart_keys],
        ]
        if table_keys:
            charts.append(_table_chart_for_position(position, players, table_keys))
            compare = _lane_compare_chart(position, players, table_keys)
            if compare is not None:
                charts.append(compare)
            charts.extend(
                _radar_charts_for_position(
                    position, players, table_keys, all_players=all_players
                )
            )
        for player in players:
            charts.extend(_line_charts_for_player(player, chart_keys))

    return ChartBundle(charts=charts, display_settings_applied=applied)
