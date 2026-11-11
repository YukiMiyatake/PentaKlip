"""Tests for replay event harvest / accumulation."""

from __future__ import annotations

from pentaklip.events.harvest import EventAccumulator, harvest_events_playthrough

SAMPLE_EARLY = [
    {"EventID": 0, "EventName": "GameStart", "EventTime": 0.0},
    {"EventID": 1, "EventName": "ChampionKill", "EventTime": 120.0, "KillerName": "A"},
]
SAMPLE_LATE = [
    {"EventID": 0, "EventName": "GameStart", "EventTime": 0.0},
    {"EventID": 2, "EventName": "ChampionKill", "EventTime": 1500.0, "KillerName": "B"},
]


class FakeLive:
    def __init__(self) -> None:
        self.payloads = [
            {"Events": SAMPLE_EARLY, "gameData": {"gameTime": 120.0}},
            {"Events": SAMPLE_LATE, "gameData": {"gameTime": 1500.0}},
        ]
        self.i = 0

    def is_available(self) -> bool:
        return True

    def get_event_data(self, *, event_id: int | None = 0) -> dict:
        _ = event_id
        idx = min(self.i, len(self.payloads) - 1)
        self.i += 1
        return self.payloads[idx]

    def get_all_game_data(self) -> dict:
        return {
            "events": {"Events": self.payloads[min(self.i - 1, len(self.payloads) - 1)]["Events"]},
            "gameData": {"gameTime": 1500.0},
            "allPlayers": [{"riotIdGameName": "A", "riotIdTagLine": "JP1", "team": "ORDER"}],
        }


class FakeReplay:
    def __init__(self, *, available: bool = True, length: float = 100.0) -> None:
        self.available = available
        self.length = length
        self.time = 0.0
        self.paused = True
        self.speed = 1.0
        self.calls: list[dict] = []

    def is_available(self) -> bool:
        return self.available

    def get_playback(self) -> dict:
        return {
            "paused": self.paused,
            "seeking": False,
            "time": self.time,
            "speed": self.speed,
            "length": self.length,
        }

    def set_playback(self, payload: dict) -> dict:
        self.calls.append(dict(payload))
        if "time" in payload:
            self.time = float(payload["time"])
        if "paused" in payload:
            self.paused = bool(payload["paused"])
        if "speed" in payload:
            self.speed = float(payload["speed"])
        # Fast-forward simulation: when unpaused, jump near end so harvest loop exits.
        if not self.paused:
            self.time = self.length
        return self.get_playback()


def test_accumulator_merges_across_polls() -> None:
    acc = EventAccumulator()
    acc.ingest({"Events": SAMPLE_EARLY})
    acc.ingest({"Events": SAMPLE_LATE})
    assert acc.events[0]["EventName"] == "GameStart"
    assert len(acc.events) == 3
    assert {e["EventID"] for e in acc.events} == {0, 1, 2}


def test_harvest_playthrough_accumulates(monkeypatch) -> None:
    monkeypatch.setattr("pentaklip.events.harvest.time.sleep", lambda _s: None)
    status, all_data = harvest_events_playthrough(
        live=FakeLive(),  # type: ignore[arg-type]
        replay=FakeReplay(length=100.0),  # type: ignore[arg-type]
        speed=16.0,
        poll_interval_sec=0.0,
    )
    assert status.available is True
    assert status.event_count >= 3
    assert status.source == "liveclientdata+harvest"
    assert all_data is not None


def test_harvest_without_replay_api_warns() -> None:
    status, _ = harvest_events_playthrough(
        live=FakeLive(),  # type: ignore[arg-type]
        replay=FakeReplay(available=False),  # type: ignore[arg-type]
    )
    assert status.available is True
    assert status.warning
    assert "EnableReplayApi" in status.warning
