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
