"""ffmpeg helpers for cutting highlight clips and transcoding sources."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

# Containers that usually need re-encode before reliable mp4 clip export.
TRANSCODE_TO_MP4_SUFFIXES = {".webm"}


def find_ffmpeg(explicit: Path | None = None) -> Path:
    if explicit is not None:
        return explicit
    found = shutil.which("ffmpeg")
    if not found:
        raise FileNotFoundError(
            "ffmpeg not found on PATH. Install ffmpeg or bundle it next to the app."
        )
    return Path(found)


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


def convert_to_mp4(
    source: Path,
    output: Path,
    *,
    ffmpeg_path: Path | None = None,
) -> ExportResult:
    """Transcode ``source`` (e.g. webm) to H.264/AAC mp4 for reliable cutting."""
    source = source.resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Source video not found: {source}")

    ffmpeg = find_ffmpeg(ffmpeg_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(ffmpeg),
        "-y",
        "-i",
        str(source),
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "20",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        str(output),
    ]
    _run_ffmpeg(command)
    return ExportResult(output_path=output.resolve(), command=command)


def ensure_mp4_source(
    source: Path,
    *,
    cache_dir: Path | None = None,
    ffmpeg_path: Path | None = None,
    force: bool = False,
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

    dest_dir = cache_dir.resolve() if cache_dir is not None else source.parent
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{source.stem}.mp4"
    if (
        not force
        and dest.is_file()
        and dest.stat().st_mtime >= source.stat().st_mtime
        and dest.stat().st_size > 0
    ):
        return dest, None

    result = convert_to_mp4(source, dest, ffmpeg_path=ffmpeg_path)
    return result.output_path, result


def cut_clip(
    source: Path,
    output: Path,
    *,
    start_sec: float,
    end_sec: float,
    ffmpeg_path: Path | None = None,
    reencode: bool | None = None,
) -> ExportResult:
    """
    Cut [start_sec, end_sec) from ``source`` into ``output``.

    Tries stream copy first for speed; falls back to H.264/AAC re-encode
    (required for many webm sources and keyframe-misaligned cuts).
    """
    if end_sec <= start_sec:
        raise ValueError("end_sec must be greater than start_sec")

    ffmpeg = find_ffmpeg(ffmpeg_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    duration = end_sec - start_sec
    prefer_reencode = (
        reencode if reencode is not None else source.suffix.lower() in TRANSCODE_TO_MP4_SUFFIXES
    )

    def build(reencode_mode: bool) -> list[str]:
        cmd = [
            str(ffmpeg),
            "-y",
            "-ss",
            f"{start_sec:.3f}",
            "-i",
            str(source),
            "-t",
            f"{duration:.3f}",
        ]
        if reencode_mode:
            cmd.extend(
                [
                    "-c:v",
                    "libx264",
                    "-preset",
                    "fast",
                    "-crf",
                    "20",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "192k",
                    "-movflags",
                    "+faststart",
                ]
            )
        else:
            cmd.extend(["-c", "copy"])
        cmd.append(str(output))
        return cmd

    if prefer_reencode:
        command = build(True)
        _run_ffmpeg(command)
        return ExportResult(output_path=output, command=command)

    command = build(False)
    try:
        _run_ffmpeg(command)
    except RuntimeError:
        command = build(True)
        _run_ffmpeg(command)
    return ExportResult(output_path=output, command=command)
