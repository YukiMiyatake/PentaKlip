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


def _decode_output(raw: bytes | str | None) -> str:
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    for encoding in ("utf-8", "cp932", "mbcs"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _run(cmd: list[str], *, timeout: float | None = None) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        timeout=timeout,
    )


def _ffmpeg_version(path: str) -> str | None:
    try:
        proc = _run([path, "-version"], timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return None
    text = _decode_output(proc.stdout)
    line = text.splitlines()
    return line[0] if line else None


def _winget_exe() -> str | None:
    return shutil.which("winget")


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
        Path(os.environ.get("LOCALAPPDATA", ""))
        / "Microsoft"
        / "WinGet"
        / "Packages",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "ffmpeg" / "bin" / "ffmpeg.exe",
        Path(os.environ.get("USERPROFILE", "")) / "scoop" / "shims" / "ffmpeg.exe",
    ]

    # Expand WinGet Packages/*/ffmpeg*/**/ffmpeg.exe lightly
    expanded: list[Path] = []
    for candidate in candidates:
        if candidate.name == "Packages" and candidate.is_dir():
            expanded.extend(candidate.glob("Gyan.FFmpeg*/**/ffmpeg.exe"))
            expanded.extend(candidate.glob("Gyan.FFmpeg*/**/bin/ffmpeg.exe"))
        else:
            expanded.append(candidate)

    for candidate in expanded:
        if candidate.is_file():
            return FfmpegStatus(
                found=True,
                path=str(candidate),
                version_line=_ffmpeg_version(str(candidate)),
                on_path=False,
                hints=[
                    "ffmpeg found but not on PATH. Click Add to PATH.",
                ],
            )

    hints = [
        "Install with: winget install --id Gyan.FFmpeg -e",
        "Or: choco install ffmpeg",
        "Then reopen the terminal / use「PATH に追加」",
    ]
    if not _winget_exe():
        hints.insert(0, "winget was not found on PATH in this process")

    return FfmpegStatus(found=False, hints=hints)


def add_to_user_path(directory: Path) -> str:
    directory = directory.resolve()
    if not directory.is_dir():
        raise FileNotFoundError(f"Directory not found: {directory}")

    current = os.environ.get("PATH", "")
    user_path = _decode_output(
        subprocess.check_output(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "[Environment]::GetEnvironmentVariable('Path','User')",
            ],
        )
    ).strip()

    parts = [p for p in user_path.split(";") if p]
    dir_str = str(directory)
    if dir_str.lower() not in {p.lower() for p in parts}:
        parts.append(dir_str)
        new_path = ";".join(parts)
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

    # Always ensure the current process can resolve ffmpeg immediately.
    process_parts = [p for p in current.split(os.pathsep) if p]
    if dir_str.lower() not in {p.lower() for p in process_parts}:
        os.environ["PATH"] = dir_str + os.pathsep + current
    return dir_str


def install_ffmpeg_winget() -> dict:
    """Attempt winget install. May require user approval / elevation."""
    winget = _winget_exe()
    if not winget:
        status = get_ffmpeg_status()
        return {
            "ok": False,
            "returncode": 127,
            "stdout": "",
            "stderr": "winget executable not found on PATH",
            "status": status.model_dump(),
        }

    cmd = [
        winget,
        "install",
        "--id",
        "Gyan.FFmpeg",
        "-e",
        "--accept-package-agreements",
        "--accept-source-agreements",
        "--disable-interactivity",
    ]
    try:
        proc = _run(cmd, timeout=600)
    except subprocess.TimeoutExpired:
        status = get_ffmpeg_status()
        return {
            "ok": False,
            "returncode": 124,
            "stdout": "",
            "stderr": "winget install timed out after 600s",
            "status": status.model_dump(),
        }
    except OSError as exc:
        status = get_ffmpeg_status()
        return {
            "ok": False,
            "returncode": 1,
            "stdout": "",
            "stderr": f"failed to start winget: {exc}",
            "status": status.model_dump(),
        }

    stdout = _decode_output(proc.stdout)
    stderr = _decode_output(proc.stderr)
    status = get_ffmpeg_status()
    path_note = ""
    if status.found and status.path and not status.on_path:
        try:
            add_to_user_path(Path(status.path).parent)
            status = get_ffmpeg_status()
            path_note = "\nAlso added ffmpeg directory to user PATH."
        except OSError as exc:
            path_note = f"\nPATH update failed: {exc}"

    ok = proc.returncode == 0 or status.found
    return {
        "ok": ok,
        "returncode": proc.returncode,
        "stdout": (stdout[-4000:] + path_note).strip(),
        "stderr": stderr[-2000:],
        "status": status.model_dump(),
    }


def add_discovered_ffmpeg_to_path() -> FfmpegStatus:
    status = get_ffmpeg_status()
    if not status.found or not status.path:
        raise FileNotFoundError("ffmpeg executable not found")
    add_to_user_path(Path(status.path).parent)
    # Ensure current process can resolve it immediately.
    os.environ["PATH"] = str(Path(status.path).parent) + os.pathsep + os.environ.get("PATH", "")
    return get_ffmpeg_status()
