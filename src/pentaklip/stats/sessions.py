"""In-memory capture session registry for the API."""

from __future__ import annotations

from pentaklip.stats.capture import StatsCaptureSession

_SESSIONS: dict[str, StatsCaptureSession] = {}


def create_session(**kwargs: object) -> StatsCaptureSession:
    session = StatsCaptureSession(**kwargs)  # type: ignore[arg-type]
    _SESSIONS[session.session_id] = session
    return session


def get_session(session_id: str) -> StatsCaptureSession | None:
    return _SESSIONS.get(session_id)


def pop_session(session_id: str) -> StatsCaptureSession | None:
    return _SESSIONS.pop(session_id, None)


def clear_sessions() -> None:
    _SESSIONS.clear()
