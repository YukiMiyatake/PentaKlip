"""Persisted UI / tool preferences (target replay, last folders)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

from pydantic import BaseModel


class UiPreferences(BaseModel):
    fixed_target_rofl: str | None = None
    last_source_dir: str | None = None
    last_video_dir: str | None = None
    last_events_dir: str | None = None
    last_output_root: str | None = None
    last_game_id: str | None = None


def _prefs_path(data_dir: Path) -> Path:
    return data_dir / "ui_preferences.json"


def load_ui_preferences(data_dir: Path) -> UiPreferences:
    path = _prefs_path(data_dir)
    if not path.is_file():
        return UiPreferences()
    return UiPreferences.model_validate(json.loads(path.read_text(encoding="utf-8")))


def save_ui_preferences(data_dir: Path, prefs: UiPreferences) -> UiPreferences:
    path = _prefs_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(prefs.model_dump_json(indent=2), encoding="utf-8")
    return prefs


class FsEntry(BaseModel):
    name: str
    path: str
    is_dir: bool
    size_bytes: int | None = None
    suffix: str | None = None


def list_directory(
    directory: Path,
    *,
    suffixes: list[str] | None = None,
) -> list[FsEntry]:
    directory = directory.expanduser().resolve()
    if not directory.is_dir():
        raise FileNotFoundError(f"Directory not found: {directory}")
    wanted = {s.lower() for s in suffixes} if suffixes else None
    entries: list[FsEntry] = []
    for item in sorted(directory.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        if item.is_dir():
            entries.append(
                FsEntry(name=item.name, path=str(item), is_dir=True, size_bytes=None, suffix=None)
            )
            continue
        suffix = item.suffix.lower()
        if wanted is not None and suffix not in wanted:
            continue
        entries.append(
            FsEntry(
                name=item.name,
                path=str(item),
                is_dir=False,
                size_bytes=item.stat().st_size,
                suffix=suffix,
            )
        )
    return entries
