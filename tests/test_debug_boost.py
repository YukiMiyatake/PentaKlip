from __future__ import annotations

from pentaklip.stats.catalog import Position, StatKey
from pentaklip.stats.debug_boost import apply_debug_stat_boost
from pentaklip.stats.identity import PlayerIdentity
from pentaklip.stats.models import AggregatedReplayStats, PlayerPositionAggregate


def _player(
    player_id: str,
    position: Position,
    *,
    dpm: float,
    dmg_share: float,
    kp: float,
    damage: int,
) -> PlayerPositionAggregate:
    game, _, tag = player_id.partition("#")
    return PlayerPositionAggregate(
        player_id=player_id,
        position=position,
        identity=PlayerIdentity(
            player_id=player_id,
            riot_id_game_name=game or player_id,
            riot_id_tag_line=tag or None,
            summoner_name=game or player_id,
        ),
        team="ORDER",
        champion_name="Ahri",
        scalars={
            StatKey.DPM.value: dpm,
            StatKey.DAMAGE_SHARE.value: dmg_share,
            StatKey.DAMAGE_TO_CHAMPIONS.value: damage,
            StatKey.KILL_PARTICIPATION.value: kp,
        },
        series={},
    )


def test_debug_boost_targets_mid_yojo_only() -> None:
    target = _player(
        "X9 YoJo#JoJo",
        Position.MIDDLE,
        dpm=500.0,
        dmg_share=25.0,
        kp=50.0,
        damage=10_000,
    )
    other_mid = _player(
        "OtherMid#JP1",
        Position.MIDDLE,
        dpm=500.0,
        dmg_share=25.0,
        kp=50.0,
        damage=10_000,
    )
    top_yojo = _player(
        "X9 YoJo#JoJo",
        Position.TOP,
        dpm=500.0,
        dmg_share=25.0,
        kp=50.0,
        damage=10_000,
    )
    aggregated = AggregatedReplayStats(
        original_match_id="JP1-1",
        game_duration_sec=1800.0,
        players=[target, other_mid, top_yojo],
        meta={},
    )

    boosted = apply_debug_stat_boost(aggregated)
    by_key = {(p.player_id, p.position): p for p in boosted.players}

    mid = by_key[("X9 YoJo#JoJo", Position.MIDDLE)]
    assert mid.scalars[StatKey.DPM.value] == 600.0
    assert mid.scalars[StatKey.DAMAGE_SHARE.value] == 30.0
    assert mid.scalars[StatKey.DAMAGE_TO_CHAMPIONS.value] == 12_000
    assert mid.scalars[StatKey.KILL_PARTICIPATION.value] == 55.0

    assert by_key[("OtherMid#JP1", Position.MIDDLE)].scalars[StatKey.DPM.value] == 500.0
    assert by_key[("X9 YoJo#JoJo", Position.TOP)].scalars[StatKey.DPM.value] == 500.0
    assert boosted.meta.get("debug_boost_applied") == 1


def test_debug_boost_matches_compact_name() -> None:
    target = _player(
        "X9YoJo#JoJo",
        Position.MIDDLE,
        dpm=100.0,
        dmg_share=20.0,
        kp=40.0,
        damage=1000,
    )
    boosted = apply_debug_stat_boost(
        AggregatedReplayStats(
            original_match_id=None,
            game_duration_sec=60.0,
            players=[target],
            meta={},
        )
    ).players[0]
    assert boosted.scalars[StatKey.DPM.value] == 120.0


def test_debug_boost_caps_percentages() -> None:
    target = _player(
        "X9 YoJo#JoJo",
        Position.MIDDLE,
        dpm=100.0,
        dmg_share=90.0,
        kp=95.0,
        damage=1000,
    )
    aggregated = AggregatedReplayStats(
        original_match_id=None,
        game_duration_sec=100.0,
        players=[target],
        meta={},
    )
    boosted = apply_debug_stat_boost(aggregated).players[0]
    assert boosted.scalars[StatKey.DAMAGE_SHARE.value] == 100.0
    assert boosted.scalars[StatKey.KILL_PARTICIPATION.value] == 100.0
