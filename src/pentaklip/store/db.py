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
        """Store the current replace mapping; one row per local slot (no history)."""
        with self.connect() as conn:
            if local_replay_id:
                conn.execute(
                    "DELETE FROM replays WHERE local_replay_id = ?",
                    (local_replay_id,),
                )
            if installed_path:
                try:
                    target = str(Path(installed_path).expanduser().resolve())
                except OSError:
                    target = installed_path
                conn.execute(
                    "DELETE FROM replays WHERE installed_path = ?",
                    (installed_path,),
                )
                if target != installed_path:
                    conn.execute(
                        "DELETE FROM replays WHERE installed_path = ?",
                        (target,),
                    )
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

    def find_replay_by_installed_path(self, installed_path: str | Path) -> dict[str, Any] | None:
        target = str(Path(installed_path).expanduser().resolve())
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM replays
                WHERE installed_path = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (target,),
            ).fetchone()
            if row is None:
                # Fallback: compare resolved paths in Python (slash / case differences).
                rows = conn.execute(
                    "SELECT * FROM replays ORDER BY id DESC"
                ).fetchall()
                for item in rows:
                    stored = item["installed_path"]
                    if not stored:
                        continue
                    try:
                        if Path(stored).expanduser().resolve() == Path(target):
                            return dict(item)
                    except OSError:
                        continue
                return None
            return dict(row)

    def find_replay_by_local_id(self, local_replay_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM replays
                WHERE local_replay_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (local_replay_id,),
            ).fetchone()
            return dict(row) if row else None

    def insert_highlight(
        self,
        *,
        replay_id: int,
        kind: str,
        game_time_sec: float,
        start_sec: float,
        end_sec: float,
        payload_json: str | None = None,
    ) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO highlights (
                    replay_id, kind, game_time_sec, start_sec, end_sec, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    replay_id,
                    kind,
                    game_time_sec,
                    start_sec,
                    end_sec,
                    payload_json,
                    _utc_now(),
                ),
            )
            return int(cur.lastrowid)

    def insert_export(self, *, highlight_id: int, output_path: str) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO exports (highlight_id, output_path, created_at)
                VALUES (?, ?, ?)
                """,
                (highlight_id, output_path, _utc_now()),
            )
            return int(cur.lastrowid)

    def list_exports(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT e.*, h.kind, h.game_time_sec, h.start_sec, h.end_sec
                FROM exports e
                JOIN highlights h ON h.id = e.highlight_id
                ORDER BY e.id DESC
                LIMIT ?
                """,
                (limit,),
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
