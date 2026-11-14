from pathlib import Path

import pytest

from pentaklip.replay.install import InstallMode, install_replay, parse_match_id_from_filename


def test_parse_match_id_from_filename() -> None:
    assert parse_match_id_from_filename("JP1-5123456789.rofl") == "JP1-5123456789"
    assert parse_match_id_from_filename(Path("foo/NA1-1.rofl")) == "NA1-1"
    assert parse_match_id_from_filename("nope.rofl") is None


def test_install_replay_copy_and_preserve_original_id(tmp_path: Path) -> None:
    source = tmp_path / "KR-999888777.rofl"
    source.write_bytes(b"rofl-bytes")
    replays_dir = tmp_path / "Replays"

    result = install_replay(
        source,
        local_replay_id="JP1-111",
        replays_dir=replays_dir,
    )

    assert result.original_match_id == "KR-999888777"
    assert result.local_replay_id == "JP1-111"
    assert result.installed_path == replays_dir / "JP1-111.rofl"
    assert result.installed_path.read_bytes() == b"rofl-bytes"
    assert result.overwritten is False
    assert result.mode == InstallMode.COPY


def test_install_replay_rejects_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        install_replay(
            tmp_path / "missing.rofl",
            local_replay_id="JP1-1",
            replays_dir=tmp_path / "Replays",
        )


def test_list_local_replays_newest_first(tmp_path: Path) -> None:
    import os
    import time

    from pentaklip.replay.install import list_local_replays

    replays = tmp_path / "Replays"
    replays.mkdir()
    older = replays / "JP1-1.rofl"
    newer = replays / "JP1-2.rofl"
    older.write_bytes(b"old")
    time.sleep(0.02)
    newer.write_bytes(b"new")
    # Reinforce mtime ordering on filesystems with coarse stamps.
    now = time.time()
    os.utime(older, (now - 10, now - 10))
    os.utime(newer, (now, now))

    listed = list_local_replays(replays)
    assert [item.filename for item in listed] == ["JP1-2.rofl", "JP1-1.rofl"]


def test_api_list_local_replays_uses_directory(tmp_path: Path, monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from pentaklip import config
    from pentaklip.api.app import app

    monkeypatch.setattr(config.settings, "data_dir", tmp_path / "data")
    monkeypatch.setattr(config.settings, "lol_replays_dir", tmp_path / "LoLReplays")
    custom = tmp_path / "custom-replays"
    custom.mkdir()
    (custom / "JP1-42.rofl").write_bytes(b"x")

    client = TestClient(app)
    response = client.get("/api/replays/local", params={"directory": str(custom)})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["directory"] == str(custom.resolve())
    assert body["default_directory"] == str((tmp_path / "LoLReplays").resolve())
    assert len(body["items"]) == 1
    assert body["items"][0]["filename"] == "JP1-42.rofl"

    prefs = client.get("/api/ui/preferences").json()
    prefs["last_replays_dir"] = str(custom)
    assert client.put("/api/ui/preferences", json=prefs).status_code == 200
    remembered = client.get("/api/replays/local").json()
    assert remembered["directory"] == str(custom.resolve())
    assert remembered["items"][0]["match_id"] == "JP1-42"


def test_install_prefers_rofl_meta_game_id(tmp_path: Path) -> None:
    from tests.test_rofl_metadata import _classic_rofl_bytes

    source = tmp_path / "downloaded-odd-name.rofl"
    source.write_bytes(
        _classic_rofl_bytes(
            {
                "gameLength": 1000,
                "gameVersion": "14.1.1",
                "gameMode": "CLASSIC",
                "gameId": "KR-999888777",
                "statsJson": "[]",
            }
        )
    )
    result = install_replay(
        source,
        local_replay_id="JP1-111",
        replays_dir=tmp_path / "Replays",
    )
    assert result.original_match_id == "KR-999888777"


def test_api_inspect_prefers_replace_db_original(tmp_path: Path, monkeypatch) -> None:
    from fastapi.testclient import TestClient

    import pentaklip.store.db as db_mod
    from pentaklip import config
    from pentaklip.api.app import app

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr(config.settings, "data_dir", data_dir)
    monkeypatch.setattr(db_mod, "_db", None)

    replays = tmp_path / "Replays"
    replays.mkdir()
    installed = replays / "JP1-111.rofl"
    installed.write_bytes(b"not-a-real-rofl")

    db = db_mod.get_database()
    db.insert_replay(
        original_match_id="KR-999888777",
        original_filename="KR-999888777.rofl",
        local_replay_id="JP1-111",
        installed_path=str(installed),
    )

    client = TestClient(app)
    listed = client.get("/api/replays/local", params={"directory": str(replays)}).json()
    assert listed["items"][0]["match_id"] == "JP1-111"
    assert listed["items"][0]["original_match_id"] == "KR-999888777"

    overview = client.get("/api/replays/inspect", params={"path": str(installed)}).json()
    assert overview["match_id"] == "KR-999888777"
    assert overview["match_id_source"] == "db"
