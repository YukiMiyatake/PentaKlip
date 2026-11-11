"""Request / response models for the HTTP API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from pentaklip.detect.models import HighlightCandidate
from pentaklip.replay.install import InstallMode
from pentaklip.stats.display import DisplaySettings
from pentaklip.stats.models import AggregatedReplayStats, ChartBundle, ReplayStatsBundle


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str


class InstallReplayRequest(BaseModel):
    source_path: str = Field(description="Path to the downloaded .rofl file")
    local_replay_id: str = Field(description="Local replay id to overwrite / install as")
    mode: InstallMode = InstallMode.COPY
    replays_dir: str | None = Field(
        default=None,
        description="Override LoL Replays folder (defaults to settings)",
    )
    dry_run: bool = False


class InstallReplayResponse(BaseModel):
    replay_db_id: int | None = None
    original_match_id: str
    original_filename: str
    local_replay_id: str
    installed_path: str
    overwritten: bool
    mode: InstallMode


class LocalReplayItem(BaseModel):
    path: str
    filename: str
    match_id: str | None
    size_bytes: int


class ParseMatchIdResponse(BaseModel):
    path: str
    match_id: str | None
    stem: str


class DetectRequest(BaseModel):
    events: list[dict] = Field(default_factory=list)
    padding_before_sec: float | None = None
    padding_after_sec: float | None = None


class DetectResponse(BaseModel):
    highlights: list[HighlightCandidate]


class ManualClipSegment(BaseModel):
    start_sec: float
    end_sec: float
    kind: str = "other"
    label: str | None = None
    game_time_sec: float | None = None


class CreateClipsRequest(BaseModel):
    source_video_path: str = Field(description="Full-match recording (mp4/mkv/etc.)")
    output_dir: str | None = None
    original_match_id: str | None = None
    replay_db_id: int | None = None
    padding_before_sec: float | None = None
    padding_after_sec: float | None = None
    events: list[dict] = Field(default_factory=list)
    highlights: list[HighlightCandidate] = Field(default_factory=list)
    segments: list[ManualClipSegment] = Field(default_factory=list)
    dry_run: bool = False


class CreatedClipItem(BaseModel):
    kind: str
    label: str | None
    game_time_sec: float
    start_sec: float
    end_sec: float
    output_path: str
    highlight_db_id: int | None = None
    export_db_id: int | None = None


class CreateClipsResponse(BaseModel):
    source_video: str
    output_dir: str
    clip_count: int
    clips: list[CreatedClipItem]
    game_id: str | None = None
    original_source_video: str | None = None
    converted: bool = False


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


class UiPreferencesModel(BaseModel):
    fixed_target_rofl: str | None = None
    last_source_dir: str | None = None
    last_video_dir: str | None = None
    last_events_dir: str | None = None
    last_output_root: str | None = None
    last_game_id: str | None = None


class ListDirRequest(BaseModel):
    directory: str
    suffixes: list[str] | None = None


class AutoSplitRequest(BaseModel):
    source_video_path: str
    events: list[dict] = Field(default_factory=list)
    events_path: str | None = None
    output_dir: str | None = None
    original_match_id: str | None = None
    replay_db_id: int | None = None
    padding_before_sec: float | None = None
    padding_after_sec: float | None = None
    dry_run: bool = False

class ExportEventsRequest(BaseModel):
    output_path: str | None = None
    directory: str | None = None
    filename: str | None = None
    events: list[dict] | None = None
    game_id: str | None = None
    game_time_sec: float | None = None
    source: str = "liveclientdata"


class ExportEventsResponse(BaseModel):
    path: str
    event_count: int
    game_id: str
    game_dir: str
    game_time_sec: float | None = None
    source: str = "liveclientdata"
