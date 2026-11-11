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
    assert any(r.get("stat") == "Kills" for r in mid_compare.rows)
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
    assert "CS" in jg_table.columns
    assert "CSPM" in jg_table.columns
    assert "Gold" in jg_table.columns
    jg_radar = next(c for c in charts.charts if c.chart_id.startswith("radar-JUNGLE-"))
    assert len(jg_radar.rows) >= 6
    assert any(c.title.startswith("SUPPORT") for c in charts.charts)
    assert "MIDDLE" in charts.display_settings_applied

    catalog = TestClient(app).get("/api/stats/catalog").json()
    assert catalog["position_labels"]["UTILITY"] == "SUPPORT"


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
    assert "CSPM" in top_table.columns
    assert "Vision Score" not in top_table.columns


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
