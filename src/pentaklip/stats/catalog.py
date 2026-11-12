"""Catalog of known / derived stat keys (capture widely; display selectively)."""

from __future__ import annotations

from enum import StrEnum


class Position(StrEnum):
    TOP = "TOP"
    JUNGLE = "JUNGLE"
    MIDDLE = "MIDDLE"
    BOTTOM = "BOTTOM"
    UTILITY = "UTILITY"
    UNKNOWN = "UNKNOWN"


# API value stays UTILITY; UI / chart titles use SUPPORT.
POSITION_LABELS: dict[Position, str] = {
    Position.TOP: "TOP",
    Position.JUNGLE: "JUNGLE",
    Position.MIDDLE: "MIDDLE",
    Position.BOTTOM: "BOTTOM",
    Position.UTILITY: "SUPPORT",
    Position.UNKNOWN: "UNKNOWN",
}


def position_label(position: Position) -> str:
    return POSITION_LABELS.get(position, position.value)


class StatKey(StrEnum):
    # Core scoreboard
    KILLS = "kills"
    DEATHS = "deaths"
    ASSISTS = "assists"
    KDA_RATIO = "kda_ratio"
    KILL_PARTICIPATION = "kill_participation"
    CREEP_SCORE = "creep_score"
    CS_PER_MIN = "cs_per_min"
    WARD_SCORE = "ward_score"
    VISION_PER_MIN = "vision_per_min"
    LEVEL = "level"
    # 15-minute lane diffs (Live Client series; LCK-like proxies)
    CS_AT_15 = "cs_at_15"
    LEVEL_AT_15 = "level_at_15"
    CSD15 = "csd15"
    LVLD15 = "lvld15"
    # Composite objective participation (events)
    OBJECTIVE_SCORE = "objective_score"
    # Identity / matchup
    CHAMPION = "champion"
    TEAM = "team"
    # Timeline / presence
    # Pocket gold for the Live Client active player only (not gold earned).
    GOLD = "gold"
    ITEM_COUNT = "item_count"
    IS_DEAD = "is_dead"
    # Objective participation (from events)
    DRAGON_KILLS = "dragon_kills"
    BARON_KILLS = "baron_kills"
    HERALD_KILLS = "herald_kills"
    TOWER_KILLS = "tower_kills"
    INHIBITOR_KILLS = "inhibitor_kills"
    # Post-game scoreboard SS (OCR) — not available from Live Client
    DAMAGE_TO_CHAMPIONS = "damage_to_champions"
    DPM = "dpm"
    DAMAGE_SHARE = "damage_share"
    # Series helpers (for charts; also stored on aggregate)
    CS_SERIES = "cs_series"
    KDA_SERIES = "kda_series"
    LEVEL_SERIES = "level_series"
    WARD_SERIES = "ward_series"
    GOLD_SERIES = "gold_series"


STAT_LABELS: dict[StatKey, str] = {
    StatKey.KILLS: "Kills",
    StatKey.DEATHS: "Deaths",
    StatKey.ASSISTS: "Assists",
    StatKey.KDA_RATIO: "KDA",
    StatKey.KILL_PARTICIPATION: "KP%",
    StatKey.CREEP_SCORE: "CS",
    StatKey.CS_PER_MIN: "CSM",
    StatKey.WARD_SCORE: "Vision Score",
    StatKey.VISION_PER_MIN: "VSPM",
    StatKey.LEVEL: "Level",
    StatKey.CS_AT_15: "CS@15",
    StatKey.LEVEL_AT_15: "LVL@15",
    StatKey.CSD15: "CSD15",
    StatKey.LVLD15: "LVLD15",
    StatKey.OBJECTIVE_SCORE: "OBJ",
    StatKey.CHAMPION: "Champion",
    StatKey.TEAM: "Team",
    StatKey.GOLD: "Gold (active)",
    StatKey.ITEM_COUNT: "Items",
    StatKey.IS_DEAD: "Dead",
    StatKey.DRAGON_KILLS: "Dragons",
    StatKey.BARON_KILLS: "Barons",
    StatKey.HERALD_KILLS: "Heralds",
    StatKey.TOWER_KILLS: "Towers",
    StatKey.INHIBITOR_KILLS: "Inhibitors",
    StatKey.DAMAGE_TO_CHAMPIONS: "DMG",
    StatKey.DPM: "DPM",
    StatKey.DAMAGE_SHARE: "DMG%",
    StatKey.CS_SERIES: "CS over time",
    StatKey.KDA_SERIES: "KDA over time",
    StatKey.LEVEL_SERIES: "Level over time",
    StatKey.WARD_SERIES: "Vision over time",
    StatKey.GOLD_SERIES: "Gold over time",
}

# Scalar / end-game style keys suitable for tables
TABLE_STAT_KEYS: tuple[StatKey, ...] = (
    StatKey.CHAMPION,
    StatKey.TEAM,
    StatKey.KILLS,
    StatKey.DEATHS,
    StatKey.ASSISTS,
    StatKey.KDA_RATIO,
    StatKey.KILL_PARTICIPATION,
    StatKey.CREEP_SCORE,
    StatKey.CS_PER_MIN,
    StatKey.CS_AT_15,
    StatKey.CSD15,
    StatKey.LEVEL_AT_15,
    StatKey.LVLD15,
    StatKey.WARD_SCORE,
    StatKey.VISION_PER_MIN,
    StatKey.LEVEL,
    StatKey.OBJECTIVE_SCORE,
    StatKey.GOLD,
    StatKey.ITEM_COUNT,
    StatKey.DRAGON_KILLS,
    StatKey.BARON_KILLS,
    StatKey.HERALD_KILLS,
    StatKey.TOWER_KILLS,
    StatKey.INHIBITOR_KILLS,
    StatKey.DAMAGE_TO_CHAMPIONS,
    StatKey.DPM,
    StatKey.DAMAGE_SHARE,
)

# Live Client cannot provide GPM / GD15 / XPD15. DPM / DMG% come from `{game_id}_ss.png` OCR.
# Default radar axes approximate the LCK octagon with available proxies.
# Towers / OBJ are omitted — noisy for lane radar; use CS@15 + Vision Score instead.
LCK_RADAR_STAT_KEYS: tuple[StatKey, ...] = (
    StatKey.CS_PER_MIN,  # CSM
    StatKey.KDA_RATIO,
    StatKey.KILL_PARTICIPATION,  # ~DMG%
    StatKey.CSD15,
    StatKey.LVLD15,  # ~XPD15
    StatKey.VISION_PER_MIN,  # ~GPM/DPM gap filler
    StatKey.CS_AT_15,  # early-lane absolute (pairs with CSD15)
    StatKey.WARD_SCORE,  # absolute vision (pairs with VSPM)
)

# Signed diffs: radar maps [-peak, +peak] → [0, 1] with 0 at center.
SIGNED_RADAR_STAT_KEYS: frozenset[StatKey] = frozenset(
    {
        StatKey.CSD15,
        StatKey.LVLD15,
    }
)

SERIES_STAT_KEYS: tuple[StatKey, ...] = (
    StatKey.CS_SERIES,
    StatKey.KDA_SERIES,
    StatKey.LEVEL_SERIES,
    StatKey.WARD_SERIES,
    StatKey.GOLD_SERIES,
)


def normalize_position(raw: str | None) -> Position:
    if not raw:
        return Position.UNKNOWN
    key = raw.strip().upper().replace(" ", "")
    mapping = {
        "TOP": Position.TOP,
        "JUNGLE": Position.JUNGLE,
        "JG": Position.JUNGLE,
        "MIDDLE": Position.MIDDLE,
        "MID": Position.MIDDLE,
        "BOTTOM": Position.BOTTOM,
        "BOT": Position.BOTTOM,
        "ADC": Position.BOTTOM,
        "UTILITY": Position.UTILITY,
        "SUPPORT": Position.UTILITY,
        "SUP": Position.UTILITY,
    }
    return mapping.get(key, Position.UNKNOWN)
