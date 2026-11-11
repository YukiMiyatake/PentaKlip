"""Rename / copy downloaded .rofl files into the local LoL Replays folder."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

# Typical downloaded / local names look like: NA1-1234567890.rofl or similar.
_MATCH_ID_RE = re.compile(r"(?P<id>[A-Za-z0-9]+-\d+)")


def parse_match_id_from_filename(path: Path | str) -> str | None:
    name = Path(path).stem
    match = _MATCH_ID_RE.search(name)
    return match.group("id") if match else None


@dataclass(frozen=True)
class InstallResult:
    original_match_id: str
    original_filename: str
    local_replay_id: str
    installed_path: Path
    overwritten: bool


def install_replay(
    source: Path,
    *,
    local_replay_id: str,
    replays_dir: Path,
    dry_run: bool = False,
) -> InstallResult:
    """
    Copy `source` into `replays_dir` as `{local_replay_id}.rofl`.

    Preserves the original match id derived from the source filename (or stem fallback)
    so callers can store it even though the on-disk name changes.
    """
    source = source.resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Replay file not found: {source}")
    if source.suffix.lower() != ".rofl":
        raise ValueError(f"Expected a .rofl file, got: {source.name}")

    original_match_id = parse_match_id_from_filename(source) or source.stem
    local_replay_id = local_replay_id.removesuffix(".rofl")
    dest = replays_dir / f"{local_replay_id}.rofl"
    overwritten = dest.exists()

    if not dry_run:
        replays_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)

    return InstallResult(
        original_match_id=original_match_id,
        original_filename=source.name,
        local_replay_id=local_replay_id,
        installed_path=dest,
        overwritten=overwritten,
    )
