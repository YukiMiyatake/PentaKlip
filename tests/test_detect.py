from pentaklip.detect.models import HighlightKind
from pentaklip.detect.service import detect_from_events


def test_detect_kills_and_objectives() -> None:
    events = [
        {"EventName": "ChampionKill", "EventTime": 120.0, "KillerName": "A"},
        {"EventName": "DragonKill", "EventTime": 300.5},
        {"EventName": "GameStart", "EventTime": 0.0},
    ]
    highlights = detect_from_events(events, padding_before_sec=10, padding_after_sec=10)

    assert len(highlights) == 2
    assert highlights[0].kind == HighlightKind.KILL
    assert highlights[0].start_sec == 110.0
    assert highlights[0].end_sec == 130.0
    assert highlights[1].kind == HighlightKind.OBJECTIVE
    assert highlights[1].game_time_sec == 300.5
