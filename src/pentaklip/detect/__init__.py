"""Highlight detection from live client / replay events."""

from pentaklip.detect.models import HighlightCandidate, HighlightKind
from pentaklip.detect.service import detect_from_events

__all__ = ["HighlightCandidate", "HighlightKind", "detect_from_events"]
