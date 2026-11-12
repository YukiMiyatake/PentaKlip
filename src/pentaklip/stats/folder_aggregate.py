"""Load and average all stats files found in a directory."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

from pydantic import BaseModel, Field

from pentaklip.stats.aggregate import aggregate_replay, merge_aggregates
from pentaklip.stats.catalog import Position
from pentaklip.stats.export import load_aggregated_stats, load_replay_stats
from pentaklip.stats.models import AggregatedReplayStats, PlayerPositionAggregate
from pentaklip.stats.roster import remap_aggregate_to_roster


class FolderAggregateResult(BaseModel):
    directory: str
    file_count: int
    files: list[str] = Field(default_factory=list)
    game_count: int
    aggregated: AggregatedReplayStats
    players: list[PlayerPositionAggregate] = Field(default_factory=list)


def _load_one_aggregated(path: Path) -> AggregatedReplayStats | None:
    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    if isinstance(data.get("aggregated"), dict):
        try:
            return AggregatedReplayStats.model_validate(data["aggregated"])
        except Exception:
            logger.debug('invalid aggregated block', exc_info=True)
    if "snapshots" in data or (
        "schema_version" in data and "events" in data and "players" not in data
    ):
        try:
            return aggregate_replay(load_replay_stats(path))
        except Exception:  # noqa: BLE001
            return None
    if "game_duration_sec" in data and "players" in data:
        try:
            return load_aggregated_stats(path)
        except Exception:  # noqa: BLE001
            try:
                return AggregatedReplayStats.model_validate(data)
            except Exception:  # noqa: BLE001
                return None
    return None


def _game_key_from_stats_filename(path: Path) -> str:
    """
    Collapse ``JP1-1_stats_aggregated`` / ``JP1-1_stats_aggregated-2`` to one key.

    Also works for ``*_stats_bundle(-N)``.
    """
    stem = path.stem
    lower = stem.lower()
    for marker in ("_stats_aggregated", "_stats_bundle"):
        idx = lower.rfind(marker)
        if idx > 0:
            return stem[:idx]
    return stem


def _stats_suffix_rank(stem: str) -> int:
    """``foo_stats_aggregated-2`` → 2; canonical (no ``-N``) → 0."""
    match = re.search(r"-(\d+)$", stem)
    return int(match.group(1)) if match else 0


def _prefer_stats_path(current: Path | None, candidate: Path) -> Path:
    """Prefer newer mtime; ties → higher ``-N`` re-export (newer than canonical)."""
    if current is None:
        return candidate

    def rank(path: Path) -> tuple[float, int]:
        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = 0.0
        return (mtime, _stats_suffix_rank(path.stem))

    return candidate if rank(candidate) >= rank(current) else current


def _dedupe_one_file_per_game(paths: list[Path]) -> list[Path]:
    by_game: dict[str, Path] = {}
    for path in paths:
        key = _game_key_from_stats_filename(path)
        by_game[key] = _prefer_stats_path(by_game.get(key), path)
    return sorted(by_game.values(), key=lambda p: p.name.lower())


def discover_stats_files(directory: Path) -> list[Path]:
    """Prefer ``*_stats_aggregated.json``, else bundles; **one file per game_id**."""
    root = directory.resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"Not a directory: {root}")
    aggregated = (
        sorted(root.glob("*_stats_aggregated.json"))
        + sorted(root.glob("*_stats_aggregated-*.json"))
        + sorted(root.glob("stats_aggregated.json"))
    )
    # Dedupe by resolve then by game id (drop stale -1/-2 copies).
    seen: set[Path] = set()
    files: list[Path] = []
    for path in aggregated:
        key = path.resolve()
        if key in seen:
            continue
        seen.add(key)
        files.append(path)
    if files:
        return _dedupe_one_file_per_game(files)
    bundles = (
        sorted(root.glob("*_stats_bundle.json"))
        + sorted(root.glob("*_stats_bundle-*.json"))
        + sorted(root.glob("stats_bundle.json"))
    )
    for path in bundles:
        key = path.resolve()
        if key in seen:
            continue
        seen.add(key)
        files.append(path)
    return _dedupe_one_file_per_game(files)


def average_merged_players(
    merged: list[PlayerPositionAggregate],
    *,
    game_count: int,
) -> list[PlayerPositionAggregate]:
    """
    Turn merge_aggregates sums into per-game averages for countable stats.

    Rates (KDA, CS/min, …) are left as computed on totals (equivalent to
    duration-weighted averages).
    """
    if game_count <= 0:
        return merged
    avg_keys = {
        "kills",
        "deaths",
        "assists",
        "creep_score",
        "ward_score",
        "dragon_kills",
        "baron_kills",
        "herald_kills",
        "tower_kills",
        "inhibitor_kills",
        "damage_to_champions",
    }
    out: list[PlayerPositionAggregate] = []
    for player in merged:
        scalars = dict(player.scalars)
        for key in avg_keys:
            if key not in scalars:
                continue
            raw = scalars[key]
            if isinstance(raw, (int, float)):
                scalars[key] = round(float(raw) / game_count, 2)
        out.append(player.model_copy(update={"scalars": scalars}))
    return out


def _game_id_from_stats_path(path: Path, loaded: AggregatedReplayStats) -> str | None:
    if loaded.original_match_id:
        return str(loaded.original_match_id)
    stem = path.stem
    lower = stem.lower()
    for marker in ("_stats_aggregated", "_stats_bundle", "_aggregated", "_bundle"):
        idx = lower.rfind(marker)
        if idx > 0:
            return stem[:idx]
    return None


def _player_has_damage(player: PlayerPositionAggregate) -> bool:
    return player.scalars.get("dpm") is not None or player.scalars.get(
        "damage_to_champions"
    ) is not None


def _enrich_loaded_with_scoreboard_ss(
    loaded: AggregatedReplayStats,
    *,
    stats_dir: Path,
    source_path: Path,
) -> tuple[AggregatedReplayStats, bool]:
    """OCR ``{game_id}*.png`` into damage scalars; optionally rewrite aggregated JSON."""
    from pentaklip.stats.export import export_aggregated_stats
    from pentaklip.stats.scoreboard_ss import enrich_aggregated_from_scoreboard_ss

    if any(_player_has_damage(player) for player in loaded.players):
        return loaded, False

    game_id = _game_id_from_stats_path(source_path, loaded)
    if not game_id:
        return loaded, False

    enriched = enrich_aggregated_from_scoreboard_ss(loaded, stats_dir, game_id)
    if not any(_player_has_damage(player) for player in enriched.players):
        return enriched, False

    # Persist so subsequent loads keep DPM/DMG% without re-OCR.
    if source_path.name.lower().endswith("_stats_aggregated.json"):
        try:
            export_aggregated_stats(enriched, source_path)
        except OSError:
            logger.exception("failed to rewrite enriched aggregate %s", source_path)
    return enriched, True


def aggregate_stats_folder(
    directory: Path | str,
    *,
    roster_by_position: dict[Position, list[str]] | None = None,
) -> FolderAggregateResult:
    root = Path(directory).expanduser().resolve()
    files = discover_stats_files(root)
    parts: list[AggregatedReplayStats] = []
    used: list[str] = []
    ss_enriched = 0
    for path in files:
        loaded = _load_one_aggregated(path)
        if loaded is None:
            continue
        loaded, did_enrich = _enrich_loaded_with_scoreboard_ss(
            loaded, stats_dir=root, source_path=path
        )
        if did_enrich:
            ss_enriched += 1
        remapped = remap_aggregate_to_roster(loaded, roster_by_position)
        parts.append(remapped)
        used.append(str(path))
    if not parts:
        raise FileNotFoundError(
            f"No readable stats JSON in {root} "
            "(expected *_stats_aggregated.json or *_stats_bundle.json)"
        )

    merged_players = merge_aggregates(parts)
    averaged = average_merged_players(merged_players, game_count=len(parts))
    duration = sum(p.game_duration_sec for p in parts) / max(len(parts), 1)
    team_totals: dict[str, dict[str, float]] = {}
    for part in parts:
        for team, vals in (part.team_totals or {}).items():
            bucket = team_totals.setdefault(team, {})
            for k, v in vals.items():
                bucket[k] = float(bucket.get(k) or 0) + float(v or 0)
    for team, vals in team_totals.items():
        for k, v in list(vals.items()):
            vals[k] = round(v / len(parts), 2)

    aggregated = AggregatedReplayStats(
        schema_version=1,
        original_match_id=None,
        local_replay_id=None,
        game_duration_sec=duration,
        players=averaged,
        team_totals=team_totals,
        meta={
            "aggregate_mode": "folder_average",
            "game_count": len(parts),
            "source_files": used,
            "roster_applied": bool(roster_by_position),
            "scoreboard_ss_enriched": ss_enriched,
        },
    )
    return FolderAggregateResult(
        directory=str(root),
        file_count=len(used),
        files=used,
        game_count=len(parts),
        aggregated=aggregated,
        players=averaged,
    )
