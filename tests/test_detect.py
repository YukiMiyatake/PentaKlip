from pentaklip.detect.models import HighlightKind
from pentaklip.detect.service import detect_from_events, summarize_event_coverage


def test_detect_kills_and_objectives() -> None:
    events = [
        {"EventName": "ChampionKill", "EventTime": 120.0, "KillerName": "A"},
        {"EventName": "DragonKill", "EventTime": 300.5},
        {"EventName": "GameStart", "EventTime": 0.0},
    ]
    highlights = detect_from_events(
        events,
        padding_before_sec=10,
        padding_after_sec=10,
        merge_fights=False,
    )

    assert len(highlights) == 2
    assert highlights[0].kind == HighlightKind.KILL
    assert highlights[0].start_sec == 110.0
    assert highlights[0].end_sec == 130.0
    assert highlights[1].kind == HighlightKind.OBJECTIVE
    assert highlights[1].game_time_sec == 300.5


def test_merge_nearby_kills_into_one_fight() -> None:
    events = [
        {"EventName": "ChampionKill", "EventTime": 1800.0},
        {"EventName": "ChampionKill", "EventTime": 1808.0},
        {"EventName": "ChampionKill", "EventTime": 1815.0},
        {"EventName": "Multikill", "EventTime": 1815.0},
        {"EventName": "ChampionKill", "EventTime": 1822.0},
        {"EventName": "ChampionKill", "EventTime": 1830.0},
        {"EventName": "DragonKill", "EventTime": 600.0},
    ]
    highlights = detect_from_events(
        events,
        padding_before_sec=10,
        padding_after_sec=10,
        merge_gap_sec=25,
        merge_fights=True,
    )
    assert len(highlights) == 2
    assert highlights[0].kind == HighlightKind.OBJECTIVE
    assert highlights[0].game_time_sec == 600.0
    fight = highlights[1]
    assert fight.kind == HighlightKind.TEAMFIGHT
    assert fight.start_sec == 1790.0
    assert fight.end_sec == 1840.0
    assert fight.meta["merged_count"] == 5  # Multikill dropped as duplicate of ChampionKill


def test_event_coverage_lists_ignored_names() -> None:
    events = [
        {"EventName": "GameStart", "EventTime": 0.0},
        {"EventName": "ChampionKill", "EventTime": 10.0},
        {"EventName": "MinionsSpawning", "EventTime": 65.0},
    ]
    coverage = summarize_event_coverage(events)
    assert coverage["used_for_clips"]["ChampionKill"] == 1
    assert coverage["ignored"]["GameStart"] == 1
    assert coverage["ignored"]["MinionsSpawning"] == 1
