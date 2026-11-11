"""Tests for Live Client event extraction and JSON export."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pentaklip.api.app import app
from pentaklip.events.service import (
    build_events_document,
    export_events_json,
    extract_events_from_payload,
    extract_game_time_sec,
    fetch_live_events,
)

SAMPLE_EVENTS = [
    {"EventID": 0, "EventName": "GameStart", "EventTime": 0.0},
    {
        "EventID": 1,
        "EventName": "ChampionKill",
        "EventTime": 120.5,
        "KillerName": "MidLaner",
        "VictimName": "EnemyMid",
    },
    {"EventID": 2, "EventName": "DragonKill", "EventTime": 300.0},
]


class FakeLiveClient:
    def __init__(self, *, available: bool = True, with_game_time: bool = True) -> None:
        self.available = available
        self.with_game_time = with_game_time

    def is_available(self) -> bool:
        return self.available

    def get_event_data(self) -> dict:
        return {"Events": SAMPLE_EVENTS}

    def get_all_game_data(self) -> dict:
        payload: dict = {
            "events": {"Events": SAMPLE_EVENTS},
        }
        if self.with_game_time:
            payload["gameData"] = {"gameTime": 310.0}
        return payload


def test_extract_events_shapes() -> None:
    assert len(extract_events_from_payload({"Events": SAMPLE_EVENTS})) == 3
    assert len(extract_events_from_payload({"events": {"Events": SAMPLE_EVENTS}})) == 3
    assert extract_game_time_sec({"gameData": {"gameTime": 12.5}}) == 12.5


def test_build_and_export_events_json(tmp_path: Path) -> None:
    doc = build_events_document(SAMPLE_EVENTS, game_time_sec=310.0, game_id="JP1-1")
    assert "Events" in doc
    assert doc["meta"]["event_count"] == 3
    assert doc["meta"]["game_id"] == "JP1-1"

    result = export_events_json(
        directory=str(tmp_path),
        filename="events.json",
        events=SAMPLE_EVENTS,
        game_id="JP1-123456",
        game_time_sec=310.0,
    )
    path = Path(result.path)
    assert path == (tmp_path / "JP1-123456" / "events.json").resolve()
    assert path.is_file()
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["Events"][1]["EventName"] == "ChampionKill"
    assert loaded["meta"]["game_id"] == "JP1-123456"
    assert result.event_count == 3
    assert result.game_id == "JP1-123456"


def test_fetch_live_events_unavailable() -> None:
    status = fetch_live_events(FakeLiveClient(available=False))  # type: ignore[arg-type]
    assert status.available is False
    assert status.event_count == 0


def test_fetch_live_events_ok() -> None:
    status = fetch_live_events(FakeLiveClient())  # type: ignore[arg-type]
    assert status.available is True
    assert status.event_count == 3
    assert status.game_time_sec == 310.0


def test_api_export_with_provided_events(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PENTAKLIP_DATA_DIR", str(tmp_path / "data"))
    client = TestClient(app)
    response = client.post(
        "/api/events/export",
        json={
            "directory": str(tmp_path / "matches"),
            "game_id": "KR-999",
            "events": SAMPLE_EVENTS,
            "game_time_sec": 200.0,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["event_count"] == 3
    assert body["game_id"] == "KR-999"
    assert Path(body["path"]) == (tmp_path / "matches" / "KR-999" / "events.json").resolve()
    assert Path(body["path"]).is_file()


def test_api_live_when_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    from pentaklip.events.service import EventsLiveStatus

    monkeypatch.setattr(
        "pentaklip.api.app.fetch_live_events",
        lambda: EventsLiveStatus(available=False, error="offline"),
    )
    client = TestClient(app)
    response = client.get("/api/events/live")
    assert response.status_code == 200
    assert response.json()["available"] is False
