"""Accumulate Live Client events across a replay/game session."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from pentaklip.events.service import (
    EventsLiveStatus,
    extract_events_from_payload,
    extract_game_time_sec,
    utc_now_iso,
)
from pentaklip.paths import extract_game_id_from_live_payload
from pentaklip.record.live_client import LiveClientClient


def _event_key(event: dict[str, Any]) -> int | str:
    event_id = event.get("EventID", event.get("EventId", event.get("eventId")))
    if event_id is not None:
        return event_id
    return f"{event.get('EventName')}:{event.get('EventTime')}"


class EventsCaptureSession:
    """
    Poll Live Client and keep a growing event list.

    Live Client returns events with EventTime <= current game time. Skipping to
    late-game without capturing earlier leaves a short JSON — this session fixes
    that when the user starts capture near the beginning and keeps polling.
    """

    def __init__(self, *, live_client: LiveClientClient | None = None) -> None:
        self.session_id = str(uuid4())
        self.live_client = live_client or LiveClientClient()
        self.events: list[dict[str, Any]] = []
        self._event_ids: set[int | str] = set()
        self.game_time_sec: float | None = None
        self.game_id: str | None = None
        self.started_at = utc_now_iso()
        self.last_poll_at: str | None = None
        self.poll_count = 0

    def ingest_payload(self, data: dict[str, Any]) -> int:
        """Merge events from one payload; return number of newly added events."""
        added = 0
        for event in extract_events_from_payload(data):
            key = _event_key(event)
            if key in self._event_ids:
                continue
            self._event_ids.add(key)
            self.events.append(event)
            added += 1
        game_time = extract_game_time_sec(data)
        if game_time is not None:
            self.game_time_sec = game_time
        game_id = extract_game_id_from_live_payload(data)
        if game_id:
            self.game_id = game_id
        return added

    def poll(self) -> EventsLiveStatus:
        if not self.live_client.is_available():
            return EventsLiveStatus(
                available=False,
                events=list(self.events),
                event_count=len(self.events),
                game_time_sec=self.game_time_sec,
                game_id=self.game_id,
                error="Live Client is not available. Start a LoL replay or game first.",
            )
        try:
            # seek=0: request history from the first event id.
            event_payload = self.live_client.get_event_data(seek=0)
            self.ingest_payload(event_payload)
            try:
                all_data = self.live_client.get_all_game_data()
                self.ingest_payload(all_data)
            except Exception as enrich_exc:  # noqa: BLE001
                _ = enrich_exc
            self.poll_count += 1
            self.last_poll_at = utc_now_iso()
            # Keep chronological order for readability.
            self.events.sort(
                key=lambda e: float(e.get("EventTime", e.get("eventTime") or 0.0))
            )
            return EventsLiveStatus(
                available=True,
                events=list(self.events),
                event_count=len(self.events),
                game_time_sec=self.game_time_sec,
                game_id=self.game_id,
                source="liveclientdata+accumulated",
            )
        except Exception as exc:  # noqa: BLE001
            return EventsLiveStatus(
                available=False,
                events=list(self.events),
                event_count=len(self.events),
                game_time_sec=self.game_time_sec,
                game_id=self.game_id,
                error=f"Live Client request failed: {exc}",
            )

    def status(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "event_count": len(self.events),
            "game_time_sec": self.game_time_sec,
            "game_id": self.game_id,
            "started_at": self.started_at,
            "last_poll_at": self.last_poll_at,
            "poll_count": self.poll_count,
        }
