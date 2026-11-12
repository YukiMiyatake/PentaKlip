"""Parse post-game Data-tab screenshots (`{game_id}.png` / `{game_id}*.png`) for damage stats.

Live Client cannot expose DPM / DMG%. The LoL end-of-game「データ」tab shows
「対チャンピオン与ダメージ合計」 per champion icon (no summoner names). This
module OCRs that row, maps columns → players via KDA and/or champion icons
(`rawChampionName`), then writes damage / DPM / damage share onto aggregates.
"""

from __future__ import annotations

import logging
import re
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pentaklip.paths import sanitize_game_id, with_game_id_prefix
from pentaklip.stats.catalog import StatKey
from pentaklip.stats.models import AggregatedReplayStats, PlayerPositionAggregate

logger = logging.getLogger(__name__)

_KDA_RE = re.compile(r"(\d+)\s*/\s*(\d+)\s*/\s*(\d+)")
_INT_RE = re.compile(r"\d{1,3}(?:\s*,\s*\d{3})+|\d+")
_DURATION_RE = re.compile(r"(\d{1,2})\s*:\s*(\d{2})")
_DAMAGE_LABEL = "対チャンピオン与ダメージ合計"
# Windows OCR often misreads ピ→ビ in チャンピオン.
_DAMAGE_LABEL_RE = re.compile(
    r"対チャン[ピビ]オン与ダメージ合計|対チャン.*与ダメージ合計"
)
_RAW_CHAMP_PREFIX = "game_character_displayname_"

OcrBackend = Callable[[Path], tuple[list["OcrLine"], tuple[int, int], int]]


@dataclass(frozen=True)
class OcrLine:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2.0

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2.0


@dataclass(frozen=True)
class ScoreboardDamageColumn:
    index: int
    center_x: float
    damage_to_champions: int
    kda: tuple[int, int, int] | None = None
    champion_key: str | None = None


@dataclass(frozen=True)
class ScoreboardSsParse:
    game_duration_sec: float | None
    columns: list[ScoreboardDamageColumn]
    source_path: str | None = None


def champion_key_from_raw(raw: dict[str, Any] | None) -> str | None:
    if not raw:
        return None
    name = raw.get("rawChampionName")
    if isinstance(name, str) and name.startswith(_RAW_CHAMP_PREFIX):
        key = name[len(_RAW_CHAMP_PREFIX) :].strip()
        return key or None
    return None


def champion_key_from_player(player: PlayerPositionAggregate) -> str | None:
    return champion_key_from_raw(player.raw_last_player)


def find_scoreboard_ss(stats_dir: Path | str, game_id: str) -> Path | None:
    """Locate a post-game screenshot matching ``{game_id}*.png`` (etc.).

    Preference order:
    1. Exact ``{game_id}.png``
    2. Legacy ``{game_id}_ss.png``
    3. Any other ``{game_id}*`` image (newest mtime wins)
    """
    root = Path(stats_dir)
    if not root.is_dir():
        return None
    safe = sanitize_game_id(game_id)
    image_exts = {".png", ".jpg", ".jpeg", ".webp"}

    exact = root / f"{safe}.png"
    if exact.is_file():
        return exact

    legacy = root / with_game_id_prefix(safe, "ss.png")
    if legacy.is_file():
        return legacy

    matches = [
        path
        for path in root.glob(f"{safe}*")
        if path.is_file() and path.suffix.lower() in image_exts
    ]
    if not matches:
        return None

    def rank(path: Path) -> tuple[int, float, str]:
        stem = path.stem
        if stem == safe:
            return (0, 0.0, path.name)
        if stem.lower() == f"{safe}_ss".lower():
            return (1, 0.0, path.name)
        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = 0.0
        return (2, -mtime, path.name)

    return min(matches, key=rank)


def parse_compact_int(text: str) -> int | None:
    cleaned = text.replace(" ", "").replace(",", "").replace("，", "")
    if not cleaned.isdigit():
        return None
    return int(cleaned)


def parse_kda(text: str) -> tuple[int, int, int] | None:
    match = _KDA_RE.search(text.replace(" ", ""))
    if not match:
        # tolerate OCR spacing inside digits already stripped
        match = _KDA_RE.search(text)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def parse_duration_sec(text: str) -> float | None:
    match = _DURATION_RE.search(text)
    if not match:
        return None
    minutes = int(match.group(1))
    seconds = int(match.group(2))
    if seconds >= 60:
        return None
    return float(minutes * 60 + seconds)


def _normalize_ocr_text(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _line_near_y(lines: Sequence[OcrLine], y: float, tol: float) -> list[OcrLine]:
    return [line for line in lines if abs(line.cy - y) <= tol]


def _cluster_column_centers(xs: Sequence[float], expected: int = 10) -> list[float]:
    if not xs:
        return []
    ordered = sorted(xs)
    if len(ordered) <= expected:
        return ordered
    # Merge nearest until ``expected`` centers remain.
    centers = list(ordered)
    while len(centers) > expected:
        gaps = [(centers[i + 1] - centers[i], i) for i in range(len(centers) - 1)]
        _gap, idx = min(gaps)
        merged = (centers[idx] + centers[idx + 1]) / 2.0
        centers = centers[:idx] + [merged] + centers[idx + 2 :]
    return centers


def _assign_to_nearest(
    items: Sequence[tuple[float, Any]],
    centers: Sequence[float],
    *,
    max_dist: float | None = None,
) -> list[Any | None]:
    slots: list[Any | None] = [None] * len(centers)
    used: set[int] = set()
    for x, value in sorted(items, key=lambda item: item[0]):
        best_i = None
        best_d = None
        for index, center in enumerate(centers):
            if index in used:
                continue
            dist = abs(x - center)
            if best_d is None or dist < best_d:
                best_d = dist
                best_i = index
        if best_i is None or best_d is None:
            continue
        if max_dist is not None and best_d > max_dist:
            continue
        slots[best_i] = value
        used.add(best_i)
    return slots


def parse_scoreboard_lines(
    lines: Sequence[OcrLine],
    *,
    image_width: int,
    ocr_scale: int = 2,
    source_path: str | None = None,
) -> ScoreboardSsParse:
    """Parse OCR lines (typically from a 2× upscaled screenshot)."""
    duration: float | None = None
    for line in lines:
        if duration is None:
            duration = parse_duration_sec(line.text)

    damage_label_y: float | None = None
    for line in lines:
        if _DAMAGE_LABEL_RE.search(_normalize_ocr_text(line.text)):
            damage_label_y = line.cy
            break
    if damage_label_y is None:
        raise ValueError("scoreboard SS missing damage row label (対チャンピオン与ダメージ合計)")

    # Numbers sit on the same row as the label (slightly to the right).
    row_tol = max(28.0, 18.0 * ocr_scale)
    damage_items: list[tuple[float, int]] = []
    for line in _line_near_y(lines, damage_label_y, row_tol):
        if _DAMAGE_LABEL_RE.search(_normalize_ocr_text(line.text)):
            continue
        for match in _INT_RE.finditer(line.text):
            value = parse_compact_int(match.group(0))
            if value is None or value < 100:  # champ damage is rarely tiny
                continue
            # Approximate token x inside the line box.
            frac = (match.start() + match.end()) / (2 * max(len(line.text), 1))
            x = line.x0 + (line.x1 - line.x0) * frac
            damage_items.append((x, value))

    if len(damage_items) < 8:
        raise ValueError(f"expected ~10 damage values, got {len(damage_items)}")

    centers = _cluster_column_centers([x for x, _ in damage_items], expected=10)
    damages = _assign_to_nearest(damage_items, centers, max_dist=image_width * ocr_scale * 0.06)
    if sum(1 for value in damages if value is not None) < 8:
        raise ValueError("failed to align damage values to columns")

    # KDA row: look for the label ``KDA`` then harvest nearby ratios.
    kda_label_y: float | None = None
    for line in lines:
        if _normalize_ocr_text(line.text) == "KDA":
            kda_label_y = line.cy
            break
    kda_items: list[tuple[float, tuple[int, int, int]]] = []
    if kda_label_y is not None:
        for line in _line_near_y(lines, kda_label_y, row_tol):
            kda = parse_kda(line.text)
            if kda is None:
                continue
            kda_items.append((line.cx, kda))
    kdas = _assign_to_nearest(kda_items, centers, max_dist=image_width * ocr_scale * 0.06)

    columns: list[ScoreboardDamageColumn] = []
    for index, center in enumerate(centers):
        dmg = damages[index]
        if dmg is None:
            continue
        columns.append(
            ScoreboardDamageColumn(
                index=index,
                center_x=center,
                damage_to_champions=int(dmg),
                kda=kdas[index] if index < len(kdas) else None,
            )
        )
    return ScoreboardSsParse(
        game_duration_sec=duration,
        columns=columns,
        source_path=source_path,
    )


def _player_kda(player: PlayerPositionAggregate) -> tuple[int, int, int] | None:
    try:
        kills = int(player.scalars.get(StatKey.KILLS.value) or 0)
        deaths = int(player.scalars.get(StatKey.DEATHS.value) or 0)
        assists = int(player.scalars.get(StatKey.ASSISTS.value) or 0)
    except (TypeError, ValueError):
        return None
    return kills, deaths, assists


def match_columns_to_players(
    parsed: ScoreboardSsParse,
    players: Sequence[PlayerPositionAggregate],
    *,
    image_path: Path | None = None,
    ocr_scale: int = 2,
) -> dict[int, PlayerPositionAggregate]:
    """Map column index → player using KDA first, champion icons as fallback."""
    remaining = list(players)
    mapping: dict[int, PlayerPositionAggregate] = {}

    # Exact unique KDA matches.
    for column in parsed.columns:
        if column.kda is None:
            continue
        hits = [player for player in remaining if _player_kda(player) == column.kda]
        if len(hits) == 1:
            mapping[column.index] = hits[0]
            remaining.remove(hits[0])

    unmatched_cols = [column for column in parsed.columns if column.index not in mapping]
    if not unmatched_cols or not remaining:
        return mapping

    # Icon fallback when Pillow is available and we still have candidates.
    if image_path is not None:
        try:
            icon_map = _match_columns_by_champion_icons(
                image_path,
                unmatched_cols,
                remaining,
                ocr_scale=ocr_scale,
            )
        except Exception:
            logger.exception("champion icon matching failed for %s", image_path)
            icon_map = {}
        for index, player in icon_map.items():
            mapping[index] = player
            if player in remaining:
                remaining.remove(player)

    unmatched_cols = [column for column in parsed.columns if column.index not in mapping]
    # Last resort: left five / right five by team if counts match.
    if unmatched_cols and remaining:
        left = [column for column in unmatched_cols if column.index < 5]
        right = [column for column in unmatched_cols if column.index >= 5]
        chaos = [player for player in remaining if (player.team or "").upper() == "CHAOS"]
        order = [player for player in remaining if (player.team or "").upper() == "ORDER"]
        # Post-game UI: left group is often the team shown first; prefer CHAOS/ORDER by count.
        if len(left) == len(chaos) and len(right) == len(order):
            for column, player in zip(sorted(left, key=lambda c: c.index), chaos, strict=False):
                mapping[column.index] = player
            for column, player in zip(sorted(right, key=lambda c: c.index), order, strict=False):
                mapping[column.index] = player
        elif len(left) == len(order) and len(right) == len(chaos):
            for column, player in zip(sorted(left, key=lambda c: c.index), order, strict=False):
                mapping[column.index] = player
            for column, player in zip(sorted(right, key=lambda c: c.index), chaos, strict=False):
                mapping[column.index] = player

    return mapping


def _match_columns_by_champion_icons(
    image_path: Path,
    columns: Sequence[ScoreboardDamageColumn],
    players: Sequence[PlayerPositionAggregate],
    *,
    ocr_scale: int,
) -> dict[int, PlayerPositionAggregate]:
    import numpy as np
    from PIL import Image

    image = Image.open(image_path).convert("RGB")
    width, height = image.size
    # Icons sit between the tab row and the「戦闘」section (~18–28% height).
    y0 = int(height * 0.17)
    y1 = int(height * 0.30)
    icon_h = max(y1 - y0, 24)
    templates: list[tuple[PlayerPositionAggregate, np.ndarray]] = []
    for player in players:
        key = champion_key_from_player(player)
        if not key:
            continue
        icon = _load_champion_icon(key)
        if icon is None:
            continue
        icon = icon.resize((icon_h, icon_h), Image.Resampling.LANCZOS)
        templates.append((player, np.asarray(icon.convert("RGB"), dtype=np.float32)))

    if not templates:
        return {}

    mapping: dict[int, PlayerPositionAggregate] = {}
    used: set[str] = set()
    for column in columns:
        cx = column.center_x / ocr_scale
        half = icon_h / 2.0
        x0 = int(max(0, cx - half))
        x1 = int(min(width, cx + half))
        if x1 - x0 < 8:
            continue
        crop = image.crop((x0, y0, x1, y1)).resize((icon_h, icon_h), Image.Resampling.LANCZOS)
        crop_arr = np.asarray(crop, dtype=np.float32)
        best_player = None
        best_score = -1.0
        for player, template in templates:
            if player.player_id in used:
                continue
            score = _ncc(crop_arr, template)
            if score > best_score:
                best_score = score
                best_player = player
        if best_player is not None and best_score >= 0.35:
            mapping[column.index] = best_player
            used.add(best_player.player_id)
    return mapping


def _ncc(a: Any, b: Any) -> float:
    import numpy as np

    aa = a.reshape(-1).astype(np.float64)
    bb = b.reshape(-1).astype(np.float64)
    aa = aa - aa.mean()
    bb = bb - bb.mean()
    denom = float(np.linalg.norm(aa) * np.linalg.norm(bb))
    if denom <= 1e-6:
        return -1.0
    return float(np.dot(aa, bb) / denom)


def _load_champion_icon(champion_key: str) -> Any | None:
    """Load a square champion icon from cache or Community Dragon / Data Dragon."""
    from PIL import Image

    cache_root = Path.home() / ".cache" / "pentaklip" / "champion_icons"
    cache_root.mkdir(parents=True, exist_ok=True)
    cache_path = cache_root / f"{champion_key}.png"
    if cache_path.is_file():
        return Image.open(cache_path).convert("RGBA")

    url = f"https://ddragon.leagueoflegends.com/cdn/14.23.1/img/champion/{champion_key}.png"
    try:
        import urllib.request

        req = urllib.request.Request(url, headers={"User-Agent": "PentaKlip/0.1"})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = response.read()
        cache_path.write_bytes(data)
        return Image.open(cache_path).convert("RGBA")
    except Exception:  # noqa: BLE001
        logger.warning("failed to download champion icon for %s", champion_key)
        return None


def ocr_lines_windows(image_path: Path, *, scale: int = 2) -> tuple[list[OcrLine], tuple[int, int], int]:
    """OCR via Windows.Media.Ocr (winrt). Raises if unavailable."""
    import asyncio

    from PIL import Image

    try:
        from winrt.windows.globalization import Language
        from winrt.windows.graphics.imaging import BitmapDecoder
        from winrt.windows.media.ocr import OcrEngine
        from winrt.windows.storage import FileAccessMode, StorageFile
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "Windows OCR requires winrt packages "
            "(winrt-Windows.Media.Ocr, winrt-Windows.Globalization, ...)"
        ) from exc

    image = Image.open(image_path).convert("RGB")
    size = image.size
    scaled = image.resize((size[0] * scale, size[1] * scale), Image.Resampling.LANCZOS)
    tmp = Path(tempfile.gettempdir()) / f"pentaklip_ocr_{image_path.stem}_x{scale}.png"
    scaled.save(tmp)

    async def _run() -> list[OcrLine]:
        engine = OcrEngine.try_create_from_language(Language("ja"))
        if engine is None:
            engine = OcrEngine.try_create_from_user_profile_languages()
        if engine is None:
            raise RuntimeError("Windows OCR engine unavailable")
        file = await StorageFile.get_file_from_path_async(str(tmp))
        stream = await file.open_async(FileAccessMode.READ)
        decoder = await BitmapDecoder.create_async(stream)
        bitmap = await decoder.get_software_bitmap_async()
        result = await engine.recognize_async(bitmap)
        lines: list[OcrLine] = []
        for line in result.lines:
            if not line.words:
                continue
            xs = [w.bounding_rect.x for w in line.words]
            ys = [w.bounding_rect.y for w in line.words]
            rights = [w.bounding_rect.x + w.bounding_rect.width for w in line.words]
            bottoms = [w.bounding_rect.y + w.bounding_rect.height for w in line.words]
            lines.append(
                OcrLine(
                    text=line.text,
                    x0=float(min(xs)),
                    y0=float(min(ys)),
                    x1=float(max(rights)),
                    y1=float(max(bottoms)),
                )
            )
        return lines

    lines = asyncio.run(_run())
    return lines, size, scale


def default_ocr_backend() -> OcrBackend:
    return ocr_lines_windows


def parse_scoreboard_ss(
    image_path: Path | str,
    *,
    ocr_backend: OcrBackend | None = None,
) -> ScoreboardSsParse:
    path = Path(image_path)
    backend = ocr_backend or default_ocr_backend()
    lines, size, scale = backend(path)
    parsed = parse_scoreboard_lines(
        lines,
        image_width=size[0],
        ocr_scale=scale,
        source_path=str(path),
    )
    return parsed


def apply_scoreboard_damage(
    aggregated: AggregatedReplayStats,
    parsed: ScoreboardSsParse,
    *,
    image_path: Path | None = None,
    ocr_scale: int = 2,
) -> AggregatedReplayStats:
    """Return a copy of ``aggregated`` with damage / DPM / DMG% filled in."""
    duration = parsed.game_duration_sec or aggregated.game_duration_sec
    if not duration or duration <= 0:
        raise ValueError("game duration required to compute DPM")

    mapping = match_columns_to_players(
        parsed,
        aggregated.players,
        image_path=image_path,
        ocr_scale=ocr_scale,
    )
    if len(mapping) < max(1, len(parsed.columns) // 2):
        raise ValueError(
            f"could not match scoreboard columns to players ({len(mapping)}/{len(parsed.columns)})"
        )

    damage_by_player_id: dict[str, int] = {}
    for index, player in mapping.items():
        column = next(col for col in parsed.columns if col.index == index)
        damage_by_player_id[player.player_id] = column.damage_to_champions

    team_totals: dict[str, int] = {}
    for player in aggregated.players:
        dmg = damage_by_player_id.get(player.player_id)
        if dmg is None:
            continue
        team = (player.team or "").upper() or "_"
        team_totals[team] = team_totals.get(team, 0) + dmg

    minutes = float(duration) / 60.0
    new_players: list[PlayerPositionAggregate] = []
    for player in aggregated.players:
        dmg = damage_by_player_id.get(player.player_id)
        if dmg is None:
            new_players.append(player)
            continue
        scalars = dict(player.scalars)
        scalars[StatKey.DAMAGE_TO_CHAMPIONS.value] = int(dmg)
        scalars[StatKey.DPM.value] = round(float(dmg) / minutes, 1)
        team = (player.team or "").upper() or "_"
        total = team_totals.get(team) or 0
        scalars[StatKey.DAMAGE_SHARE.value] = (
            round(100.0 * float(dmg) / float(total), 1) if total > 0 else None
        )
        new_players.append(player.model_copy(update={"scalars": scalars}))

    updates: dict[str, Any] = {"players": new_players}
    if aggregated.game_duration_sec is None and parsed.game_duration_sec is not None:
        updates["game_duration_sec"] = parsed.game_duration_sec
    return aggregated.model_copy(update=updates)


def enrich_aggregated_from_scoreboard_ss(
    aggregated: AggregatedReplayStats,
    stats_dir: Path | str,
    game_id: str | None = None,
    *,
    ocr_backend: OcrBackend | None = None,
) -> AggregatedReplayStats:
    """If ``{game_id}*.png`` exists beside stats, merge damage metrics into aggregate."""
    gid = game_id or aggregated.original_match_id
    if not gid:
        return aggregated
    ss_path = find_scoreboard_ss(stats_dir, gid)
    if ss_path is None:
        return aggregated
    try:
        backend = ocr_backend or default_ocr_backend()
        lines, size, scale = backend(ss_path)
        parsed = parse_scoreboard_lines(
            lines,
            image_width=size[0],
            ocr_scale=scale,
            source_path=str(ss_path),
        )
        return apply_scoreboard_damage(
            aggregated,
            parsed,
            image_path=ss_path,
            ocr_scale=scale,
        )
    except Exception:
        logger.exception("scoreboard SS enrich failed for %s", ss_path)
        return aggregated
