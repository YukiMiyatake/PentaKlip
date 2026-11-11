"""Export / import per-replay stats bundles as JSON or YAML."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pentaklip.stats.models import AggregatedReplayStats, ReplayStatsBundle

Format = Literal["json", "yaml"]


def _dump(data: dict, path: Path, fmt: Format) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "json":
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return
    import yaml

    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def _load(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        import yaml

        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    if not isinstance(data, dict):
        raise TypeError(f"Expected mapping in {path}")
    return data


def export_replay_stats(
    bundle: ReplayStatsBundle,
    path: Path,
    *,
    fmt: Format | None = None,
) -> Path:
    resolved_fmt: Format
    if fmt is not None:
        resolved_fmt = fmt
    elif path.suffix.lower() in {".yaml", ".yml"}:
        resolved_fmt = "yaml"
    else:
        resolved_fmt = "json"
        if path.suffix == "":
            path = path.with_suffix(".json")
    _dump(bundle.model_dump(mode="json"), path, resolved_fmt)
    return path


def load_replay_stats(path: Path) -> ReplayStatsBundle:
    return ReplayStatsBundle.model_validate(_load(path))


def export_aggregated_stats(
    aggregated: AggregatedReplayStats,
    path: Path,
    *,
    fmt: Format | None = None,
) -> Path:
    resolved_fmt: Format
    if fmt is not None:
        resolved_fmt = fmt
    elif path.suffix.lower() in {".yaml", ".yml"}:
        resolved_fmt = "yaml"
    else:
        resolved_fmt = "json"
        if path.suffix == "":
            path = path.with_suffix(".json")
    _dump(aggregated.model_dump(mode="json"), path, resolved_fmt)
    return path


def load_aggregated_stats(path: Path) -> AggregatedReplayStats:
    return AggregatedReplayStats.model_validate(_load(path))
