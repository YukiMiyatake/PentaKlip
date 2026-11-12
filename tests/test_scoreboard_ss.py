"""Scoreboard SS OCR → DPM / DMG% merge."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pentaklip.stats.catalog import StatKey
from pentaklip.stats.export import load_aggregated_stats
from pentaklip.stats.scoreboard_ss import (
    OcrLine,
    apply_scoreboard_damage,
    find_scoreboard_ss,
    parse_scoreboard_lines,
)

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE_OCR = FIXTURES / "scoreboard_ss_ocr_JP1-612229453.json"
FIXTURE_AGG = FIXTURES / "JP1-612229453_stats_aggregated_slim.json"
SAMPLE_SS_DIR = Path(r"E:\Game\PentaKlip\test1\stats")
SAMPLE_SS = next(
    (
        path
        for path in (
            SAMPLE_SS_DIR / "JP1-612229453.png",
            SAMPLE_SS_DIR / "JP1-612229453_ss.png",
        )
        if path.is_file()
    ),
    SAMPLE_SS_DIR / "JP1-612229453.png",
)


def _load_fixture_lines() -> tuple[list[OcrLine], int, int]:
    payload = json.loads(FIXTURE_OCR.read_text(encoding="utf-8"))
    lines = [OcrLine(**row) for row in payload["lines"]]
    width, _height = payload["image_size"]
    return lines, int(width), int(payload["ocr_scale"])


def test_find_scoreboard_ss(tmp_path: Path) -> None:
    exact = tmp_path / "JP1-612229453.png"
    exact.write_bytes(b"exact")
    assert find_scoreboard_ss(tmp_path, "JP1-612229453") == exact

    # Prefer exact name over legacy / wildcard suffixes.
    legacy = tmp_path / "JP1-612229453_ss.png"
    wildcard = tmp_path / "JP1-612229453_data.png"
    legacy.write_bytes(b"legacy")
    wildcard.write_bytes(b"wild")
    assert find_scoreboard_ss(tmp_path, "JP1-612229453") == exact

    exact.unlink()
    assert find_scoreboard_ss(tmp_path, "JP1-612229453") == legacy

    legacy.unlink()
    assert find_scoreboard_ss(tmp_path, "JP1-612229453") == wildcard
    assert find_scoreboard_ss(tmp_path, "missing") is None


def test_parse_fixture_damage_and_duration() -> None:
    lines, width, scale = _load_fixture_lines()
    parsed = parse_scoreboard_lines(lines, image_width=width, ocr_scale=scale)
    assert parsed.game_duration_sec == pytest.approx(46 * 60 + 26)
    assert len(parsed.columns) == 10
    damages = [col.damage_to_champions for col in parsed.columns]
    assert damages[0] == 12175
    assert damages[2] == 19220
    assert damages[8] == 46897
    assert damages[9] == 10642


def test_apply_damage_matches_players_by_kda() -> None:
    lines, width, scale = _load_fixture_lines()
    parsed = parse_scoreboard_lines(lines, image_width=width, ocr_scale=scale)
    aggregated = load_aggregated_stats(FIXTURE_AGG)
    enriched = apply_scoreboard_damage(aggregated, parsed, image_path=None, ocr_scale=scale)

    by_champ = {p.champion_name: p for p in enriched.players}
    ahri = by_champ["アーリ"]
    jhin = by_champ["ジン"]
    assert ahri.scalars[StatKey.DAMAGE_TO_CHAMPIONS.value] == 19220
    assert jhin.scalars[StatKey.DAMAGE_TO_CHAMPIONS.value] == 46897
    minutes = (46 * 60 + 26) / 60.0
    assert ahri.scalars[StatKey.DPM.value] == round(19220 / minutes, 1)
    # Ahri is CHAOS with teammates Leona/Caitlyn/Zyra/Sion
    chaos_total = 12175 + 41147 + 19220 + 46499 + 42959
    assert ahri.scalars[StatKey.DAMAGE_SHARE.value] == round(100.0 * 19220 / chaos_total, 1)


@pytest.mark.skipif(
    not SAMPLE_SS.is_file(),
    reason="local sample SS missing",
)
def test_windows_ocr_live_optional() -> None:
    pytest.importorskip("winrt.windows.media.ocr")
    from pentaklip.stats.scoreboard_ss import parse_scoreboard_ss

    parsed = parse_scoreboard_ss(SAMPLE_SS)
    assert parsed.game_duration_sec == pytest.approx(46 * 60 + 26)
    assert len(parsed.columns) >= 8
