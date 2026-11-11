"""Fetch Live Client events and write clip-compatible JSON files."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from pentaklip.paths import (
    allocate_game_dir,
    extract_game_id_from_live_payload,
    sanitize_game_id,
)
from pentaklip.record.live_client import LiveClientClient


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class EventsLiveStatus(BaseModel):
    available: bool
    events: list[dict[str, Any]] = Field(default_factory=list)
    event_count: int = 0
    game_time_sec: float | None = None
    game_id: str | None = None
    source: str = "liveclientdata"
    error: str | None = None


class EventsExportResult(BaseModel):
    path: str
    event_count: int
    game_id: str
    game_dir: str
    game_time_sec: float | None = None
    source: str = "liveclientdata"


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def extract_events_from_payload(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize Live Client eventdata / allgamedata shapes into a list of event dicts."""
    if "Events" in data and isinstance(data["Events"], list):
        return [e for e in data["Events"] if isinstance(e, dict)]
    if "events" in data:
        events_obj = data["events"]
        if isinstance(events_obj, list):
            return [e for e in events_obj if isinstance(e, dict)]
        if isinstance(events_obj, dict):
            nested = events_obj.get("Events") or events_obj.get("events") or []
            return [e for e in _as_list(nested) if isinstance(e, dict)]
    return []


def extract_game_time_sec(data: dict[str, Any]) -> float | None:
    game_data = _as_dict(data.get("gameData"))
    raw = game_data.get("gameTime", data.get("gameTime"))
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def suggest_events_filename(*, game_time_sec: float | None = None) -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if game_time_sec is None:
        return f"events_{stamp}.json"
    return f"events_{stamp}_t{int(game_time_sec)}s.json"


def fetch_live_events(client: LiveClientClient | None = None) -> EventsLiveStatus:
    """Pull current match events from the local Live Client Data API."""
    live = client or LiveClientClient()
    if not live.is_available():
        return EventsLiveStatus(
            available=False,
            error="Live Client is not available. Start a LoL replay or game first.",
        )
    try:
        # seek=0 requests history from the first event id.
        # In replay, Live Client still only includes EventTime <= current game time.
        event_payload = live.get_event_data(seek=0)
        events_by_key: dict[int | str, dict[str, Any]] = {}

        def _key(event: dict[str, Any]) -> int | str:
            event_id = event.get("EventID", event.get("EventId", event.get("eventId")))
            if event_id is not None:
                return event_id
            return f"{event.get('EventName')}:{event.get('EventTime')}"

        for event in extract_events_from_payload(event_payload):
            events_by_key[_key(event)] = event

        game_time = extract_game_time_sec(event_payload)
        game_id = extract_game_id_from_live_payload(event_payload)
        try:
            all_data = live.get_all_game_data()
            for event in extract_events_from_payload(all_data):
                events_by_key[_key(event)] = event
            if game_time is None:
                game_time = extract_game_time_sec(all_data)
            if game_id is None:
                game_id = extract_game_id_from_live_payload(all_data)
        except Exception as enrich_exc:  # noqa: BLE001 - optional enrichment
            _ = enrich_exc

        events = sorted(
            events_by_key.values(),
            key=lambda e: float(e.get("EventTime", e.get("eventTime") or 0.0)),
        )
        return EventsLiveStatus(
            available=True,
            events=events,
            event_count=len(events),
            game_time_sec=game_time,
            game_id=game_id,
            source="liveclientdata",
        )
    except Exception as exc:  # noqa: BLE001 - surface as status for UI
        return EventsLiveStatus(
            available=False,
            error=f"Live Client request failed: {exc}",
        )


def build_events_document(
    events: list[dict[str, Any]],
    *,
    game_time_sec: float | None = None,
    game_id: str | None = None,
    source: str = "liveclientdata",
    extra_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "source": source,
        "captured_at": utc_now_iso(),
        "event_count": len(events),
    }
    if game_time_sec is not None:
        meta["game_time_sec"] = game_time_sec
    if game_id:
        meta["game_id"] = game_id
    if extra_meta:
        meta.update(extra_meta)
    # Capital-E Events matches Live Client eventdata and auto-split loader.
    return {"Events": events, "meta": meta}


def resolve_export_path(
    *,
    output_path: str | None = None,
    directory: str | None = None,
    filename: str | None = None,
    game_id: str | None = None,
    game_time_sec: float | None = None,
    default_dir: Path | None = None,
) -> Path:
    if output_path:
        return Path(output_path).expanduser().resolve()

    root = Path(directory).expanduser() if directory else (default_dir or Path.cwd())
    base = allocate_game_dir(root, game_id) if game_id else root.resolve()
    if filename:
        name = filename
    elif game_id:
        name = "events.json"
    else:
        name = suggest_events_filename(game_time_sec=game_time_sec)
    if not name.lower().endswith(".json"):
        name = f"{name}.json"
    return (base / name).resolve()


def export_events_json(
    *,
    output_path: str | None = None,
    directory: str | None = None,
    filename: str | None = None,
    events: list[dict[str, Any]] | None = None,
    game_id: str | None = None,
    game_time_sec: float | None = None,
    source: str = "liveclientdata",
    client: LiveClientClient | None = None,
    default_dir: Path | None = None,
) -> EventsExportResult:
    """
    Write events to a JSON file compatible with /api/clips/auto-split.

    Files are stored under ``{directory|default}/{game_id}/`` unless ``output_path``
    is an explicit file path. If ``events`` is omitted, fetch from Live Client.
    """
    resolved_events = list(events) if events is not None else None
    resolved_time = game_time_sec
    resolved_source = source
    resolved_game_id = sanitize_game_id(game_id) if game_id else None

    if resolved_events is None:
        # Prefer an active accumulating capture session when present.
        from pentaklip.events.sessions import get_active_events_session

        active = get_active_events_session()
        if active is not None and active.events:
            # One more poll to catch the latest frame, then export accumulated.
            status = active.poll()
            if not status.available and not active.events:
                raise RuntimeError(status.error or "Live Client unavailable")
            resolved_events = list(active.events)
            if resolved_time is None:
                resolved_time = active.game_time_sec
            if resolved_game_id is None and active.game_id:
                resolved_game_id = sanitize_game_id(active.game_id)
            resolved_source = "liveclientdata+accumulated"
        else:
            status = fetch_live_events(client)
            if not status.available:
                raise RuntimeError(status.error or "Live Client unavailable")
            resolved_events = status.events
            if resolved_time is None:
                resolved_time = status.game_time_sec
            if resolved_game_id is None and status.game_id:
                resolved_game_id = sanitize_game_id(status.game_id)
            resolved_source = status.source

    if resolved_game_id is None and output_path is None:
        raise ValueError("game_id is required to create a game folder (or pass output_path)")

    path = resolve_export_path(
        output_path=output_path,
        directory=directory,
        filename=filename,
        game_id=resolved_game_id,
        game_time_sec=resolved_time,
        default_dir=default_dir,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    # If only output_path was given, still record folder name as game id when possible.
    # Folder may be game_id-1 on collision; persist the actual folder name.
    resolved_game_id = sanitize_game_id(path.parent.name)

    document = build_events_document(
        resolved_events,
        game_time_sec=resolved_time,
        game_id=resolved_game_id,
        source=resolved_source,
    )
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    return EventsExportResult(
        path=str(path),
        event_count=len(resolved_events),
        game_id=resolved_game_id,
        game_dir=str(path.parent),
        game_time_sec=resolved_time,
        source=resolved_source,
    )
