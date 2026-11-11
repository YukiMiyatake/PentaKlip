"""Roster fuzzy match and folder multi-game averages."""

from __future__ import annotations

import json
from pathlib import Path

from pentaklip.stats.catalog import Position
from pentaklip.stats.folder_aggregate import aggregate_stats_folder
from pentaklip.stats.identity import PlayerIdentity
from pentaklip.stats.models import AggregatedReplayStats, PlayerPositionAggregate
from pentaklip.stats.roster import fuzzy_riot_name_match, resolve_roster_name


def test_fuzzy_riot_name_examples() -> None:
    assert fuzzy_riot_name_match("Tanaka", "T1 Tanaka#JP1")
    assert fuzzy_riot_name_match("Tanaka", "T1 Tanakakun")
    assert fuzzy_riot_name_match("Tanaka", "Tanaka")
    assert not fuzzy_riot_name_match("Tanaka", "Sato#JP1")


def test_resolve_roster_ignores_tag() -> None:
    identity = PlayerIdentity(
        player_id="T1 Tanakakun#JP1",
        riot_id_game_name="T1 Tanakakun",
        riot_id_tag_line="JP1",
    )
    name = resolve_roster_name(
        identity,
        Position.MIDDLE,
        {Position.MIDDLE: ["Tanaka"]},
    )
    assert name == "Tanaka"


def _agg(player_id: str, kills: int, duration: float = 600.0) -> AggregatedReplayStats:
    return AggregatedReplayStats(
        game_duration_sec=duration,
        players=[
            PlayerPositionAggregate(
                player_id=player_id,
                position=Position.MIDDLE,
                identity=PlayerIdentity(player_id=player_id, riot_id_game_name=player_id),
                scalars={"kills": kills, "deaths": 1, "assists": 2, "creep_score": 100},
            )
        ],
        team_totals={"ORDER": {"kills": 10}},
    )


def test_folder_average_with_roster(tmp_path: Path) -> None:
    a = _agg("T1 Tanaka#JP1", kills=4)
    b = _agg("T1 Tanakakun#JP1", kills=6)
    (tmp_path / "JP1-1_stats_aggregated.json").write_text(
        a.model_dump_json(indent=2), encoding="utf-8"
    )
    (tmp_path / "JP1-2_stats_aggregated.json").write_text(
        b.model_dump_json(indent=2), encoding="utf-8"
    )
    result = aggregate_stats_folder(
        tmp_path,
        roster_by_position={Position.MIDDLE: ["Tanaka"]},
    )
    assert result.game_count == 2
    mids = [p for p in result.players if p.position == Position.MIDDLE]
    assert len(mids) == 1
    assert mids[0].player_id == "Tanaka"
    # average of 4 and 6
    assert float(mids[0].scalars["kills"]) == 5.0
