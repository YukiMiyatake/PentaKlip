"""Capture as much Live Client data as possible during replay playback."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from pentaklip.record.live_client import LiveClientClient
from pentaklip.stats.catalog import normalize_position
from pentaklip.stats.identity import extract_player_identity
from pentaklip.stats.models import GameSnapshot, PlayerSnapshot, ReplayStatsBundle, utc_now_iso


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def snapshot_from_all_game_data(data: dict[str, Any]) -> GameSnapshot:
    """Normalize one allgamedata payload into a rich snapshot (keeps raw)."""
    game_data = _as_dict(data.get("gameData"))
    game_time = float(game_data.get("gameTime") or data.get("gameTime") or 0.0)
    events_obj = data.get("events")
    if isinstance(events_obj, dict):
        events = _as_list(events_obj.get("Events") or events_obj.get("events"))
    else:
        events = _as_list(events_obj)

    players: list[PlayerSnapshot] = []
    for raw_player in _as_list(data.get("allPlayers")):
        if not isinstance(raw_player, dict):
            continue
        identity = extract_player_identity(raw_player)
        players.append(
            PlayerSnapshot(
                identity=identity,
                position=normalize_position(
                    raw_player.get("position") or raw_player.get("Position")
                ),
                champion_name=raw_player.get("championName"),
                team=raw_player.get("team"),
                level=raw_player.get("level"),
                is_dead=raw_player.get("isDead"),
                respawn_timer=raw_player.get("respawnTimer"),
                scores=_as_dict(raw_player.get("scores")),
                items=[i for i in _as_list(raw_player.get("items")) if isinstance(i, dict)],
                runes=_as_dict(raw_player.get("runes")),
                summoner_spells=_as_dict(raw_player.get("summonerSpells")),
                raw=dict(raw_player),
            )
        )

    return GameSnapshot(
        game_time_sec=game_time,
        game_data=game_data,
        active_player=_as_dict(data.get("activePlayer")),
        players=players,
        events=[e for e in events if isinstance(e, dict)],
        raw_all_game_data=data,
    )


class StatsCaptureSession:
    """In-memory capture session; poll Live Client or ingest payloads."""

    def __init__(
        self,
        *,
        original_match_id: str | None = None,
        local_replay_id: str | None = None,
        source_filename: str | None = None,
        sample_interval_sec: float = 5.0,
        live_client: LiveClientClient | None = None,
    ) -> None:
        self.session_id = str(uuid4())
        self.sample_interval_sec = sample_interval_sec
        self.live_client = live_client or LiveClientClient()
        self.bundle = ReplayStatsBundle(
            original_match_id=original_match_id,
            local_replay_id=local_replay_id,
            source_filename=source_filename,
            captured_at=utc_now_iso(),
            sample_interval_sec=sample_interval_sec,
        )
        self._event_ids: set[int | str] = set()

    def ingest_all_game_data(self, data: dict[str, Any]) -> GameSnapshot:
        snap = snapshot_from_all_game_data(data)
        self.bundle.snapshots.append(snap)
        for event in snap.events:
            event_id = event.get("EventID", event.get("EventId", event.get("eventId")))
            key: int | str
            if event_id is None:
                key = f"{event.get('EventName')}:{event.get('EventTime')}"
            else:
                key = event_id
            if key in self._event_ids:
                continue
            self._event_ids.add(key)
            self.bundle.events.append(event)
        return snap

    def poll_live_client(self) -> GameSnapshot:
        data = self.live_client.get_all_game_data()
        return self.ingest_all_game_data(data)

    def finalize(self) -> ReplayStatsBundle:
        self.bundle.meta["snapshot_count"] = len(self.bundle.snapshots)
        self.bundle.meta["event_count"] = len(self.bundle.events)
        if self.bundle.snapshots:
            self.bundle.meta["game_time_last_sec"] = self.bundle.snapshots[-1].game_time_sec
        return self.bundle
