"""Persisted UI / tool preferences (target replay, last folders)."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from pydantic import BaseModel, ConfigDict


class UiPreferences(BaseModel):
    """Folder and match prefs written to ``ui_preferences.json`` under the data dir."""

    model_config = ConfigDict(extra="ignore")

    fixed_target_rofl: str | None = None
    last_source_dir: str | None = None
    last_replays_dir: str | None = None
    last_video_dir: str | None = None
    last_highlights_dir: str | None = None
    last_events_dir: str | None = None
    last_output_root: str | None = None
    last_game_id: str | None = None


def ui_preferences_path(data_dir: Path) -> Path:
    return Path(data_dir).expanduser() / "ui_preferences.json"


def _prefs_path(data_dir: Path) -> Path:
    return ui_preferences_path(data_dir)


def load_ui_preferences(data_dir: Path) -> UiPreferences:
    path = _prefs_path(data_dir)
    if not path.is_file():
        return UiPreferences()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to read UI preferences %s: %s", path, exc)
        return UiPreferences()
    if not isinstance(raw, dict):
        logger.warning("UI preferences root must be an object: %s", path)
        return UiPreferences()
    return UiPreferences.model_validate(raw)


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def save_ui_preferences(data_dir: Path, prefs: UiPreferences) -> UiPreferences:
    path = _prefs_path(data_dir)
    _atomic_write_json(path, prefs.model_dump())
    return prefs


def update_ui_preferences(data_dir: Path, updates: dict[str, Any]) -> UiPreferences:
    """
    Merge ``updates`` into the on-disk preferences and save.

    Only keys present in ``updates`` are changed (including explicit ``null`` clears).
    Unknown keys are ignored. Always reloads from disk first so concurrent UI
    pages cannot clobber each other with stale full-document PUTs.
    """
    allowed = set(UiPreferences.model_fields)
    cleaned = {key: value for key, value in updates.items() if key in allowed}
    current = load_ui_preferences(data_dir)
    if not cleaned:
        return current
    merged = current.model_copy(update=cleaned)
    return save_ui_preferences(data_dir, merged)


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
    try:
        children = list(directory.iterdir())
    except OSError as exc:
        raise FileNotFoundError(f"Cannot read directory: {directory}") from exc
    for item in sorted(children, key=lambda p: (not p.is_dir(), p.name.lower())):
        if item.is_dir():
            entries.append(
                FsEntry(name=item.name, path=str(item), is_dir=True, size_bytes=None, suffix=None)
            )
            continue
        suffix = item.suffix.lower()
        if wanted is not None and suffix not in wanted:
            continue
        try:
            size = item.stat().st_size
        except OSError:
            size = None
        entries.append(
            FsEntry(
                name=item.name,
                path=str(item),
                is_dir=False,
                size_bytes=size,
                suffix=suffix,
            )
        )
    return entries


def pick_directory(*, title: str = "フォルダを選択", initial: str | None = None) -> str | None:
    """
    Open a native OS folder dialog on the machine running the API.

    Returns the selected absolute path, or ``None`` if cancelled / unavailable.
    Browser ``showDirectoryPicker`` cannot give a real path to Python, so local
    tools use this server-side dialog instead.
    """
    initial_dir = None
    if initial:
        candidate = Path(initial).expanduser()
        if candidate.is_dir():
            initial_dir = str(candidate.resolve())
        elif candidate.parent.is_dir():
            initial_dir = str(candidate.parent.resolve())

    # Prefer tkinter (stdlib) — works for local desktop API processes.
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        try:
            root.attributes("-topmost", True)
        except tk.TclError:
            pass
        selected = filedialog.askdirectory(
            title=title,
            initialdir=initial_dir or str(Path.home()),
            mustexist=True,
        )
        root.destroy()
        if selected:
            return str(Path(selected).resolve())
        return None
    except Exception:
        logger.debug("tkinter folder picker unavailable", exc_info=True)

    # Windows fallback: WinForms FolderBrowserDialog via PowerShell.
    import platform
    import subprocess

    if platform.system() != "Windows":
        return None
    ps_initial = (initial_dir or "").replace("'", "''")
    ps_title = title.replace("'", "''")
    script = f"""
Add-Type -AssemblyName System.Windows.Forms
$dialog = New-Object System.Windows.Forms.FolderBrowserDialog
$dialog.Description = '{ps_title}'
$dialog.ShowNewFolderButton = $true
if ('{ps_initial}') {{ $dialog.SelectedPath = '{ps_initial}' }}
$result = $dialog.ShowDialog()
if ($result -eq [System.Windows.Forms.DialogResult]::OK) {{
  Write-Output $dialog.SelectedPath
}}
"""
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-STA", "-Command", script],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError:
        return None
    line = (completed.stdout or "").strip().splitlines()
    if not line:
        return None
    path = Path(line[-1].strip())
    return str(path.resolve()) if path.is_dir() else None
