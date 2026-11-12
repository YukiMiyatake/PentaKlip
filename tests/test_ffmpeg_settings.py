from pathlib import Path

from fastapi.testclient import TestClient

from pentaklip.api.app import app
from pentaklip.tools.ffmpeg_settings import (
    FfmpegSettings,
    encode_args_for_quality,
    load_ffmpeg_settings,
    resolve_encode_backend,
    save_ffmpeg_settings,
)


def test_encode_args_change_with_quality() -> None:
    light = encode_args_for_quality("light")
    high = encode_args_for_quality("high")
    assert "28" in light
    assert "18" in high
    assert light != high
    assert "libx264" in light


def test_encode_args_nvenc() -> None:
    args = encode_args_for_quality("standard", video_codec="h264_nvenc")
    assert "h264_nvenc" in args
    assert "-cq" in args


def test_resolve_auto_prefers_nvenc() -> None:
    backend, codec = resolve_encode_backend(
        "auto",
        available_codecs=frozenset({"h264_nvenc", "libx264"}),
    )
    assert backend == "nvenc"
    assert codec == "h264_nvenc"


def test_resolve_missing_hw_falls_back_to_cpu() -> None:
    backend, codec = resolve_encode_backend(
        "nvenc",
        available_codecs=frozenset({"libx264"}),
    )
    assert backend == "cpu"
    assert codec == "libx264"


def test_ffmpeg_settings_persist(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("PENTAKLIP_DATA_DIR", str(tmp_path))
    # Settings object is already constructed; write via helper path directly.
    saved = save_ffmpeg_settings(
        tmp_path,
        FfmpegSettings(
            quality="high",
            encoder="cpu",
            auto_convert_webm=False,
            ffmpeg_path=None,
        ),
    )
    loaded = load_ffmpeg_settings(tmp_path)
    assert loaded.quality == "high"
    assert loaded.encoder == "cpu"
    assert loaded.auto_convert_webm is False
    assert saved.quality == "high"


def test_ffmpeg_settings_api(tmp_path: Path, monkeypatch) -> None:
    from pentaklip import config

    monkeypatch.setattr(config.settings, "data_dir", tmp_path)
    client = TestClient(app)
    response = client.get("/api/tools/ffmpeg/settings")
    assert response.status_code == 200
    body = response.json()
    assert body["quality"] == "standard"
    assert body["encoder"] == "auto"
    assert "available_encoders" in body

    put = client.put(
        "/api/tools/ffmpeg/settings",
        json={
            "ffmpeg_path": None,
            "quality": "light",
            "encoder": "cpu",
            "auto_convert_webm": True,
        },
    )
    assert put.status_code == 200, put.text
    assert put.json()["quality"] == "light"
    assert put.json()["encoder"] == "cpu"

    reset = client.post("/api/tools/ffmpeg/settings/reset")
    assert reset.status_code == 200
    assert reset.json()["quality"] == "standard"
    assert reset.json()["encoder"] == "auto"


def test_find_and_resolve_ffmpeg_install_root(tmp_path: Path) -> None:
    from pentaklip.tools.ffmpeg_setup import find_ffmpeg_under, resolve_ffmpeg_install_root

    root = tmp_path / "ffmpeg-release"
    exe = root / "bin" / "ffmpeg.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"fake")
    assert find_ffmpeg_under(root) == exe.resolve()
    assert resolve_ffmpeg_install_root(exe) == root.resolve()


def test_move_ffmpeg_install(tmp_path: Path, monkeypatch) -> None:
    from pentaklip.tools import ffmpeg_setup

    src = tmp_path / "old-ffmpeg"
    exe = src / "bin" / "ffmpeg.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"fake")
    dest = tmp_path / "new-home"

    monkeypatch.setattr(ffmpeg_setup, "add_to_user_path", lambda directory: str(directory))
    monkeypatch.setattr(ffmpeg_setup, "_ffmpeg_version", lambda path: "ffmpeg version test")

    result = ffmpeg_setup.move_ffmpeg_install(dest, source_exe=exe)
    assert result["ok"] is True
    assert result["moved"] is True
    new_exe = Path(result["ffmpeg_path"])
    assert new_exe.is_file()
    assert new_exe == (dest / "bin" / "ffmpeg.exe").resolve()
    assert not src.exists()


def test_ffmpeg_move_api(tmp_path: Path, monkeypatch) -> None:
    from pentaklip import config
    from pentaklip.tools import ffmpeg_setup

    monkeypatch.setattr(config.settings, "data_dir", tmp_path)
    src = tmp_path / "pkg"
    exe = src / "bin" / "ffmpeg.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"fake")
    dest = tmp_path / "moved"

    monkeypatch.setattr(ffmpeg_setup, "add_to_user_path", lambda directory: str(directory))
    monkeypatch.setattr(ffmpeg_setup, "_ffmpeg_version", lambda path: "ffmpeg version test")

    client = TestClient(app)
    response = client.post(
        "/api/tools/ffmpeg/move",
        json={"destination": str(dest), "source_exe": str(exe)},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["moved"] is True
    assert Path(body["ffmpeg_path"]).is_file()
    saved = load_ffmpeg_settings(tmp_path)
    assert saved.ffmpeg_path == body["ffmpeg_path"]


def test_ffmpeg_install_passes_location(monkeypatch, tmp_path: Path) -> None:
    from pentaklip.tools import ffmpeg_setup

    captured: dict[str, object] = {}

    class FakeProc:
        returncode = 0
        stdout = b"ok"
        stderr = b""

    def fake_run(cmd: list[str], *, timeout: float | None = None):
        _ = timeout
        captured["cmd"] = cmd
        dest = Path(cmd[cmd.index("--location") + 1])
        exe = dest / "bin" / "ffmpeg.exe"
        exe.parent.mkdir(parents=True, exist_ok=True)
        exe.write_bytes(b"fake")
        return FakeProc()

    monkeypatch.setattr(ffmpeg_setup, "_winget_exe", lambda: "winget")
    monkeypatch.setattr(ffmpeg_setup, "_run", fake_run)
    monkeypatch.setattr(ffmpeg_setup, "add_to_user_path", lambda directory: str(directory))
    monkeypatch.setattr(ffmpeg_setup, "_ffmpeg_version", lambda path: "ffmpeg version test")

    dest = tmp_path / "custom"
    result = ffmpeg_setup.install_ffmpeg_winget(destination=dest)
    assert result["ok"] is True
    assert "--location" in captured["cmd"]  # type: ignore[operator]
    assert Path(result["ffmpeg_path"]).is_file()
    assert Path(result["ffmpeg_path"]).is_relative_to(dest.resolve())
