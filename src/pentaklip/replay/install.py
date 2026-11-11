"""Rename / copy downloaded .rofl files into the local LoL Replays folder."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

# Typical downloaded / local names look like: NA1-1234567890.rofl or similar.
_MATCH_ID_RE = re.compile(r"(?P<id>[A-Za-z0-9]+-\d+)")


class InstallMode(StrEnum):
    COPY = "copy"
    MOVE = "move"
    RENAME_IN_PLACE = "rename_in_place"


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
    mode: InstallMode


@dataclass(frozen=True)
class LocalReplayInfo:
    path: Path
    filename: str
    match_id: str | None
    size_bytes: int


def list_local_replays(replays_dir: Path) -> list[LocalReplayInfo]:
    if not replays_dir.is_dir():
        return []
    items: list[LocalReplayInfo] = []
    for path in sorted(replays_dir.glob("*.rofl")):
        items.append(
            LocalReplayInfo(
                path=path,
                filename=path.name,
                match_id=parse_match_id_from_filename(path),
                size_bytes=path.stat().st_size,
            )
        )
    return items


def install_replay(
    source: Path,
    *,
    local_replay_id: str,
    replays_dir: Path,
    mode: InstallMode = InstallMode.COPY,
    dry_run: bool = False,
) -> InstallResult:
    """
    Place `source` into `replays_dir` as `{local_replay_id}.rofl`.

    Preserves the original match id derived from the source filename (or stem fallback)
    so callers can store it even though the on-disk name changes.
    """
    source = source.resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Replay file not found: {source}")
    if source.suffix.lower() != ".rofl":
        raise ValueError(f"Expected a .rofl file, got: {source.name}")

    original_match_id = parse_match_id_from_filename(source) or source.stem
    original_filename = source.name
    local_replay_id = local_replay_id.removesuffix(".rofl")

    if mode == InstallMode.RENAME_IN_PLACE:
        dest = source.with_name(f"{local_replay_id}.rofl")
    else:
        dest = replays_dir / f"{local_replay_id}.rofl"

    if dest.resolve() == source.resolve():
        return InstallResult(
            original_match_id=original_match_id,
            original_filename=original_filename,
            local_replay_id=local_replay_id,
            installed_path=dest,
            overwritten=False,
            mode=mode,
        )

    overwritten = dest.exists()
    if not dry_run:
        if mode != InstallMode.RENAME_IN_PLACE:
            replays_dir.mkdir(parents=True, exist_ok=True)
        if mode == InstallMode.COPY:
            shutil.copy2(source, dest)
        elif mode == InstallMode.MOVE:
            shutil.move(str(source), str(dest))
        elif mode == InstallMode.RENAME_IN_PLACE:
            source.rename(dest)
        else:
            raise ValueError(f"Unsupported mode: {mode}")

    return InstallResult(
        original_match_id=original_match_id,
        original_filename=original_filename,
        local_replay_id=local_replay_id,
        installed_path=dest,
        overwritten=overwritten,
        mode=mode,
    )
