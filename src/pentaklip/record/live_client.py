"""Client for the local Live Client Data API."""

from __future__ import annotations

from typing import Any

import httpx


class LiveClientClient:
    """Thin wrapper around https://127.0.0.1:2999/liveclientdata/..."""

    def __init__(self, base_url: str = "https://127.0.0.1:2999", timeout: float = 2.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def _client(self) -> httpx.Client:
        # Local game cert is self-signed; verify=False is required for 2999.
        return httpx.Client(base_url=self._base_url, timeout=self._timeout, verify=False)

    def get_all_game_data(self) -> dict[str, Any]:
        with self._client() as client:
            response = client.get("/liveclientdata/allgamedata")
            response.raise_for_status()
            return response.json()

    def get_event_data(self, *, event_id: int | None = 0) -> dict[str, Any]:
        """
        Fetch events from Live Client.

        ``event_id`` maps to the Riot query param ``eventID`` (next EventID you
        expect). ``0`` returns history from the start; omit with ``None`` for
        the default payload. In replay, only EventTime <= current game time
        is included.
        """
        params: dict[str, int] = {}
        if event_id is not None:
            params["eventID"] = event_id
        with self._client() as client:
            response = client.get("/liveclientdata/eventdata", params=params or None)
            response.raise_for_status()
            return response.json()

    def is_available(self) -> bool:
        """True when Live Client responds (works in replay/spectator too)."""
        try:
            with self._client() as client:
                # gamestats works without an active player; activeplayername often 404s in spectator.
                response = client.get("/liveclientdata/gamestats")
                return response.status_code == 200
        except httpx.HTTPError:
            return False
