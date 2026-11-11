"""Detect / install ffmpeg and ensure it is on the user PATH (Windows-focused)."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from pydantic import BaseModel, Field


class FfmpegStatus(BaseModel):
    found: bool
    path: str | None = None
    version_line: str | None = None
    on_path: bool = False
    hints: list[str] = Field(default_factory=list)


def _ffmpeg_version(path: str) -> str | None:
    try:
        proc = subprocess.run(
            [path, "-version"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    line = (proc.stdout or "").splitlines()
    return line[0] if line else None


def get_ffmpeg_status() -> FfmpegStatus:
    which = shutil.which("ffmpeg")
    if which:
        return FfmpegStatus(
            found=True,
            path=which,
            version_line=_ffmpeg_version(which),
            on_path=True,
        )

    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Links" / "ffmpeg.exe",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "ffmpeg" / "bin" / "ffmpeg.exe",
        Path(os.environ.get("USERPROFILE", "")) / "scoop" / "shims" / "ffmpeg.exe",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return FfmpegStatus(
                found=True,
                path=str(candidate),
                version_line=_ffmpeg_version(str(candidate)),
                on_path=False,
                hints=[
                    "ffmpeg found but not on PATH. Call /api/tools/ffmpeg/add-to-path",
                ],
            )

    return FfmpegStatus(
        found=False,
        hints=[
            "Install with: winget install --id Gyan.FFmpeg -e",
            "Or: choco install ffmpeg",
            "Then reopen the terminal / call add-to-path",
        ],
    )


def add_to_user_path(directory: Path) -> str:
    directory = directory.resolve()
    if not directory.is_dir():
        raise FileNotFoundError(f"Directory not found: {directory}")

    current = os.environ.get("PATH", "")
    user_path = subprocess.check_output(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "[Environment]::GetEnvironmentVariable('Path','User')",
        ],
        text=True,
    ).strip()

    parts = [p for p in user_path.split(";") if p]
    dir_str = str(directory)
    if dir_str.lower() not in {p.lower() for p in parts}:
        parts.append(dir_str)
        new_path = ";".join(parts)
        # Pass via env var to avoid quoting issues with paths.
        env = os.environ.copy()
        env["PENTAKLIP_NEW_PATH"] = new_path
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "[Environment]::SetEnvironmentVariable('Path', $env:PENTAKLIP_NEW_PATH, 'User')",
            ],
            check=True,
            env=env,
        )
        os.environ["PATH"] = current + os.pathsep + dir_str
    return dir_str


def install_ffmpeg_winget() -> dict:
    """Attempt winget install. May require user approval / elevation."""
    cmd = [
        "winget",
        "install",
        "--id",
        "Gyan.FFmpeg",
        "-e",
        "--accept-package-agreements",
        "--accept-source-agreements",
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    status = get_ffmpeg_status()
    if status.found and status.path and not status.on_path:
        add_to_user_path(Path(status.path).parent)
        status = get_ffmpeg_status()
    return {
        "returncode": proc.returncode,
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-2000:],
        "status": status.model_dump(),
    }


def add_discovered_ffmpeg_to_path() -> FfmpegStatus:
    status = get_ffmpeg_status()
    if not status.found or not status.path:
        raise FileNotFoundError("ffmpeg executable not found")
    add_to_user_path(Path(status.path).parent)
    return get_ffmpeg_status()
