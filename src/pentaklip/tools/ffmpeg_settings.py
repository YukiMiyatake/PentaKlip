"""Persisted simple ffmpeg encoding / path settings."""

from __future__ import annotations

import json
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

EncodeQuality = Literal["light", "standard", "high"]
EncodeBackend = Literal["auto", "nvenc", "qsv", "amf", "cpu"]

QUALITY_PRESETS: dict[EncodeQuality, dict[str, str]] = {
    "light": {"preset": "veryfast", "crf": "28", "audio_bitrate": "128k"},
    "standard": {"preset": "fast", "crf": "20", "audio_bitrate": "192k"},
    "high": {"preset": "slow", "crf": "18", "audio_bitrate": "256k"},
}

# NVENC p1=fastest … p7=slowest. QSV/AMF use their own preset names.
NVENC_PRESETS: dict[EncodeQuality, str] = {
    "light": "p1",
    "standard": "p4",
    "high": "p6",
}
QSV_PRESETS: dict[EncodeQuality, str] = {
    "light": "veryfast",
    "standard": "medium",
    "high": "slow",
}
AMF_QUALITY: dict[EncodeQuality, str] = {
    "light": "speed",
    "standard": "balanced",
    "high": "quality",
}

HW_ENCODER_CODECS: dict[str, str] = {
    "nvenc": "h264_nvenc",
    "qsv": "h264_qsv",
    "amf": "h264_amf",
}
AUTO_BACKEND_ORDER: tuple[EncodeBackend, ...] = ("nvenc", "amf", "qsv")


class FfmpegSettings(BaseModel):
    """User-facing ffmpeg options used by convert / re-encode cuts."""

    ffmpeg_path: str | None = None
    quality: EncodeQuality = "standard"
    # auto = prefer GPU (NVENC/AMF/QSV) then fall back to CPU libx264.
    encoder: EncodeBackend = "auto"
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


def resolved_ffmpeg_path(settings: FfmpegSettings) -> Path | None:
    if not settings.ffmpeg_path:
        return None
    path = Path(settings.ffmpeg_path).expanduser()
    return path if path.is_file() else None


@lru_cache(maxsize=8)
def probe_h264_encoder_names(ffmpeg_exe: str) -> frozenset[str]:
    """Return codec names like h264_nvenc that this ffmpeg binary lists."""
    try:
        completed = subprocess.run(
            [ffmpeg_exe, "-hide_banner", "-encoders"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError:
        return frozenset()
    text = f"{completed.stdout or ''}\n{completed.stderr or ''}"
    found: set[str] = set()
    for codec in ("h264_nvenc", "h264_qsv", "h264_amf", "libx264"):
        if codec in text:
            found.add(codec)
    return frozenset(found)


def clear_encoder_probe_cache() -> None:
    probe_h264_encoder_names.cache_clear()


def available_encode_backends(ffmpeg: Path | None) -> list[EncodeBackend]:
    """Backends the UI can offer (cpu always; GPU only if ffmpeg lists the encoder)."""
    backends: list[EncodeBackend] = ["auto", "cpu"]
    if ffmpeg is None or not ffmpeg.is_file():
        return backends
    names = probe_h264_encoder_names(str(ffmpeg))
    for backend, codec in HW_ENCODER_CODECS.items():
        if codec in names:
            backends.append(backend)  # type: ignore[arg-type]
    return backends


def resolve_encode_backend(
    preferred: EncodeBackend,
    *,
    available_codecs: frozenset[str] | None = None,
    ffmpeg: Path | None = None,
) -> tuple[EncodeBackend, str]:
    """
    Map settings.encoder → (effective backend, ffmpeg -c:v name).

    ``auto`` picks the first available of NVENC → AMF → QSV, else CPU.
    """
    codecs = available_codecs
    if codecs is None and ffmpeg is not None and ffmpeg.is_file():
        codecs = probe_h264_encoder_names(str(ffmpeg))
    codecs = codecs or frozenset({"libx264"})

    if preferred == "cpu":
        return "cpu", "libx264"
    if preferred in HW_ENCODER_CODECS:
        codec = HW_ENCODER_CODECS[preferred]
        if codec in codecs:
            return preferred, codec
        return "cpu", "libx264"
    # auto
    for backend in AUTO_BACKEND_ORDER:
        codec = HW_ENCODER_CODECS[backend]
        if codec in codecs:
            return backend, codec
    return "cpu", "libx264"


def encode_args_for_quality(
    quality: EncodeQuality,
    *,
    video_codec: str = "libx264",
) -> list[str]:
    preset = QUALITY_PRESETS[quality]
    audio = ["-c:a", "aac", "-b:a", preset["audio_bitrate"], "-movflags", "+faststart"]

    if video_codec == "libx264":
        return [
            "-c:v",
            "libx264",
            "-preset",
            preset["preset"],
            "-crf",
            preset["crf"],
            *audio,
        ]
    if video_codec == "h264_nvenc":
        return [
            "-c:v",
            "h264_nvenc",
            "-preset",
            NVENC_PRESETS[quality],
            "-rc",
            "vbr",
            "-cq",
            preset["crf"],
            "-b:v",
            "0",
            *audio,
        ]
    if video_codec == "h264_qsv":
        return [
            "-c:v",
            "h264_qsv",
            "-preset",
            QSV_PRESETS[quality],
            "-global_quality",
            preset["crf"],
            *audio,
        ]
    if video_codec == "h264_amf":
        return [
            "-c:v",
            "h264_amf",
            "-quality",
            AMF_QUALITY[quality],
            "-rc",
            "cqp",
            "-qp_i",
            preset["crf"],
            "-qp_p",
            preset["crf"],
            *audio,
        ]
    # Unknown codec: still try with a generic CRF-ish path via libx264.
    return encode_args_for_quality(quality, video_codec="libx264")


def encode_args_for_settings(
    settings: FfmpegSettings,
    *,
    ffmpeg: Path | None = None,
    force_cpu: bool = False,
) -> tuple[list[str], EncodeBackend, str]:
    """Build encode argv and report which backend/codec were chosen."""
    if force_cpu:
        backend, codec = "cpu", "libx264"
    else:
        backend, codec = resolve_encode_backend(settings.encoder, ffmpeg=ffmpeg)
    return encode_args_for_quality(settings.quality, video_codec=codec), backend, codec
