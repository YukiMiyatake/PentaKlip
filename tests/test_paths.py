from pathlib import Path

from pentaklip.paths import (
    extract_game_id_from_live_payload,
    infer_game_id,
    resolve_game_dir,
    sanitize_game_id,
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
