"""Unit tests for snowball calculation, multi-hero counters, upgrade tree evolution, lane matchups, and Top Priority."""

from __future__ import annotations

from backend.engine.recommender import RecommendationEngine
from backend.models.game_state import (
    LaneStatus,
    MatchState,
    PlayerState,
    RecommendationSection,
    Team,
)


def _make_player(
    slot: int,
    team: Team,
    hero: str,
    souls: int,
    kills: int = 1,
    deaths: int = 1,
    items: list[str] | None = None,
    lane_id: int = 1,
    is_self: bool = False,
) -> PlayerState:
    return PlayerState(
        slot_index=slot,
        team=team,
        hero_name=hero,
        souls=souls,
        kills=kills,
        deaths=deaths,
        assists=2,
        items=items or [],
        lane_id=lane_id,
        is_self=is_self,
    )


def test_early_losing_lane_recommends_defensive_items() -> None:
    match = MatchState(
        timestamp=100.0,
        match_minutes=6.0,
        players=[
            _make_player(0, Team.SAPPHIRE_FLAME, "Haze", 3200, lane_id=1, is_self=True),
            _make_player(6, Team.AMBER_HAND, "Bebop", 4400, lane_id=1),
        ],
    )
    engine = RecommendationEngine()
    status, diff, _ = engine.evaluate_lane_status(match)
    assert status == LaneStatus.BEHIND
    assert diff == -1200

    recs = engine.recommend(match)
    direct = [r for r in recs if r.section == RecommendationSection.DIRECT_MATCHUP]
    names = {r.item_name for r in direct}
    assert "Extra Regen" in names
    assert "Healing Rite" in names
    assert any("Bebop" in r.reason and "1 200" in r.reason for r in direct)


def test_early_winning_lane_recommends_snowball_items() -> None:
    match = MatchState(
        timestamp=100.0,
        match_minutes=6.5,
        players=[
            _make_player(0, Team.SAPPHIRE_FLAME, "Haze", 5100, lane_id=1, is_self=True),
            _make_player(6, Team.AMBER_HAND, "Wraith", 3900, lane_id=1),
        ],
    )
    engine = RecommendationEngine()
    status, diff, _ = engine.evaluate_lane_status(match)
    assert status == LaneStatus.SNOWBALLING
    assert diff == 1200

    recs = engine.recommend(match)
    direct = [r for r in recs if r.section == RecommendationSection.DIRECT_MATCHUP]
    names = {r.item_name for r in direct}
    assert "Headshot Booster" in names
    assert "High-Velocity Rounds" in names
    assert all(r.reason_en for r in direct)


def test_multi_hero_counter_reason_lists_all_matching_enemies() -> None:
    match = MatchState(
        timestamp=500.0,
        match_minutes=20.0,
        players=[
            _make_player(0, Team.SAPPHIRE_FLAME, "Vindicta", 12_000, lane_id=1, is_self=True),
            _make_player(6, Team.AMBER_HAND, "Bebop", 16_000, lane_id=1),
            _make_player(7, Team.AMBER_HAND, "Seven", 15_500, lane_id=2),
            _make_player(8, Team.AMBER_HAND, "Lady Geist", 11_000, lane_id=3),
            _make_player(9, Team.AMBER_HAND, "Rem", 10_500, lane_id=2),
        ],
    )
    engine = RecommendationEngine()
    recs = engine.recommend(match)
    spirit_shield = next(
        r for r in recs
        if r.item_name == "Spirit Shielding" and r.section == RecommendationSection.GLOBAL_THREATS
    )
    for hero in ("Bebop", "Seven", "Lady Geist", "Rem"):
        assert hero in spirit_shield.reason
        assert hero in spirit_shield.target_heroes


def test_upgrade_graph_status_and_top_priority_with_tight_inventory() -> None:
    upgrade_graph = {
        "upgrades_from": {
            "sharpshooter": [{"name": "Long Range", "cost": 1600, "category": "Weapon", "tier": 2}],
            "headhunter": [{"name": "Headshot Booster", "cost": 800, "category": "Weapon", "tier": 1}],
            "crippling headshot": [{"name": "Headhunter", "cost": 3200, "category": "Weapon", "tier": 3}],
        },
        "upgrades_into": {
            "long range": [{"name": "Sharpshooter", "cost": 3200, "category": "Weapon", "tier": 3}],
            "headshot booster": [{"name": "Headhunter", "cost": 3200, "category": "Weapon", "tier": 3}],
            "headhunter": [{"name": "Crippling Headshot", "cost": 6400, "category": "Weapon", "tier": 4}],
        },
        "ancestors": {
            "crippling headshot": {"headhunter", "headshot booster"},
            "headhunter": {"headshot booster"},
        },
    }
    owned_9_items = [
        "Long Range",
        "Crippling Headshot",
        "Battle Vest",
        "Lucky Shot",
        "Spellslinger",
        "Dispel Magic",
        "Rapid Recharge",
        "Spiritual Overflow",
        "Glass Cannon",
    ]
    match = MatchState(
        timestamp=500.0,
        match_minutes=24.0,
        players=[
            _make_player(0, Team.SAPPHIRE_FLAME, "Vindicta", 22_000, items=owned_9_items, lane_id=1, is_self=True),
            _make_player(6, Team.AMBER_HAND, "Abrams", 28_000, items=["Leech"], lane_id=1),
            _make_player(7, Team.AMBER_HAND, "Bebop", 26_000, lane_id=2),
        ],
    )
    core_build = [
        {"item_name": "Headshot Booster", "category": "Weapon", "cost": 800, "tier": 1},
        {"item_name": "Long Range", "category": "Weapon", "cost": 1600, "tier": 2},
        {"item_name": "Sharpshooter", "category": "Weapon", "cost": 3200, "tier": 3},
        {"item_name": "Crippling Headshot", "category": "Weapon", "cost": 6400, "tier": 4},
    ]

    engine = RecommendationEngine()
    recs = engine.recommend(match, default_core_build=core_build, upgrade_graph=upgrade_graph)

    core_by_name = {r.item_name: r for r in recs if r.section == RecommendationSection.CORE_ITEMS}
    assert core_by_name["Sharpshooter"].upgrade_status == "upgrade_ready"
    assert core_by_name["Sharpshooter"].upgrades_from_owned == "Long Range"
    assert core_by_name["Sharpshooter"].net_cost == 1600
    assert core_by_name["Headshot Booster"].upgrade_status == "evolved"
    assert core_by_name["Headshot Booster"].already_owned is True

    top_prio = [r for r in recs if r.section == RecommendationSection.TOP_PRIORITY]
    assert 1 <= len(top_prio) <= 4
    assert any(r.item_name == "Sharpshooter" and r.upgrade_status == "upgrade_ready" for r in top_prio)

    direct = [r for r in recs if r.section == RecommendationSection.DIRECT_MATCHUP]
    assert len(direct) > 0
