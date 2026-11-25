"""Core domain models for Deadlock Helper."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Team(str, Enum):
    """Deadlock faction identifiers."""

    SAPPHIRE_FLAME = "sapphire_flame"
    AMBER_HAND = "amber_hand"


class LaneStatus(str, Enum):
    """Player's current laning economy state."""

    SNOWBALLING = "snowballing"
    EVEN = "even"
    BEHIND = "behind"


class RecommendationSection(str, Enum):
    """UI display buckets for the companion overlay."""

    TOP_PRIORITY = "Priorité absolue"
    DIRECT_MATCHUP = "Matchup direct"
    GLOBAL_THREATS = "Menaces globales"
    CORE_ITEMS = "Items Core"
    SITUATIONAL_ITEMS = "Items Situationnels"


@dataclass
class BuildBalance:
    """Breakdown of the local player's current build across Weapon/Spirit/Vitality/Sustain."""

    weapon_count: int
    spirit_count: int
    vitality_count: int
    sustain_count: int
    needs_damage: bool
    needs_sustain: bool
    needs_defense: bool


@dataclass
class PlayerState:
    """Snapshot of a single player's state extracted from scoreboard or test fixture."""

    slot_index: int
    team: Team
    hero_name: str
    souls: int
    kills: int = 0
    deaths: int = 0
    assists: int = 0
    items: list[str] = field(default_factory=list)
    lane_id: int | None = None
    is_self: bool = False
    player_name: str = ""


@dataclass
class MatchState:
    """Full live match state at a given point in time."""

    timestamp: float
    match_minutes: float
    players: list[PlayerState]
    self_is_dead: bool = False

    @property
    def self_player(self) -> PlayerState | None:
        """Return the local player if marked."""
        for player in self.players:
            if player.is_self:
                return player
        return None

    @property
    def allies(self) -> list[PlayerState]:
        """Return all teammates excluding the local player."""
        me = self.self_player
        if me is None:
            return []
        return [p for p in self.players if p.team == me.team and not p.is_self]

    @property
    def enemies(self) -> list[PlayerState]:
        """Return all enemy players relative to the local player."""
        me = self.self_player
        if me is None:
            return []
        return [p for p in self.players if p.team != me.team]

    @property
    def lobby_average_souls(self) -> float:
        """Mean souls across all active players in the match."""
        if not self.players:
            return 0.0
        return sum(p.souls for p in self.players) / len(self.players)


@dataclass
class SnowballReport:
    """Quantified snowball assessment for an enemy hero."""

    hero_name: str
    souls: int
    souls_gap_vs_avg: int
    snowball_score: float
    is_fed: bool
    key_items: list[str] = field(default_factory=list)


@dataclass
class ItemRecommendation:
    """Single item suggestion with conditional explanations, upgrade tracking, and priority."""

    item_name: str
    category: str
    cost: int
    section: RecommendationSection
    reason: str
    priority: float
    already_owned: bool = False
    reason_en: str = ""
    upgrade_status: str = "new"  # "new" | "upgrade_ready" | "owned" | "evolved"
    upgrades_from_owned: str | None = None
    net_cost: int | None = None
    target_heroes: list[str] = field(default_factory=list)
