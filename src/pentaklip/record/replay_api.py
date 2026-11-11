"""Client for the local Replay API (playback / rendering controls)."""

from __future__ import annotations

from typing import Any

import httpx


class ReplayApiClient:
    """
    Thin wrapper around https://127.0.0.1:2999/replay/...

    Requires ``EnableReplayApi=1`` under ``[General]`` in the game ``game.cfg``.
    """

    def __init__(self, base_url: str = "https://127.0.0.1:2999", timeout: float = 2.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def _client(self) -> httpx.Client:
        return httpx.Client(base_url=self._base_url, timeout=self._timeout, verify=False)

    def get_playback(self) -> dict[str, Any]:
        with self._client() as client:
            response = client.get("/replay/playback")
            response.raise_for_status()
            return response.json()

    def set_playback(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._client() as client:
            response = client.post("/replay/playback", json=payload)
            response.raise_for_status()
            return response.json() if response.content else {}

    def get_render(self) -> dict[str, Any]:
        with self._client() as client:
            response = client.get("/replay/render")
            response.raise_for_status()
            return response.json()

    def set_render(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._client() as client:
            response = client.post("/replay/render", json=payload)
            response.raise_for_status()
            return response.json() if response.content else {}

    def seek(self, time_sec: float, *, paused: bool = True) -> dict[str, Any]:
        return self.set_playback({"time": float(time_sec), "paused": paused})

    def is_available(self) -> bool:
        try:
            self.get_playback()
            return True
        except httpx.HTTPError:
            return False
