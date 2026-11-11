"""Plan and create highlight clips from a source video."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from pentaklip.detect.models import HighlightCandidate, HighlightKind
from pentaklip.detect.service import detect_from_events
from pentaklip.export.ffmpeg import ExportResult, cut_clip, ensure_mp4_source
from pentaklip.paths import unique_file_path


@dataclass(frozen=True)
class ClipSegment:
    kind: str
    game_time_sec: float
    start_sec: float
    end_sec: float
    label: str | None = None


@dataclass(frozen=True)
class CreatedClip:
    segment: ClipSegment
    output_path: Path
    export: ExportResult


@dataclass(frozen=True)
class ClipJobResult:
    source_video: Path
    output_dir: Path
    segments: list[ClipSegment]
    clips: list[CreatedClip]
    original_source_video: Path | None = None
    converted: bool = False


_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_slug(value: str | None, fallback: str) -> str:
    text = (value or fallback).strip() or fallback
    return _SAFE_NAME.sub("_", text)[:80]


def plan_segments(
    *,
    events: list[dict] | None = None,
    highlights: list[HighlightCandidate] | None = None,
    segments: list[ClipSegment] | None = None,
    padding_before_sec: float = 10.0,
    padding_after_sec: float = 10.0,
    merge_gap_sec: float = 25.0,
    merge_fights: bool = True,
) -> list[ClipSegment]:
    """
    Build clip segments from explicit ranges, highlight candidates, and/or events.

    Priority merge order: explicit segments, then highlights, then detected events.
    Detected events are fight-merged by default (nearby kills → one clip).
    """
    planned: list[ClipSegment] = []

    if segments:
        planned.extend(segments)

    if highlights:
        for item in highlights:
            planned.append(
                ClipSegment(
                    kind=item.kind.value if isinstance(item.kind, HighlightKind) else str(item.kind),
                    game_time_sec=item.game_time_sec,
                    start_sec=item.start_sec,
                    end_sec=item.end_sec,
                    label=item.label,
                )
            )

    if events:
        detected = detect_from_events(
            events,
            padding_before_sec=padding_before_sec,
            padding_after_sec=padding_after_sec,
            merge_gap_sec=merge_gap_sec,
            merge_fights=merge_fights,
        )
        for item in detected:
            planned.append(
                ClipSegment(
                    kind=item.kind.value,
                    game_time_sec=item.game_time_sec,
                    start_sec=item.start_sec,
                    end_sec=item.end_sec,
                    label=item.label,
                )
            )

    # Deduplicate identical windows
    unique: list[ClipSegment] = []
    seen: set[tuple[float, float, str]] = set()
    for seg in planned:
        if seg.end_sec <= seg.start_sec:
            raise ValueError(
                f"Invalid segment window: start={seg.start_sec}, end={seg.end_sec}"
            )
        key = (round(seg.start_sec, 3), round(seg.end_sec, 3), seg.kind)
        if key in seen:
            continue
        seen.add(key)
        unique.append(seg)

    unique.sort(key=lambda s: s.start_sec)
    return unique


def create_clips(
    source_video: Path,
    *,
    output_dir: Path,
    events: list[dict] | None = None,
    highlights: list[HighlightCandidate] | None = None,
    segments: list[ClipSegment] | None = None,
    padding_before_sec: float = 10.0,
    padding_after_sec: float = 10.0,
    merge_gap_sec: float = 25.0,
    merge_fights: bool = True,
    dry_run: bool = False,
    match_id: str | None = None,
) -> ClipJobResult:
    """
    Cut one clip file per planned segment from `source_video`.

    `source_video` is a full-match recording (or any timeline-aligned video).
    Automated LoL-client capture is out of scope here; feed a recorded file.
    """
    original_source = source_video.resolve()
    if not original_source.is_file():
        raise FileNotFoundError(f"Source video not found: {original_source}")

    planned = plan_segments(
        events=events,
        highlights=highlights,
        segments=segments,
        padding_before_sec=padding_before_sec,
        padding_after_sec=padding_after_sec,
        merge_gap_sec=merge_gap_sec,
        merge_fights=merge_fights,
    )
    if not planned:
        raise ValueError("No clip segments to create (provide events, highlights, or segments)")

    output_dir = output_dir.resolve()
    if not dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)

    converted = False
    if dry_run:
        source_video = original_source
    else:
        source_video, convert_result = ensure_mp4_source(
            original_source,
            cache_dir=output_dir,
        )
        converted = convert_result is not None

    prefix = _safe_slug(match_id, original_source.stem)
    created: list[CreatedClip] = []
    for index, seg in enumerate(planned, start=1):
        label = _safe_slug(seg.label or seg.kind, seg.kind)
        filename = f"{prefix}_{index:02d}_{label}_{int(seg.start_sec)}-{int(seg.end_sec)}.mp4"
        output_path = unique_file_path(output_dir / filename)
        if dry_run:
            created.append(
                CreatedClip(
                    segment=seg,
                    output_path=output_path,
                    export=ExportResult(output_path=output_path, command=[]),
                )
            )
            continue
        export = cut_clip(
            source_video,
            output_path,
            start_sec=seg.start_sec,
            end_sec=seg.end_sec,
        )
        created.append(CreatedClip(segment=seg, output_path=output_path, export=export))

    return ClipJobResult(
        source_video=source_video,
        output_dir=output_dir,
        segments=planned,
        clips=created,
        original_source_video=original_source,
        converted=converted,
    )
