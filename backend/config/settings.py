"""Application settings, resolution-independent ROI loader, and user profile helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from backend.models.game_state import Team

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROIS_PATH = Path(__file__).resolve().parent / "rois.json"
DEFAULT_RULES_PATH = PROJECT_ROOT / "data" / "item_rules.json"
DEFAULT_HERO_ALIASES_PATH = PROJECT_ROOT / "data" / "heroes_aliases.json"
DEFAULT_CACHE_DIR = PROJECT_ROOT / "data" / "cache"
DEFAULT_ITEM_ICONS_DIR = DEFAULT_CACHE_DIR / "item_icons"
DEFAULT_USER_PROFILE_PATH = PROJECT_ROOT / "data" / "user_profile.json"


@dataclass(frozen=True)
class NormalizedRoi:
    """Bounding box normalized in [0.0, 1.0] relative to full screen dimensions."""

    x: float
    y: float
    w: float
    h: float


@dataclass(frozen=True)
class InventoryGridConfig:
    """Normalized 6x2 bottom-left own inventory tile grid."""

    start_x: float
    start_y: float
    slot_w: float
    slot_h: float
    step_x: float
    step_y: float
    cols: int
    rows: int


@dataclass(frozen=True)
class ScoreboardItemGridConfig:
    """Normalized 2x6 per-player item grid under each TAB scoreboard column."""

    offset_x: float
    start_y: float
    slot_w: float
    slot_h: float
    step_x: float
    step_y: float
    cols: int
    rows: int


@dataclass(frozen=True)
class PlayerRoiConfig:
    """ROI mapping for a single scoreboard player column/card."""

    slot_index: int
    team: Team
    souls_roi: NormalizedRoi
    player_name_roi: NormalizedRoi | None = None
    hero_name_roi: NormalizedRoi | None = None


@dataclass(frozen=True)
class ScoreboardRoiConfig:
    """Full scoreboard & HUD ROI configuration."""

    aspect_ratio: str
    scoreboard_bounds: NormalizedRoi
    players: list[PlayerRoiConfig]
    match_timer_roi: NormalizedRoi | None = None
    own_inventory_grid: InventoryGridConfig | None = None
    scoreboard_item_grid: ScoreboardItemGridConfig | None = None


@dataclass(frozen=True)
class AppSettings:
    """Runtime settings for capture, OCR, API caching, and recommendation thresholds."""

    monitor_index: int = 1
    tab_settle_delay_ms: int = 120
    tab_min_interval_s: float = 0.35
    tab_hold_poll_interval_s: float = 1.0
    max_souls_jump_per_5s: int = 15_000
    early_lane_minutes: float = 10.0
    fed_souls_gap_threshold: int = 1_500
    fed_snowball_score_threshold: float = 0.20
    lane_lead_threshold: int = 800
    rois_path: Path = DEFAULT_ROIS_PATH
    rules_path: Path = DEFAULT_RULES_PATH
    hero_aliases_path: Path = DEFAULT_HERO_ALIASES_PATH
    cache_dir: Path = DEFAULT_CACHE_DIR
    item_icons_dir: Path = DEFAULT_ITEM_ICONS_DIR
    user_profile_path: Path = DEFAULT_USER_PROFILE_PATH


def load_rois(path: Path = DEFAULT_ROIS_PATH) -> ScoreboardRoiConfig:
    """Load normalized scoreboard and HUD ROIs from JSON."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    sb = raw["scoreboard_bounds"]
    timer_raw = raw.get("match_timer_roi")
    inv_raw = raw.get("own_inventory_grid")
    sb_items_raw = raw.get("scoreboard_item_grid")
    players = [
        PlayerRoiConfig(
            slot_index=int(entry["slot_index"]),
            team=Team(entry["team"]),
            souls_roi=NormalizedRoi(**entry["souls_roi"]),
            player_name_roi=NormalizedRoi(**entry["player_name_roi"]) if entry.get("player_name_roi") else None,
            hero_name_roi=NormalizedRoi(**entry["hero_name_roi"]) if entry.get("hero_name_roi") else None,
        )
        for entry in raw["players"]
    ]
    return ScoreboardRoiConfig(
        aspect_ratio=raw.get("aspect_ratio", "16:9"),
        scoreboard_bounds=NormalizedRoi(**sb),
        players=players,
        match_timer_roi=NormalizedRoi(**timer_raw) if timer_raw else None,
        own_inventory_grid=InventoryGridConfig(**inv_raw) if inv_raw else None,
        scoreboard_item_grid=ScoreboardItemGridConfig(**sb_items_raw) if sb_items_raw else None,
    )


def scale_roi(norm_roi: NormalizedRoi, width: int, height: int) -> tuple[int, int, int, int]:
    """Convert normalized (x, y, w, h) floats to clamped integer pixel coordinates."""
    x = max(0, min(width - 1, int(round(norm_roi.x * width))))
    y = max(0, min(height - 1, int(round(norm_roi.y * height))))
    w = max(1, min(width - x, int(round(norm_roi.w * width))))
    h = max(1, min(height - y, int(round(norm_roi.h * height))))
    return x, y, w, h


def load_user_pseudo(path: Path = DEFAULT_USER_PROFILE_PATH) -> str | None:
    """Load the user's saved in-game Deadlock pseudo if configured."""
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    pseudo = str(data.get("player_name", "")).strip()
    return pseudo or None


def save_user_pseudo(pseudo: str, path: Path = DEFAULT_USER_PROFILE_PATH) -> None:
    """Persist the user's in-game Deadlock pseudo locally."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"player_name": pseudo.strip()}, ensure_ascii=False, indent=2), encoding="utf-8")
