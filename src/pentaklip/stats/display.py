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
    # Explicit radar axes (independent of table columns).
    radar_by_position: dict[Position, list[StatKey]] = Field(default_factory=dict)
    # Registered names per lane for fuzzy Riot-ID matching (tag ignored).
    roster_by_position: dict[Position, list[str]] = Field(default_factory=dict)
    # Lane × player ids/names excluded from chart/aggregate calculations.
    excluded_players_by_position: dict[Position, list[str]] = Field(default_factory=dict)


def default_display_settings() -> DisplaySettings:
    """Minimal LCK-readable defaults; extras stay available in display settings."""
    # Tables keep a tight core. Radar uses LCK_RADAR_STAT_KEYS (8 axes).
    # Optional (off by default): CS, CS@15, LVL@15, Level, Team, DMG raw, OBJ,
    # Towers, Inhibitors, Gold, Items, raw K/D/A.
    core_table = [
        StatKey.CHAMPION,
        StatKey.KDA_RATIO,
        StatKey.KILL_PARTICIPATION,
        StatKey.CS_PER_MIN,
        StatKey.CSD15,
        StatKey.LVLD15,
        StatKey.DPM,
        StatKey.DAMAGE_SHARE,
        StatKey.VISION_PER_MIN,
    ]
    support_table = [
        StatKey.CHAMPION,
        StatKey.KDA_RATIO,
        StatKey.KILL_PARTICIPATION,
        StatKey.WARD_SCORE,
        StatKey.VISION_PER_MIN,
        StatKey.DPM,
        StatKey.DAMAGE_SHARE,
        StatKey.LVLD15,
    ]
    jg_table = [
        *core_table,
        StatKey.DRAGON_KILLS,
        StatKey.BARON_KILLS,
        StatKey.HERALD_KILLS,
    ]
    radar = list(LCK_RADAR_STAT_KEYS)
    shared_charts = [StatKey.CS_SERIES, StatKey.KDA_SERIES]
    jg_charts = [StatKey.CS_SERIES, StatKey.KDA_SERIES, StatKey.WARD_SERIES]
    support_charts = [StatKey.WARD_SERIES, StatKey.KDA_SERIES]

    table = {
        Position.TOP: list(core_table),
        Position.JUNGLE: list(jg_table),
        Position.MIDDLE: list(core_table),
        Position.BOTTOM: list(core_table),
        Position.UTILITY: list(support_table),
        Position.UNKNOWN: list(core_table),
    }
    charts = {
        Position.TOP: list(shared_charts),
        Position.JUNGLE: list(jg_charts),
        Position.MIDDLE: list(shared_charts),
        Position.BOTTOM: list(shared_charts),
        Position.UTILITY: list(support_charts),
        Position.UNKNOWN: list(shared_charts),
    }
    radar_by_position = {pos: list(radar) for pos in Position}
    return DisplaySettings(
        table_by_position=table,
        charts_by_position=charts,
        radar_by_position=radar_by_position,
        roster_by_position={pos: [] for pos in Position},
        excluded_players_by_position={pos: [] for pos in Position},
    )


def validate_display_settings(settings: DisplaySettings) -> DisplaySettings:
    allowed_table = set(TABLE_STAT_KEYS)
    allowed_charts = set(SERIES_STAT_KEYS) | set(TABLE_STAT_KEYS)
    allowed_radar = set(TABLE_STAT_KEYS)
    table: dict[Position, list[StatKey]] = {}
    charts: dict[Position, list[StatKey]] = {}
    radar: dict[Position, list[StatKey]] = {}
    roster: dict[Position, list[str]] = {}
    excluded: dict[Position, list[str]] = {}
    for pos in Position:
        table[pos] = [k for k in settings.table_by_position.get(pos, []) if k in allowed_table]
        charts[pos] = [
            k for k in settings.charts_by_position.get(pos, []) if k in allowed_charts
        ]
        configured_radar = settings.radar_by_position.get(pos, [])
        if configured_radar:
            radar[pos] = [k for k in configured_radar if k in allowed_radar]
        else:
            # Older settings JSON without radar_by_position → LCK defaults.
            radar[pos] = list(LCK_RADAR_STAT_KEYS)
        roster[pos] = clean_roster_aliases(settings.roster_by_position.get(pos, []))
        excluded[pos] = clean_roster_aliases(
            settings.excluded_players_by_position.get(pos, [])
        )
    return DisplaySettings(
        table_by_position=table,
        charts_by_position=charts,
        radar_by_position=radar,
        roster_by_position=roster,
        excluded_players_by_position=excluded,
    )


def display_settings_path(data_dir: Path) -> Path:
    return data_dir / "stats_display_settings.json"


def _sanitize_display_settings_payload(data: object) -> object:
    """Drop unknown StatKey strings so older/newer settings JSON cannot 500 the API."""
    if not isinstance(data, dict):
        return data
    known = {key.value for key in StatKey}
    out = dict(data)
    for field in ("table_by_position", "charts_by_position", "radar_by_position"):
        block = out.get(field)
        if not isinstance(block, dict):
            continue
        cleaned: dict[str, list[str]] = {}
        for pos, keys in block.items():
            if not isinstance(keys, list):
                continue
            cleaned[str(pos)] = [
                key for key in keys if isinstance(key, str) and key in known
            ]
        out[field] = cleaned
    return out


def load_display_settings(data_dir: Path) -> DisplaySettings:
    path = display_settings_path(data_dir)
    if not path.is_file():
        return default_display_settings()
    data = json.loads(path.read_text(encoding="utf-8"))
    return validate_display_settings(
        DisplaySettings.model_validate(_sanitize_display_settings_payload(data))
    )


def save_display_settings(data_dir: Path, settings: DisplaySettings) -> Path:
    path = display_settings_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    cleaned = validate_display_settings(settings)
    path.write_text(cleaned.model_dump_json(indent=2), encoding="utf-8")
    return path
