"""In-memory event capture session registry."""

from __future__ import annotations

from pentaklip.events.capture import EventsCaptureSession

_SESSIONS: dict[str, EventsCaptureSession] = {}
_ACTIVE_ID: str | None = None


def create_events_session(**kwargs: object) -> EventsCaptureSession:
    global _ACTIVE_ID
    session = EventsCaptureSession(**kwargs)  # type: ignore[arg-type]
    _SESSIONS[session.session_id] = session
    _ACTIVE_ID = session.session_id
    return session


def get_events_session(session_id: str) -> EventsCaptureSession | None:
    return _SESSIONS.get(session_id)


def get_active_events_session() -> EventsCaptureSession | None:
    if _ACTIVE_ID is None:
        return None
    return _SESSIONS.get(_ACTIVE_ID)


def pop_events_session(session_id: str) -> EventsCaptureSession | None:
    global _ACTIVE_ID
    session = _SESSIONS.pop(session_id, None)
    if _ACTIVE_ID == session_id:
        _ACTIVE_ID = None
    return session


def clear_events_sessions() -> None:
    global _ACTIVE_ID
    _SESSIONS.clear()
    _ACTIVE_ID = None
