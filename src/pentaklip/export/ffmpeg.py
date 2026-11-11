"""ffmpeg helpers for cutting highlight clips."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


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


def cut_clip(
    source: Path,
    output: Path,
    *,
    start_sec: float,
    end_sec: float,
    ffmpeg_path: Path | None = None,
) -> ExportResult:
    """
    Cut [start_sec, end_sec) from `source` into `output`.

    Uses stream copy when possible for speed; re-encode may be added later for Shorts.
    """
    if end_sec <= start_sec:
        raise ValueError("end_sec must be greater than start_sec")

    ffmpeg = find_ffmpeg(ffmpeg_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    duration = end_sec - start_sec
    command = [
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
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        raise RuntimeError(f"ffmpeg failed: {detail or exc}") from exc
    return ExportResult(output_path=output, command=command)
