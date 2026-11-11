"""Harvest full event history from a LoL replay via Replay API + Live Client."""

from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)
from typing import Any

from pentaklip.events.service import (
    EventsLiveStatus,
    extract_events_from_payload,
    extract_game_time_sec,
    utc_now_iso,
)
from pentaklip.paths import extract_game_id_from_live_payload
from pentaklip.record.live_client import LiveClientClient
from pentaklip.record.replay_api import ReplayApiClient


def _event_key(event: dict[str, Any]) -> int | str:
    event_id = event.get("EventID", event.get("EventId", event.get("eventId")))
    if event_id is not None:
        return event_id
    return f"{event.get('EventName')}:{event.get('EventTime')}"


class EventAccumulator:
    """Merge Live Client event payloads across many polls (dedupe by EventID)."""

    def __init__(self) -> None:
        self.events_by_key: dict[int | str, dict[str, Any]] = {}
        self.game_time_sec: float | None = None
        self.game_id: str | None = None
        self.poll_count = 0
        self.last_all_game_data: dict[str, Any] | None = None

    def ingest(self, data: dict[str, Any]) -> int:
        added = 0
        for event in extract_events_from_payload(data):
            key = _event_key(event)
            if key in self.events_by_key:
                continue
            self.events_by_key[key] = event
            added += 1
        game_time = extract_game_time_sec(data)
        if game_time is not None:
            self.game_time_sec = game_time
        game_id = extract_game_id_from_live_payload(data)
        if game_id:
            self.game_id = game_id
        return added

    @property
    def events(self) -> list[dict[str, Any]]:
        return sorted(
            self.events_by_key.values(),
            key=lambda e: float(e.get("EventTime", e.get("eventTime") or 0.0)),
        )

    def to_status(
        self,
        *,
        available: bool = True,
        source: str = "liveclientdata+harvest",
        error: str | None = None,
        player_count: int | None = None,
    ) -> EventsLiveStatus:
        events = self.events
        return EventsLiveStatus(
            available=available,
            events=events,
            event_count=len(events),
            game_time_sec=self.game_time_sec,
            game_id=self.game_id,
            player_count=player_count,
            source=source,
            error=error,
        )


def _wait_seek_settled(
    replay: ReplayApiClient,
    *,
    timeout_sec: float = 8.0,
    poll_sec: float = 0.15,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_sec
    last = replay.get_playback()
    while time.monotonic() < deadline:
        if not bool(last.get("seeking")):
            return last
        time.sleep(poll_sec)
        last = replay.get_playback()
    return last


def _poll_live(acc: EventAccumulator, live: LiveClientClient) -> None:
    acc.poll_count += 1
    try:
        acc.ingest(live.get_event_data(event_id=0))
    except Exception:  # noqa: BLE001 - keep harvesting on transient errors
        return
    try:
        all_data = live.get_all_game_data()
        acc.ingest(all_data)
        acc.last_all_game_data = all_data
        players = all_data.get("allPlayers")
        if isinstance(players, list):
            acc._player_count = len(players)  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        return


def harvest_events_playthrough(
    *,
    live: LiveClientClient | None = None,
    replay: ReplayApiClient | None = None,
    speed: float = 16.0,
    poll_interval_sec: float = 0.35,
    end_padding_sec: float = 1.0,
) -> tuple[EventsLiveStatus, dict[str, Any] | None]:
    """
    Seek to the start of the open replay, play at high speed, and accumulate
    Live Client events until near the end.

    Jumping only to late game leaves early kills out of Live Client's buffer;
    continuous forward playback is what fills EventTime history.
    """
    live_client = live or LiveClientClient()
    replay_client = replay or ReplayApiClient()
    acc = EventAccumulator()
    acc._player_count = None  # type: ignore[attr-defined]

    if not live_client.is_available():
        return (
            EventsLiveStatus(
                available=False,
                error="Live Client is not available. Start a LoL replay first.",
            ),
            None,
        )
    if not replay_client.is_available():
        # Fall back to one snapshot so the UI still works, with a clear warning.
        try:
            _poll_live(acc, live_client)
        except Exception as exc:  # noqa: BLE001
            return (
                EventsLiveStatus(
                    available=False,
                    error=f"Live Client request failed: {exc}",
                ),
                None,
            )
        status = acc.to_status(
            source="liveclientdata",
            player_count=getattr(acc, "_player_count", None),
        )
        status.warning = (
            "Replay API が無効です（game.cfg の [General] に EnableReplayApi=1）。"
            " 終端 Seek だけの取得だと序盤イベントが欠けることがあります。"
            f" 今回は現在時刻までの {len(acc.events)} 件のみ取得しました。"
        )
        return status, acc.last_all_game_data

    playback = replay_client.get_playback()
    length = float(playback.get("length") or 0.0)
    if length <= 0:
        _poll_live(acc, live_client)
        status = acc.to_status(player_count=getattr(acc, "_player_count", None))
        status.warning = "Replay length was 0; captured a single Live Client snapshot."
        return status, acc.last_all_game_data

    original = {
        "paused": bool(playback.get("paused", True)),
        "speed": float(playback.get("speed") or 1.0),
        "time": float(playback.get("time") or 0.0),
    }

    try:
        replay_client.set_playback({"time": 0.0, "paused": True, "speed": float(speed)})
        _wait_seek_settled(replay_client)
        _poll_live(acc, live_client)

        replay_client.set_playback({"paused": False, "speed": float(speed)})
        # Wall-clock budget: game_length / speed + small buffer.
        deadline = time.monotonic() + (length / max(speed, 0.1)) + 15.0
        while time.monotonic() < deadline:
            time.sleep(poll_interval_sec)
            pb = replay_client.get_playback()
            t = float(pb.get("time") or 0.0)
            if t > (acc.game_time_sec or 0):
                acc.game_time_sec = t
            _poll_live(acc, live_client)
            if t >= length - end_padding_sec:
                break
            # Safety: if playback stalled while paused unexpectedly, unpause again.
            if bool(pb.get("paused")) and t < length - end_padding_sec:
                replay_client.set_playback({"paused": False, "speed": float(speed)})

        replay_client.set_playback({"time": length, "paused": True, "speed": float(speed)})
        _wait_seek_settled(replay_client)
        _poll_live(acc, live_client)
    finally:
        # Leave the user at the end, paused, rather than restoring mid-fight scrub.
        try:
            replay_client.set_playback(
                {
                    "time": length,
                    "paused": True,
                    "speed": original["speed"] if original["speed"] > 0 else 1.0,
                }
            )
        except Exception:
            logger.debug('failed to restore replay playback after harvest', exc_info=True)

    meta_note = (
        f"harvest playthrough @ {speed:g}x; polls={acc.poll_count}; "
        f"length={length:.0f}s; captured_at={utc_now_iso()}"
    )
    status = acc.to_status(player_count=getattr(acc, "_player_count", None))
    # Stash note in error only when partial; otherwise keep error None.
    _ = meta_note
    return status, acc.last_all_game_data
