"""ffmpeg helpers for cutting highlight clips and transcoding sources."""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from pentaklip.tools.ffmpeg_settings import (
    EncodeBackend,
    EncodeQuality,
    FfmpegSettings,
    encode_args_for_settings,
    load_ffmpeg_settings,
    resolved_ffmpeg_path,
)

# Containers that usually need re-encode before reliable mp4 clip export.
TRANSCODE_TO_MP4_SUFFIXES = {".webm"}


def find_ffmpeg(explicit: Path | None = None) -> Path:
    if explicit is not None:
        return explicit

    # Prefer user-configured path from the ffmpeg settings tab.
    try:
        from pentaklip.config import settings as app_settings

        configured = resolved_ffmpeg_path(load_ffmpeg_settings(app_settings.data_dir))
        if configured is not None:
            return configured
    except Exception as settings_exc:  # noqa: BLE001 - settings optional in tests
        _ = settings_exc

    found = shutil.which("ffmpeg")
    if found:
        return Path(found)

    # API process often starts before user PATH is refreshed; reuse Tools discovery.
    from pentaklip.tools.ffmpeg_setup import get_ffmpeg_status

    status = get_ffmpeg_status()
    if status.found and status.path:
        return Path(status.path)

    raise FileNotFoundError(
        "ffmpeg not found on PATH. Use the ffmpeg tab to install / Add to PATH / set path, "
        "then retry (or restart the API)."
    )


@dataclass(frozen=True)
class ExportResult:
    output_path: Path
    command: list[str]


def _run_ffmpeg(command: list[str]) -> None:
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        raise RuntimeError(f"ffmpeg failed: {detail or exc}") from exc


def _active_settings() -> FfmpegSettings:
    try:
        from pentaklip.config import settings as app_settings

        return load_ffmpeg_settings(app_settings.data_dir)
    except Exception as settings_exc:  # noqa: BLE001
        _ = settings_exc
        return FfmpegSettings()


def _run_reencode(
    ffmpeg: Path,
    build_cmd: Callable[[list[str]], list[str]],
    *,
    cfg: FfmpegSettings,
) -> list[str]:
    """Run GPU/CPU encode; auto (and missing HW) fall back to libx264 on failure."""
    args, backend, _codec = encode_args_for_settings(cfg, ffmpeg=ffmpeg)
    command = build_cmd(args)
    try:
        _run_ffmpeg(command)
        return command
    except RuntimeError:
        if backend == "cpu":
            raise
        # GPU encoder missing/failed (auto or explicit): retry once with libx264.
        cpu_args, _, _ = encode_args_for_settings(cfg, ffmpeg=ffmpeg, force_cpu=True)
        command = build_cmd(cpu_args)
        _run_ffmpeg(command)
        return command


def convert_to_mp4(
    source: Path,
    output: Path,
    *,
    ffmpeg_path: Path | None = None,
    quality: EncodeQuality | None = None,
    encoder: EncodeBackend | None = None,
) -> ExportResult:
    """Transcode ``source`` (e.g. webm) to H.264/AAC mp4 for reliable cutting."""
    source = source.resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Source video not found: {source}")

    cfg = _active_settings()
    if quality is not None:
        cfg = cfg.model_copy(update={"quality": quality})
    if encoder is not None:
        cfg = cfg.model_copy(update={"encoder": encoder})
    ffmpeg = find_ffmpeg(ffmpeg_path or resolved_ffmpeg_path(cfg))

    output.parent.mkdir(parents=True, exist_ok=True)

    def build(encode_args: list[str]) -> list[str]:
        return [
            str(ffmpeg),
            "-y",
            "-i",
            str(source),
            *encode_args,
            str(output),
        ]

    command = _run_reencode(ffmpeg, build, cfg=cfg)
    return ExportResult(output_path=output.resolve(), command=command)


def ensure_mp4_source(
    source: Path,
    *,
    cache_dir: Path | None = None,
    ffmpeg_path: Path | None = None,
    force: bool = False,
    quality: EncodeQuality | None = None,
    encoder: EncodeBackend | None = None,
    name_prefix: str | None = None,
) -> tuple[Path, ExportResult | None]:
    """
    Return an mp4 path suitable for clip cutting.

    webm (and similar) are transcoded once next to the source or under ``cache_dir``.
    Existing newer mp4 caches are reused.
    """
    source = source.resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Source video not found: {source}")

    suffix = source.suffix.lower()
    if suffix == ".mp4":
        return source, None
    if suffix not in TRANSCODE_TO_MP4_SUFFIXES:
        # mkv/mov/avi: keep original; cut_clip may stream-copy or re-encode on failure.
        return source, None

    cfg = _active_settings()
    if not cfg.auto_convert_webm:
        return source, None

    dest_dir = cache_dir.resolve() if cache_dir is not None else source.parent
    dest_dir.mkdir(parents=True, exist_ok=True)
    stem = source.stem
    if name_prefix:
        from pentaklip.paths import with_game_id_prefix

        stem = with_game_id_prefix(name_prefix, f"{stem}.mp4").removesuffix(".mp4")
    dest = dest_dir / f"{stem}.mp4"
    if (
        not force
        and dest.is_file()
        and dest.stat().st_mtime >= source.stat().st_mtime
        and dest.stat().st_size > 0
    ):
        return dest, None

    result = convert_to_mp4(
        source,
        dest,
        ffmpeg_path=ffmpeg_path,
        quality=quality,
        encoder=encoder,
    )
    return result.output_path, result


def cut_clip(
    source: Path,
    output: Path,
    *,
    start_sec: float,
    end_sec: float,
    ffmpeg_path: Path | None = None,
    reencode: bool | None = None,
    quality: EncodeQuality | None = None,
    encoder: EncodeBackend | None = None,
) -> ExportResult:
    """
    Cut [start_sec, end_sec) from ``source`` into ``output``.

    Tries stream copy first for speed; falls back to H.264/AAC re-encode
    (required for many webm sources and keyframe-misaligned cuts).
    """
    if end_sec <= start_sec:
        raise ValueError("end_sec must be greater than start_sec")

    cfg = _active_settings()
    if quality is not None:
        cfg = cfg.model_copy(update={"quality": quality})
    if encoder is not None:
        cfg = cfg.model_copy(update={"encoder": encoder})
    ffmpeg = find_ffmpeg(ffmpeg_path or resolved_ffmpeg_path(cfg))
    output.parent.mkdir(parents=True, exist_ok=True)
    duration = end_sec - start_sec
    prefer_reencode = (
        reencode if reencode is not None else source.suffix.lower() in TRANSCODE_TO_MP4_SUFFIXES
    )

    def build_copy() -> list[str]:
        return [
            str(ffmpeg),
            "-y",
            "-ss",
            f"{start_sec:.3f}",
            "-i",
            str(source),
            "-t",
            f"{duration:.3f}",
            "-c",
            "copy",
            str(output),
        ]

    def build_reencode(encode_args: list[str]) -> list[str]:
        return [
            str(ffmpeg),
            "-y",
            "-ss",
            f"{start_sec:.3f}",
            "-i",
            str(source),
            "-t",
            f"{duration:.3f}",
            *encode_args,
            str(output),
        ]

    if prefer_reencode:
        command = _run_reencode(ffmpeg, build_reencode, cfg=cfg)
        return ExportResult(output_path=output, command=command)

    command = build_copy()
    try:
        _run_ffmpeg(command)
    except RuntimeError:
        command = _run_reencode(ffmpeg, build_reencode, cfg=cfg)
    return ExportResult(output_path=output, command=command)
