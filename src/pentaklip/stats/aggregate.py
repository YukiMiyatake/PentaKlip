"""Aggregate captured snapshots into player × position stats (separate from charts)."""

from __future__ import annotations

import itertools
from collections import defaultdict
from typing import Any

from pentaklip.stats.catalog import Position, StatKey
from pentaklip.stats.identity import PlayerIdentity
from pentaklip.stats.models import (
    AggregatedReplayStats,
    PlayerPositionAggregate,
    ReplayStatsBundle,
    TimePoint,
)


def _score(scores: dict[str, Any], *keys: str, default: float = 0.0) -> float:
    for key in keys:
        if key in scores and scores[key] is not None:
            return float(scores[key])
    return default


def _kda_ratio(kills: float, deaths: float, assists: float) -> float:
    return (kills + assists) / max(deaths, 1.0)


def _as_optional_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


_MARK_15_SEC = 15.0 * 60.0


def _value_at_time(
    points: list[TimePoint],
    target_sec: float,
    *,
    max_edge_delta: float = 120.0,
) -> float | None:
    """Linear-interpolate a series at target_sec (for CSD15 / LVLD15)."""
    if not points:
        return None
    ordered = sorted(points, key=lambda p: p.game_time_sec)
    if target_sec <= ordered[0].game_time_sec:
        if ordered[0].game_time_sec - target_sec > max_edge_delta:
            return None
        return ordered[0].value
    if target_sec >= ordered[-1].game_time_sec:
        if target_sec - ordered[-1].game_time_sec > max_edge_delta:
            return None
        return ordered[-1].value
    for left, right in itertools.pairwise(ordered):
        if left.game_time_sec <= target_sec <= right.game_time_sec:
            span = right.game_time_sec - left.game_time_sec
            if span <= 1e-9:
                return right.value
            ratio = (target_sec - left.game_time_sec) / span
            return left.value + (right.value - left.value) * ratio
    return None


def _objective_score(counts: dict[str, int]) -> int:
    return int(
        counts.get(StatKey.DRAGON_KILLS.value, 0)
        + counts.get(StatKey.BARON_KILLS.value, 0)
        + counts.get(StatKey.HERALD_KILLS.value, 0)
        + counts.get(StatKey.TOWER_KILLS.value, 0)
        + counts.get(StatKey.INHIBITOR_KILLS.value, 0)
    )


def _lane_opponent(
    focus: PlayerPositionAggregate,
    players: list[PlayerPositionAggregate],
) -> PlayerPositionAggregate | None:
    """Prefer the single opposite-team player on the same lane."""
    same_lane = [
        p
        for p in players
        if p.position == focus.position and p.player_id != focus.player_id
    ]
    if not same_lane:
        return None
    opposite = [
        p
        for p in same_lane
        if focus.team and p.team and str(p.team) != str(focus.team)
    ]
    pool = opposite or same_lane
    if len(pool) == 1:
        return pool[0]
    return None


def _active_gold(active_player: dict[str, Any], player_id: str) -> float | None:
    if not active_player:
        return None
    name = active_player.get("summonerName") or active_player.get("riotIdGameName")
    riot_tag = active_player.get("riotIdTagLine")
    active_id = None
    if active_player.get("riotIdGameName"):
        active_id = str(active_player["riotIdGameName"])
        if riot_tag:
            active_id = f"{active_id}#{riot_tag}"
    elif name:
        active_id = str(name)
    if active_id != player_id:
        return None
    gold = active_player.get("currentGold")
    return float(gold) if gold is not None else None


def _event_participant_names(event: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for key in (
        "KillerName",
        "VictimName",
        "Assisters",
        "Recipient",
        "Acer",
    ):
        value = event.get(key)
        if isinstance(value, str) and value:
            names.add(value)
        elif isinstance(value, list):
            names.update(str(v) for v in value if v)
    return names


def _identity_aliases(identity: PlayerIdentity) -> set[str]:
    aliases = {identity.player_id}
    if identity.summoner_name:
        aliases.add(identity.summoner_name)
    if identity.riot_id_game_name:
        aliases.add(identity.riot_id_game_name)
        if identity.riot_id_tag_line:
            aliases.add(f"{identity.riot_id_game_name}#{identity.riot_id_tag_line}")
    return aliases


def aggregate_replay(bundle: ReplayStatsBundle) -> AggregatedReplayStats:
    """
    Build per (player_id, position) aggregates from a capture bundle.

    Keeps end scalars + time series. Chart rendering is intentionally not done here.
    """
    # Track latest identity/position observations
    series: dict[tuple[str, Position], dict[str, list[TimePoint]]] = defaultdict(
        lambda: defaultdict(list)
    )
    last_player: dict[tuple[str, Position], dict[str, Any]] = {}
    last_identity: dict[tuple[str, Position], PlayerIdentity] = {}
    last_meta: dict[tuple[str, Position], dict[str, Any]] = {}

    duration = 0.0
    for snap in bundle.snapshots:
        duration = max(duration, snap.game_time_sec)
        for player in snap.players:
            key = (player.identity.player_id, player.position)
            last_identity[key] = player.identity
            last_player[key] = player.raw
            last_meta[key] = {
                "champion_name": player.champion_name,
                "team": player.team,
            }
            kills = _score(player.scores, "kills", "Kills")
            deaths = _score(player.scores, "deaths", "Deaths")
            assists = _score(player.scores, "assists", "Assists")
            cs = _score(player.scores, "creepScore", "creep_score")
            ward = _score(player.scores, "wardScore", "ward_score")
            level = float(player.level or 0)
            t = snap.game_time_sec
            series[key][StatKey.CS_SERIES].append(TimePoint(game_time_sec=t, value=cs))
            series[key][StatKey.WARD_SERIES].append(TimePoint(game_time_sec=t, value=ward))
            series[key][StatKey.LEVEL_SERIES].append(TimePoint(game_time_sec=t, value=level))
            series[key][StatKey.KDA_SERIES].append(
                TimePoint(game_time_sec=t, value=_kda_ratio(kills, deaths, assists))
            )
            gold = _active_gold(snap.active_player, player.identity.player_id)
            if gold is not None:
                series[key][StatKey.GOLD_SERIES].append(TimePoint(game_time_sec=t, value=gold))

    # Team kill totals from last snapshots
    team_kills: dict[str, float] = defaultdict(float)
    end_scores: dict[tuple[str, Position], dict[str, float]] = {}
    for key, raw in last_player.items():
        scores = raw.get("scores") if isinstance(raw.get("scores"), dict) else {}
        kills = _score(scores, "kills", "Kills")
        deaths = _score(scores, "deaths", "Deaths")
        assists = _score(scores, "assists", "Assists")
        cs = _score(scores, "creepScore", "creep_score")
        ward = _score(scores, "wardScore", "ward_score")
        team = str(last_meta[key].get("team") or raw.get("team") or "UNKNOWN")
        team_kills[team] += kills
        end_scores[key] = {
            "kills": kills,
            "deaths": deaths,
            "assists": assists,
            "cs": cs,
            "ward": ward,
            "level": float(raw.get("level") or 0),
            "item_count": float(len(raw.get("items") or [])),
        }

    # Objective participation from events
    event_counts: dict[tuple[str, Position], dict[str, int]] = defaultdict(
        lambda: defaultdict(int)
    )
    objective_map = {
        "DragonKill": StatKey.DRAGON_KILLS,
        "BaronKill": StatKey.BARON_KILLS,
        "HeraldKill": StatKey.HERALD_KILLS,
        "TurretKilled": StatKey.TOWER_KILLS,
        "InhibKilled": StatKey.INHIBITOR_KILLS,
    }
    # Map summoner-ish names to keys
    alias_to_keys: dict[str, list[tuple[str, Position]]] = defaultdict(list)
    for key, identity in last_identity.items():
        for alias in _identity_aliases(identity):
            alias_to_keys[alias].append(key)

    for event in bundle.events:
        name = str(event.get("EventName") or "")
        stat = objective_map.get(name)
        if stat is None:
            continue
        for participant in _event_participant_names(event):
            for key in alias_to_keys.get(participant, []):
                event_counts[key][stat.value] += 1

    minutes = max(duration / 60.0, 1e-6)
    players: list[PlayerPositionAggregate] = []
    for key, identity in last_identity.items():
        scores = end_scores[key]
        team = str(last_meta[key].get("team") or "UNKNOWN")
        kp = 0.0
        if team_kills[team] > 0:
            kp = (scores["kills"] + scores["assists"]) / team_kills[team] * 100.0
        gold_series = series[key].get(StatKey.GOLD_SERIES, [])
        gold_last = gold_series[-1].value if gold_series else None
        cs_at_15 = _value_at_time(series[key].get(StatKey.CS_SERIES, []), _MARK_15_SEC)
        level_at_15 = _value_at_time(
            series[key].get(StatKey.LEVEL_SERIES, []), _MARK_15_SEC
        )
        obj = _objective_score(event_counts[key])
        agg = PlayerPositionAggregate(
            player_id=key[0],
            position=key[1],
            identity=identity,
            champion_name=last_meta[key].get("champion_name"),
            team=team,
            scalars={
                StatKey.CHAMPION.value: last_meta[key].get("champion_name"),
                StatKey.TEAM.value: team,
                StatKey.KILLS.value: int(scores["kills"]),
                StatKey.DEATHS.value: int(scores["deaths"]),
                StatKey.ASSISTS.value: int(scores["assists"]),
                StatKey.KDA_RATIO.value: round(
                    _kda_ratio(scores["kills"], scores["deaths"], scores["assists"]), 3
                ),
                StatKey.KILL_PARTICIPATION.value: round(kp, 1),
                StatKey.CREEP_SCORE.value: int(scores["cs"]),
                StatKey.CS_PER_MIN.value: round(scores["cs"] / minutes, 2),
                StatKey.CS_AT_15.value: (
                    round(cs_at_15, 1) if cs_at_15 is not None else None
                ),
                StatKey.LEVEL_AT_15.value: (
                    round(level_at_15, 2) if level_at_15 is not None else None
                ),
                StatKey.CSD15.value: None,
                StatKey.LVLD15.value: None,
                StatKey.WARD_SCORE.value: round(scores["ward"], 1),
                StatKey.VISION_PER_MIN.value: round(scores["ward"] / minutes, 2),
                StatKey.LEVEL.value: int(scores["level"]),
                StatKey.OBJECTIVE_SCORE.value: obj,
                StatKey.GOLD.value: gold_last,
                StatKey.ITEM_COUNT.value: int(scores["item_count"]),
                StatKey.DRAGON_KILLS.value: event_counts[key].get(StatKey.DRAGON_KILLS.value, 0),
                StatKey.BARON_KILLS.value: event_counts[key].get(StatKey.BARON_KILLS.value, 0),
                StatKey.HERALD_KILLS.value: event_counts[key].get(StatKey.HERALD_KILLS.value, 0),
                StatKey.TOWER_KILLS.value: event_counts[key].get(StatKey.TOWER_KILLS.value, 0),
                StatKey.INHIBITOR_KILLS.value: event_counts[key].get(
                    StatKey.INHIBITOR_KILLS.value, 0
                ),
            },
            series={k.value if isinstance(k, StatKey) else str(k): v for k, v in series[key].items()},
            event_counts=dict(event_counts[key]),
            raw_last_player=last_player[key],
        )
        players.append(agg)

    # Lane diffs at 15:00 vs the opposite-lane opponent (LCK CSD15 / ~XPD15).
    for player in players:
        opp = _lane_opponent(player, players)
        if opp is None:
            continue
        my_cs = _as_optional_float(player.scalars.get(StatKey.CS_AT_15.value))
        opp_cs = _as_optional_float(opp.scalars.get(StatKey.CS_AT_15.value))
        if my_cs is not None and opp_cs is not None:
            player.scalars[StatKey.CSD15.value] = round(my_cs - opp_cs, 1)
        my_lvl = _as_optional_float(player.scalars.get(StatKey.LEVEL_AT_15.value))
        opp_lvl = _as_optional_float(opp.scalars.get(StatKey.LEVEL_AT_15.value))
        if my_lvl is not None and opp_lvl is not None:
            player.scalars[StatKey.LVLD15.value] = round(my_lvl - opp_lvl, 2)

    players.sort(key=lambda p: (p.position.value, p.player_id))
    team_totals = {
        team: {"kills": kills} for team, kills in sorted(team_kills.items())
    }
    return AggregatedReplayStats(
        original_match_id=bundle.original_match_id,
        local_replay_id=bundle.local_replay_id,
        game_duration_sec=duration,
        players=players,
        team_totals=team_totals,
        meta={
            "snapshot_count": len(bundle.snapshots),
            "event_count": len(bundle.events),
            "source_filename": bundle.source_filename,
        },
    )


def merge_aggregates(parts: list[AggregatedReplayStats]) -> list[PlayerPositionAggregate]:
    """
    Merge multiple replay aggregates by (player_id, position).

    Sums countable stats and averages rates weighted by game duration.
    """
    buckets: dict[tuple[str, Position], list[tuple[AggregatedReplayStats, PlayerPositionAggregate]]] = (
        defaultdict(list)
    )
    for agg in parts:
        for player in agg.players:
            buckets[(player.player_id, player.position)].append((agg, player))

    merged: list[PlayerPositionAggregate] = []
    sum_keys = {
        StatKey.KILLS.value,
        StatKey.DEATHS.value,
        StatKey.ASSISTS.value,
        StatKey.CREEP_SCORE.value,
        StatKey.WARD_SCORE.value,
        StatKey.DRAGON_KILLS.value,
        StatKey.BARON_KILLS.value,
        StatKey.HERALD_KILLS.value,
        StatKey.TOWER_KILLS.value,
        StatKey.INHIBITOR_KILLS.value,
        StatKey.OBJECTIVE_SCORE.value,
    }
    avg_keys = {
        StatKey.CS_AT_15.value,
        StatKey.LEVEL_AT_15.value,
        StatKey.CSD15.value,
        StatKey.LVLD15.value,
    }
    for (player_id, position), items in sorted(buckets.items()):
        total_duration = sum(a.game_duration_sec for a, _ in items) or 1.0
        identity = items[-1][1].identity
        scalars: dict[str, float | int | str | bool | None] = {
            StatKey.CHAMPION.value: items[-1][1].scalars.get(StatKey.CHAMPION.value),
            StatKey.TEAM.value: items[-1][1].scalars.get(StatKey.TEAM.value),
        }
        for key in sum_keys:
            scalars[key] = int(
                sum(float(p.scalars.get(key) or 0) for _, p in items)
            )
        for key in avg_keys:
            vals = [
                _as_optional_float(p.scalars.get(key))
                for _, p in items
            ]
            present = [v for v in vals if v is not None]
            scalars[key] = round(sum(present) / len(present), 2) if present else None
        kills = float(scalars[StatKey.KILLS.value] or 0)
        deaths = float(scalars[StatKey.DEATHS.value] or 0)
        assists = float(scalars[StatKey.ASSISTS.value] or 0)
        cs = float(scalars[StatKey.CREEP_SCORE.value] or 0)
        ward = float(scalars[StatKey.WARD_SCORE.value] or 0)
        minutes = total_duration / 60.0
        scalars[StatKey.KDA_RATIO.value] = round(_kda_ratio(kills, deaths, assists), 3)
        scalars[StatKey.CS_PER_MIN.value] = round(cs / max(minutes, 1e-6), 2)
        scalars[StatKey.VISION_PER_MIN.value] = round(ward / max(minutes, 1e-6), 2)
        # KP across merges is approximate from summed K+A / summed team kills if present
        team_kill_sum = 0.0
        for a, p in items:
            team = str(p.team or "")
            team_kill_sum += float((a.team_totals.get(team) or {}).get("kills") or 0)
        scalars[StatKey.KILL_PARTICIPATION.value] = (
            round((kills + assists) / team_kill_sum * 100.0, 1) if team_kill_sum else 0.0
        )
        merged.append(
            PlayerPositionAggregate(
                player_id=player_id,
                position=position,
                identity=identity,
                champion_name=items[-1][1].champion_name,
                team=items[-1][1].team,
                scalars=scalars,
                series={},
                event_counts={},
                raw_last_player={},
            )
        )
    return merged
