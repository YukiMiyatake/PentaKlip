"""Request / response models for the HTTP API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from pentaklip.detect.models import HighlightCandidate
from pentaklip.stats.display import DisplaySettings
from pentaklip.stats.models import AggregatedReplayStats, ChartBundle, ReplayStatsBundle


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


class StartStatsSessionRequest(BaseModel):
    original_match_id: str | None = None
    local_replay_id: str | None = None
    source_filename: str | None = None
    sample_interval_sec: float = 5.0


class StartStatsSessionResponse(BaseModel):
    session_id: str


class IngestStatsRequest(BaseModel):
    all_game_data: dict[str, Any]


class FinalizeStatsRequest(BaseModel):
    export_path: str | None = None
    export_format: Literal["json", "yaml"] = "json"
    build_charts: bool = True


class FinalizeStatsResponse(BaseModel):
    bundle: ReplayStatsBundle
    aggregated: AggregatedReplayStats
    charts: ChartBundle | None = None
    export_path: str | None = None


class AggregateStatsRequest(BaseModel):
    bundle: ReplayStatsBundle | None = None
    bundle_path: str | None = None


class ChartsRequest(BaseModel):
    aggregated: AggregatedReplayStats
    display: DisplaySettings | None = None
