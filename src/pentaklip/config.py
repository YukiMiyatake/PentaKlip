"""Application settings."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def default_data_dir() -> Path:
    return Path.home() / "AppData" / "Local" / "PentaKlip"


def default_lol_replays_dir() -> Path:
    return Path.home() / "Documents" / "League of Legends" / "Replays"


def default_lol_highlights_dir() -> Path:
    """LoL client Highlights folder (typically .webm recordings)."""
    return Path.home() / "Documents" / "League of Legends" / "Highlights"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PENTAKLIP_", env_file=".env", extra="ignore")

    data_dir: Path = default_data_dir()
    lol_replays_dir: Path = default_lol_replays_dir()
    lol_highlights_dir: Path = default_lol_highlights_dir()
    database_path: Path | None = None
    live_client_base_url: str = "https://127.0.0.1:2999"
    clip_padding_before_sec: float = 10.0
    clip_padding_after_sec: float = 10.0
    clip_merge_gap_sec: float = 25.0
    clips_dir: Path | None = None

    def resolved_database_path(self) -> Path:
        if self.database_path is not None:
            return self.database_path
        return self.data_dir / "pentaklip.sqlite3"

    def resolved_clips_dir(self) -> Path:
        if self.clips_dir is not None:
            return self.clips_dir
        return self.data_dir / "clips"


settings = Settings()
