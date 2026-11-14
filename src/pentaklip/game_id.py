"""Resolve a preferred game / match id for output folders."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pentaklip.paths import infer_game_id, look_like_game_id
from pentaklip.replay.install import parse_match_id_from_filename
from pentaklip.replay.metadata import inspect_rofl
from pentaklip.store.db import Database


def game_id_from_rofl_path(
    rofl_path: str | Path | None,
    *,
    db: Database | None = None,
) -> tuple[str | None, str | None]:
    """
    Resolve game id for a .rofl path.

    Priority:
      1. DB original_match_id (survives replace/rename of local file)
      2. ROFL metadata explicit id / rename-stable fingerprint
      3. Filename (last resort; changes on replace)
    """
    if not rofl_path:
        return None, None
    path = Path(rofl_path)
    if not path.is_file():
        # Still try filename / DB with the given path string.
        if db is not None:
            row = db.find_replay_by_installed_path(path)
            if row and row.get("original_match_id"):
                return str(row["original_match_id"]), "db"
            local_id = parse_match_id_from_filename(path)
            if local_id:
                row = db.find_replay_by_local_id(local_id)
                if row and row.get("original_match_id"):
                    return str(row["original_match_id"]), "db"
        return infer_game_id(path), "filename" if infer_game_id(path) else None

    if db is not None:
        row = db.find_replay_by_installed_path(path)
        if row and row.get("original_match_id"):
            return str(row["original_match_id"]), "db"
        local_id = parse_match_id_from_filename(path)
        if local_id:
            row = db.find_replay_by_local_id(local_id)
            if row and row.get("original_match_id"):
                return str(row["original_match_id"]), "db"

    if path.suffix.lower() == ".rofl":
        try:
            overview = inspect_rofl(path)
        except (OSError, ValueError):
            overview = None
        if overview and overview.match_id:
            return overview.match_id, overview.match_id_source

    filename_id = parse_match_id_from_filename(path) or look_like_game_id(path.name)
    return filename_id, "filename" if filename_id else None


def _replay_row_for_rofl(
    rofl_path: str | Path | None, db: Database | None
) -> dict[str, Any] | None:
    if db is None or not rofl_path:
        return None
    path = Path(rofl_path)
    row = db.find_replay_by_installed_path(path)
    if row:
        return row
    local_id = parse_match_id_from_filename(path)
    if local_id:
        return db.find_replay_by_local_id(local_id)
    return None


def resolve_output_game_id(
    *candidates: str | Path | None,
    rofl_path: str | Path | None = None,
    db: Database | None = None,
) -> tuple[str | None, str | None]:
    """
    Resolve the game id used for Event / Replay / stats / Clip prefixes.

    After replace-copy the on-disk ``.rofl`` name is the *local* id. When a
    candidate equals that local id, rewrite it to the pre-copy
    ``original_match_id`` from the install DB. Unrelated explicit game ids
    (other matches) are left unchanged.
    """
    row = _replay_row_for_rofl(rofl_path, db)
    original: str | None = None
    local_id: str | None = None
    if row:
        if row.get("original_match_id"):
            original = str(row["original_match_id"])
        if row.get("local_replay_id"):
            local_id = str(row["local_replay_id"])

    remapped: list[str | Path | None] = []
    saw_local = False
    for candidate in candidates:
        if candidate is None:
            continue
        text = candidate.name if isinstance(candidate, Path) else str(candidate).strip()
        if not text:
            continue
        as_id = look_like_game_id(text) or parse_match_id_from_filename(Path(text))
        if (
            local_id
            and original
            and as_id
            and as_id.lower() == local_id.lower()
        ):
            saw_local = True
            remapped.append(original)
            continue
        remapped.append(candidate)

    found = infer_game_id(*remapped)
    if found:
        if local_id and original and found.lower() == local_id.lower():
            return original, "db"
        if saw_local and original and found.lower() == original.lower():
            return original, "db"
        return found, "candidate"

    if original:
        return original, "db"

    rofl_id, rofl_src = game_id_from_rofl_path(rofl_path, db=db)
    if rofl_id:
        return rofl_id, rofl_src
    return None, None
