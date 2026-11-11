"""Stats data models: raw capture bundles vs aggregated views."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from pentaklip.stats.catalog import Position, StatKey
from pentaklip.stats.identity import PlayerIdentity


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class PlayerSnapshot(BaseModel):
    """One player's state at a sample time (keeps raw payload for max fidelity)."""

    identity: PlayerIdentity
    position: Position
    champion_name: str | None = None
    team: str | None = None
    level: int | None = None
    is_dead: bool | None = None
    respawn_timer: float | None = None
    scores: dict[str, Any] = Field(default_factory=dict)
    items: list[dict[str, Any]] = Field(default_factory=list)
    runes: dict[str, Any] = Field(default_factory=dict)
    summoner_spells: dict[str, Any] = Field(default_factory=dict)
    raw: dict[str, Any] = Field(default_factory=dict)


class GameSnapshot(BaseModel):
    game_time_sec: float
    game_data: dict[str, Any] = Field(default_factory=dict)
    active_player: dict[str, Any] = Field(default_factory=dict)
    players: list[PlayerSnapshot] = Field(default_factory=list)
    events: list[dict[str, Any]] = Field(default_factory=list)
    raw_all_game_data: dict[str, Any] = Field(default_factory=dict)


class ReplayStatsBundle(BaseModel):
    """Per-replay capture file (JSON/YAML). Prefer rich raw retention."""

    schema_version: int = 1
    original_match_id: str | None = None
    local_replay_id: str | None = None
    source_filename: str | None = None
    captured_at: str = Field(default_factory=utc_now_iso)
    sample_interval_sec: float | None = None
    snapshots: list[GameSnapshot] = Field(default_factory=list)
    events: list[dict[str, Any]] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)


class TimePoint(BaseModel):
    game_time_sec: float
    value: float


class PlayerPositionAggregate(BaseModel):
    """Aggregated end + series stats for one (player_id, position)."""

    player_id: str
    position: Position
    identity: PlayerIdentity
    champion_name: str | None = None
    team: str | None = None
    scalars: dict[str, float | int | str | bool | None] = Field(default_factory=dict)
    series: dict[str, list[TimePoint]] = Field(default_factory=dict)
    event_counts: dict[str, int] = Field(default_factory=dict)
    raw_last_player: dict[str, Any] = Field(default_factory=dict)


class AggregatedReplayStats(BaseModel):
    schema_version: int = 1
    original_match_id: str | None = None
    local_replay_id: str | None = None
    game_duration_sec: float = 0.0
    players: list[PlayerPositionAggregate] = Field(default_factory=list)
    team_totals: dict[str, dict[str, float]] = Field(default_factory=dict)
    meta: dict[str, Any] = Field(default_factory=dict)


class ChartSeries(BaseModel):
    key: StatKey | str
    label: str
    player_id: str
    position: Position
    points: list[TimePoint] = Field(default_factory=list)
    value: float | int | str | bool | None = None


class ChartSpec(BaseModel):
    """Frontend-ready chart description (Recharts/Chart.js etc.). Separate from aggregation."""

    chart_id: str
    chart_type: str  # "line" | "bar" | "table"
    title: str
    position: Position | None = None
    series: list[ChartSeries] = Field(default_factory=list)
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)


class ChartBundle(BaseModel):
    charts: list[ChartSpec] = Field(default_factory=list)
    display_settings_applied: dict[str, list[str]] = Field(default_factory=dict)
