"""Resolve a preferred game / match id for output folders."""

from __future__ import annotations

from pathlib import Path

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
