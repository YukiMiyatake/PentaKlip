"""UI preferences file merge / atomic persistence."""

from pathlib import Path

from fastapi.testclient import TestClient

from pentaklip.api.app import app
from pentaklip.config import settings
from pentaklip.settings_store import (
    UiPreferences,
    load_ui_preferences,
    save_ui_preferences,
    ui_preferences_path,
    update_ui_preferences,
)


def test_update_merges_without_clobbering(tmp_path: Path) -> None:
    data = tmp_path / "data"
    save_ui_preferences(
        data,
        UiPreferences(
            last_output_root=str(tmp_path / "out"),
            last_game_id="JP1-1",
            last_replays_dir=str(tmp_path / "replays"),
        ),
    )
    updated = update_ui_preferences(
        data,
        {"last_game_id": "JP1-2", "last_highlights_dir": str(tmp_path / "hl")},
    )
    assert updated.last_output_root == str(tmp_path / "out")
    assert updated.last_replays_dir == str(tmp_path / "replays")
    assert updated.last_game_id == "JP1-2"
    assert updated.last_highlights_dir == str(tmp_path / "hl")
    reloaded = load_ui_preferences(data)
    assert reloaded == updated


def test_update_can_clear_with_explicit_null(tmp_path: Path) -> None:
    data = tmp_path / "data"
    save_ui_preferences(
        data,
        UiPreferences(fixed_target_rofl=str(tmp_path / "a.rofl"), last_game_id="JP1-1"),
    )
    updated = update_ui_preferences(data, {"fixed_target_rofl": None})
    assert updated.fixed_target_rofl is None
    assert updated.last_game_id == "JP1-1"


def test_load_tolerates_corrupt_json(tmp_path: Path) -> None:
    data = tmp_path / "data"
    path = ui_preferences_path(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not-json", encoding="utf-8")
    assert load_ui_preferences(data) == UiPreferences()


def test_preferences_api_patch_and_settings_path(tmp_path: Path, monkeypatch) -> None:
    data = tmp_path / "data"
    monkeypatch.setattr(settings, "data_dir", data)
    client = TestClient(app)

    first = client.patch(
        "/api/ui/preferences",
        json={"last_output_root": str(tmp_path / "out"), "last_game_id": "JP1-9"},
    )
    assert first.status_code == 200
    body = first.json()
    assert body["last_output_root"] == str(tmp_path / "out")
    assert body["last_game_id"] == "JP1-9"
    assert body["settings_path"] == str(ui_preferences_path(data).resolve())

    second = client.patch(
        "/api/ui/preferences",
        json={"last_highlights_dir": str(tmp_path / "Highlights")},
    )
    assert second.status_code == 200
    merged = second.json()
    assert merged["last_output_root"] == str(tmp_path / "out")
    assert merged["last_game_id"] == "JP1-9"
    assert merged["last_highlights_dir"] == str(tmp_path / "Highlights")

    got = client.get("/api/ui/preferences")
    assert got.status_code == 200
    assert got.json()["last_output_root"] == str(tmp_path / "out")
