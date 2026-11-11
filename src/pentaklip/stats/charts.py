"""Build chart specs from aggregated stats + display settings (separate from aggregation)."""

from __future__ import annotations

from pentaklip.stats.catalog import SERIES_STAT_KEYS, STAT_LABELS, Position, StatKey
from pentaklip.stats.display import DisplaySettings, default_display_settings
from pentaklip.stats.models import (
    AggregatedReplayStats,
    ChartBundle,
    ChartSeries,
    ChartSpec,
    PlayerPositionAggregate,
)


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
    """
    settings = display or default_display_settings()
    charts: list[ChartSpec] = []

    by_pos: dict[Position, list[PlayerPositionAggregate]] = {}
    for player in aggregated.players:
        by_pos.setdefault(player.position, []).append(player)

    applied: dict[str, list[str]] = {}
    for position, players in by_pos.items():
        table_keys = settings.table_by_position.get(position) or []
        chart_keys = settings.charts_by_position.get(position) or []
        applied[position.value] = [
            *[f"table:{k.value}" for k in table_keys],
            *[f"chart:{k.value}" for k in chart_keys],
        ]
        if table_keys:
            charts.append(_table_chart_for_position(position, players, table_keys))
        for player in players:
            charts.extend(_line_charts_for_player(player, chart_keys))

    return ChartBundle(charts=charts, display_settings_applied=applied)
