"""Unit and integration tests for corner-masked ItemMatcher."""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from backend.config.settings import DEFAULT_ITEM_ICONS_DIR
from backend.ocr.item_matcher import ItemMatcher
from backend.ocr.souls_tracker import OcrSoulsTracker


def test_is_empty_slot_rejects_dark_uniform_tile() -> None:
    empty = np.full((54, 54, 3), 24, dtype=np.uint8)
    assert ItemMatcher.is_empty_slot(empty) is True

    colored = np.zeros((54, 54, 3), dtype=np.uint8)
    cv2.circle(colored, (27, 27), 16, (40, 180, 240), -1)
    assert ItemMatcher.is_empty_slot(colored) is False


def test_corner_masked_matching_ignores_tier_and_keybind_badges(tmp_path: Path) -> None:
    # Create two distinct synthetic item icons
    icon_a = np.zeros((64, 64, 3), dtype=np.uint8)
    icon_a[:] = (35, 65, 105)
    cv2.circle(icon_a, (32, 32), 18, (60, 190, 245), -1)
    cv2.imwrite(str(tmp_path / "1.png"), icon_a)

    icon_b = np.zeros((64, 64, 3), dtype=np.uint8)
    icon_b[:] = (95, 45, 75)
    cv2.rectangle(icon_b, (14, 14), (50, 50), (220, 120, 210), -1)
    cv2.imwrite(str(tmp_path / "2.png"), icon_b)

    manifest = {
        "1": {"id": 1, "name": "Lucky Shot", "slot_type": "weapon", "filename": "1.png"},
        "2": {"id": 2, "name": "Boundless Spirit", "slot_type": "spirit", "filename": "2.png"},
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    matcher = ItemMatcher(icons_dir=tmp_path)
    assert matcher.is_ready

    # Add Roman numeral 'IV' in top-right and 'ACTIF' badge in bottom-right
    tile = cv2.resize(icon_a, (54, 54))
    cv2.rectangle(tile, (36, 0), (54, 16), (255, 255, 255), -1)
    cv2.rectangle(tile, (34, 38), (54, 54), (20, 20, 20), -1)
    cv2.putText(tile, "IV", (38, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 0, 0), 1)

    matched = matcher.match_tile(tile, min_score=0.50)
    assert matched is not None
    assert matched[0] == "Lucky Shot"


def test_real_screenshot_inventory_detection() -> None:
    sample_path = Path("images/image.png")
    manifest_path = DEFAULT_ITEM_ICONS_DIR / "manifest.json"
    if not sample_path.exists() or not manifest_path.exists():
        return

    frame = cv2.imread(str(sample_path))
    assert frame is not None

    tracker = OcrSoulsTracker(item_matcher=ItemMatcher(DEFAULT_ITEM_ICONS_DIR))
    detected = tracker.extract_own_inventory(frame)
    slots_found = {idx for idx, _, _, _ in detected}

    # On updated images/image.png: 9 items bought (slots 0..4 and 6..9), 3 empty slots (5, 10, 11)
    assert len(detected) == 9
    assert slots_found == {0, 1, 2, 3, 4, 6, 7, 8, 9}
    assert slots_found.isdisjoint({5, 10, 11})


def test_all_item_rules_exist_in_manifest() -> None:
    manifest_path = DEFAULT_ITEM_ICONS_DIR / "manifest.json"
    if not manifest_path.exists():
        return

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    by_name = {v["name"].strip().lower(): v for v in manifest.values()}
    rules = json.loads(Path("data/item_rules.json").read_text(encoding="utf-8"))

    for group in ("counter_items", "lane_defensive_items", "lane_snowball_items"):
        for entry in rules[group]:
            name = entry["item_name"]
            assert name.strip().lower() in by_name, f"Outdated/missing item in {group}: {name}"

    for name in rules["key_power_spike_items"]:
        assert name.strip().lower() in by_name, f"Outdated/missing item in key_power_spike_items: {name}"
