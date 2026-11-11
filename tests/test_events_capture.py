from pentaklip.events.capture import EventsCaptureSession
from pentaklip.events.sessions import (
    clear_events_sessions,
    create_events_session,
    get_active_events_session,
    pop_events_session,
)


class FakeLiveClient:
    def __init__(self) -> None:
        self.phase = 1

    def is_available(self) -> bool:
        return True

    def _payload(self) -> dict:
        if self.phase == 1:
            return {
                "Events": [
                    {"EventID": 0, "EventName": "GameStart", "EventTime": 0.0},
                    {"EventID": 1, "EventName": "ChampionKill", "EventTime": 120.0},
                ],
                "gameData": {"gameTime": 130.0},
            }
        return {
            "Events": [
                {"EventID": 0, "EventName": "GameStart", "EventTime": 0.0},
                {"EventID": 1, "EventName": "ChampionKill", "EventTime": 120.0},
                {"EventID": 2, "EventName": "ChampionKill", "EventTime": 1800.0},
            ],
            "gameData": {"gameTime": 1810.0},
        }

    def get_event_data(self, *, seek: int | None = 0) -> dict:
        _ = seek
        return self._payload()

    def get_all_game_data(self) -> dict:
        return self._payload()


def test_events_capture_accumulates_across_polls() -> None:
    clear_events_sessions()
    client = FakeLiveClient()
    session = EventsCaptureSession(live_client=client)  # type: ignore[arg-type]
    first = session.poll()
    assert first.available
    assert first.event_count == 2
    client.phase = 2
    second = session.poll()
    assert second.event_count == 3
    assert [e["EventID"] for e in session.events] == [0, 1, 2]


def test_active_session_registry() -> None:
    clear_events_sessions()
    session = create_events_session(live_client=FakeLiveClient())
    assert get_active_events_session() is session
    pop_events_session(session.session_id)
    assert get_active_events_session() is None
