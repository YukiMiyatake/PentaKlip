"""Minimal SQLite access layer."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS replays (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    original_match_id TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    local_replay_id TEXT,
    installed_path TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS highlights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    replay_id INTEGER NOT NULL REFERENCES replays(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    game_time_sec REAL NOT NULL,
    start_sec REAL NOT NULL,
    end_sec REAL NOT NULL,
    payload_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS exports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    highlight_id INTEGER NOT NULL REFERENCES highlights(id) ON DELETE CASCADE,
    output_path TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class Database:
    path: Path

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    def insert_replay(
        self,
        *,
        original_match_id: str,
        original_filename: str,
        local_replay_id: str | None = None,
        installed_path: str | None = None,
    ) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO replays (
                    original_match_id, original_filename, local_replay_id, installed_path, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    original_match_id,
                    original_filename,
                    local_replay_id,
                    installed_path,
                    _utc_now(),
                ),
            )
            return int(cur.lastrowid)

    def list_replays(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM replays ORDER BY id DESC"
            ).fetchall()
            return [dict(row) for row in rows]


_db: Database | None = None


def get_database(path: Path | None = None) -> Database:
    global _db
    if _db is None:
        from pentaklip.config import settings

        resolved = path or settings.resolved_database_path()
        _db = Database(path=resolved)
        _db.initialize()
    return _db
