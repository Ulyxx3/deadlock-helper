"""End-to-end tests for OCR souls parsing, timer parsing, skin-proof hero matching, pseudo detection, and anti-jitter filtering."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from backend.config.settings import load_rois, scale_roi
from backend.engine.recommender import RecommendationEngine
from backend.models.game_state import Team
from backend.ocr.hero_matcher import HeroMatcher, match_player_pseudo
from backend.ocr.ocr_engine import RapidOcrBackend, parse_match_timer, parse_souls_text
from backend.ocr.souls_tracker import OcrSoulsTracker


def _render_synthetic_scoreboard(
    values_by_slot: dict[int, str],
    timer_text: str = "3:34",
    width: int = 1920,
    height: int = 1080,
) -> np.ndarray:
    """Create a realistic 1080p Deadlock horizontal top-bar scoreboard image."""
    img = Image.new("RGB", (width, height), color=(18, 22, 28))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 15)
        timer_font = ImageFont.truetype("arial.ttf", 15)
    except OSError:
        try:
            font = ImageFont.load_default(size=15)
            timer_font = ImageFont.load_default(size=15)
        except TypeError:
            font = ImageFont.load_default()
            timer_font = ImageFont.load_default()

    rois = load_rois()
    sb_x, sb_y, sb_w, sb_h = scale_roi(rois.scoreboard_bounds, width, height)
    draw.rectangle([sb_x, sb_y, sb_x + sb_w, sb_y + sb_h], fill=(24, 28, 34))

    if rois.match_timer_roi is not None and timer_text:
        tx, ty, tw, th = scale_roi(rois.match_timer_roi, width, height)
        draw.rectangle([tx, ty, tx + tw, ty + th], fill=(18, 18, 20))
        draw.text((tx + tw // 2, ty + th // 2), timer_text, fill=(235, 235, 235), font=timer_font, anchor="mm")

    for player in rois.players:
        x, y, w, h = scale_roi(player.souls_roi, width, height)
        pill_bg = (140, 95, 32) if player.team == Team.AMBER_HAND else (48, 86, 138)
        draw.rectangle([x, y, x + w, y + h], fill=pill_bg)
        text = values_by_slot.get(player.slot_index, "")
        if text:
            draw.text((x + w // 2, y + h // 2), text, fill=(175, 245, 220), font=font, anchor="mm")

    rgb = np.array(img, dtype=np.uint8)
    return rgb[:, :, ::-1].copy()  # RGB -> BGR


def test_parse_souls_text_variants() -> None:
    assert parse_souls_text("600") == 600
    assert parse_souls_text("G00") == 600
    assert parse_souls_text("|35k") == 35000
    assert parse_souls_text("135k") == 35000
    assert parse_souls_text("30:") == 30
    assert parse_souls_text("5.0") == 5000
    assert parse_souls_text("5,0") == 5000
    assert parse_souls_text("12.4") == 12400
    assert parse_souls_text("12.4k") == 12400
    assert parse_souls_text("12,4K") == 12400
    assert parse_souls_text("4,250") == 4250
    assert parse_souls_text("14 200") == 14200
    assert parse_souls_text("O850") == 850
    assert parse_souls_text("not a number") is None
    assert parse_souls_text("9999999") is None


def test_late_game_missing_k_and_timer_retention() -> None:
    tracker = OcrSoulsTracker(ocr_backend=RapidOcrBackend())
    # Simulate a 28:04 frame where '30', '29', '40', '31' lost their 'k' suffix
    img = _render_synthetic_scoreboard(
        {0: "30", 1: "22k", 2: "29", 6: "35k", 9: "40", 11: "31"},
        timer_text="28:04",
    )
    _, mins = tracker.extract_match_timer(img)
    assert mins == 28.07
    souls = tracker.extract_from_frame(img, match_minutes_hint=mins)
    assert souls[0] == 30000
    assert souls[1] == 22000
    assert souls[2] == 29000
    assert souls[6] == 35000
    assert souls[9] == 40000
    assert souls[11] == 31000

    # Even if next frame misses the clock, monotonic timer retention keeps 28.07 min
    blank_timer = _render_synthetic_scoreboard({0: "31k"}, timer_text="")
    _, retained = tracker.extract_match_timer(blank_timer)
    assert retained == 28.07


def test_parse_match_timer() -> None:
    assert parse_match_timer("3:34") == 3.57
    assert parse_match_timer("334") == 3.57
    assert parse_match_timer("14:30") == 14.5
    assert parse_match_timer("3:99") is None
    assert parse_match_timer("invalid") is None


def test_hero_matcher_fr_en_and_noisy_ocr() -> None:
    matcher = HeroMatcher()
    assert matcher.match("MGGINNIS") == "McGinnis"
    assert matcher.match("SERREGRISE") == "Grey Talon"
    assert matcher.match("TOMBALE") == "Graves"
    assert matcher.match("DAME GEIST") == "Lady Geist"
    assert matcher.match("VYPERE") == "Vyper"
    assert matcher.match("CELESTE") == "Celeste"
    assert matcher.match("VINDICTA") == "Vindicta"


def test_match_player_pseudo() -> None:
    names = {0: "Rem", 5: "ulyxx3", 6: "Pocket"}
    assert match_player_pseudo("Ulyxx3", names) == 5
    assert match_player_pseudo("Ulyx3", names) == 5
    assert match_player_pseudo("SomeoneElse", names) is None


def test_monotonic_anti_jitter_filter() -> None:
    tracker = OcrSoulsTracker(ocr_backend=RapidOcrBackend())
    assert tracker.apply_monotonic_filter(0, 4200, now=10.0, match_minutes=5.0) == 4200
    # Single-frame drop caused by OCR missing a digit must be rejected
    assert tracker.apply_monotonic_filter(0, 420, now=11.0, match_minutes=5.0) == 4200
    # Plausible increase is accepted
    assert tracker.apply_monotonic_filter(0, 4950, now=15.0, match_minutes=5.5) == 4950
    # Impossible single-frame spike (+30k in 1s) and economic ceiling (85k at 23 min) rejected
    assert tracker.apply_monotonic_filter(0, 35000, now=16.0, match_minutes=5.5) == 4950
    assert tracker.apply_monotonic_filter(1, 85000, now=20.0, match_minutes=23.0, lobby_median=22000.0) is None

    # 2-frame self-healing recovery if a lower value persists across 2 consecutive scans
    assert tracker.apply_monotonic_filter(2, 40000, now=10.0, match_minutes=23.0) == 40000
    assert tracker.apply_monotonic_filter(2, 20000, now=11.0, match_minutes=23.0) == 40000
    assert tracker.apply_monotonic_filter(2, 20500, now=12.0, match_minutes=23.0) == 20500


def test_dead_portrait_spectator_guard_and_team_sides() -> None:
    # Build synthetic 1024x575 scoreboard where left banner is Sapphire Blue,
    # Slot 05 has darkened portrait + red respawn countdown ("48"), and Slot 04 is alive.
    img = np.full((575, 1024, 3), 24, dtype=np.uint8)
    # Left banner blue (BGR: 190, 125, 90)
    img[23:41, 455:498] = (190, 125, 90)
    # Right banner amber (BGR: 20, 110, 175)
    img[23:41, 527:570] = (20, 110, 175)

    tracker = OcrSoulsTracker(ocr_backend=RapidOcrBackend())
    left_team, right_team = tracker.detect_team_sides(img)
    assert left_team == Team.SAPPHIRE_FLAME
    assert right_team == Team.AMBER_HAND

    cfg_slot5 = tracker.roi_config.players[5]
    cfg_slot4 = tracker.roi_config.players[4]
    # Draw darkened portrait + red respawn countdown text ("48") on slot 05
    px = int(cfg_slot5.souls_roi.x * 1024)
    pw = int(cfg_slot5.souls_roi.w * 1024)
    img[12:43, px : px + pw] = (40, 40, 50)
    cv2.putText(img, "48", (px + 3, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (30, 40, 235), 2)

    assert tracker.is_slot_dead(img, cfg_slot5) is True
    assert tracker.is_slot_dead(img, cfg_slot4) is False

    # Spectator POV guard: if _last_own_items has 6 items and self_is_dead=True,
    # extract_match_state must keep _last_own_items instead of reading bottom-left POV items
    tracker._locked_self_slot = 5
    tracker._last_own_items = ["Battle Vest", "Lucky Shot", "Glass Cannon", "Sharpshooter", "Spellslinger", "Rapid Recharge"]
    match = tracker.extract_match_state(img, player_pseudo="Ulyxx3")
    assert match.self_is_dead is True
    assert match.self_player is not None
    assert match.self_player.items == tracker._last_own_items


def test_rapidocr_end_to_end_on_synthetic_scoreboard() -> None:
    expected_strings = {
        0: "600",
        1: "4,250",
        2: "12.4k",
        5: "5.0",
        6: "15,100",
        7: "10,600",
        11: "6,350",
    }
    expected_values = {
        0: 600,
        1: 4250,
        2: 12400,
        5: 5000,
        6: 15100,
        7: 10600,
        11: 6350,
    }
    frame = _render_synthetic_scoreboard(expected_strings, timer_text="3:34")
    tracker = OcrSoulsTracker(ocr_backend=RapidOcrBackend())
    extracted = tracker.extract_from_frame(frame)
    _, match_minutes = tracker.extract_match_timer(frame)

    assert match_minutes == 3.57
    for slot, expected_val in expected_values.items():
        assert extracted.get(slot) == expected_val, f"Slot {slot} mismatch: got {extracted.get(slot)}, expected {expected_val}"


def test_native_screenshot_full_match_extraction() -> None:
    sample_path = Path("images/image.png")
    if not sample_path.exists():
        return

    frame = cv2.imread(str(sample_path))
    assert frame is not None

    tracker = OcrSoulsTracker(ocr_backend=RapidOcrBackend())
    match = tracker.extract_match_state(frame, player_pseudo="Ulyxx3")

    assert match.match_minutes == 27.88
    expected_heroes = [
        "Rem",
        "Graves",
        "Grey Talon",
        "Vyper",
        "Celeste",
        "Vindicta",
        "Pocket",
        "Lady Geist",
        "McGinnis",
        "McGinnis",
        "Paradox",
        "Paige",
    ]
    assert [p.hero_name for p in match.players] == expected_heroes

    me = match.self_player
    assert me is not None
    assert me.slot_index == 5
    assert me.hero_name == "Vindicta"
    assert me.souls == 6600

    recs = RecommendationEngine().recommend(match)
    assert len(recs) > 0
