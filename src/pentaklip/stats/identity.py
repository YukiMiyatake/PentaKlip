"""Player identity extraction from Live Client player payloads."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PlayerIdentity(BaseModel):
    """Stable-enough key for scrim aggregation (name/UUID + optional riot id parts)."""

    player_id: str = Field(description="Primary id used in aggregation keys")
    summoner_name: str | None = None
    riot_id_game_name: str | None = None
    riot_id_tag_line: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


def extract_player_identity(player: dict[str, Any]) -> PlayerIdentity:
    riot_game = player.get("riotIdGameName") or player.get("riot_id_game_name")
    riot_tag = player.get("riotIdTagLine") or player.get("riot_id_tag_line")
    summoner = player.get("summonerName") or player.get("summoner_name")

    if isinstance(riot_game, str) and riot_game.strip():
        if isinstance(riot_tag, str) and riot_tag.strip():
            player_id = f"{riot_game.strip()}#{riot_tag.strip()}"
        else:
            player_id = riot_game.strip()
    elif isinstance(summoner, str) and summoner.strip():
        player_id = summoner.strip()
    else:
        champ = player.get("championName") or player.get("champion_name") or "unknown"
        team = player.get("team") or "?"
        player_id = f"unknown:{team}:{champ}"

    return PlayerIdentity(
        player_id=player_id,
        summoner_name=str(summoner) if summoner else None,
        riot_id_game_name=str(riot_game) if riot_game else None,
        riot_id_tag_line=str(riot_tag) if riot_tag else None,
        raw={
            k: player.get(k)
            for k in (
                "summonerName",
                "riotIdGameName",
                "riotIdTagLine",
                "riotId",
                "puuid",
            )
            if k in player
        },
    )
