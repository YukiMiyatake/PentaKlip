from pathlib import Path

from pentaklip.replay.metadata import inspect_rofl


def _classic_rofl_bytes(meta: dict) -> bytes:
    import json

    meta_bytes = json.dumps(meta, separators=(",", ":")).encode("utf-8")
    header = bytearray(288)
    header[0:4] = b"RIOT"
    header[4:6] = b"\x00\x00"
    # metadata offset/length at 268/272
    offset = 288
    header[268:272] = int(offset).to_bytes(4, "little")
    header[272:276] = len(meta_bytes).to_bytes(4, "little")
    return bytes(header) + meta_bytes


def test_inspect_classic_rofl(tmp_path: Path) -> None:
    path = tmp_path / "JP1-123456.rofl"
    path.write_bytes(
        _classic_rofl_bytes(
            {
                "gameLength": 125000,
                "gameVersion": "14.1.1",
                "gameMode": "CLASSIC",
                "statsJson": "[]",
            }
        )
    )
    overview = inspect_rofl(path)
    assert overview.match_id == "JP1-123456"
    assert overview.game_length_sec == 125.0
    assert overview.game_mode == "CLASSIC"
    assert overview.is_practice_tool is False


def test_inspect_practice_mode(tmp_path: Path) -> None:
    path = tmp_path / "NA1-1.rofl"
    path.write_bytes(
        _classic_rofl_bytes(
            {
                "gameLength": 60000,
                "gameVersion": "14.1.1",
                "gameMode": "PRACTICETOOL",
                "statsJson": "[]",
            }
        )
    )
    overview = inspect_rofl(path)
    assert overview.is_practice_tool is True
