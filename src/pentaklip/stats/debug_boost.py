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


def _name_hits_target(name: str) -> bool:
    if not name:
        return False
    target = _DEBUG_TARGET_NAME
    compact = name.replace(" ", "")
    target_compact = target.replace(" ", "")
    return (
        name == target
        or target in name
        or name in target
        or compact == target_compact
        or target_compact in compact
        or "yojo" in compact
    )


def _is_debug_target(player: PlayerPositionAggregate) -> bool:
    if player.position != Position.MIDDLE:
        return False
    candidates = [
        player.player_id,
        player.identity.riot_id_game_name if player.identity else None,
        player.identity.summoner_name if player.identity else None,
        player.identity.player_id if player.identity else None,
    ]
    for raw in candidates:
        if _name_hits_target(riot_game_name_only(raw)):
            return True
    return False


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
        changed = False
        for key in _DAMAGE_KEYS:
            if key not in scalars or scalars[key] is None:
                continue
            # Damage share is a percentage — still scale, but cap at 100.
            cap = 100.0 if key == StatKey.DAMAGE_SHARE.value else None
            boosted_val = _boost_scalar(scalars[key], _DAMAGE_MULT, cap=cap)
            if boosted_val is not None:
                scalars[key] = (
                    round(boosted_val)
                    if key == StatKey.DAMAGE_TO_CHAMPIONS.value
                    else boosted_val
                )
                changed = True
        kp_key = StatKey.KILL_PARTICIPATION.value
        if kp_key in scalars and scalars[kp_key] is not None:
            boosted_kp = _boost_scalar(scalars[kp_key], _KP_MULT, cap=100.0)
            if boosted_kp is not None:
                scalars[kp_key] = boosted_kp
                changed = True
        players.append(player.model_copy(update={"scalars": scalars}))
        if changed:
            boosted += 1

    meta = dict(aggregated.meta or {})
    if boosted:
        meta["debug_boost_applied"] = boosted
    return aggregated.model_copy(update={"players": players, "meta": meta})
