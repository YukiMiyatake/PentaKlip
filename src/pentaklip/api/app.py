"""FastAPI application."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from pentaklip import __version__
from pentaklip.api.schemas import (
    DetectRequest,
    DetectResponse,
    HealthResponse,
    InstallReplayRequest,
    InstallReplayResponse,
)
from pentaklip.config import settings
from pentaklip.detect.service import detect_from_events
from pentaklip.replay.install import install_replay
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
