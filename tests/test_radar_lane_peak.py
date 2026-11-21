"""Radar peak uses the lane cohort (max / percentile), not max(player, avg)."""

from __future__ import annotations

from pentaklip.stats.catalog import Position, StatKey
from pentaklip.stats.charts import (
    _axis_peak_from_values,
    _lane_peaks_for_axes,
    build_charts,
)
from pentaklip.stats.display import default_display_settings
from pentaklip.stats.identity import PlayerIdentity
from pentaklip.stats.models import AggregatedReplayStats, PlayerPositionAggregate


def _mid(player_id: str, *, kda: float, csm: float = 8.0, kp: float = 50.0) -> PlayerPositionAggregate:
    game, _, tag = player_id.partition("#")
    return PlayerPositionAggregate(
        player_id=player_id,
        position=Position.MIDDLE,
        identity=PlayerIdentity(
            player_id=player_id,
            riot_id_game_name=game or player_id,
            riot_id_tag_line=tag or None,
            summoner_name=game or player_id,
        ),
        team="ORDER",
        champion_name="Ahri",
        scalars={
            StatKey.KDA_RATIO.value: kda,
            StatKey.CS_PER_MIN.value: csm,
            StatKey.KILL_PARTICIPATION.value: kp,
            StatKey.VISION_PER_MIN.value: 1.2,
        },
    )


def test_axis_peak_uses_lane_max_by_default() -> None:
    assert _axis_peak_from_values([3.0, 5.0, 8.0]) == 8.0


def test_axis_peak_percentile_softens_outlier() -> None:
    # With ≥3 values, p50 of sorted abs → middle.
    assert _axis_peak_from_values([3.0, 5.0, 8.0], percentile=50.0) == 5.0


def test_radar_kda_peak_shared_across_lane_players() -> None:
    high = _mid("HighKda#JP1", kda=8.0)
    mid = _mid("MidKda#JP1", kda=4.0)
    low = _mid("LowKda#JP1", kda=2.0)
    aggregated = AggregatedReplayStats(
        original_match_id="LANE-PEAK",
        game_duration_sec=1800.0,
        players=[high, mid, low],
    )
    charts = build_charts(aggregated, default_display_settings())
    radars = [c for c in charts.charts if c.chart_type == "radar" and "MIDDLE" in c.chart_id]
    assert len(radars) == 3

    kda_maxes = []
    for radar in radars:
        row = next(r for r in radar.rows if r["stat_key"] == "kda_ratio")
        kda_maxes.append(row["max"])
        # Shared lane max: never shrink to max(player, avg) alone.
        assert row["max"] == 8.0

    assert len(set(kda_maxes)) == 1

    # Low-KDA chart: player is well below lane max, not remapped so avg sits at rim.
    low_radar = next(c for c in radars if "LowKda" in c.chart_id)
    low_kda = next(r for r in low_radar.rows if r["stat_key"] == "kda_ratio")
    assert low_kda["player"] == 2.0
    assert low_kda["player_norm"] == 2.0 / 8.0
    # Baseline is lane mean of 8/4/2 = ~4.67 → not forced to 1.0
    assert low_kda["baseline_norm"] == low_kda["baseline"] / 8.0
    assert low_kda["baseline_norm"] < 1.0


def test_lane_peaks_for_axes_keys() -> None:
    players = [
        _mid("A#JP1", kda=8.0, csm=9.0),
        _mid("B#JP1", kda=3.0, csm=7.0),
    ]
    peaks = _lane_peaks_for_axes(
        players,
        [StatKey.KDA_RATIO, StatKey.CS_PER_MIN],
    )
    assert peaks["kda_ratio"] == 8.0
    assert peaks["cs_per_min"] == 9.0
