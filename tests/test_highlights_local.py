"""LoL Highlights folder listing for AutoSplit webm sources."""

from pathlib import Path

from fastapi.testclient import TestClient

from pentaklip.api.app import app
from pentaklip.config import settings


def test_list_local_highlights_defaults_and_lists_webm(
    tmp_path: Path, monkeypatch
) -> None:
    highlights = tmp_path / "Highlights"
    highlights.mkdir()
    (highlights / "match.webm").write_bytes(b"fake")
    (highlights / "notes.txt").write_text("x", encoding="utf-8")
    monkeypatch.setattr(settings, "lol_highlights_dir", highlights)
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")

    client = TestClient(app)
    response = client.get("/api/highlights/local")
    assert response.status_code == 200
    body = response.json()
    assert Path(body["directory"]) == highlights.resolve()
    assert Path(body["default_directory"]) == highlights.resolve()
    names = {e["name"] for e in body["entries"]}
    assert names == {"match.webm"}


def test_list_local_highlights_custom_directory(tmp_path: Path, monkeypatch) -> None:
    default = tmp_path / "default"
    default.mkdir()
    custom = tmp_path / "custom"
    custom.mkdir()
    (custom / "clip.webm").write_bytes(b"x")
    monkeypatch.setattr(settings, "lol_highlights_dir", default)
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")

    client = TestClient(app)
    response = client.get(
        "/api/highlights/local",
        params={"directory": str(custom)},
    )
    assert response.status_code == 200
    body = response.json()
    assert Path(body["directory"]) == custom.resolve()
    assert body["entries"][0]["name"] == "clip.webm"
