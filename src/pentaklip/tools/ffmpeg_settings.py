"""Persisted simple ffmpeg encoding / path settings."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

EncodeQuality = Literal["light", "standard", "high"]

QUALITY_PRESETS: dict[EncodeQuality, dict[str, str]] = {
    "light": {"preset": "veryfast", "crf": "28", "audio_bitrate": "128k"},
    "standard": {"preset": "fast", "crf": "20", "audio_bitrate": "192k"},
    "high": {"preset": "slow", "crf": "18", "audio_bitrate": "256k"},
}


class FfmpegSettings(BaseModel):
    """User-facing ffmpeg options used by convert / re-encode cuts."""

    ffmpeg_path: str | None = None
    quality: EncodeQuality = "standard"
    auto_convert_webm: bool = True


def _settings_path(data_dir: Path) -> Path:
    return data_dir / "ffmpeg_settings.json"


def default_ffmpeg_settings() -> FfmpegSettings:
    return FfmpegSettings()


def load_ffmpeg_settings(data_dir: Path) -> FfmpegSettings:
    path = _settings_path(data_dir)
    if not path.is_file():
        return default_ffmpeg_settings()
    return FfmpegSettings.model_validate(json.loads(path.read_text(encoding="utf-8")))


def save_ffmpeg_settings(data_dir: Path, settings: FfmpegSettings) -> FfmpegSettings:
    path = _settings_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(settings.model_dump_json(indent=2), encoding="utf-8")
    return settings


def encode_args_for_quality(quality: EncodeQuality) -> list[str]:
    preset = QUALITY_PRESETS[quality]
    return [
        "-c:v",
        "libx264",
        "-preset",
        preset["preset"],
        "-crf",
        preset["crf"],
        "-c:a",
        "aac",
        "-b:a",
        preset["audio_bitrate"],
        "-movflags",
        "+faststart",
    ]


def resolved_ffmpeg_path(settings: FfmpegSettings) -> Path | None:
    if not settings.ffmpeg_path:
        return None
    path = Path(settings.ffmpeg_path).expanduser()
    return path if path.is_file() else None
