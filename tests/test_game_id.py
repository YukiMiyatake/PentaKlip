from pathlib import Path

from fastapi.testclient import TestClient

import pentaklip.store.db as db_mod
from pentaklip import config
from pentaklip.api.app import app
from pentaklip.game_id import resolve_output_game_id


def test_resolve_output_keeps_unrelated_explicit_id(tmp_path: Path) -> None:
    db_path = tmp_path / "pentaklip.sqlite3"
    db = db_mod.Database(db_path)
    db.initialize()
    installed = tmp_path / "JP1-111.rofl"
    installed.write_bytes(b"x")
    db.insert_replay(
        original_match_id="KR-999888777",
        original_filename="KR-999888777.rofl",
        local_replay_id="JP1-111",
        installed_path=str(installed),
    )

    gid, src = resolve_output_game_id(
        "JP1-777",
        rofl_path=installed,
        db=db,
    )
    assert gid == "JP1-777"
    assert src == "candidate"


def test_resolve_output_prefers_db_original_over_local_candidate(tmp_path: Path) -> None:
    db_path = tmp_path / "pentaklip.sqlite3"
    db = db_mod.Database(db_path)
    db.initialize()
    installed = tmp_path / "JP1-111.rofl"
    installed.write_bytes(b"x")
    db.insert_replay(
        original_match_id="KR-999888777",
        original_filename="KR-999888777.rofl",
        local_replay_id="JP1-111",
        installed_path=str(installed),
    )

    gid, src = resolve_output_game_id(
        "JP1-111",
        "JP1-111",
        rofl_path=installed,
        db=db,
    )
    assert gid == "KR-999888777"
    assert src == "db"


def test_auto_split_prefixes_use_replace_original(tmp_path: Path, monkeypatch) -> None:
    import json

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr(config.settings, "data_dir", data_dir)
    monkeypatch.setattr(db_mod, "_db", None)

    replays = tmp_path / "Replays"
    replays.mkdir()
    installed = replays / "JP1-111.rofl"
    installed.write_bytes(b"rofl")

    db = db_mod.get_database()
    db.insert_replay(
        original_match_id="KR-999888777",
        original_filename="KR-999888777.rofl",
        local_replay_id="JP1-111",
        installed_path=str(installed),
    )

    video = tmp_path / "JP1-111_full.mp4"
    video.write_bytes(b"video")
    # Events may still carry the local id from an older export.
    events = {
        "Events": [{"EventName": "ChampionKill", "EventTime": 30.0}],
        "meta": {"game_id": "JP1-111"},
    }
    events_path = tmp_path / "Event" / "JP1-111_events.json"
    events_path.parent.mkdir(parents=True)
    events_path.write_text(json.dumps(events), encoding="utf-8")
    out_root = tmp_path / "out"

    client = TestClient(app)
    prefs = client.get("/api/ui/preferences").json()
    prefs["last_output_root"] = str(out_root)
    prefs["fixed_target_rofl"] = str(installed)
    prefs["last_game_id"] = "JP1-111"
    assert client.put("/api/ui/preferences", json=prefs).status_code == 200

    response = client.post(
        "/api/clips/auto-split",
        json={
            "source_video_path": str(video),
            "events_path": str(events_path),
            "original_match_id": "JP1-111",
            "dry_run": True,
            "padding_before_sec": 5,
            "padding_after_sec": 5,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["game_id"] == "KR-999888777"
    assert Path(body["output_dir"]) == (out_root / "Clip" / "KR-999888777").resolve()
    clip_name = Path(body["clips"][0]["output_path"]).name
    assert clip_name.startswith("KR-999888777_")
