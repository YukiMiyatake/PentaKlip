"""Heuristic highlight detection (MVP: kill-centric)."""

from __future__ import annotations

from typing import Any

from pentaklip.detect.models import HighlightCandidate, HighlightKind


def detect_from_events(
    events: list[dict[str, Any]],
    *,
    padding_before_sec: float = 10.0,
    padding_after_sec: float = 10.0,
) -> list[HighlightCandidate]:
    """
    Build highlight candidates from Live Client-style event dicts.

    Expected kill-like shape (subset):
      {"EventName": "ChampionKill", "EventTime": 123.4, ...}
    """
    candidates: list[HighlightCandidate] = []
    for event in events:
        name = str(event.get("EventName") or event.get("eventName") or "")
        time_raw = event.get("EventTime", event.get("eventTime"))
        if time_raw is None:
            continue
        game_time = float(time_raw)

        kind: HighlightKind | None = None
        label: str | None = None
        if name in {"ChampionKill", "Multikill"}:
            kind = HighlightKind.KILL
            label = name
        elif name in {"DragonKill", "BaronKill", "HeraldKill", "TurretKilled", "InhibKilled"}:
            kind = HighlightKind.OBJECTIVE
            label = name

        if kind is None:
            continue

        candidates.append(
            HighlightCandidate(
                kind=kind,
                game_time_sec=game_time,
                start_sec=max(0.0, game_time - padding_before_sec),
                end_sec=game_time + padding_after_sec,
                label=label,
                meta=dict(event),
            )
        )

    candidates.sort(key=lambda c: c.game_time_sec)
    return candidates
