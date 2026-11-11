"""FastAPI application."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from pentaklip import __version__
from pentaklip.api.schemas import (
    AggregateStatsRequest,
    AutoSplitRequest,
    ChartsRequest,
    CreateClipsRequest,
    CreateClipsResponse,
    CreatedClipItem,
    DetectRequest,
    DetectResponse,
    ExportEventsRequest,
    ExportEventsResponse,
    FinalizeStatsRequest,
    FinalizeStatsResponse,
    HealthResponse,
    IngestStatsRequest,
    InstallReplayRequest,
    InstallReplayResponse,
    ListDirRequest,
    LocalReplayItem,
    ParseMatchIdResponse,
    StartStatsSessionRequest,
    StartStatsSessionResponse,
    UiPreferencesModel,
)
from pentaklip.clips.service import ClipSegment, create_clips
from pentaklip.config import settings
from pentaklip.detect.service import detect_from_events
from pentaklip.events.service import export_events_json, fetch_live_events
from pentaklip.replay.install import (
    install_replay,
    list_local_replays,
    parse_match_id_from_filename,
)
from pentaklip.replay.metadata import RoflOverview, inspect_rofl
from pentaklip.settings_store import (
    UiPreferences,
    list_directory,
    load_ui_preferences,
    save_ui_preferences,
)
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
from pentaklip.tools.ffmpeg_setup import (
    add_discovered_ffmpeg_to_path,
    get_ffmpeg_status,
    install_ffmpeg_winget,
)


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
    replays_dir = Path(body.replays_dir) if body.replays_dir else settings.lol_replays_dir
    try:
        result = install_replay(
            Path(body.source_path),
            local_replay_id=body.local_replay_id,
            replays_dir=replays_dir,
            mode=body.mode,
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
        mode=result.mode,
    )


@app.get("/api/replays")
def api_list_replays() -> list[dict]:
    return get_database().list_replays()


@app.get("/api/replays/local", response_model=list[LocalReplayItem])
def api_list_local_replays() -> list[LocalReplayItem]:
    items = list_local_replays(settings.lol_replays_dir)
    return [
        LocalReplayItem(
            path=str(item.path),
            filename=item.filename,
            match_id=item.match_id,
            size_bytes=item.size_bytes,
        )
        for item in items
    ]


@app.get("/api/replays/parse-id", response_model=ParseMatchIdResponse)
def api_parse_match_id(path: str) -> ParseMatchIdResponse:
    p = Path(path)
    return ParseMatchIdResponse(
        path=str(p),
        match_id=parse_match_id_from_filename(p),
        stem=p.stem,
    )


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


@app.post("/api/clips/create", response_model=CreateClipsResponse)
def api_create_clips(body: CreateClipsRequest) -> CreateClipsResponse:
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
    output_dir = Path(body.output_dir) if body.output_dir else settings.resolved_clips_dir()
    manual = [
        ClipSegment(
            kind=seg.kind,
            game_time_sec=seg.game_time_sec if seg.game_time_sec is not None else seg.start_sec,
            start_sec=seg.start_sec,
            end_sec=seg.end_sec,
            label=seg.label,
        )
        for seg in body.segments
    ]
    try:
        result = create_clips(
            Path(body.source_video_path),
            output_dir=output_dir,
            events=body.events or None,
            highlights=body.highlights or None,
            segments=manual or None,
            padding_before_sec=before,
            padding_after_sec=after,
            dry_run=body.dry_run,
            match_id=body.original_match_id,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    clip_items: list[CreatedClipItem] = []
    db = get_database()
    for clip in result.clips:
        highlight_db_id: int | None = None
        export_db_id: int | None = None
        if not body.dry_run and body.replay_db_id is not None:
            highlight_db_id = db.insert_highlight(
                replay_id=body.replay_db_id,
                kind=clip.segment.kind,
                game_time_sec=clip.segment.game_time_sec,
                start_sec=clip.segment.start_sec,
                end_sec=clip.segment.end_sec,
                payload_json=json.dumps({"label": clip.segment.label}),
            )
            export_db_id = db.insert_export(
                highlight_id=highlight_db_id,
                output_path=str(clip.output_path),
            )
        clip_items.append(
            CreatedClipItem(
                kind=clip.segment.kind,
                label=clip.segment.label,
                game_time_sec=clip.segment.game_time_sec,
                start_sec=clip.segment.start_sec,
                end_sec=clip.segment.end_sec,
                output_path=str(clip.output_path),
                highlight_db_id=highlight_db_id,
                export_db_id=export_db_id,
            )
        )

    return CreateClipsResponse(
        source_video=str(result.source_video),
        output_dir=str(result.output_dir),
        clip_count=len(clip_items),
        clips=clip_items,
    )


@app.get("/api/clips")
def api_list_clips() -> list[dict]:
    return get_database().list_exports()


@app.post("/api/clips/auto-split", response_model=CreateClipsResponse)
def api_auto_split(body: AutoSplitRequest) -> CreateClipsResponse:
    """Detect highlights from events (or events file) and cut clips automatically."""
    events = list(body.events)
    if body.events_path:
        events_path = Path(body.events_path)
        if not events_path.is_file():
            raise HTTPException(status_code=404, detail=f"Events file not found: {events_path}")
        loaded = json.loads(events_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict) and "Events" in loaded:
            loaded = loaded["Events"]
        if isinstance(loaded, dict) and "events" in loaded:
            loaded = loaded["events"]
        if not isinstance(loaded, list):
            raise HTTPException(status_code=400, detail="Events JSON must be a list or {Events:[...]}")
        events.extend(e for e in loaded if isinstance(e, dict))

    create_body = CreateClipsRequest(
        source_video_path=body.source_video_path,
        output_dir=body.output_dir,
        original_match_id=body.original_match_id,
        replay_db_id=body.replay_db_id,
        padding_before_sec=body.padding_before_sec,
        padding_after_sec=body.padding_after_sec,
        events=events,
        dry_run=body.dry_run,
    )
    return api_create_clips(create_body)

@app.get("/api/events/live")
def api_events_live() -> dict:
    """Return current Live Client events (empty/unavailable when LoL is not running)."""
    return fetch_live_events().model_dump()


@app.post("/api/events/export", response_model=ExportEventsResponse)
def api_events_export(body: ExportEventsRequest) -> ExportEventsResponse:
    """Fetch Live Client events (or use provided events) and write clip-compatible JSON."""
    prefs = load_ui_preferences(settings.data_dir)
    default_dir = Path(prefs.last_events_dir) if prefs.last_events_dir else settings.data_dir / "events"
    try:
        result = export_events_json(
            output_path=body.output_path,
            directory=body.directory,
            filename=body.filename,
            events=body.events,
            game_time_sec=body.game_time_sec,
            source=body.source,
            default_dir=default_dir,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"Failed to write events JSON: {exc}") from exc

    # Remember export directory for the AutoSplit file picker.
    export_dir = str(Path(result.path).parent)
    if prefs.last_events_dir != export_dir:
        prefs.last_events_dir = export_dir
        save_ui_preferences(settings.data_dir, prefs)

    return ExportEventsResponse.model_validate(result.model_dump())


@app.get("/api/replays/inspect", response_model=RoflOverview)
def api_inspect_rofl(path: str) -> RoflOverview:
    try:
        return inspect_rofl(Path(path))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/ui/preferences", response_model=UiPreferencesModel)
def api_get_ui_preferences() -> UiPreferencesModel:
    prefs = load_ui_preferences(settings.data_dir)
    return UiPreferencesModel.model_validate(prefs.model_dump())


@app.put("/api/ui/preferences", response_model=UiPreferencesModel)
def api_put_ui_preferences(body: UiPreferencesModel) -> UiPreferencesModel:
    saved = save_ui_preferences(settings.data_dir, UiPreferences.model_validate(body.model_dump()))
    return UiPreferencesModel.model_validate(saved.model_dump())


@app.post("/api/fs/list")
def api_fs_list(body: ListDirRequest) -> dict:
    try:
        entries = list_directory(Path(body.directory), suffixes=body.suffixes)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "directory": str(Path(body.directory).expanduser().resolve()),
        "entries": [e.model_dump() for e in entries],
    }


@app.get("/api/tools/ffmpeg")
def api_ffmpeg_status() -> dict:
    return get_ffmpeg_status().model_dump()


@app.post("/api/tools/ffmpeg/install")
def api_ffmpeg_install() -> dict:
    try:
        result = install_ffmpeg_winget()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"ffmpeg install failed: {exc}") from exc
    return result


@app.post("/api/tools/ffmpeg/add-to-path")
def api_ffmpeg_add_to_path() -> dict:
    try:
        status = add_discovered_ffmpeg_to_path()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return status.model_dump()


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


def _web_dist_dir() -> Path | None:
    candidates = [
        Path(__file__).resolve().parents[3] / "web" / "dist",
        Path.cwd() / "web" / "dist",
    ]
    for path in candidates:
        if (path / "index.html").is_file():
            return path
    return None


_WEB_DIST = _web_dist_dir()
if _WEB_DIST is not None:
    assets_dir = _WEB_DIST / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="web-assets")

    @app.get("/")
    def spa_index() -> FileResponse:
        return FileResponse(_WEB_DIST / "index.html")

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str) -> FileResponse:
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        candidate = _WEB_DIST / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_WEB_DIST / "index.html")
