"""Request / response models for the HTTP API."""

from __future__ import annotations

from pydantic import BaseModel, Field

from pentaklip.detect.models import HighlightCandidate


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str


class InstallReplayRequest(BaseModel):
    source_path: str = Field(description="Path to the downloaded .rofl file")
    local_replay_id: str = Field(description="Local replay id to overwrite / install as")
    dry_run: bool = False


class InstallReplayResponse(BaseModel):
    replay_db_id: int | None = None
    original_match_id: str
    original_filename: str
    local_replay_id: str
    installed_path: str
    overwritten: bool


class DetectRequest(BaseModel):
    events: list[dict] = Field(default_factory=list)
    padding_before_sec: float | None = None
    padding_after_sec: float | None = None


class DetectResponse(BaseModel):
    highlights: list[HighlightCandidate]
