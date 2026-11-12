"""Lane roster registration and fuzzy Riot-ID matching (tag ignored)."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

from pentaklip.stats.catalog import Position
from pentaklip.stats.identity import PlayerIdentity
from pentaklip.stats.models import AggregatedReplayStats, PlayerPositionAggregate

_SPACE_RE = re.compile(r"\s+")


def normalize_riot_name_key(value: str | None) -> str:
    """
    Normalize a Riot game name for fuzzy compare.

    - strips ``#tag``
    - NFKC (full-width ↔ half-width, compatibility forms)
    - casefold (A/a and unicode case pairs)
    - collapses whitespace
    """
    if not value:
        return ""
    text = str(value).strip()
    if "#" in text:
        text = text.split("#", 1)[0]
    text = unicodedata.normalize("NFKC", text)
    text = _SPACE_RE.sub(" ", text).strip().casefold()
    return text


def riot_game_name_only(value: str | None) -> str:
    """Strip ``#tag`` and normalize width/case/whitespace for matching."""
    return normalize_riot_name_key(value)


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

def player_is_excluded(
    player: PlayerPositionAggregate,
    excluded_by_position: dict[Position, list[str]] | None,
) -> bool:
    """True when this lane×player is in the exclusion filter (tag ignored)."""
    if not excluded_by_position:
        return False
    aliases = excluded_by_position.get(player.position) or []
    if not aliases:
        return False
    candidates = [
        player.player_id,
        player.identity.riot_id_game_name if player.identity else None,
        player.identity.player_id if player.identity else None,
        player.identity.summoner_name if player.identity else None,
    ]
    observed = [c for c in candidates if isinstance(c, str) and c.strip()]
    for alias in aliases:
        alias_s = str(alias).strip()
        if not alias_s:
            continue
        for name in observed:
            if fuzzy_riot_name_match(alias_s, name):
                return True
    return False


def filter_excluded_players(
    players: list[PlayerPositionAggregate],
    excluded_by_position: dict[Position, list[str]] | None,
) -> list[PlayerPositionAggregate]:
    """Drop lane×player rows that are excluded from chart/aggregate math."""
    if not excluded_by_position:
        return players
    return [
        p for p in players if not player_is_excluded(p, excluded_by_position)
    ]


def apply_player_exclusions(
    aggregated: AggregatedReplayStats,
    excluded_by_position: dict[Position, list[str]] | None,
) -> AggregatedReplayStats:
    """Return a copy of ``aggregated`` without excluded lane×player rows."""
    if not excluded_by_position:
        return aggregated
    kept = filter_excluded_players(list(aggregated.players), excluded_by_position)
    if len(kept) == len(aggregated.players):
        return aggregated
    meta = dict(aggregated.meta or {})
    meta["excluded_players_applied"] = True
    meta["excluded_player_count"] = len(aggregated.players) - len(kept)
    return aggregated.model_copy(update={"players": kept, "meta": meta})


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
        key = normalize_riot_name_key(text)
        if not key or key in seen:
            continue
        seen.add(key)
        cleaned.append(text)
    return cleaned
