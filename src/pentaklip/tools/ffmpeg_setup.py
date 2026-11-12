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


def find_ffmpeg_under(root: Path | str) -> Path | None:
    """Locate ``ffmpeg.exe`` under an install root (bin/ or nested)."""
    base = Path(root).expanduser().resolve()
    if not base.exists():
        return None
    if base.is_file() and base.name.lower() == "ffmpeg.exe":
        return base
    direct = base / "ffmpeg.exe"
    if direct.is_file():
        return direct
    bin_exe = base / "bin" / "ffmpeg.exe"
    if bin_exe.is_file():
        return bin_exe
    matches = sorted(base.rglob("ffmpeg.exe"))
    return matches[0] if matches else None


def resolve_ffmpeg_install_root(ffmpeg_exe: Path | str) -> Path:
    """
    Infer the install folder to move/copy.

    ``…/bin/ffmpeg.exe`` → parent of ``bin``; otherwise the exe directory.
    """
    exe = Path(ffmpeg_exe).expanduser().resolve()
    if not exe.is_file():
        raise FileNotFoundError(f"ffmpeg executable not found: {exe}")
    if exe.parent.name.lower() == "bin":
        return exe.parent.parent
    return exe.parent


def install_ffmpeg_winget(*, destination: Path | str | None = None) -> dict:
    """Attempt winget install. Optional ``destination`` uses ``--location``."""
    winget = _winget_exe()
    if not winget:
        status = get_ffmpeg_status()
        return {
            "ok": False,
            "returncode": 127,
            "stdout": "",
            "stderr": "winget executable not found on PATH",
            "status": status.model_dump(),
            "ffmpeg_path": None,
            "destination": None,
        }

    dest: Path | None = None
    if destination:
        dest = Path(destination).expanduser().resolve()
        dest.mkdir(parents=True, exist_ok=True)

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
    if dest is not None:
        cmd.extend(["--location", str(dest)])

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
            "ffmpeg_path": None,
            "destination": str(dest) if dest else None,
        }
    except OSError as exc:
        status = get_ffmpeg_status()
        return {
            "ok": False,
            "returncode": 1,
            "stdout": "",
            "stderr": f"failed to start winget: {exc}",
            "status": status.model_dump(),
            "ffmpeg_path": None,
            "destination": str(dest) if dest else None,
        }

    stdout = _decode_output(proc.stdout)
    stderr = _decode_output(proc.stderr)

    located: Path | None = find_ffmpeg_under(dest) if dest is not None else None
    status = get_ffmpeg_status()
    path_note = ""
    if located is not None:
        try:
            add_to_user_path(located.parent)
        except OSError as exc:
            path_note = f"\nPATH update failed: {exc}"
        status = FfmpegStatus(
            found=True,
            path=str(located),
            version_line=_ffmpeg_version(str(located)),
            on_path=True,
            hints=list(status.hints),
        )
        path_note = (
            f"\nInstalled under {dest}; using {located}."
            + (" Added bin dir to user PATH." if not path_note else path_note)
        )
    elif status.found and status.path and not status.on_path:
        try:
            add_to_user_path(Path(status.path).parent)
            status = get_ffmpeg_status()
            path_note = "\nAlso added ffmpeg directory to user PATH."
        except OSError as exc:
            path_note = f"\nPATH update failed: {exc}"
        if dest is not None:
            path_note += (
                f"\nNote: winget may have ignored --location ({dest}); "
                f"detected ffmpeg at {status.path}."
            )

    ok = proc.returncode == 0 or status.found
    return {
        "ok": ok,
        "returncode": proc.returncode,
        "stdout": (stdout[-4000:] + path_note).strip(),
        "stderr": stderr[-2000:],
        "status": status.model_dump(),
        "ffmpeg_path": status.path,
        "destination": str(dest) if dest else None,
    }


def move_ffmpeg_install(
    destination: Path | str,
    *,
    source_exe: Path | str | None = None,
) -> dict:
    """
    Move the current ffmpeg install folder to ``destination``.

    ``destination`` is the new install root (created if missing). If it already
    contains files, the source folder is moved as ``destination/<old_name>``.
    """
    dest = Path(destination).expanduser().resolve()
    if source_exe:
        exe = Path(source_exe).expanduser().resolve()
    else:
        status = get_ffmpeg_status()
        if not status.found or not status.path:
            raise FileNotFoundError("ffmpeg executable not found; install or set path first")
        exe = Path(status.path).resolve()
    if not exe.is_file():
        raise FileNotFoundError(f"ffmpeg executable not found: {exe}")

    src_root = resolve_ffmpeg_install_root(exe)
    if dest == src_root:
        new_exe = find_ffmpeg_under(dest) or exe
        return {
            "ok": True,
            "moved": False,
            "source_root": str(src_root),
            "destination": str(dest),
            "ffmpeg_path": str(new_exe),
            "status": get_ffmpeg_status().model_dump(),
            "message": "Source and destination are the same; nothing moved.",
        }

    if src_root in dest.parents or dest == src_root:
        raise ValueError("Destination cannot be inside the current ffmpeg install folder")

    if dest.exists() and dest.is_file():
        raise ValueError(f"Destination is a file, not a folder: {dest}")

    if dest.exists() and any(dest.iterdir()):
        target = dest / src_root.name
        if target.exists():
            raise FileExistsError(f"Destination already exists: {target}")
    else:
        # Empty or missing: move/rename the install root onto dest.
        target = dest
        if target.exists() and not any(target.iterdir()):
            target.rmdir()

    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src_root), str(target))
    new_exe = find_ffmpeg_under(target)
    if new_exe is None:
        raise FileNotFoundError(
            f"Moved to {target} but ffmpeg.exe was not found underneath"
        )

    path_note = ""
    try:
        add_to_user_path(new_exe.parent)
        path_note = " Updated user PATH."
    except OSError as exc:
        path_note = f" PATH update failed: {exc}"

    status = FfmpegStatus(
        found=True,
        path=str(new_exe),
        version_line=_ffmpeg_version(str(new_exe)),
        on_path=True,
        hints=[],
    )
    return {
        "ok": True,
        "moved": True,
        "source_root": str(src_root),
        "destination": str(target),
        "ffmpeg_path": str(new_exe),
        "status": status.model_dump(),
        "message": f"Moved {src_root} → {target}.{path_note}",
    }


def add_discovered_ffmpeg_to_path() -> FfmpegStatus:
    status = get_ffmpeg_status()
    if not status.found or not status.path:
        raise FileNotFoundError("ffmpeg executable not found")
    add_to_user_path(Path(status.path).parent)
    # Ensure current process can resolve it immediately.
    os.environ["PATH"] = str(Path(status.path).parent) + os.pathsep + os.environ.get("PATH", "")
    return get_ffmpeg_status()
