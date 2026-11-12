"""Fetch Live Client events and write clip-compatible JSON files."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from pentaklip.paths import (
    EVENT_DIR_NAME,
    OutputLayout,
    extract_game_id_from_live_payload,
    sanitize_game_id,
    unique_file_path,
    with_game_id_prefix,
)
from pentaklip.record.live_client import LiveClientClient
from pentaklip.stats.aggregate import aggregate_replay
from pentaklip.stats.capture import snapshot_from_all_game_data
from pentaklip.stats.export import export_aggregated_stats, export_replay_stats
from pentaklip.stats.models import ReplayStatsBundle


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class EventsLiveStatus(BaseModel):
    available: bool
    events: list[dict[str, Any]] = Field(default_factory=list)
    event_count: int = 0
    game_time_sec: float | None = None
    game_id: str | None = None
    player_count: int | None = None
    source: str = "liveclientdata"
    error: str | None = None
    warning: str | None = None


class EventsExportResult(BaseModel):
    path: str
    event_count: int
    game_id: str
    game_dir: str
    game_time_sec: float | None = None
    source: str = "liveclientdata"
    stats_bundle_path: str | None = None
    stats_aggregated_path: str | None = None
    player_count: int | None = None


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


def fetch_live_events(
    client: LiveClientClient | None = None,
) -> tuple[EventsLiveStatus, dict[str, Any] | None]:
    """
    Pull current match events (and allgamedata when available).

    Returns ``(status, all_game_data_or_none)``. Callers that only need the
    status can ignore the second value.
    """
    live = client or LiveClientClient()
    if not live.is_available():
        return (
            EventsLiveStatus(
                available=False,
                error="Live Client is not available. Start a LoL replay or game first.",
            ),
            None,
        )
    try:
        # eventID=0 requests history from the first event id.
        # In replay, Live Client still only includes EventTime <= current game time.
        event_payload = live.get_event_data(event_id=0)
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
        all_data: dict[str, Any] | None = None
        player_count: int | None = None
        try:
            all_data = live.get_all_game_data()
            for event in extract_events_from_payload(all_data):
                events_by_key[_key(event)] = event
            if game_time is None:
                game_time = extract_game_time_sec(all_data)
            if game_id is None:
                game_id = extract_game_id_from_live_payload(all_data)
            players = all_data.get("allPlayers")
            if isinstance(players, list):
                player_count = len(players)
        except Exception as enrich_exc:  # noqa: BLE001 - optional enrichment
            _ = enrich_exc

        events = sorted(
            events_by_key.values(),
            key=lambda e: float(e.get("EventTime", e.get("eventTime") or 0.0)),
        )
        return (
            EventsLiveStatus(
                available=True,
                events=events,
                event_count=len(events),
                game_time_sec=game_time,
                game_id=game_id,
                player_count=player_count,
                source="liveclientdata",
            ),
            all_data,
        )
    except Exception as exc:  # noqa: BLE001 - surface as status for UI
        return (
            EventsLiveStatus(
                available=False,
                error=f"Live Client request failed: {exc}",
            ),
            None,
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
    layout = OutputLayout(root)
    target_dir = layout.event_dir
    if filename:
        name = filename
    elif game_id:
        name = "events.json"
    else:
        name = suggest_events_filename(game_time_sec=game_time_sec)
    if not name.lower().endswith(".json"):
        name = f"{name}.json"
    if game_id:
        name = with_game_id_prefix(game_id, name)
    return unique_file_path((target_dir / name).resolve())


def build_stats_bundle_from_all_game_data(
    all_game_data: dict[str, Any],
    *,
    events: list[dict[str, Any]] | None = None,
    game_id: str | None = None,
) -> ReplayStatsBundle:
    """Build a one-shot stats bundle from Live Client allgamedata (+ event list)."""
    snap = snapshot_from_all_game_data(all_game_data)
    resolved_events = list(events) if events is not None else list(snap.events)
    return ReplayStatsBundle(
        original_match_id=game_id,
        snapshots=[snap],
        events=resolved_events,
        meta={
            "capture_mode": "events_export_oneshot",
            "note": (
                "Single allgamedata snapshot at event export time. "
                "Time-series charts need multi-poll stats capture during playback."
            ),
            "snapshot_count": 1,
            "event_count": len(resolved_events),
            "game_time_last_sec": snap.game_time_sec,
        },
    )


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
    include_stats: bool = True,
    all_game_data: dict[str, Any] | None = None,
    harvest: bool = True,
    harvest_speed: float = 16.0,
) -> EventsExportResult:
    """
    Write events to a JSON file compatible with /api/clips/auto-split.

    Default layout (when ``directory``/``default_dir`` is the output base):
    ``{base}/Event/{game_id}_events.json`` and stats under ``{base}/stats/``.
    Pass ``output_path`` for an explicit file path. If ``events`` is omitted,
    fetch from Live Client.

    When ``include_stats`` is True and allgamedata is available, also write
    ``{game_id}_stats_bundle.json`` and ``{game_id}_stats_aggregated.json``.
    """
    resolved_events = list(events) if events is not None else None
    resolved_time = game_time_sec
    resolved_source = source
    resolved_game_id = sanitize_game_id(game_id) if game_id else None
    resolved_all_data = all_game_data
    player_count: int | None = None

    if resolved_events is None or (include_stats and resolved_all_data is None):
        if harvest and resolved_events is None:
            from pentaklip.events.harvest import harvest_events_playthrough

            status, fetched_all = harvest_events_playthrough(
                live=client,
                speed=harvest_speed,
            )
        else:
            status, fetched_all = fetch_live_events(client)
        if resolved_events is None:
            if not status.available:
                raise RuntimeError(status.error or "Live Client unavailable")
            resolved_events = status.events
            if resolved_time is None:
                resolved_time = status.game_time_sec
            if resolved_game_id is None and status.game_id:
                resolved_game_id = sanitize_game_id(status.game_id)
            resolved_source = status.source
            player_count = status.player_count
        elif status.available:
            if resolved_time is None:
                resolved_time = status.game_time_sec
            if player_count is None:
                player_count = status.player_count
        if resolved_all_data is None:
            resolved_all_data = fetched_all

    assert resolved_events is not None

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

    # Prefer explicit game_id; fall back to filename prefix or legacy per-game folder name.
    if resolved_game_id is None:
        stem = path.stem
        if "_events" in stem.lower():
            maybe = stem[: stem.lower().rfind("_events")]
            if maybe:
                resolved_game_id = sanitize_game_id(maybe)
        if resolved_game_id is None and path.parent.name != EVENT_DIR_NAME:
            resolved_game_id = sanitize_game_id(path.parent.name)

    assert resolved_game_id is not None

    document = build_events_document(
        resolved_events,
        game_time_sec=resolved_time,
        game_id=resolved_game_id,
        source=resolved_source,
    )
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")

    stats_bundle_path: str | None = None
    stats_aggregated_path: str | None = None
    if include_stats and resolved_all_data is not None:
        bundle = build_stats_bundle_from_all_game_data(
            resolved_all_data,
            events=resolved_events,
            game_id=resolved_game_id,
        )
        if player_count is None:
            player_count = len(bundle.snapshots[0].players) if bundle.snapshots else None
        # Stats live under {base}/stats when Event/ is used; else beside the events file.
        if path.parent.name == EVENT_DIR_NAME:
            stats_dir = path.parent.parent / "stats"
        else:
            stats_dir = path.parent
        stats_dir.mkdir(parents=True, exist_ok=True)
        stats_prefix = with_game_id_prefix(resolved_game_id, "stats_bundle.json")
        agg_name = with_game_id_prefix(resolved_game_id, "stats_aggregated.json")
        bundle_path = export_replay_stats(
            bundle, unique_file_path(stats_dir / stats_prefix)
        )
        aggregated = aggregate_replay(bundle)
        aggregated_path = export_aggregated_stats(
            aggregated, unique_file_path(stats_dir / agg_name)
        )
        stats_bundle_path = str(bundle_path)
        stats_aggregated_path = str(aggregated_path)

    return EventsExportResult(
        path=str(path),
        event_count=len(resolved_events),
        game_id=resolved_game_id,
        game_dir=str(path.parent),
        game_time_sec=resolved_time,
        source=resolved_source,
        stats_bundle_path=stats_bundle_path,
        stats_aggregated_path=stats_aggregated_path,
        player_count=player_count,
    )
