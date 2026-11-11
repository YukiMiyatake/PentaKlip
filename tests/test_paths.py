import json
from pathlib import Path

from pentaklip.paths import (
    allocate_game_dir,
    extract_game_id_from_live_payload,
    infer_game_id,
    resolve_game_dir,
    sanitize_game_id,
    unique_file_path,
)


def test_sanitize_and_resolve(tmp_path: Path) -> None:
    assert sanitize_game_id(" JP1-123 ") == "JP1-123"
    game_dir = resolve_game_dir(tmp_path, "JP1-999")
    assert game_dir == (tmp_path / "JP1-999").resolve()


def test_infer_game_id_from_sources(tmp_path: Path) -> None:
    video = tmp_path / "scrim_JP1-555666777.mp4"
    video.write_bytes(b"x")
    assert infer_game_id(video) == "JP1-555666777"
    assert infer_game_id(None, tmp_path / "JP1-111", "ignore") == "JP1-111"
    assert extract_game_id_from_live_payload({"gameData": {"gameId": "NA1-42"}}) == "NA1-42"


def test_allocate_game_dir_collision_uses_suffix(tmp_path: Path) -> None:
    first = allocate_game_dir(tmp_path, "JP1-1")
    first.mkdir()
    (first / "events.json").write_text(
        json.dumps({"Events": [], "meta": {"game_id": "OTHER-9"}}),
        encoding="utf-8",
    )
    second = allocate_game_dir(tmp_path, "JP1-1")
    assert second == (tmp_path / "JP1-1-1").resolve()

    # Same game meta reuses the folder.
    second.mkdir()
    (second / "events.json").write_text(
        json.dumps({"Events": [], "meta": {"game_id": "JP1-1-1"}}),
        encoding="utf-8",
    )
    again = allocate_game_dir(tmp_path, "JP1-1")
    assert again == second


def test_unique_file_path(tmp_path: Path) -> None:
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"a")
    assert unique_file_path(path) == tmp_path / "clip-1.mp4"
