from pathlib import Path
from unittest.mock import patch

from pentaklip.export.ffmpeg import ExportResult, ensure_mp4_source


def test_ensure_mp4_source_passthrough_for_mp4(tmp_path: Path) -> None:
    video = tmp_path / "a.mp4"
    video.write_bytes(b"x")
    path, result = ensure_mp4_source(video)
    assert path == video.resolve()
    assert result is None


def test_ensure_mp4_source_converts_webm(tmp_path: Path) -> None:
    video = tmp_path / "a.webm"
    video.write_bytes(b"webm")
    cache = tmp_path / "out"
    converted = cache / "a.mp4"

    with patch(
        "pentaklip.export.ffmpeg.convert_to_mp4",
        return_value=ExportResult(output_path=converted, command=["ffmpeg"]),
    ) as mocked:
        # Pretend convert wrote the file so mtime cache checks are irrelevant.
        cache.mkdir()
        converted.write_bytes(b"mp4")
        path, result = ensure_mp4_source(video, cache_dir=cache, force=True)

    mocked.assert_called_once()
    assert path == converted.resolve()
    assert result is not None
