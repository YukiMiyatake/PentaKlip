"""Per-lane (position) settings for which stats to show. Independent of capture/aggregate."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from pentaklip.stats.catalog import (
    LCK_RADAR_STAT_KEYS,
    SERIES_STAT_KEYS,
    TABLE_STAT_KEYS,
    Position,
    StatKey,
)
from pentaklip.stats.roster import clean_roster_aliases


class DisplaySettings(BaseModel):
    """Which stats to display for each lane / position, plus roster aliases."""

    table_by_position: dict[Position, list[StatKey]] = Field(default_factory=dict)
    charts_by_position: dict[Position, list[StatKey]] = Field(default_factory=dict)
    # Registered names per lane for fuzzy Riot-ID matching (tag ignored).
    roster_by_position: dict[Position, list[str]] = Field(default_factory=dict)


def default_display_settings() -> DisplaySettings:
    """LCK-ish defaults; radar axes lead with Live Client proxies for the LCK octagon."""
    # First columns drive radar (see LCK_RADAR_STAT_KEYS); extras follow for tables.
    lck_lead = [StatKey.CHAMPION, *LCK_RADAR_STAT_KEYS]
    shared_table = [
        *lck_lead,
        StatKey.KILLS,
        StatKey.DEATHS,
        StatKey.ASSISTS,
        StatKey.CREEP_SCORE,
        StatKey.LEVEL_AT_15,
        StatKey.LEVEL,
    ]
    jg_table = [
        *lck_lead,
        StatKey.KILLS,
        StatKey.DEATHS,
        StatKey.ASSISTS,
        StatKey.CREEP_SCORE,
        StatKey.LEVEL_AT_15,
        StatKey.DRAGON_KILLS,
        StatKey.BARON_KILLS,
        StatKey.HERALD_KILLS,
        StatKey.GOLD,
        StatKey.LEVEL,
    ]
    support_table = [
        *lck_lead,
        StatKey.KILLS,
        StatKey.DEATHS,
        StatKey.ASSISTS,
        StatKey.LEVEL,
    ]
    shared_charts = [StatKey.CS_SERIES, StatKey.KDA_SERIES, StatKey.LEVEL_SERIES]
    jg_charts = [
        StatKey.WARD_SERIES,
        StatKey.KDA_SERIES,
        StatKey.CS_SERIES,
        StatKey.GOLD_SERIES,
        StatKey.LEVEL_SERIES,
    ]
    support_charts = [StatKey.WARD_SERIES, StatKey.KDA_SERIES]

    table = {
        Position.TOP: list(shared_table),
        Position.JUNGLE: list(jg_table),
        Position.MIDDLE: list(shared_table),
        Position.BOTTOM: list(shared_table),
        Position.UTILITY: list(support_table),
        Position.UNKNOWN: list(shared_table),
    }
    charts = {
        Position.TOP: list(shared_charts),
        Position.JUNGLE: list(jg_charts),
        Position.MIDDLE: list(shared_charts),
        Position.BOTTOM: list(shared_charts),
        Position.UTILITY: list(support_charts),
        Position.UNKNOWN: list(shared_charts),
    }
    return DisplaySettings(
        table_by_position=table,
        charts_by_position=charts,
        roster_by_position={pos: [] for pos in Position},
    )


def validate_display_settings(settings: DisplaySettings) -> DisplaySettings:
    allowed_table = set(TABLE_STAT_KEYS)
    allowed_charts = set(SERIES_STAT_KEYS) | set(TABLE_STAT_KEYS)
    table: dict[Position, list[StatKey]] = {}
    charts: dict[Position, list[StatKey]] = {}
    roster: dict[Position, list[str]] = {}
    for pos in Position:
        table[pos] = [k for k in settings.table_by_position.get(pos, []) if k in allowed_table]
        charts[pos] = [
            k for k in settings.charts_by_position.get(pos, []) if k in allowed_charts
        ]
        roster[pos] = clean_roster_aliases(settings.roster_by_position.get(pos, []))
    return DisplaySettings(
        table_by_position=table,
        charts_by_position=charts,
        roster_by_position=roster,
    )


def display_settings_path(data_dir: Path) -> Path:
    return data_dir / "stats_display_settings.json"


def load_display_settings(data_dir: Path) -> DisplaySettings:
    path = display_settings_path(data_dir)
    if not path.is_file():
        return default_display_settings()
    data = json.loads(path.read_text(encoding="utf-8"))
    return validate_display_settings(DisplaySettings.model_validate(data))


def save_display_settings(data_dir: Path, settings: DisplaySettings) -> Path:
    path = display_settings_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    cleaned = validate_display_settings(settings)
    path.write_text(cleaned.model_dump_json(indent=2), encoding="utf-8")
    return path
