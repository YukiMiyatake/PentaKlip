"""Heuristic highlight detection (kill / objective / fight clustering)."""

from __future__ import annotations

from typing import Any

from pentaklip.detect.models import HighlightCandidate, HighlightKind

# Live Client event names we turn into clips.
KILL_EVENTS = {
    "ChampionKill",
    "Ace",
    "FirstBlood",
}
# Multikill duplicates ChampionKill timestamps; keep for clustering signal only if alone.
MULTIKILL_EVENTS = {"Multikill"}
OBJECTIVE_EVENTS = {
    "DragonKill",
    "BaronKill",
    "HeraldKill",
    "HordeKill",  # Voidgrubs
    "AtakhanKill",
    "TurretKilled",
    "InhibKilled",
    "InhibitorKilled",
}


def classify_event_name(name: str) -> HighlightKind | None:
    if name in KILL_EVENTS or name in MULTIKILL_EVENTS:
        return HighlightKind.KILL
    if name in OBJECTIVE_EVENTS:
        return HighlightKind.OBJECTIVE
    return None


def merge_fight_candidates(
    candidates: list[HighlightCandidate],
    *,
    max_gap_sec: float = 25.0,
) -> list[HighlightCandidate]:
    """
    Merge nearby highlights into one clip window.

    Consecutive events belong to the same fight when the gap between their
    ``game_time_sec`` values is <= ``max_gap_sec`` (ongoing kills / trades).
    """
    if not candidates:
        return []
    ordered = sorted(candidates, key=lambda c: (c.game_time_sec, c.start_sec))
    clusters: list[list[HighlightCandidate]] = [[ordered[0]]]
    for item in ordered[1:]:
        prev = clusters[-1][-1]
        if item.game_time_sec - prev.game_time_sec <= max_gap_sec:
            clusters[-1].append(item)
        else:
            clusters.append([item])

    merged: list[HighlightCandidate] = []
    for cluster in clusters:
        if len(cluster) == 1:
            merged.append(cluster[0])
            continue

        kinds = {c.kind for c in cluster}
        if HighlightKind.KILL in kinds and HighlightKind.OBJECTIVE in kinds or sum(1 for c in cluster if c.kind == HighlightKind.KILL) >= 2:
            kind = HighlightKind.TEAMFIGHT
        elif HighlightKind.OBJECTIVE in kinds:
            kind = HighlightKind.OBJECTIVE
        else:
            kind = next(iter(kinds))

        labels = [c.label for c in cluster if c.label]
        label = f"fight_{len(cluster)}x"
        if labels:
            # e.g. fight_5x:ChampionKill+DragonKill
            uniq = []
            for name in labels:
                if name not in uniq:
                    uniq.append(name)
            label = f"{label}:{('+'.join(uniq[:4]))}"

        merged.append(
            HighlightCandidate(
                kind=kind,
                game_time_sec=cluster[0].game_time_sec,
                start_sec=min(c.start_sec for c in cluster),
                end_sec=max(c.end_sec for c in cluster),
                label=label,
                meta={
                    "merged_count": len(cluster),
                    "event_times": [c.game_time_sec for c in cluster],
                    "event_names": labels,
                },
            )
        )
    return merged


def detect_from_events(
    events: list[dict[str, Any]],
    *,
    padding_before_sec: float = 10.0,
    padding_after_sec: float = 10.0,
    merge_gap_sec: float = 25.0,
    merge_fights: bool = True,
) -> list[HighlightCandidate]:
    """
    Build highlight candidates from Live Client-style event dicts.

    Expected kill-like shape (subset):
      {"EventName": "ChampionKill", "EventTime": 123.4, ...}

    Nearby kills/objectives are merged into one fight window when
    ``merge_fights`` is enabled (default).
    """
    candidates: list[HighlightCandidate] = []
    seen_keys: set[tuple[str, float]] = set()

    for event in events:
        name = str(event.get("EventName") or event.get("eventName") or "")
        time_raw = event.get("EventTime", event.get("eventTime"))
        if time_raw is None:
            continue
        game_time = float(time_raw)
        kind = classify_event_name(name)
        if kind is None:
            continue

        # Drop exact duplicate EventName@time (common with Multikill + ChampionKill).
        key = (name, round(game_time, 3))
        if key in seen_keys:
            continue
        seen_keys.add(key)

        # Prefer ChampionKill over Multikill at the same second.
        if name in MULTIKILL_EVENTS and any(
            str(e.get("EventName") or e.get("eventName") or "") == "ChampionKill"
            and abs(float(e.get("EventTime", e.get("eventTime") or -1)) - game_time) < 0.05
            for e in events
            if e.get("EventTime", e.get("eventTime")) is not None
        ):
            continue

        candidates.append(
            HighlightCandidate(
                kind=kind,
                game_time_sec=game_time,
                start_sec=max(0.0, game_time - padding_before_sec),
                end_sec=game_time + padding_after_sec,
                label=name,
                meta=dict(event),
            )
        )

    candidates.sort(key=lambda c: c.game_time_sec)
    if merge_fights:
        return merge_fight_candidates(candidates, max_gap_sec=merge_gap_sec)
    return candidates


def summarize_event_coverage(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Explain which Live Client events become clips vs ignored (for debugging)."""
    counted: dict[str, int] = {}
    used: dict[str, int] = {}
    ignored: dict[str, int] = {}
    for event in events:
        name = str(event.get("EventName") or event.get("eventName") or "") or "(missing)"
        counted[name] = counted.get(name, 0) + 1
        if classify_event_name(name) is None:
            ignored[name] = ignored.get(name, 0) + 1
        else:
            used[name] = used.get(name, 0) + 1
    return {
        "total_events": len(events),
        "by_name": dict(sorted(counted.items())),
        "used_for_clips": dict(sorted(used.items())),
        "ignored": dict(sorted(ignored.items())),
        "clip_event_names": sorted(KILL_EVENTS | MULTIKILL_EVENTS | OBJECTIVE_EVENTS),
    }
