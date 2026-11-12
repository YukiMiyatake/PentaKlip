"""Filesystem helpers for per-game-id output folders."""

from __future__ import annotations

import json
import re
from pathlib import Path

from pentaklip.replay.install import parse_match_id_from_filename

_UNSAFE_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_MATCH_ID_RE = re.compile(r"(?P<id>[A-Za-z0-9]+-\d+)")
_REGION_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]{1,4}$")

# ROFL / Live Client often expose bare numeric game ids without a region.
# Japan installs commonly use JP1-… filenames; default when region is unknown.
DEFAULT_MATCH_REGION = "JP1"


def sanitize_game_id(game_id: str) -> str:
    cleaned = _UNSAFE_CHARS.sub("_", game_id.strip())
    cleaned = cleaned.strip(" .")
    if not cleaned:
        raise ValueError("game_id must not be empty")
    return cleaned


def with_game_id_prefix(game_id: str, basename: str) -> str:
    """Return ``{game_id}_{basename}`` without double-prefixing."""
    safe = sanitize_game_id(game_id)
    name = basename.strip()
    if not name:
        raise ValueError("basename must not be empty")
    if name.lower().startswith(f"{safe.lower()}_"):
        return name
    return f"{safe}_{name}"


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


def normalize_region_code(value: str | None) -> str | None:
    if not value:
        return None
    text = str(value).strip().upper()
    if not text or not _REGION_RE.fullmatch(text):
        return None
    # Reject pure digits masquerading as region.
    if text.isdigit():
        return None
    return text


def format_region_match_id(
    value: str | int | None,
    *,
    region: str | None = None,
    default_region: str = DEFAULT_MATCH_REGION,
) -> str | None:
    """
    Normalize to ``REGION-digits`` (e.g. ``JP1-612229453``).

    Bare numeric ids get ``default_region`` (JP1) when meta has no platform/region.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    existing = _MATCH_ID_RE.fullmatch(text) or _MATCH_ID_RE.search(text)
    if existing:
        return sanitize_game_id(existing.group("id"))
    digits = text if text.isdigit() else None
    if digits is None:
        # Allow "JP1 612229453" / "game 612229453" loose forms.
        m = re.search(r"(\d{6,})", text)
        if m:
            digits = m.group(1)
    if not digits or len(digits) < 6:
        return None
    prefix = normalize_region_code(region) or default_region
    return sanitize_game_id(f"{prefix}-{digits}")


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
        formatted = format_region_match_id(raw)
        if formatted:
            return formatted
        found = look_like_game_id(str(raw))
        if found:
            return found
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


# Standard output tree under a single configurable base folder.
EVENT_DIR_NAME = "Event"
REPLAY_DIR_NAME = "Replay"
STATS_DIR_NAME = "stats"
CLIP_DIR_NAME = "Clip"


class OutputLayout:
    """
    ``{root}/Event``, ``Replay``, ``stats``, ``Clip/{game_id}``.

    Event / stats files are flat under their folders and use a game-id filename prefix.
    Clips are grouped per game under ``Clip/{game_id}/``.
    """

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).expanduser().resolve()

    @property
    def event_dir(self) -> Path:
        return self.root / EVENT_DIR_NAME

    @property
    def replay_dir(self) -> Path:
        return self.root / REPLAY_DIR_NAME

    @property
    def stats_dir(self) -> Path:
        return self.root / STATS_DIR_NAME

    @property
    def clip_root(self) -> Path:
        return self.root / CLIP_DIR_NAME

    def clip_dir(self, game_id: str) -> Path:
        return allocate_game_dir(self.clip_root, game_id)

    def ensure(self) -> None:
        for path in (self.event_dir, self.replay_dir, self.stats_dir, self.clip_root):
            path.mkdir(parents=True, exist_ok=True)


def resolve_output_layout(
    base_dir: Path | str | None,
    *,
    fallback: Path | str,
) -> OutputLayout:
    root = Path(base_dir).expanduser() if base_dir else Path(fallback).expanduser()
    return OutputLayout(root)


def format_clip_time_range(start_sec: float, end_sec: float) -> str:
    """Human-readable clip window for filenames, e.g. ``1m05s-1m25s``."""

    def _fmt(total_sec: float) -> str:
        total = max(0, int(total_sec))
        minutes, seconds = divmod(total, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours}h{minutes:02d}m{seconds:02d}s"
        return f"{minutes}m{seconds:02d}s"

    return f"{_fmt(start_sec)}-{_fmt(end_sec)}"


def _events_meta_game_id(folder: Path) -> str | None:
    candidates = sorted(folder.glob("*_events.json")) + sorted(folder.glob("events.json"))
    for events in candidates:
        if not events.is_file():
            continue
        try:
            data = json.loads(events.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        meta = data.get("meta")
        if not isinstance(meta, dict):
            continue
        raw = meta.get("game_id")
        if raw:
            try:
                return sanitize_game_id(str(raw))
            except ValueError:
                continue
    return None


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
