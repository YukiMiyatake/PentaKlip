"""Filesystem helpers for per-game-id output folders."""

from __future__ import annotations

import json
import re
from pathlib import Path

from pentaklip.replay.install import parse_match_id_from_filename

_UNSAFE_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_MATCH_ID_RE = re.compile(r"(?P<id>[A-Za-z0-9]+-\d+)")


def sanitize_game_id(game_id: str) -> str:
    cleaned = _UNSAFE_CHARS.sub("_", game_id.strip())
    cleaned = cleaned.strip(" .")
    if not cleaned:
        raise ValueError("game_id must not be empty")
    return cleaned


def look_like_game_id(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    match = _MATCH_ID_RE.fullmatch(text) or _MATCH_ID_RE.search(text)
    if match:
        return match.group("id")
    # Allow non-standard IDs that are still path-safe (manual entry).
    try:
        return sanitize_game_id(text)
    except ValueError:
        return None


def extract_game_id_from_live_payload(data: dict) -> str | None:
    """Best-effort game id from Live Client allgamedata / event payloads."""
    candidates: list[object] = []
    game_data = data.get("gameData") if isinstance(data.get("gameData"), dict) else {}
    assert isinstance(game_data, dict)
    for key in (
        "gameId",
        "gameID",
        "matchId",
        "matchID",
        "game_id",
        "match_id",
    ):
        candidates.append(game_data.get(key))
        candidates.append(data.get(key))
    for raw in candidates:
        if raw is None:
            continue
        found = look_like_game_id(str(raw))
        if found:
            return found
        # Numeric-only Live Client ids: keep as-is after sanitize.
        try:
            return sanitize_game_id(str(raw))
        except ValueError:
            continue
    return None


def infer_game_id(
    *candidates: str | Path | None,
) -> str | None:
    """
    Return the first usable game id from explicit values, filenames, or folder names.
    """
    for candidate in candidates:
        if candidate is None:
            continue
        if isinstance(candidate, Path):
            parsed = parse_match_id_from_filename(candidate)
            if parsed:
                return parsed
            folder_id = look_like_game_id(candidate.name)
            if folder_id:
                return folder_id
            continue
        text = str(candidate).strip()
        if not text:
            continue
        as_path = Path(text)
        parsed = parse_match_id_from_filename(as_path)
        if parsed:
            return parsed
        folder_id = look_like_game_id(as_path.name)
        if folder_id:
            return folder_id
        direct = look_like_game_id(text)
        if direct:
            return direct
    return None


def resolve_game_dir(base_dir: Path | str, game_id: str) -> Path:
    """Return ``{base}/{game_id}`` (created by callers as needed)."""
    base = Path(base_dir).expanduser()
    return (base / sanitize_game_id(game_id)).resolve()


def _events_meta_game_id(folder: Path) -> str | None:
    events = folder / "events.json"
    if not events.is_file():
        return None
    try:
        loaded = json.loads(events.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(loaded, dict):
        return None
    meta = loaded.get("meta")
    if not isinstance(meta, dict):
        return None
    raw = meta.get("game_id")
    return str(raw) if raw else None


def allocate_game_dir(
    base_dir: Path | str,
    game_id: str,
    *,
    reuse_matching: bool = True,
) -> Path:
    """
    Resolve ``{base}/{game_id}``, or ``{game_id}-1`` / ``-2`` / ... on collision.

    Reuses an existing folder when empty, or when events.json meta.game_id matches.
    If another game already occupies the name, allocate the next free ``-N`` suffix.
    """
    base = Path(base_dir).expanduser().resolve()
    safe = sanitize_game_id(game_id)
    primary = base / safe
    if not primary.exists():
        return primary

    if reuse_matching:
        try:
            entries = list(primary.iterdir())
        except OSError:
            entries = ["?"]
        if not entries:
            return primary
        meta_gid = _events_meta_game_id(primary)
        if meta_gid is None or meta_gid in {safe, game_id}:
            return primary

    index = 1
    while True:
        candidate = base / f"{safe}-{index}"
        if not candidate.exists():
            return candidate
        if reuse_matching:
            meta_gid = _events_meta_game_id(candidate)
            if meta_gid is None or meta_gid in {safe, game_id, f"{safe}-{index}"}:
                return candidate
        index += 1


def unique_file_path(path: Path) -> Path:
    """If ``path`` exists, return ``stem-1.ext``, ``stem-2.ext``, ..."""
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    index = 1
    while True:
        candidate = parent / f"{stem}-{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1
