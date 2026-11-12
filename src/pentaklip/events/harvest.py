"""Harvest full event history from a LoL replay via Replay API + Live Client."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
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
from pentaklip.stats.capture import StatsCaptureSession
from pentaklip.stats.models import ReplayStatsBundle

logger = logging.getLogger(__name__)

# Keep ~one allgamedata sample per N game-seconds (plus first/last).
DEFAULT_STATS_SAMPLE_INTERVAL_SEC = 30.0


def _event_key(event: dict[str, Any]) -> int | str:
    event_id = event.get("EventID", event.get("EventId", event.get("eventId")))
    if event_id is not None:
        return event_id
    return f"{event.get('EventName')}:{event.get('EventTime')}"


@dataclass
class HarvestResult:
    status: EventsLiveStatus
    last_all_game_data: dict[str, Any] | None
    stats_bundle: ReplayStatsBundle | None = None


class EventAccumulator:
    """Merge Live Client event payloads across many polls (dedupe by EventID)."""

    def __init__(
        self,
        *,
        stats_sample_interval_sec: float = DEFAULT_STATS_SAMPLE_INTERVAL_SEC,
    ) -> None:
        self.events_by_key: dict[int | str, dict[str, Any]] = {}
        self.game_time_sec: float | None = None
        self.game_id: str | None = None
        self.poll_count = 0
        self.last_all_game_data: dict[str, Any] | None = None
        self.stats_sample_interval_sec = max(1.0, float(stats_sample_interval_sec))
        self.stats_session = StatsCaptureSession(
            sample_interval_sec=self.stats_sample_interval_sec
        )
        self._last_stats_sample_sec: float | None = None

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


def _maybe_sample_stats(
    acc: EventAccumulator,
    all_data: dict[str, Any],
    *,
    force: bool = False,
) -> None:
    """Append allgamedata into the stats session on a game-time cadence."""
    t = extract_game_time_sec(all_data)
    if t is None:
        t = float(acc.game_time_sec or 0.0)
    if (
        force
        or acc._last_stats_sample_sec is None
        or (t - acc._last_stats_sample_sec) >= acc.stats_sample_interval_sec
    ):
        acc.stats_session.ingest_all_game_data(all_data)
        acc._last_stats_sample_sec = t


def _poll_live(
    acc: EventAccumulator,
    live: LiveClientClient,
    *,
    force_stats_sample: bool = False,
) -> None:
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
        _maybe_sample_stats(acc, all_data, force=force_stats_sample)
    except Exception:  # noqa: BLE001
        return


def _finalize_stats_bundle(
    acc: EventAccumulator,
    *,
    game_id: str | None = None,
    capture_note: str,
) -> ReplayStatsBundle | None:
    if acc.last_all_game_data is not None:
        _maybe_sample_stats(acc, acc.last_all_game_data, force=True)
    if not acc.stats_session.bundle.snapshots:
        return None
    if game_id:
        acc.stats_session.bundle.original_match_id = game_id
    elif acc.game_id:
        acc.stats_session.bundle.original_match_id = acc.game_id
    bundle = acc.stats_session.finalize()
    # Prefer full harvested event list over per-snapshot event fragments.
    bundle.events = list(acc.events)
    bundle.meta["capture_mode"] = "harvest_multipoll"
    bundle.meta["note"] = capture_note
    bundle.meta["event_count"] = len(bundle.events)
    return bundle


def harvest_events_playthrough(
    *,
    live: LiveClientClient | None = None,
    replay: ReplayApiClient | None = None,
    speed: float = 16.0,
    poll_interval_sec: float = 0.35,
    end_padding_sec: float = 1.0,
    stats_sample_interval_sec: float = DEFAULT_STATS_SAMPLE_INTERVAL_SEC,
) -> HarvestResult:
    """
    Seek to the start of the open replay, play at high speed, and accumulate
    Live Client events until near the end.

    Also samples allgamedata on a game-time cadence into a stats bundle so
    CSD15 / LVLD15 / time-series can be derived after export.

    Jumping only to late game leaves early kills out of Live Client's buffer;
    continuous forward playback is what fills EventTime history.
    """
    live_client = live or LiveClientClient()
    replay_client = replay or ReplayApiClient()
    acc = EventAccumulator(stats_sample_interval_sec=stats_sample_interval_sec)
    acc._player_count = None  # type: ignore[attr-defined]

    if not live_client.is_available():
        return HarvestResult(
            status=EventsLiveStatus(
                available=False,
                error="Live Client is not available. Start a LoL replay first.",
            ),
            last_all_game_data=None,
            stats_bundle=None,
        )
    if not replay_client.is_available():
        # Fall back to one snapshot so the UI still works, with a clear warning.
        try:
            _poll_live(acc, live_client, force_stats_sample=True)
        except Exception as exc:  # noqa: BLE001
            return HarvestResult(
                status=EventsLiveStatus(
                    available=False,
                    error=f"Live Client request failed: {exc}",
                ),
                last_all_game_data=None,
                stats_bundle=None,
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
        return HarvestResult(
            status=status,
            last_all_game_data=acc.last_all_game_data,
            stats_bundle=_finalize_stats_bundle(
                acc,
                capture_note="replay API unavailable; single Live Client sample",
            ),
        )

    playback = replay_client.get_playback()
    length = float(playback.get("length") or 0.0)
    if length <= 0:
        _poll_live(acc, live_client, force_stats_sample=True)
        status = acc.to_status(player_count=getattr(acc, "_player_count", None))
        status.warning = "Replay length was 0; captured a single Live Client snapshot."
        return HarvestResult(
            status=status,
            last_all_game_data=acc.last_all_game_data,
            stats_bundle=_finalize_stats_bundle(
                acc, capture_note="replay length 0; single sample"
            ),
        )

    original = {
        "paused": bool(playback.get("paused", True)),
        "speed": float(playback.get("speed") or 1.0),
        "time": float(playback.get("time") or 0.0),
    }

    try:
        replay_client.set_playback({"time": 0.0, "paused": True, "speed": float(speed)})
        _wait_seek_settled(replay_client)
        _poll_live(acc, live_client, force_stats_sample=True)

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
        _poll_live(acc, live_client, force_stats_sample=True)
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
            logger.debug(
                "failed to restore replay playback after harvest", exc_info=True
            )

    meta_note = (
        f"harvest playthrough @ {speed:g}x; polls={acc.poll_count}; "
        f"stats_samples={len(acc.stats_session.bundle.snapshots)}; "
        f"sample_interval={acc.stats_sample_interval_sec:g}s; "
        f"length={length:.0f}s; captured_at={utc_now_iso()}"
    )
    status = acc.to_status(player_count=getattr(acc, "_player_count", None))
    return HarvestResult(
        status=status,
        last_all_game_data=acc.last_all_game_data,
        stats_bundle=_finalize_stats_bundle(acc, capture_note=meta_note),
    )
