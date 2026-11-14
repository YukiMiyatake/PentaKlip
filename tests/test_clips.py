import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from pentaklip.api.app import app
from pentaklip.clips.service import ClipSegment, create_clips, plan_segments
from pentaklip.detect.models import HighlightCandidate, HighlightKind
from pentaklip.export.ffmpeg import ExportResult
from pentaklip.replay.install import InstallMode, install_replay, list_local_replays


def test_install_move_and_list_local(tmp_path: Path) -> None:
    source = tmp_path / "downloads" / "KR-123.rofl"
    source.parent.mkdir()
    source.write_bytes(b"rofl")
    replays = tmp_path / "Replays"

    result = install_replay(
        source,
        local_replay_id="JP1-999",
        replays_dir=replays,
        mode=InstallMode.MOVE,
    )
    assert result.mode == InstallMode.MOVE
    assert result.installed_path.exists()
    assert not source.exists()
    listed = list_local_replays(replays)
    assert len(listed) == 1
    assert listed[0].match_id == "JP1-999"


def test_plan_segments_from_events_and_manual() -> None:
    segments = plan_segments(
        events=[{"EventName": "ChampionKill", "EventTime": 100.0}],
        segments=[ClipSegment(kind="other", game_time_sec=50, start_sec=40, end_sec=60, label="manual")],
        padding_before_sec=10,
        padding_after_sec=10,
    )
    assert segments[0].label == "manual"
    assert segments[1].kind == "kill"
    assert segments[1].start_sec == 90.0
    assert segments[1].end_sec == 110.0


def test_create_clips_converts_webm_before_cut(tmp_path: Path) -> None:
    video = tmp_path / "match.webm"
    video.write_bytes(b"webm")
    out = tmp_path / "clips"
    converted = out / "match.mp4"

    with (
        patch(
            "pentaklip.clips.service.ensure_mp4_source",
            return_value=(
                converted,
                ExportResult(output_path=converted, command=["ffmpeg", "-i"]),
            ),
        ) as ensure_mock,
        patch(
            "pentaklip.clips.service.cut_clip",
            return_value=ExportResult(output_path=out / "x.mp4", command=["ffmpeg"]),
        ) as cut_mock,
    ):
        result = create_clips(
            video,
            output_dir=out,
            segments=[ClipSegment(kind="kill", game_time_sec=10, start_sec=5, end_sec=15)],
            dry_run=False,
        )
    ensure_mock.assert_called_once()
    cut_mock.assert_called_once()
    assert cut_mock.call_args.args[0] == converted
    assert result.converted is True
    assert result.original_source_video == video.resolve()


def test_create_clips_dry_run_and_mocked_ffmpeg(tmp_path: Path) -> None:
    video = tmp_path / "match.mp4"
    video.write_bytes(b"fake-video")
    out = tmp_path / "clips"

    dry = create_clips(
        video,
        output_dir=out,
        segments=[ClipSegment(kind="kill", game_time_sec=20, start_sec=10, end_sec=30, label="solo")],
        dry_run=True,
        match_id="JP1-1",
    )
    assert len(dry.clips) == 1
    assert dry.clips[0].output_path.name == "JP1-1_01_solo_0m10s-0m30s.mp4"

    with patch(
        "pentaklip.clips.service.cut_clip",
        return_value=ExportResult(output_path=out / "x.mp4", command=["ffmpeg"]),
    ) as mocked:
        result = create_clips(
            video,
            output_dir=out,
            highlights=[
                HighlightCandidate(
                    kind=HighlightKind.KILL,
                    game_time_sec=20,
                    start_sec=10,
                    end_sec=30,
                    label="ChampionKill",
                )
            ],
            dry_run=False,
        )
        mocked.assert_called_once()
        assert len(result.clips) == 1


def test_create_clips_requires_inputs(tmp_path: Path) -> None:
    video = tmp_path / "match.mp4"
    video.write_bytes(b"x")
    with pytest.raises(ValueError, match="No clip segments"):
        create_clips(video, output_dir=tmp_path / "out")


def test_clips_api_dry_run(tmp_path: Path) -> None:
    video = tmp_path / "game.mp4"
    video.write_bytes(b"video")
    client = TestClient(app)
    response = client.post(
        "/api/clips/create",
        json={
            "source_video_path": str(video),
            "output_dir": str(tmp_path / "out"),
            "dry_run": True,
            "segments": [{"start_sec": 5, "end_sec": 15, "kind": "kill", "label": "test"}],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["clip_count"] == 1
    assert body["clips"][0]["start_sec"] == 5


def test_auto_split_uses_clip_game_id_folder(tmp_path: Path, monkeypatch) -> None:
    import pentaklip.store.db as db_mod
    from pentaklip import config

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr(config.settings, "data_dir", data_dir)
    monkeypatch.setattr(db_mod, "_db", None)

    video = tmp_path / "rec_JP1-777.mp4"
    video.write_bytes(b"video")
    events = {
        "Events": [{"EventName": "ChampionKill", "EventTime": 30.0}],
        "meta": {"game_id": "JP1-777"},
    }
    events_path = tmp_path / "Event" / "JP1-777_events.json"
    events_path.parent.mkdir(parents=True)
    events_path.write_text(json.dumps(events), encoding="utf-8")
    out_root = tmp_path / "out"

    client = TestClient(app)
    prefs = client.get("/api/ui/preferences").json()
    prefs["last_output_root"] = str(out_root)
    prefs["fixed_target_rofl"] = None
    prefs["last_game_id"] = None
    assert client.put("/api/ui/preferences", json=prefs).status_code == 200

    response = client.post(
        "/api/clips/auto-split",
        json={
            "source_video_path": str(video),
            "events_path": str(events_path),
            "dry_run": True,
            "padding_before_sec": 5,
            "padding_after_sec": 5,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["game_id"] == "JP1-777"
    assert Path(body["output_dir"]) == (out_root / "Clip" / "JP1-777").resolve()
    assert body["clip_count"] == 1
    assert "0m25s-0m35s" in Path(body["clips"][0]["output_path"]).name


def test_install_api_supports_mode(tmp_path: Path) -> None:
    source = tmp_path / "NA1-42.rofl"
    source.write_bytes(b"rofl")
    client = TestClient(app)
    response = client.post(
        "/api/replays/install",
        json={
            "source_path": str(source),
            "local_replay_id": "JP1-7",
            "replays_dir": str(tmp_path / "Replays"),
            "mode": "copy",
            "dry_run": True,
        },
    )
    assert response.status_code == 200
    assert response.json()["original_match_id"] == "NA1-42"
    assert response.json()["mode"] == "copy"
