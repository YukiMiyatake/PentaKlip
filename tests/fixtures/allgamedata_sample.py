"""Minimal multi-player Live Client style fixtures for stats tests."""

from __future__ import annotations

from typing import Any


def make_player(
    *,
    name: str,
    champion: str,
    position: str,
    team: str,
    kills: int,
    deaths: int,
    assists: int,
    cs: int,
    ward: float,
    level: int,
    riot_tag: str = "JP1",
) -> dict[str, Any]:
    return {
        "championName": champion,
        "isBot": False,
        "isDead": False,
        "items": [{"itemID": 1001, "displayName": "Boots"}],
        "level": level,
        "position": position,
        "scores": {
            "assists": assists,
            "creepScore": cs,
            "deaths": deaths,
            "kills": kills,
            "wardScore": ward,
        },
        "summonerName": name,
        "riotIdGameName": name,
        "riotIdTagLine": riot_tag,
        "team": team,
        "summonerSpells": {},
        "runes": {},
    }


def all_game_data_at(
    game_time: float,
    *,
    mid_kills: int = 1,
    mid_cs: int = 50,
) -> dict[str, Any]:
    return {
        "activePlayer": {
            "summonerName": "MidLaner",
            "riotIdGameName": "MidLaner",
            "riotIdTagLine": "JP1",
            "currentGold": 1200.0 + game_time,
            "level": 6,
            "championStats": {},
        },
        "allPlayers": [
            make_player(
                name="TopLaner",
                champion="Gnar",
                position="TOP",
                team="ORDER",
                kills=0,
                deaths=1,
                assists=2,
                cs=int(40 + game_time / 10),
                ward=3.0,
                level=5,
            ),
            make_player(
                name="Jungler",
                champion="Lee Sin",
                position="JUNGLE",
                team="ORDER",
                kills=2,
                deaths=0,
                assists=3,
                cs=20,
                ward=8.0,
                level=6,
            ),
            make_player(
                name="MidLaner",
                champion="Azir",
                position="MIDDLE",
                team="ORDER",
                kills=mid_kills,
                deaths=1,
                assists=1,
                cs=mid_cs,
                ward=4.5,
                level=6,
            ),
            make_player(
                name="BotLaner",
                champion="Jinx",
                position="BOTTOM",
                team="CHAOS",
                kills=3,
                deaths=2,
                assists=0,
                cs=70,
                ward=2.0,
                level=5,
            ),
            make_player(
                name="Support",
                champion="Nautilus",
                position="UTILITY",
                team="CHAOS",
                kills=0,
                deaths=3,
                assists=5,
                cs=15,
                ward=12.0,
                level=5,
            ),
        ],
        "events": {
            "Events": [
                {"EventID": 0, "EventName": "GameStart", "EventTime": 0.0},
                {
                    "EventID": 1,
                    "EventName": "DragonKill",
                    "EventTime": 300.0,
                    "KillerName": "Jungler",
                    "Assisters": ["MidLaner"],
                },
                {
                    "EventID": 2,
                    "EventName": "ChampionKill",
                    "EventTime": game_time,
                    "KillerName": "MidLaner",
                    "VictimName": "BotLaner",
                    "Assisters": ["Jungler"],
                },
            ]
        },
        "gameData": {
            "gameMode": "CLASSIC",
            "gameTime": game_time,
            "mapName": "Map11",
            "mapNumber": 11,
            "mapTerrain": "Default",
        },
    }
