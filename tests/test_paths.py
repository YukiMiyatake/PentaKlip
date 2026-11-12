import json
from pathlib import Path

from pentaklip.paths import (
    OutputLayout,
    allocate_game_dir,
    extract_game_id_from_live_payload,
    format_clip_time_range,
    infer_game_id,
    resolve_game_dir,
    resolve_output_layout,
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
    assert (
        extract_game_id_from_live_payload({"gameData": {"gameId": "612229453"}})
        == "JP1-612229453"
    )


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


def test_output_layout_and_clip_time(tmp_path: Path) -> None:
    layout = resolve_output_layout(tmp_path / "out", fallback=tmp_path)
    layout.ensure()
    assert layout.event_dir.is_dir()
    assert layout.replay_dir.is_dir()
    assert layout.stats_dir.is_dir()
    assert layout.clip_root.is_dir()
    assert layout.clip_dir("JP1-9") == (tmp_path / "out" / "Clip" / "JP1-9").resolve()
    assert isinstance(layout, OutputLayout)
    assert format_clip_time_range(65, 90) == "1m05s-1m30s"
    assert format_clip_time_range(3661, 3725) == "1h01m01s-1h02m05s"
