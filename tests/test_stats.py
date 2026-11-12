import json
from pathlib import Path

from fastapi.testclient import TestClient
from fixtures.allgamedata_sample import all_game_data_at

from pentaklip.api.app import app
from pentaklip.stats.aggregate import aggregate_replay, merge_aggregates
from pentaklip.stats.capture import StatsCaptureSession
from pentaklip.stats.catalog import Position, StatKey
from pentaklip.stats.charts import build_charts
from pentaklip.stats.display import default_display_settings, validate_display_settings
from pentaklip.stats.export import export_replay_stats, load_replay_stats
from pentaklip.stats.sessions import clear_sessions


def test_capture_aggregate_and_charts_are_separated(tmp_path: Path) -> None:
    session = StatsCaptureSession(original_match_id="SCRIM-1", sample_interval_sec=5)
    session.ingest_all_game_data(all_game_data_at(600.0, mid_kills=1, mid_cs=100))
    session.ingest_all_game_data(all_game_data_at(900.0, mid_kills=3, mid_cs=160))
    bundle = session.finalize()

    out = export_replay_stats(bundle, tmp_path / "scrim-1.json")
    loaded = load_replay_stats(out)
    assert loaded.original_match_id == "SCRIM-1"
    assert len(loaded.snapshots) == 2
    assert len(loaded.events) >= 3

    aggregated = aggregate_replay(loaded)
    mid = next(p for p in aggregated.players if p.player_id == "MidLaner#JP1")
    assert mid.position == Position.MIDDLE
    assert mid.scalars[StatKey.KILLS.value] == 3
    assert mid.scalars[StatKey.CREEP_SCORE.value] == 160
    assert StatKey.CS_SERIES.value in mid.series
    assert mid.series[StatKey.CS_SERIES.value][-1].value == 160
    # gold series only for active player
    assert StatKey.GOLD_SERIES.value in mid.series

    jg = next(p for p in aggregated.players if p.player_id == "Jungler#JP1")
    assert jg.scalars[StatKey.DRAGON_KILLS.value] == 1

    display = default_display_settings()
    charts = build_charts(aggregated, display)
    assert any(c.chart_type == "table" for c in charts.charts)
    assert any(c.chart_type == "lane_compare" for c in charts.charts)
    assert any(c.chart_type == "radar" for c in charts.charts)
    assert any(c.chart_type == "line" for c in charts.charts)
    mid_compare = next(c for c in charts.charts if c.chart_id == "lane-compare-MIDDLE")
    assert mid_compare.rows
    assert any(r.get("stat") == "KDA" for r in mid_compare.rows)
    mid_radar = next(c for c in charts.charts if c.chart_id.startswith("radar-MIDDLE-"))
    assert len(mid_radar.rows) >= 3
    assert all("player_norm" in r and "baseline_norm" in r for r in mid_radar.rows)
    assert any(s.key == "baseline" for s in mid_radar.series)
    # Never name a 1v1 opponent; always an average baseline.
    baseline = next(s for s in mid_radar.series if s.key == "baseline")
    assert baseline.label in {"レーン平均", "全体平均", "平均"}
    assert not str(baseline.label).startswith("vs ")

    jg_table = next(c for c in charts.charts if c.chart_id == "table-JUNGLE")
    assert "Dragons" in jg_table.columns
    assert "CSM" in jg_table.columns
    assert "CS" not in jg_table.columns
    assert "Gold (active)" not in jg_table.columns
    jg_radar = next(c for c in charts.charts if c.chart_id.startswith("radar-JUNGLE-"))
    assert len(jg_radar.rows) >= 3
    assert any(c.title.startswith("SUPPORT") for c in charts.charts)
    assert "MIDDLE" in charts.display_settings_applied

    catalog = TestClient(app).get("/api/stats/catalog").json()
    assert catalog["position_labels"]["UTILITY"] == "SUPPORT"
    assert "csd15" in {k["key"] for k in catalog["table_stat_keys"]}
    assert "dpm" in {k["key"] for k in catalog["table_stat_keys"]}
    mid_axes = {r["stat_key"] for r in mid_radar.rows}
    assert "cs_per_min" in mid_axes
    assert "kda_ratio" in mid_axes
    assert "kill_participation" in mid_axes
    # No OCR damage in Live Client fixture → DPM/DMG% axes omitted
    assert "dpm" not in mid_axes
    assert "damage_share" not in mid_axes
    assert "cs_at_15" not in mid_axes
    assert "ward_score" not in mid_axes
    # No 15:00 snapshots in oneshot fixture → CSD15/LVLD15 axes omitted
    assert "csd15" not in mid_axes
    assert "lvld15" not in mid_axes
    assert len(mid_axes) >= 3


def test_csd15_and_lvld15_vs_lane_opponent() -> None:
    """CSD15 / LVLD15 need ~15m samples and an opposite-lane opponent."""
    from fixtures.allgamedata_sample import make_player

    def payload(game_time: float, *, mid_cs: int, mid_level: int, foe_cs: int, foe_level: int):
        data = all_game_data_at(game_time, mid_kills=1, mid_cs=mid_cs)
        # bump ORDER mid level
        for p in data["allPlayers"]:
            if p.get("riotIdGameName") == "MidLaner":
                p["level"] = mid_level
        data["allPlayers"].append(
            make_player(
                name="EnemyMid",
                champion="Syndra",
                position="MIDDLE",
                team="CHAOS",
                kills=0,
                deaths=1,
                assists=0,
                cs=foe_cs,
                ward=2.0,
                level=foe_level,
            )
        )
        return data

    session = StatsCaptureSession(original_match_id="LANE-DIFF")
    session.ingest_all_game_data(payload(600.0, mid_cs=80, mid_level=9, foe_cs=70, foe_level=8))
    session.ingest_all_game_data(payload(900.0, mid_cs=120, mid_level=11, foe_cs=100, foe_level=10))
    aggregated = aggregate_replay(session.finalize())
    mid = next(p for p in aggregated.players if p.player_id == "MidLaner#JP1")
    foe = next(p for p in aggregated.players if p.player_id == "EnemyMid#JP1")
    assert mid.scalars[StatKey.CS_AT_15.value] == 120
    assert mid.scalars[StatKey.CSD15.value] == 20.0
    assert foe.scalars[StatKey.CSD15.value] == -20.0
    assert mid.scalars[StatKey.LVLD15.value] == 1.0
    assert foe.scalars[StatKey.LVLD15.value] == -1.0
    assert mid.scalars[StatKey.OBJECTIVE_SCORE.value] >= 1

    charts = build_charts(aggregated, default_display_settings())
    radar = next(c for c in charts.charts if c.chart_id.startswith("radar-MIDDLE-MidLaner"))
    keys = [r["stat_key"] for r in radar.rows]
    assert keys[:5] == [
        "cs_per_min",
        "kda_ratio",
        "kill_participation",
        "csd15",
        "lvld15",
    ]

def test_radar_includes_dpm_when_ocr_damage_present() -> None:
    session = StatsCaptureSession(original_match_id="SCRIM-DMG")
    session.ingest_all_game_data(all_game_data_at(900.0, mid_kills=3, mid_cs=160))
    aggregated = aggregate_replay(session.finalize())
    players = []
    for player in aggregated.players:
        scalars = dict(player.scalars)
        if player.player_id == "MidLaner#JP1":
            scalars[StatKey.DPM.value] = 500.0
            scalars[StatKey.DAMAGE_SHARE.value] = 22.0
        players.append(player.model_copy(update={"scalars": scalars}))
    aggregated = aggregated.model_copy(update={"players": players})
    charts = build_charts(aggregated, default_display_settings())
    radar = next(c for c in charts.charts if c.chart_id.startswith("radar-MIDDLE-MidLaner"))
    keys = [r["stat_key"] for r in radar.rows]
    assert "dpm" in keys
    assert "damage_share" in keys
    assert keys.index("dpm") < keys.index("vision_per_min")


def test_display_settings_per_lane_filter() -> None:
    settings = default_display_settings()
    settings.table_by_position[Position.TOP] = [StatKey.KILLS, StatKey.CS_PER_MIN]
    settings.charts_by_position[Position.TOP] = [StatKey.CS_SERIES]
    cleaned = validate_display_settings(settings)
    assert cleaned.table_by_position[Position.TOP] == [StatKey.KILLS, StatKey.CS_PER_MIN]

    session = StatsCaptureSession()
    session.ingest_all_game_data(all_game_data_at(600.0))
    aggregated = aggregate_replay(session.finalize())
    charts = build_charts(aggregated, cleaned)
    top_table = next(c for c in charts.charts if c.chart_id == "table-TOP")
    assert "Kills" in top_table.columns
    assert "CSM" in top_table.columns
    assert "DPM" not in top_table.columns

def test_load_display_settings_ignores_unknown_stat_keys(tmp_path: Path) -> None:
    """Newer settings (e.g. dpm) must not 500 when running an older StatKey set."""
    from pentaklip.stats.display import load_display_settings, save_display_settings

    settings = default_display_settings()
    path = save_display_settings(tmp_path, settings)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["table_by_position"]["TOP"].extend(
        ["gpm", "gd15", "not_a_real_stat"]
    )
    path.write_text(json.dumps(raw), encoding="utf-8")

    loaded = load_display_settings(tmp_path)
    top_keys = {key.value for key in loaded.table_by_position[Position.TOP]}
    assert "gpm" not in top_keys
    assert "gd15" not in top_keys
    assert "not_a_real_stat" not in top_keys
    assert StatKey.KDA_RATIO.value in top_keys


def test_merge_aggregates_by_player_and_position() -> None:
    s1 = StatsCaptureSession(original_match_id="A")
    s1.ingest_all_game_data(all_game_data_at(600.0, mid_kills=2, mid_cs=100))
    s2 = StatsCaptureSession(original_match_id="B")
    s2.ingest_all_game_data(all_game_data_at(600.0, mid_kills=1, mid_cs=80))
    a1 = aggregate_replay(s1.finalize())
    a2 = aggregate_replay(s2.finalize())
    merged = merge_aggregates([a1, a2])
    mid = next(p for p in merged if p.player_id == "MidLaner#JP1" and p.position == Position.MIDDLE)
    assert mid.scalars[StatKey.KILLS.value] == 3
    assert mid.scalars[StatKey.CREEP_SCORE.value] == 180


def test_merge_averages_optional_scalars_present_only() -> None:
    """CSD15 / DPM: games without values are skipped, not treated as 0."""
    from fixtures.allgamedata_sample import make_player

    def with_foe(game_time: float, *, mid_cs: int, foe_cs: int):
        data = all_game_data_at(game_time, mid_kills=1, mid_cs=mid_cs)
        data["allPlayers"].append(
            make_player(
                name="EnemyMid",
                champion="Syndra",
                position="MIDDLE",
                team="CHAOS",
                kills=0,
                deaths=0,
                assists=0,
                cs=foe_cs,
                ward=2.0,
                level=10,
            )
        )
        return data

    s_present = StatsCaptureSession(original_match_id="WITH-15")
    s_present.ingest_all_game_data(with_foe(600.0, mid_cs=80, foe_cs=70))
    s_present.ingest_all_game_data(with_foe(900.0, mid_cs=120, foe_cs=100))
    a_present = aggregate_replay(s_present.finalize())

    s_missing = StatsCaptureSession(original_match_id="NO-15")
    s_missing.ingest_all_game_data(with_foe(1800.0, mid_cs=200, foe_cs=180))
    a_missing = aggregate_replay(s_missing.finalize())

    mid_present = next(p for p in a_present.players if "MidLaner" in p.player_id)
    mid_missing = next(p for p in a_missing.players if "MidLaner" in p.player_id)
    assert mid_present.scalars[StatKey.CSD15.value] == 20.0
    assert mid_missing.scalars[StatKey.CSD15.value] is None

    # Inject OCR on present game only; missing stays None.
    mid_present.scalars[StatKey.DPM.value] = 400.0
    mid_missing.scalars[StatKey.DPM.value] = None

    merged = merge_aggregates([a_present, a_missing])
    mid = next(p for p in merged if "MidLaner" in p.player_id)
    assert mid.scalars[StatKey.CSD15.value] == 20.0
    assert mid.scalars[StatKey.DPM.value] == 400.0


def test_stats_api_session_flow(tmp_path: Path) -> None:
    clear_sessions()
    client = TestClient(app)

    catalog = client.get("/api/stats/catalog")
    assert catalog.status_code == 200
    assert "table_stat_keys" in catalog.json()

    started = client.post(
        "/api/stats/sessions",
        json={"original_match_id": "SCRIM-API", "sample_interval_sec": 5},
    )
    assert started.status_code == 200
    session_id = started.json()["session_id"]

    ingested = client.post(
        f"/api/stats/sessions/{session_id}/ingest",
        json={"all_game_data": all_game_data_at(600.0)},
    )
    assert ingested.status_code == 200
    assert ingested.json()["player_count"] == 5

    export_path = tmp_path / "out.yaml"
    finalized = client.post(
        f"/api/stats/sessions/{session_id}/finalize",
        json={"export_path": str(export_path), "export_format": "yaml", "build_charts": True},
    )
    assert finalized.status_code == 200
    body = finalized.json()
    assert body["aggregated"]["original_match_id"] == "SCRIM-API"
    assert body["charts"] is not None
    assert export_path.is_file()

    # per-lane settings round-trip
    settings = default_display_settings().model_dump(mode="json")
    settings["table_by_position"]["JUNGLE"] = ["kills", "dragon_kills"]
    put = client.put("/api/stats/display-settings", json=settings)
    assert put.status_code == 200
    assert put.json()["table_by_position"]["JUNGLE"] == ["kills", "dragon_kills"]
