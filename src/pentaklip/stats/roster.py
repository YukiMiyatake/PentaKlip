"""Lane roster registration and fuzzy Riot-ID matching (tag ignored)."""

from __future__ import annotations

import re
from typing import Iterable

from pentaklip.stats.catalog import Position
from pentaklip.stats.identity import PlayerIdentity
from pentaklip.stats.models import AggregatedReplayStats, PlayerPositionAggregate

_SPACE_RE = re.compile(r"\s+")


def riot_game_name_only(value: str | None) -> str:
    """Strip ``#tag`` and normalize whitespace/case for matching."""
    if not value:
        return ""
    text = str(value).strip()
    if "#" in text:
        text = text.split("#", 1)[0]
    text = _SPACE_RE.sub(" ", text).strip().lower()
    return text


def fuzzy_riot_name_match(registered: str, observed: str) -> bool:
    """
    True when ``registered`` should identify ``observed``.

    Tag lines are ignored. Examples with registered ``Tanaka``:
    - ``T1 Tanaka`` / ``T1 Tanaka#JP1``
    - ``T1 Tanakakun``
    """
    reg = riot_game_name_only(registered)
    obs = riot_game_name_only(observed)
    if not reg or not obs:
        return False
    if len(reg) < 2:
        return reg == obs
    if reg == obs:
        return True
    # Substring on spaced and compacted forms (Tanaka ⊂ Tanakakun, T1 Tanaka).
    if reg in obs:
        return True
    obs_compact = obs.replace(" ", "")
    reg_compact = reg.replace(" ", "")
    if reg_compact and reg_compact in obs_compact:
        return True
    for token in obs.split(" "):
        if reg in token or (len(token) >= 2 and token in reg):
            return True
    return False


def resolve_roster_name(
    identity: PlayerIdentity,
    position: Position,
    roster_by_position: dict[Position, list[str]] | None,
) -> str | None:
    """Return the registered lane alias that fuzzy-matches this player, if any."""
    if not roster_by_position:
        return None
    aliases = roster_by_position.get(position) or []
    if not aliases:
        return None
    candidates = [
        identity.riot_id_game_name,
        identity.player_id,
        identity.summoner_name,
    ]
    observed_names = [c for c in candidates if isinstance(c, str) and c.strip()]
    for alias in aliases:
        alias_s = str(alias).strip()
        if not alias_s:
            continue
        for observed in observed_names:
            if fuzzy_riot_name_match(alias_s, observed):
                return alias_s
    return None


def remap_aggregate_to_roster(
    aggregated: AggregatedReplayStats,
    roster_by_position: dict[Position, list[str]] | None,
) -> AggregatedReplayStats:
    """
    Copy aggregate with player_id rewritten to roster aliases when fuzzy-matched.

    Unmatched players keep their RiotID-based player_id.
    """
    if not roster_by_position:
        return aggregated
    players: list[PlayerPositionAggregate] = []
    for player in aggregated.players:
        canonical = resolve_roster_name(
            player.identity, player.position, roster_by_position
        )
        if canonical and canonical != player.player_id:
            players.append(
                player.model_copy(
                    update={
                        "player_id": canonical,
                        "identity": player.identity.model_copy(
                            update={"player_id": canonical}
                        ),
                    }
                )
            )
        else:
            players.append(player)
    return aggregated.model_copy(update={"players": players})


def clean_roster_aliases(values: Iterable[str] | None) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in values or []:
        text = str(raw).strip()
        if not text:
            continue
        # Drop accidental tag when registering.
        if "#" in text:
            text = text.split("#", 1)[0].strip()
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(text)
    return cleaned
