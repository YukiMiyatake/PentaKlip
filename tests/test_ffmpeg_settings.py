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
