"""Best-effort ROFL / ROFL2 metadata extraction for UI overview."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from pentaklip.paths import (
    DEFAULT_MATCH_REGION,
    format_region_match_id,
    normalize_region_code,
)
from pentaklip.replay.install import parse_match_id_from_filename


class RoflOverview(BaseModel):
    path: str
    filename: str
    match_id: str | None = None
    match_id_source: Literal["meta", "meta_fingerprint", "filename"] | None = None
    format: str | None = None
    game_version: str | None = None
    game_length_ms: int | None = None
    game_length_sec: float | None = None
    game_mode: str | None = None
    map_name: str | None = None
    is_practice_tool: bool | None = None
    player_count: int | None = None
    players: list[str] = Field(default_factory=list)
    size_bytes: int = 0
    note: str | None = None
    raw_keys: list[str] = Field(default_factory=list)


def _decode_json_blob(data: bytes) -> dict[str, Any] | None:
    try:
        text = data.decode("utf-8")
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def _read_classic_rofl_metadata(data: bytes) -> dict[str, Any] | None:
    if len(data) < 276:
        return None
    offset = int.from_bytes(data[268:272], "little")
    length = int.from_bytes(data[272:276], "little")
    if offset <= 0 or length <= 0 or offset + length > len(data):
        return None
    return _decode_json_blob(data[offset : offset + length])


def _read_rofl2_trailing_metadata(data: bytes) -> dict[str, Any] | None:
    # ROFL2 (14.11+) often stores a JSON object near EOF.
    # Search backwards for a plausible JSON object containing gameLength/gameVersion.
    window = data[-min(len(data), 2_000_000) :]
    for marker in (b'{"gameLength"', b'{"gameVersion"', b'{"lastGameChunkId"'):
        idx = window.rfind(marker)
        if idx < 0:
            continue
        # Walk back to opening brace if marker isn't at start
        start = window.rfind(b"{", 0, idx + 1)
        if start < 0:
            start = idx
        blob = window[start:]
        # Trim to last closing brace
        end = blob.rfind(b"}")
        if end < 0:
            continue
        parsed = _decode_json_blob(blob[: end + 1])
        if parsed:
            return parsed
    return None


def _parse_stats_list(meta: dict[str, Any]) -> list[dict[str, Any]]:
    stats_raw = meta.get("statsJson") or meta.get("stats_json") or "[]"
    if isinstance(stats_raw, str):
        try:
            loaded = json.loads(stats_raw)
        except json.JSONDecodeError:
            return []
    else:
        loaded = stats_raw
    if not isinstance(loaded, list):
        return []
    return [s for s in loaded if isinstance(s, dict)]


def _region_from_rofl_meta(
    meta: dict[str, Any],
    stats: list[dict[str, Any]] | None = None,
) -> str:
    """Best-effort platform/region code; falls back to JP1."""
    rows = stats if stats is not None else _parse_stats_list(meta)
    candidates: list[object] = [
        meta.get("platformId"),
        meta.get("platformID"),
        meta.get("region"),
        meta.get("gameServerRegion"),
        meta.get("serverRegion"),
    ]
    for row in rows:
        candidates.extend(
            [
                row.get("PLATFORM_ID"),
                row.get("platformId"),
                row.get("REGION"),
                row.get("region"),
            ]
        )
    for raw in candidates:
        code = normalize_region_code(str(raw) if raw is not None else None)
        if code:
            return code
    return DEFAULT_MATCH_REGION


def extract_match_id_from_rofl_meta(meta: dict[str, Any]) -> tuple[str | None, str | None]:
    """
    Prefer an explicit match/game id from ROFL metadata.

    Bare numeric ``gameId`` values are formatted as ``{region}-{id}``. Region is
    taken from meta when present; otherwise defaults to ``JP1`` (filename-style).
    If no game id exists, return ``(None, None)`` so callers can fall back to the
    filename before using a fingerprint.
    """
    stats = _parse_stats_list(meta)
    region = _region_from_rofl_meta(meta, stats)

    candidates: list[object] = []
    for key in (
        "gameId",
        "gameID",
        "matchId",
        "matchID",
        "game_id",
        "match_id",
        "gameIdStr",
    ):
        candidates.append(meta.get(key))

    for row in stats:
        for key in ("GAME_ID", "MATCH_ID", "gameId", "matchId", "game_id", "match_id"):
            candidates.append(row.get(key))

    for raw in candidates:
        if raw is None or raw == "":
            continue
        formatted = format_region_match_id(raw, region=region)
        if formatted:
            return formatted, "meta"

    return None, None


def fingerprint_rofl_meta(
    meta: dict[str, Any],
    stats: list[dict[str, Any]] | None = None,
) -> str | None:
    """Build a rename-stable id from ROFL metadata (not the .rofl filename)."""
    rows = stats if stats is not None else _parse_stats_list(meta)
    length = meta.get("gameLength") or meta.get("game_length")
    version = meta.get("gameVersion") or meta.get("game_version") or ""
    player_tokens: list[str] = []
    for row in rows:
        token = (
            row.get("ID")
            or row.get("PUUID")
            or row.get("RIOT_ID_GAME_NAME")
            or row.get("NAME")
            or row.get("name")
        )
        if token is not None and str(token).strip():
            player_tokens.append(str(token).strip())
    player_tokens = sorted(set(player_tokens))
    if length is None and not player_tokens and not version:
        return None
    material = "|".join([str(length or ""), str(version), *player_tokens])
    digest = hashlib.sha1(material.encode("utf-8")).hexdigest()[:10]
    return f"rofl-{digest}"

def _infer_practice(meta: dict[str, Any], stats: list[dict[str, Any]]) -> bool | None:
    mode = str(meta.get("gameMode") or meta.get("game_mode") or "").upper()
    if mode in {"PRACTICETOOL", "PRACTICE", "TUTORIAL"}:
        return True
    if any(str(p.get("NAME") or "").startswith("Practice Tool") for p in stats):
        return True
    if any(str(p.get("NAME") or "") == "" and str(p.get("SKIN") or "") for p in stats):
        # weak signal; leave None
        pass
    map_name = str(meta.get("mapName") or meta.get("map_name") or "")
    if "Practice" in map_name:
        return True
    return False if mode else None


def _overview_from_meta(path: Path, meta: dict[str, Any], fmt: str) -> RoflOverview:
    stats = _parse_stats_list(meta)

    length_ms = meta.get("gameLength") or meta.get("game_length")
    length_ms_i = int(length_ms) if length_ms is not None else None
    players = [str(p.get("NAME") or p.get("name") or p.get("RIOT_ID_GAME_NAME") or "") for p in stats]
    players = [p for p in players if p]

    game_mode = meta.get("gameMode") or meta.get("game_mode")
    # Sometimes mode only appears inside stats / nested fields
    if not game_mode and stats:
        game_mode = stats[0].get("GAME_MODE") or stats[0].get("gameMode")

    meta_id, meta_source = extract_match_id_from_rofl_meta(meta)
    filename_id = parse_match_id_from_filename(path)
    fingerprint = fingerprint_rofl_meta(meta, stats)
    note = None
    match_id_source: Literal["meta", "meta_fingerprint", "filename"] | None
    if meta_id:
        match_id = meta_id
        match_id_source = "meta" if meta_source == "meta" else "meta_fingerprint"
        bare = next(
            (
                str(v).strip()
                for v in (
                    meta.get("gameId"),
                    meta.get("gameID"),
                    meta.get("matchId"),
                    meta.get("matchID"),
                )
                if v is not None and str(v).strip().isdigit()
            ),
            None,
        )
        if bare and match_id == format_region_match_id(bare):
            note = f"ROFL gameId={bare} にリージョンが無いため {DEFAULT_MATCH_REGION}- を付与"
    elif filename_id:
        match_id = filename_id
        match_id_source = "filename"
    elif fingerprint:
        match_id = fingerprint
        match_id_source = "meta_fingerprint"
        note = (
            "ROFL metadata has no gameId; using rename-stable fingerprint "
            "(no REGION-digits filename either)"
        )
    else:
        match_id = None
        match_id_source = None

    return RoflOverview(
        path=str(path),
        filename=path.name,
        match_id=match_id,
        match_id_source=match_id_source,
        format=fmt,
        game_version=str(meta.get("gameVersion") or meta.get("game_version") or "") or None,
        game_length_ms=length_ms_i,
        game_length_sec=(length_ms_i / 1000.0) if length_ms_i is not None else None,
        game_mode=str(game_mode) if game_mode else None,
        map_name=str(meta.get("mapName") or meta.get("map_name") or "") or None,
        is_practice_tool=_infer_practice(meta, stats),
        player_count=len(stats) if stats else None,
        players=players[:10],
        size_bytes=path.stat().st_size,
        note=note,
        raw_keys=sorted(meta.keys()),
    )


def inspect_rofl(path: Path) -> RoflOverview:
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Replay not found: {path}")
    if path.suffix.lower() != ".rofl":
        raise ValueError(f"Expected .rofl file, got: {path.name}")

    data = path.read_bytes()
    magic = data[:4]
    if magic != b"RIOT":
        filename_id = parse_match_id_from_filename(path)
        return RoflOverview(
            path=str(path),
            filename=path.name,
            match_id=filename_id,
            match_id_source="filename" if filename_id else None,
            size_bytes=path.stat().st_size,
            note="Unrecognized ROFL magic; only filename metadata available",
        )

    version_byte = data[4] if len(data) > 4 else 0
    if version_byte == 0:
        meta = _read_classic_rofl_metadata(data)
        if meta:
            return _overview_from_meta(path, meta, "ROFL")
        filename_id = parse_match_id_from_filename(path)
        return RoflOverview(
            path=str(path),
            filename=path.name,
            match_id=filename_id,
            match_id_source="filename" if filename_id else None,
            format="ROFL",
            size_bytes=path.stat().st_size,
            note="Classic ROFL header found but metadata JSON could not be parsed",
        )

    # ROFL2
    meta = _read_rofl2_trailing_metadata(data) or _read_classic_rofl_metadata(data)
    if meta:
        return _overview_from_meta(path, meta, "ROFL2")
    filename_id = parse_match_id_from_filename(path)
    return RoflOverview(
        path=str(path),
        filename=path.name,
        match_id=filename_id,
        match_id_source="filename" if filename_id else None,
        format="ROFL2",
        size_bytes=path.stat().st_size,
        note="ROFL2 metadata unavailable (e.g. patch 14.9–14.10) or unreadable",
    )
