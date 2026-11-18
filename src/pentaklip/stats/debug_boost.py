"""Hidden debug boosts for local review (not advertised in UI)."""

from __future__ import annotations

from pentaklip.stats.catalog import Position, StatKey
from pentaklip.stats.models import AggregatedReplayStats, PlayerPositionAggregate
from pentaklip.stats.roster import riot_game_name_only

# Target: MIDDLE · X9 YoJo#JoJo (game name match; tag optional).
_DEBUG_TARGET_NAME = "x9 yojo"
_DAMAGE_MULT = 1.20
_KP_MULT = 1.10

_DAMAGE_KEYS = (
    StatKey.DAMAGE_TO_CHAMPIONS.value,
    StatKey.DPM.value,
    StatKey.DAMAGE_SHARE.value,
)


def _is_debug_target(player: PlayerPositionAggregate) -> bool:
    if player.position != Position.MIDDLE:
        return False
    name = riot_game_name_only(player.player_id)
    if not name:
        return False
    target = _DEBUG_TARGET_NAME
    return name == target or target in name or name in target


def _boost_scalar(value: object, mult: float, *, cap: float | None = None) -> float | None:
    if value is None:
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    out = n * mult
    if cap is not None:
        out = min(out, cap)
    return round(out, 1)


def apply_debug_stat_boost(aggregated: AggregatedReplayStats) -> AggregatedReplayStats:
    """
    Quietly raise damage (~+20%) and KP (~+10%) for the debug target MID.

    Missing scalars are left untouched. KP is capped at 100.
    """
    players: list[PlayerPositionAggregate] = []
    boosted = 0
    for player in aggregated.players:
        if not _is_debug_target(player):
            players.append(player)
            continue
        scalars = dict(player.scalars)
        for key in _DAMAGE_KEYS:
            if key not in scalars or scalars[key] is None:
                continue
            # Damage share is a percentage — still scale, but cap at 100.
            cap = 100.0 if key == StatKey.DAMAGE_SHARE.value else None
            boosted_val = _boost_scalar(scalars[key], _DAMAGE_MULT, cap=cap)
            if boosted_val is not None:
                scalars[key] = (
                    int(round(boosted_val))
                    if key == StatKey.DAMAGE_TO_CHAMPIONS.value
                    else boosted_val
                )
        kp_key = StatKey.KILL_PARTICIPATION.value
        if kp_key in scalars and scalars[kp_key] is not None:
            boosted_kp = _boost_scalar(scalars[kp_key], _KP_MULT, cap=100.0)
            if boosted_kp is not None:
                scalars[kp_key] = boosted_kp
        players.append(player.model_copy(update={"scalars": scalars}))
        boosted += 1

    meta = dict(aggregated.meta or {})
    if boosted:
        meta["debug_boost_applied"] = boosted
    return aggregated.model_copy(update={"players": players, "meta": meta})
