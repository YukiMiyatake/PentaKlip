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
    AggregateFolderStatsRequest,
    AggregateStatsRequest,
    AutoSplitRequest,
    ChartsRequest,
    CreateClipsRequest,
    CreateClipsResponse,
    CreatedClipItem,
    DetectRequest,
    DetectResponse,
    EnrichScoreboardSsRequest,
    ExportEventsRequest,
    ExportEventsResponse,
    FfmpegInstallRequest,
    FfmpegMoveRequest,
    FfmpegSettingsModel,
    FinalizeStatsRequest,
    FinalizeStatsResponse,
    HealthResponse,
    IngestStatsRequest,
    InstallReplayRequest,
    InstallReplayResponse,
    ListDirRequest,
    LocalReplayItem,
    LocalReplaysResponse,
    ParseMatchIdResponse,
    PickDirectoryRequest,
    StartStatsSessionRequest,
    StartStatsSessionResponse,
    UiPreferencesModel,
    UiPreferencesPatch,
)
from pentaklip.clips.service import ClipSegment, create_clips
from pentaklip.config import settings
from pentaklip.detect.service import detect_from_events, summarize_event_coverage
from pentaklip.events.harvest import harvest_events_playthrough
from pentaklip.events.service import export_events_json, fetch_live_events
from pentaklip.game_id import game_id_from_rofl_path
from pentaklip.paths import infer_game_id, resolve_output_layout
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
    pick_directory,
    save_ui_preferences,
    ui_preferences_path,
    update_ui_preferences,
)
from pentaklip.stats.aggregate import aggregate_replay
from pentaklip.stats.catalog import (
    LCK_RADAR_STAT_KEYS,
    POSITION_LABELS,
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
from pentaklip.stats.folder_aggregate import aggregate_stats_folder
from pentaklip.stats.models import AggregatedReplayStats, ChartBundle
from pentaklip.stats.sessions import create_session, get_session, pop_session
from pentaklip.store.db import get_database
from pentaklip.tools.ffmpeg_settings import (
    FfmpegSettings,
    available_encode_backends,
    default_ffmpeg_settings,
    load_ffmpeg_settings,
    resolve_encode_backend,
    resolved_ffmpeg_path,
    save_ffmpeg_settings,
)
from pentaklip.tools.ffmpeg_setup import (
    add_discovered_ffmpeg_to_path,
    get_ffmpeg_status,
    install_ffmpeg_winget,
    move_ffmpeg_install,
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
    prefs = load_ui_preferences(settings.data_dir)
    if body.replays_dir:
        replays_dir = Path(body.replays_dir)
    elif prefs.last_replays_dir:
        replays_dir = Path(prefs.last_replays_dir)
    else:
        replays_dir = settings.lol_replays_dir
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
        prefs.last_game_id = result.original_match_id
        prefs.fixed_target_rofl = str(result.installed_path)
        prefs.last_replays_dir = str(Path(result.installed_path).parent)
        save_ui_preferences(settings.data_dir, prefs)

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


@app.get("/api/replays/local", response_model=LocalReplaysResponse)
def api_list_local_replays(directory: str | None = None) -> LocalReplaysResponse:
    prefs = load_ui_preferences(settings.data_dir)
    default_directory = settings.lol_replays_dir.expanduser().resolve()
    chosen = directory or prefs.last_replays_dir or str(default_directory)
    replays_dir = Path(chosen).expanduser()
    try:
        resolved = replays_dir.resolve()
    except OSError:
        resolved = default_directory
    if not resolved.is_dir():
        # Fall back to LoL default when remembered path is missing.
        resolved = default_directory
    items = list_local_replays(resolved)
    return LocalReplaysResponse(
        directory=str(resolved),
        default_directory=str(default_directory),
        items=[
            LocalReplayItem(
                path=str(item.path),
                filename=item.filename,
                match_id=item.match_id,
                size_bytes=item.size_bytes,
            )
            for item in items
        ],
    )


@app.get("/api/highlights/local")
def api_list_local_highlights(directory: str | None = None) -> dict:
    """List LoL Highlights folder videos (.webm / common containers)."""
    prefs = load_ui_preferences(settings.data_dir)
    default_directory = settings.lol_highlights_dir.expanduser().resolve()
    chosen = directory or prefs.last_highlights_dir or str(default_directory)
    highlights_dir = Path(chosen).expanduser()
    try:
        resolved = highlights_dir.resolve()
    except OSError:
        resolved = default_directory
    if not resolved.is_dir():
        resolved = default_directory
    suffixes = [".webm", ".mp4", ".mkv", ".mov", ".avi"]
    try:
        entries = list_directory(resolved, suffixes=suffixes)
    except FileNotFoundError:
        entries = []
    return {
        "directory": str(resolved),
        "default_directory": str(default_directory),
        "entries": [e.model_dump() for e in entries if not e.is_dir],
    }


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
    gap = body.merge_gap_sec if body.merge_gap_sec is not None else settings.clip_merge_gap_sec
    highlights = detect_from_events(
        body.events,
        padding_before_sec=before,
        padding_after_sec=after,
        merge_gap_sec=gap,
        merge_fights=body.merge_fights,
    )
    return DetectResponse(
        highlights=highlights,
        event_coverage=summarize_event_coverage(body.events),
    )


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
    gap = body.merge_gap_sec if body.merge_gap_sec is not None else settings.clip_merge_gap_sec

    prefs = load_ui_preferences(settings.data_dir)
    db = get_database()
    rofl_id, _rofl_src = game_id_from_rofl_path(prefs.fixed_target_rofl, db=db)
    game_id = infer_game_id(
        body.original_match_id,
        rofl_id,
        body.source_video_path,
        prefs.last_game_id,
    )

    layout = resolve_output_layout(
        prefs.last_output_root,
        fallback=settings.resolved_clips_dir(),
    )
    if body.output_dir:
        output_dir = Path(body.output_dir)
        replay_dir = layout.replay_dir if prefs.last_output_root else None
    elif game_id:
        layout.ensure()
        output_dir = layout.clip_dir(game_id)
        replay_dir = layout.replay_dir
    else:
        layout.ensure()
        output_dir = layout.clip_root
        replay_dir = layout.replay_dir

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
            merge_gap_sec=gap,
            merge_fights=body.merge_fights,
            dry_run=body.dry_run,
            match_id=game_id or body.original_match_id,
            replay_dir=replay_dir,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if not body.dry_run:
        changed = False
        if game_id and prefs.last_game_id != game_id:
            prefs.last_game_id = game_id
            changed = True
        root_for_prefs = str(layout.root)
        if prefs.last_output_root != root_for_prefs:
            prefs.last_output_root = root_for_prefs
            changed = True
        event_dir = str(layout.event_dir)
        if prefs.last_events_dir != event_dir:
            prefs.last_events_dir = event_dir
            changed = True
        if changed:
            save_ui_preferences(settings.data_dir, prefs)

    clip_items: list[CreatedClipItem] = []
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
        game_id=game_id,
        original_source_video=(
            str(result.original_source_video) if result.original_source_video else None
        ),
        converted=result.converted,
        event_coverage=summarize_event_coverage(body.events) if body.events else None,
    )


@app.get("/api/clips")
def api_list_clips() -> list[dict]:
    return get_database().list_exports()


@app.post("/api/clips/auto-split", response_model=CreateClipsResponse)
def api_auto_split(body: AutoSplitRequest) -> CreateClipsResponse:
    """Detect highlights from events (or events file) and cut clips automatically."""
    events = list(body.events)
    events_meta: dict = {}
    events_path: Path | None = None
    if body.events_path:
        events_path = Path(body.events_path)
        if not events_path.is_file():
            raise HTTPException(status_code=404, detail=f"Events file not found: {events_path}")
        loaded = json.loads(events_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            meta = loaded.get("meta")
            if isinstance(meta, dict):
                events_meta = meta
            if "Events" in loaded:
                loaded = loaded["Events"]
            elif "events" in loaded:
                loaded = loaded["events"]
        if not isinstance(loaded, list):
            raise HTTPException(status_code=400, detail="Events JSON must be a list or {Events:[...]}")
        events.extend(e for e in loaded if isinstance(e, dict))

    prefs = load_ui_preferences(settings.data_dir)
    db = get_database()
    rofl_id, _ = game_id_from_rofl_path(prefs.fixed_target_rofl, db=db)
    game_id = infer_game_id(
        body.original_match_id,
        events_meta.get("game_id"),
        rofl_id,
        events_path.parent if events_path else None,
        body.source_video_path,
        prefs.last_game_id,
    )

    output_dir = body.output_dir
    if output_dir is None and game_id:
        layout = resolve_output_layout(
            prefs.last_output_root,
            fallback=settings.resolved_clips_dir(),
        )
        layout.ensure()
        output_dir = str(layout.clip_dir(game_id))

    create_body = CreateClipsRequest(
        source_video_path=body.source_video_path,
        output_dir=output_dir,
        original_match_id=game_id or body.original_match_id,
        replay_db_id=body.replay_db_id,
        padding_before_sec=body.padding_before_sec,
        padding_after_sec=body.padding_after_sec,
        merge_gap_sec=body.merge_gap_sec,
        merge_fights=body.merge_fights,
        events=events,
        dry_run=body.dry_run,
    )
    return api_create_clips(create_body)

@app.get("/api/events/live")
def api_events_live() -> dict:
    """Return current Live Client events (empty/unavailable when LoL is not running)."""
    status, _ = fetch_live_events()
    return status.model_dump()


@app.post("/api/events/harvest")
def api_events_harvest(speed: float = 16.0) -> dict:
    """
    Play the open replay from the start at high speed and accumulate events.

    One-shot Live Client fetch at late game only sees recent EventTime values;
    this walk fills early kills/objectives. Requires EnableReplayApi=1.
    """
    if speed < 1.0 or speed > 32.0:
        raise HTTPException(status_code=400, detail="speed must be between 1 and 32")
    status, _ = harvest_events_playthrough(speed=speed)
    return status.model_dump()


@app.post("/api/events/export", response_model=ExportEventsResponse)
def api_events_export(body: ExportEventsRequest) -> ExportEventsResponse:
    """Fetch Live Client events (or use provided events) and write clip-compatible JSON.

    With ``include_stats`` (default True), also writes stats_bundle.json and
    stats_aggregated.json from a one-shot allgamedata snapshot.
    """
    prefs = load_ui_preferences(settings.data_dir)
    if prefs.last_output_root:
        default_root = Path(prefs.last_output_root)
    elif prefs.last_events_dir:
        # New: …/Event ; legacy: …/{gameId} — parent is the output base either way.
        default_root = Path(prefs.last_events_dir).parent
    else:
        default_root = settings.data_dir / "matches"
    layout = resolve_output_layout(default_root, fallback=default_root)
    db = get_database()
    rofl_id, _ = game_id_from_rofl_path(prefs.fixed_target_rofl, db=db)
    game_id = infer_game_id(
        body.game_id,
        prefs.last_game_id,
        rofl_id,
    )
    try:
        if game_id is None and body.output_path is None:
            # Last chance: Live Client payload may include a game id.
            live, _ = fetch_live_events()
            game_id = live.game_id
        if game_id is None and body.output_path is None:
            raise HTTPException(
                status_code=400,
                detail="game_id is required (ROFL meta/fingerprint, DB original id, or manual JP1-...)",
            )
        result = export_events_json(
            output_path=body.output_path,
            directory=body.directory or str(layout.root),
            filename=body.filename,
            events=body.events,
            game_id=game_id,
            game_time_sec=body.game_time_sec,
            source=body.source,
            default_dir=layout.root,
            include_stats=body.include_stats,
            harvest=body.harvest,
            harvest_speed=body.harvest_speed,
        )
    except HTTPException:
        raise
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"Failed to write events JSON: {exc}") from exc

    export_dir = str(Path(result.path).parent)
    # Prefer the configured base (Event's parent), not a legacy nested game folder.
    root_dir = (
        str(Path(export_dir).parent)
        if Path(export_dir).name == "Event"
        else str(layout.root)
    )
    changed = False
    if prefs.last_events_dir != export_dir:
        prefs.last_events_dir = export_dir
        changed = True
    if prefs.last_output_root != root_dir:
        prefs.last_output_root = root_dir
        changed = True
    if prefs.last_game_id != result.game_id:
        prefs.last_game_id = result.game_id
        changed = True
    if changed:
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


def _ui_preferences_response(prefs: UiPreferences) -> UiPreferencesModel:
    payload = prefs.model_dump()
    payload["settings_path"] = str(ui_preferences_path(settings.data_dir).resolve())
    return UiPreferencesModel.model_validate(payload)


@app.get("/api/ui/preferences", response_model=UiPreferencesModel)
def api_get_ui_preferences() -> UiPreferencesModel:
    return _ui_preferences_response(load_ui_preferences(settings.data_dir))


@app.patch("/api/ui/preferences", response_model=UiPreferencesModel)
def api_patch_ui_preferences(body: UiPreferencesPatch) -> UiPreferencesModel:
    """Merge only the fields present in the JSON body into ``ui_preferences.json``."""
    updates = body.model_dump(exclude_unset=True)
    saved = update_ui_preferences(settings.data_dir, updates)
    return _ui_preferences_response(saved)


@app.put("/api/ui/preferences", response_model=UiPreferencesModel)
def api_put_ui_preferences(body: UiPreferencesModel) -> UiPreferencesModel:
    """
    Merge preferences (same as PATCH).

    Full-document replace from a stale UI state used to wipe other folders; PUT
    now merges so existing keys are preserved unless explicitly sent.
    """
    updates = body.model_dump(exclude_unset=True, exclude={"settings_path"})
    # Legacy clients always send every key; treat null-only "clear all" carefully
    # by still merging — explicit null clears that key, omitted keys keep disk values.
    # When every field is present (typical JSON.stringify of full object), this
    # behaves like replace for those fields, which is what a deliberate full save wants.
    saved = update_ui_preferences(settings.data_dir, updates)
    return _ui_preferences_response(saved)


@app.post("/api/fs/list")
def api_fs_list(body: ListDirRequest) -> dict:
    try:
        entries = list_directory(Path(body.directory), suffixes=body.suffixes)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "directory": str(Path(body.directory).expanduser().resolve()),
        "entries": [e.model_dump() for e in entries],
    }


@app.post("/api/fs/pick-directory")
def api_fs_pick_directory(body: PickDirectoryRequest) -> dict:
    """Native OS folder dialog on the API host (local desktop use)."""
    selected = pick_directory(
        title=body.title or "フォルダを選択",
        initial=body.initial,
    )
    return {
        "path": selected,
        "cancelled": selected is None,
    }


@app.get("/api/tools/ffmpeg")
def api_ffmpeg_status() -> dict:
    return get_ffmpeg_status().model_dump()


def _persist_ffmpeg_path(ffmpeg_path: str | None) -> None:
    """Update saved ffmpeg_path while keeping other encoding preferences."""
    if not ffmpeg_path:
        return
    current = load_ffmpeg_settings(settings.data_dir)
    save_ffmpeg_settings(
        settings.data_dir,
        current.model_copy(update={"ffmpeg_path": ffmpeg_path}),
    )


@app.post("/api/tools/ffmpeg/install")
def api_ffmpeg_install(body: FfmpegInstallRequest | None = None) -> dict:
    destination = body.destination if body is not None else None
    try:
        result = install_ffmpeg_winget(destination=destination)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"ffmpeg install failed: {exc}") from exc
    if result.get("ok") and result.get("ffmpeg_path"):
        _persist_ffmpeg_path(str(result["ffmpeg_path"]))
    return result


@app.post("/api/tools/ffmpeg/move")
def api_ffmpeg_move(body: FfmpegMoveRequest) -> dict:
    try:
        result = move_ffmpeg_install(
            body.destination,
            source_exe=body.source_exe,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to move ffmpeg: {exc}") from exc
    if result.get("ffmpeg_path"):
        _persist_ffmpeg_path(str(result["ffmpeg_path"]))
    return result


@app.post("/api/tools/ffmpeg/add-to-path")
def api_ffmpeg_add_to_path() -> dict:
    try:
        status = add_discovered_ffmpeg_to_path()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return status.model_dump()


def _ffmpeg_settings_payload(cfg: FfmpegSettings) -> dict:
    ffmpeg = resolved_ffmpeg_path(cfg)
    if ffmpeg is None:
        status = get_ffmpeg_status()
        ffmpeg = Path(status.path) if status.found and status.path else None
    effective, codec = resolve_encode_backend(cfg.encoder, ffmpeg=ffmpeg)
    return {
        **cfg.model_dump(),
        "available_encoders": available_encode_backends(ffmpeg),
        "effective_encoder": effective,
        "effective_codec": codec,
    }


@app.get("/api/tools/ffmpeg/settings")
def api_get_ffmpeg_settings() -> dict:
    return _ffmpeg_settings_payload(load_ffmpeg_settings(settings.data_dir))


@app.put("/api/tools/ffmpeg/settings")
def api_put_ffmpeg_settings(body: FfmpegSettingsModel) -> dict:
    if body.ffmpeg_path:
        path = Path(body.ffmpeg_path).expanduser()
        if not path.is_file():
            raise HTTPException(status_code=400, detail=f"ffmpeg path not found: {path}")
    saved = save_ffmpeg_settings(
        settings.data_dir,
        FfmpegSettings.model_validate(body.model_dump()),
    )
    return _ffmpeg_settings_payload(saved)


@app.post("/api/tools/ffmpeg/settings/reset")
def api_reset_ffmpeg_settings() -> dict:
    saved = save_ffmpeg_settings(settings.data_dir, default_ffmpeg_settings())
    return _ffmpeg_settings_payload(saved)


@app.get("/api/stats/catalog")
def api_stats_catalog() -> dict:
    return {
        "positions": [p.value for p in Position],
        "position_labels": {p.value: POSITION_LABELS[p] for p in Position},
        "table_stat_keys": [
            {"key": k.value, "label": STAT_LABELS[k]} for k in TABLE_STAT_KEYS
        ],
        "series_stat_keys": [
            {"key": k.value, "label": STAT_LABELS[k]} for k in SERIES_STAT_KEYS
        ],
        "lck_radar_stat_keys": [
            {"key": k.value, "label": STAT_LABELS[k]} for k in LCK_RADAR_STAT_KEYS
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


@app.post("/api/stats/aggregate-folder")
def api_aggregate_stats_folder(body: AggregateFolderStatsRequest) -> dict:
    """Average all stats JSON files in a folder; apply lane roster fuzzy matching."""
    roster = None
    if body.apply_roster:
        roster = load_display_settings(settings.data_dir).roster_by_position
    try:
        result = aggregate_stats_folder(body.directory, roster_by_position=roster)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NotADirectoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result.model_dump(mode="json")


@app.post("/api/stats/enrich-scoreboard-ss", response_model=AggregatedReplayStats)
def api_enrich_scoreboard_ss(body: EnrichScoreboardSsRequest) -> AggregatedReplayStats:
    """OCR `{game_id}_ss.png` (データ tab) and merge DPM / DMG% into aggregated stats."""
    from pentaklip.stats.export import export_aggregated_stats, load_aggregated_stats
    from pentaklip.stats.scoreboard_ss import (
        apply_scoreboard_damage,
        enrich_aggregated_from_scoreboard_ss,
        find_scoreboard_ss,
        parse_scoreboard_ss,
    )

    aggregated_path = Path(body.aggregated_path) if body.aggregated_path else None
    stats_dir = Path(body.stats_dir) if body.stats_dir else None
    if aggregated_path is None and stats_dir is None:
        raise HTTPException(status_code=400, detail="Provide aggregated_path or stats_dir")

    if aggregated_path is not None:
        if not aggregated_path.is_file():
            raise HTTPException(status_code=404, detail=f"aggregated not found: {aggregated_path}")
        aggregated = load_aggregated_stats(aggregated_path)
        stats_dir = stats_dir or aggregated_path.parent
    else:
        assert stats_dir is not None
        if body.game_id:
            from pentaklip.paths import with_game_id_prefix

            candidate = stats_dir / with_game_id_prefix(body.game_id, "stats_aggregated.json")
            if not candidate.is_file():
                raise HTTPException(status_code=404, detail=f"aggregated not found: {candidate}")
            aggregated_path = candidate
            aggregated = load_aggregated_stats(candidate)
        else:
            raise HTTPException(status_code=400, detail="game_id required when using stats_dir alone")

    try:
        if body.ss_path:
            ss_path = Path(body.ss_path)
            parsed = parse_scoreboard_ss(ss_path)
            enriched = apply_scoreboard_damage(aggregated, parsed, image_path=ss_path)
        else:
            gid = body.game_id or aggregated.original_match_id
            if not gid:
                raise HTTPException(status_code=400, detail="game_id required to locate _ss.png")
            assert stats_dir is not None
            if find_scoreboard_ss(stats_dir, gid) is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"scoreboard SS not found under {stats_dir} for {gid}",
                )
            enriched = enrich_aggregated_from_scoreboard_ss(aggregated, stats_dir, gid)
            # enrich swallows errors — detect no-op
            if enriched == aggregated:
                sample = next(iter(enriched.players), None)
                if sample is None or sample.scalars.get("dpm") is None:
                    raise HTTPException(
                        status_code=422,
                        detail="scoreboard SS present but OCR/merge failed (see server logs)",
                    )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if body.write and aggregated_path is not None:
        export_aggregated_stats(enriched, aggregated_path)
    return enriched


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
