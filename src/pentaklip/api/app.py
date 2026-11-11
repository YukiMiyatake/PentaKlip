"""FastAPI application."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from pentaklip import __version__
from pentaklip.api.schemas import (
    AggregateStatsRequest,
    ChartsRequest,
    DetectRequest,
    DetectResponse,
    FinalizeStatsRequest,
    FinalizeStatsResponse,
    HealthResponse,
    IngestStatsRequest,
    InstallReplayRequest,
    InstallReplayResponse,
    StartStatsSessionRequest,
    StartStatsSessionResponse,
)
from pentaklip.config import settings
from pentaklip.detect.service import detect_from_events
from pentaklip.replay.install import install_replay
from pentaklip.stats.aggregate import aggregate_replay
from pentaklip.stats.catalog import (
    SERIES_STAT_KEYS,
    STAT_LABELS,
    TABLE_STAT_KEYS,
    Position,
    StatKey,
)
from pentaklip.stats.charts import build_charts
from pentaklip.stats.display import (
    DisplaySettings,
    default_display_settings,
    load_display_settings,
    save_display_settings,
    validate_display_settings,
)
from pentaklip.stats.export import export_replay_stats, load_replay_stats
from pentaklip.stats.models import AggregatedReplayStats, ChartBundle
from pentaklip.stats.sessions import create_session, get_session, pop_session
from pentaklip.store.db import get_database


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    get_database().initialize()
    yield


app = FastAPI(title="PentaKlip", version=__version__, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:8787",
        "http://localhost:8787",
        "tauri://localhost",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", version=__version__)


@app.post("/api/replays/install", response_model=InstallReplayResponse)
def api_install_replay(body: InstallReplayRequest) -> InstallReplayResponse:
    try:
        result = install_replay(
            Path(body.source_path),
            local_replay_id=body.local_replay_id,
            replays_dir=settings.lol_replays_dir,
            dry_run=body.dry_run,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    replay_db_id: int | None = None
    if not body.dry_run:
        replay_db_id = get_database().insert_replay(
            original_match_id=result.original_match_id,
            original_filename=result.original_filename,
            local_replay_id=result.local_replay_id,
            installed_path=str(result.installed_path),
        )

    return InstallReplayResponse(
        replay_db_id=replay_db_id,
        original_match_id=result.original_match_id,
        original_filename=result.original_filename,
        local_replay_id=result.local_replay_id,
        installed_path=str(result.installed_path),
        overwritten=result.overwritten,
    )


@app.get("/api/replays")
def api_list_replays() -> list[dict]:
    return get_database().list_replays()


@app.post("/api/detect", response_model=DetectResponse)
def api_detect(body: DetectRequest) -> DetectResponse:
    before = (
        body.padding_before_sec
        if body.padding_before_sec is not None
        else settings.clip_padding_before_sec
    )
    after = (
        body.padding_after_sec
        if body.padding_after_sec is not None
        else settings.clip_padding_after_sec
    )
    highlights = detect_from_events(
        body.events,
        padding_before_sec=before,
        padding_after_sec=after,
    )
    return DetectResponse(highlights=highlights)


@app.get("/api/stats/catalog")
def api_stats_catalog() -> dict:
    return {
        "positions": [p.value for p in Position],
        "table_stat_keys": [
            {"key": k.value, "label": STAT_LABELS[k]} for k in TABLE_STAT_KEYS
        ],
        "series_stat_keys": [
            {"key": k.value, "label": STAT_LABELS[k]} for k in SERIES_STAT_KEYS
        ],
        "all_stat_keys": [{"key": k.value, "label": STAT_LABELS[k]} for k in StatKey],
    }


@app.get("/api/stats/display-settings", response_model=DisplaySettings)
def api_get_display_settings() -> DisplaySettings:
    return load_display_settings(settings.data_dir)


@app.put("/api/stats/display-settings", response_model=DisplaySettings)
def api_put_display_settings(body: DisplaySettings) -> DisplaySettings:
    cleaned = validate_display_settings(body)
    save_display_settings(settings.data_dir, cleaned)
    return cleaned


@app.post("/api/stats/display-settings/reset", response_model=DisplaySettings)
def api_reset_display_settings() -> DisplaySettings:
    defaults = default_display_settings()
    save_display_settings(settings.data_dir, defaults)
    return defaults


@app.post("/api/stats/sessions", response_model=StartStatsSessionResponse)
def api_start_stats_session(body: StartStatsSessionRequest) -> StartStatsSessionResponse:
    session = create_session(
        original_match_id=body.original_match_id,
        local_replay_id=body.local_replay_id,
        source_filename=body.source_filename,
        sample_interval_sec=body.sample_interval_sec,
    )
    return StartStatsSessionResponse(session_id=session.session_id)


@app.post("/api/stats/sessions/{session_id}/ingest")
def api_ingest_stats(session_id: str, body: IngestStatsRequest) -> dict:
    session = get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Unknown stats session")
    snap = session.ingest_all_game_data(body.all_game_data)
    return {
        "game_time_sec": snap.game_time_sec,
        "player_count": len(snap.players),
        "snapshot_count": len(session.bundle.snapshots),
        "event_count": len(session.bundle.events),
    }


@app.post("/api/stats/sessions/{session_id}/poll")
def api_poll_stats(session_id: str) -> dict:
    session = get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Unknown stats session")
    try:
        snap = session.poll_live_client()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Live Client poll failed: {exc}") from exc
    return {
        "game_time_sec": snap.game_time_sec,
        "player_count": len(snap.players),
        "snapshot_count": len(session.bundle.snapshots),
        "event_count": len(session.bundle.events),
    }


@app.post("/api/stats/sessions/{session_id}/finalize", response_model=FinalizeStatsResponse)
def api_finalize_stats(session_id: str, body: FinalizeStatsRequest) -> FinalizeStatsResponse:
    session = pop_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Unknown stats session")
    bundle = session.finalize()
    aggregated = aggregate_replay(bundle)
    charts: ChartBundle | None = None
    if body.build_charts:
        charts = build_charts(aggregated, load_display_settings(settings.data_dir))
    export_path: str | None = None
    if body.export_path:
        path = export_replay_stats(
            bundle, Path(body.export_path), fmt=body.export_format
        )
        export_path = str(path)
    return FinalizeStatsResponse(
        bundle=bundle,
        aggregated=aggregated,
        charts=charts,
        export_path=export_path,
    )


@app.post("/api/stats/aggregate", response_model=AggregatedReplayStats)
def api_aggregate_stats(body: AggregateStatsRequest) -> AggregatedReplayStats:
    if body.bundle is not None:
        return aggregate_replay(body.bundle)
    if body.bundle_path:
        return aggregate_replay(load_replay_stats(Path(body.bundle_path)))
    raise HTTPException(status_code=400, detail="Provide bundle or bundle_path")


@app.post("/api/stats/charts", response_model=ChartBundle)
def api_build_charts(body: ChartsRequest) -> ChartBundle:
    display = body.display or load_display_settings(settings.data_dir)
    return build_charts(body.aggregated, display)
