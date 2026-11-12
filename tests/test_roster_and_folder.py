"""Roster fuzzy match and folder multi-game averages."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

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
    # Case + full-width / half-width treated as the same.
    assert fuzzy_riot_name_match("tanaka", "TANAKA#JP1")
    assert fuzzy_riot_name_match("Tanaka", "Ｔａｎａｋａ#ＪＰ１")
    assert fuzzy_riot_name_match("ﾀﾅｶ", "タナカ")
    assert fuzzy_riot_name_match("ABC", "ａｂｃ")


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

def test_folder_aggregate_enriches_from_scoreboard_ss(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pentaklip.stats import folder_aggregate as fa

    agg = _agg("MidLaner#JP1", kills=3)
    path = tmp_path / "JP1-999_stats_aggregated.json"
    path.write_text(agg.model_dump_json(indent=2), encoding="utf-8")

    def fake_enrich(loaded, stats_dir, game_id):
        assert game_id == "JP1-999"
        players = []
        for player in loaded.players:
            scalars = dict(player.scalars)
            scalars["damage_to_champions"] = 12000
            scalars["dpm"] = 400.0
            scalars["damage_share"] = 25.0
            players.append(player.model_copy(update={"scalars": scalars}))
        return loaded.model_copy(update={"players": players})

    monkeypatch.setattr(
        "pentaklip.stats.scoreboard_ss.enrich_aggregated_from_scoreboard_ss",
        fake_enrich,
    )
    # Ensure PNG is "found" path isn't required because we stub enrich itself.
    result = fa.aggregate_stats_folder(tmp_path)
    assert result.aggregated.meta.get("scoreboard_ss_enriched") == 1
    mid = next(p for p in result.players if p.player_id == "MidLaner#JP1")
    assert mid.scalars["dpm"] == 400.0
    # Rewritten on disk
    rewritten = json.loads(path.read_text(encoding="utf-8"))
    assert rewritten["players"][0]["scalars"]["dpm"] == 400.0

def test_discover_stats_one_file_per_game(tmp_path: Path) -> None:
    from pentaklip.stats.folder_aggregate import discover_stats_files

    older = tmp_path / "JP1-1_stats_aggregated.json"
    newer = tmp_path / "JP1-1_stats_aggregated-1.json"
    other = tmp_path / "JP1-2_stats_aggregated.json"
    older.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "game_duration_sec": 100,
                "players": [],
                "original_match_id": "JP1-1",
            }
        ),
        encoding="utf-8",
    )
    import time

    time.sleep(0.02)
    newer.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "game_duration_sec": 200,
                "players": [],
                "original_match_id": "JP1-1",
            }
        ),
        encoding="utf-8",
    )
    other.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "game_duration_sec": 300,
                "players": [],
                "original_match_id": "JP1-2",
            }
        ),
        encoding="utf-8",
    )
    found = discover_stats_files(tmp_path)
    assert len(found) == 2
    assert {p.name for p in found} == {
        "JP1-1_stats_aggregated-1.json",
        "JP1-2_stats_aggregated.json",
    }
