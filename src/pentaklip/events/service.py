"""Fetch Live Client events and write clip-compatible JSON files."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from pentaklip.record.live_client import LiveClientClient


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class EventsLiveStatus(BaseModel):
    available: bool
    events: list[dict[str, Any]] = Field(default_factory=list)
    event_count: int = 0
    game_time_sec: float | None = None
    source: str = "liveclientdata"
    error: str | None = None


class EventsExportResult(BaseModel):
    path: str
    event_count: int
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
        # Prefer eventdata (lighter); fall back to allgamedata for game time.
        event_payload = live.get_event_data()
        events = extract_events_from_payload(event_payload)
        game_time = extract_game_time_sec(event_payload)
        if game_time is None:
            try:
                all_data = live.get_all_game_data()
                game_time = extract_game_time_sec(all_data)
                if not events:
                    events = extract_events_from_payload(all_data)
            except Exception as enrich_exc:  # noqa: BLE001 - optional enrichment
                _ = enrich_exc
        return EventsLiveStatus(
            available=True,
            events=events,
            event_count=len(events),
            game_time_sec=game_time,
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
    if extra_meta:
        meta.update(extra_meta)
    # Capital-E Events matches Live Client eventdata and auto-split loader.
    return {"Events": events, "meta": meta}


def resolve_export_path(
    *,
    output_path: str | None = None,
    directory: str | None = None,
    filename: str | None = None,
    game_time_sec: float | None = None,
    default_dir: Path | None = None,
) -> Path:
    if output_path:
        path = Path(output_path).expanduser()
    else:
        base = Path(directory).expanduser() if directory else (default_dir or Path.cwd())
        name = filename or suggest_events_filename(game_time_sec=game_time_sec)
        if not name.lower().endswith(".json"):
            name = f"{name}.json"
        path = base / name
    return path.resolve()


def export_events_json(
    *,
    output_path: str | None = None,
    directory: str | None = None,
    filename: str | None = None,
    events: list[dict[str, Any]] | None = None,
    game_time_sec: float | None = None,
    source: str = "liveclientdata",
    client: LiveClientClient | None = None,
    default_dir: Path | None = None,
) -> EventsExportResult:
    """
    Write events to a JSON file compatible with /api/clips/auto-split.

    If ``events`` is omitted, fetch from Live Client.
    """
    resolved_events = list(events) if events is not None else None
    resolved_time = game_time_sec
    resolved_source = source

    if resolved_events is None:
        status = fetch_live_events(client)
        if not status.available:
            raise RuntimeError(status.error or "Live Client unavailable")
        resolved_events = status.events
        if resolved_time is None:
            resolved_time = status.game_time_sec
        resolved_source = status.source

    path = resolve_export_path(
        output_path=output_path,
        directory=directory,
        filename=filename,
        game_time_sec=resolved_time,
        default_dir=default_dir,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    document = build_events_document(
        resolved_events,
        game_time_sec=resolved_time,
        source=resolved_source,
    )
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    return EventsExportResult(
        path=str(path),
        event_count=len(resolved_events),
        game_time_sec=resolved_time,
        source=resolved_source,
    )
