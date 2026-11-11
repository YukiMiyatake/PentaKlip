"""Highlight candidate types."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class HighlightKind(StrEnum):
    KILL = "kill"
    TEAMFIGHT = "teamfight"
    OBJECTIVE = "objective"
    OTHER = "other"


class HighlightCandidate(BaseModel):
    kind: HighlightKind
    game_time_sec: float
    start_sec: float
    end_sec: float
    label: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)
