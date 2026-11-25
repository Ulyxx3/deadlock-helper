"""Scoreboard souls, hero, item, dead-state, and team-side tracker with anti-jitter recovery."""

from __future__ import annotations

import statistics
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path

import cv2
import numpy as np

from backend.capture.screen_capture import ScreenCapture
from backend.capture.tab_listener import TabScoreboardListener
from backend.config.settings import (
    AppSettings,
    NormalizedRoi,
    PlayerRoiConfig,
    ScoreboardRoiConfig,
    load_rois,
    scale_roi,
)
from backend.models.game_state import MatchState, PlayerState, Team
from backend.ocr.hero_matcher import HeroMatcher, match_player_pseudo
from backend.ocr.item_matcher import ItemMatcher
from backend.ocr.ocr_engine import (
    OcrBackend,
    RapidOcrBackend,
    parse_match_timer,
    parse_souls_text,
)
from backend.ocr.preprocessor import preprocess_souls_roi


class MatchDataProvider(ABC):
    """Abstract live match data provider (allows seamless swap if Valve adds GSI)."""

    @abstractmethod
    def poll_souls(self) -> dict[int, int]:
        """Return a mapping of player slot_index (0..11) -> current souls."""


class GsiProvider(MatchDataProvider):
    """Future Valve Game State Integration provider stub."""

    def poll_souls(self) -> dict[int, int]:
        raise NotImplementedError(
            "Valve n'a pas encore activé le Game State Integration (GSI) pour Deadlock. "
            "Utilisez OcrSoulsTracker en attendant."
        )


class OcrSoulsTracker(MatchDataProvider):
    """VAC-safe scoreboard OCR & item icon tracker with dead/spectator POV protection."""

    def __init__(
        self,
        settings: AppSettings | None = None,
        roi_config: ScoreboardRoiConfig | None = None,
        ocr_backend: OcrBackend | None = None,
        hero_matcher: HeroMatcher | None = None,
        item_matcher: ItemMatcher | None = None,
    ) -> None:
        self.settings = settings or AppSettings()
        self.roi_config = roi_config or load_rois(self.settings.rois_path)
        self._ocr_backend = ocr_backend
        self._hero_matcher = hero_matcher
        self._item_matcher = item_matcher
        self._capture = ScreenCapture(monitor_index=self.settings.monitor_index)
        self._last_valid_souls: dict[int, int] = {}
        self._last_update_ts: dict[int, float] = {}
        self._pending_lower: dict[int, tuple[int, int]] = {}
        self._last_valid_minutes: float | None = None
        self._locked_heroes: dict[int, str] = {}
        self._locked_player_names: dict[int, str] = {}
        self._locked_self_slot: int | None = None
        self._last_own_items: list[str] = []

    @property
    def ocr_backend(self) -> OcrBackend:
        if self._ocr_backend is None:
            self._ocr_backend = RapidOcrBackend()
        return self._ocr_backend

    @property
    def hero_matcher(self) -> HeroMatcher:
        if self._hero_matcher is None:
            self._hero_matcher = HeroMatcher(self.settings.hero_aliases_path)
        return self._hero_matcher

    @property
    def item_matcher(self) -> ItemMatcher:
        if self._item_matcher is None:
            self._item_matcher = ItemMatcher(self.settings.item_icons_dir)
        return self._item_matcher

    def reset_match(self) -> None:
        """Clear monotonic history, locked heroes/self slot, and protected inventory cache."""
        self._last_valid_souls.clear()
        self._last_update_ts.clear()
        self._pending_lower.clear()
        self._last_valid_minutes = None
        self._locked_heroes.clear()
        self._locked_player_names.clear()
        self._locked_self_slot = None
        self._last_own_items.clear()

    def apply_monotonic_filter(
        self,
        slot_index: int,
        candidate_souls: int | None,
        now: float | None = None,
        match_minutes: float | None = None,
        lobby_median: float | None = None,
    ) -> int | None:
        """Reject impossible spikes/drops while allowing 2-frame recovery if a lower value persists."""
        if candidate_souls is None:
            return self._last_valid_souls.get(slot_index)

        # Economic ceiling: prevent OCR spikes like 85k at 23 min or >2.5x lobby median
        if match_minutes is not None and match_minutes > 0:
            max_by_time = max(7_500, int(match_minutes * 2_200 + 4_000))
            if candidate_souls > max_by_time:
                return self._last_valid_souls.get(slot_index)

        if lobby_median is not None and lobby_median >= 5_000 and candidate_souls > int(lobby_median * 2.5):
            return self._last_valid_souls.get(slot_index)

        ts = now if now is not None else time.monotonic()
        prev = self._last_valid_souls.get(slot_index)
        if prev is None:
            self._last_valid_souls[slot_index] = candidate_souls
            self._last_update_ts[slot_index] = ts
            self._pending_lower.pop(slot_index, None)
            return candidate_souls

        if candidate_souls < prev:
            # Reject single-frame drops, but self-heal after 2 consecutive consistent lower frames
            pending = self._pending_lower.get(slot_index)
            if pending is not None and abs(candidate_souls - pending[0]) <= 2_500:
                count = pending[1] + 1
                if count >= 2:
                    self._last_valid_souls[slot_index] = candidate_souls
                    self._last_update_ts[slot_index] = ts
                    self._pending_lower.pop(slot_index, None)
                    return candidate_souls
                self._pending_lower[slot_index] = (candidate_souls, count)
            else:
                self._pending_lower[slot_index] = (candidate_souls, 1)
            return prev

        self._pending_lower.pop(slot_index, None)
        elapsed = max(0.1, ts - self._last_update_ts.get(slot_index, ts))
        allowed_jump = min(18_000, max(3_500, int(elapsed * 180)))
        if (candidate_souls - prev) > allowed_jump:
            return prev

        self._last_valid_souls[slot_index] = candidate_souls
        self._last_update_ts[slot_index] = ts
        return candidate_souls

    def _ocr_roi(
        self,
        frame_bgr: np.ndarray,
        norm_roi: NormalizedRoi | None,
        frame_origin: tuple[int, int],
        screen_size: tuple[int, int],
    ) -> tuple[str, tuple[int, int, int, int] | None]:
        if norm_roi is None:
            return "", None
        fh, fw = frame_bgr.shape[:2]
        ox, oy = frame_origin
        px, py, pw, ph = scale_roi(norm_roi, screen_size[0], screen_size[1])
        lx, ly = px - ox, py - oy
        if lx < 0 or ly < 0 or lx + pw > fw or ly + ph > fh:
            return "", None
        crop = frame_bgr[ly : ly + ph, lx : lx + pw]
        processed = preprocess_souls_roi(crop)
        return self.ocr_backend.recognize_text(processed), (lx, ly, pw, ph)

    @staticmethod
    def detect_team_sides(
        frame_bgr: np.ndarray,
        frame_origin: tuple[int, int] = (0, 0),
        full_screen_size: tuple[int, int] | None = None,
    ) -> tuple[Team, Team]:
        """Detect whether left slots (0..5) are Sapphire Flame or Amber Hand via banner color."""
        fh, fw = frame_bgr.shape[:2]
        screen_w, screen_h = full_screen_size or (fw, fh)
        ox, oy = frame_origin

        left_roi = NormalizedRoi(x=0.445, y=0.040, w=0.042, h=0.032)
        px, py, pw, ph = scale_roi(left_roi, screen_w, screen_h)
        lx, ly = px - ox, py - oy
        if lx >= 0 and ly >= 0 and lx + pw <= fw and ly + ph <= fh:
            patch = frame_bgr[ly : ly + ph, lx : lx + pw]
            mean_bgr = patch.mean(axis=(0, 1))
            if float(mean_bgr[0]) > float(mean_bgr[2]) + 20.0:
                return Team.SAPPHIRE_FLAME, Team.AMBER_HAND
        return Team.AMBER_HAND, Team.SAPPHIRE_FLAME

    @staticmethod
    def is_slot_dead(
        frame_bgr: np.ndarray,
        player_cfg: PlayerRoiConfig,
        frame_origin: tuple[int, int] = (0, 0),
        full_screen_size: tuple[int, int] | None = None,
    ) -> bool:
        """Detect whether a player portrait displays the darkened state + red respawn timer."""
        fh, fw = frame_bgr.shape[:2]
        screen_w, screen_h = full_screen_size or (fw, fh)
        ox, oy = frame_origin
        portrait_roi = NormalizedRoi(
            x=player_cfg.souls_roi.x,
            y=0.020,
            w=player_cfg.souls_roi.w,
            h=0.055,
        )
        px, py, pw, ph = scale_roi(portrait_roi, screen_w, screen_h)
        lx, ly = px - ox, py - oy
        if lx < 0 or ly < 0 or lx + pw > fw or ly + ph > fh:
            return False

        crop = frame_bgr[ly : ly + ph, lx : lx + pw]
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        red_mask = ((hsv[:, :, 0] <= 14) | (hsv[:, :, 0] >= 166)) & (hsv[:, :, 1] > 140) & (hsv[:, :, 2] > 140)
        red_ratio = float(red_mask.mean())
        mean_val = float(hsv[:, :, 2].mean())
        return red_ratio >= 0.08 and mean_val < 118.0

    def extract_match_timer(
        self,
        frame_bgr: np.ndarray,
        frame_origin: tuple[int, int] = (0, 0),
        full_screen_size: tuple[int, int] | None = None,
    ) -> tuple[str | None, float | None]:
        """Extract the match clock text and minutes float from `match_timer_roi`."""
        fh, fw = frame_bgr.shape[:2]
        screen_size = full_screen_size or (fw, fh)
        raw_text, _ = self._ocr_roi(frame_bgr, self.roi_config.match_timer_roi, frame_origin, screen_size)
        parsed = parse_match_timer(raw_text)
        if parsed is not None:
            if self._last_valid_minutes is None or parsed >= self._last_valid_minutes:
                self._last_valid_minutes = parsed
        elif self._last_valid_minutes is not None:
            parsed = self._last_valid_minutes
        return (raw_text or None), parsed

    def extract_own_inventory(
        self,
        frame_bgr: np.ndarray,
        full_screen_size: tuple[int, int] | None = None,
        min_score: float = 0.45,
    ) -> list[tuple[int, str, float, tuple[int, int, int, int]]]:
        """Detect purchased items in the bottom-left 6x2 own inventory grid."""
        grid = self.roi_config.own_inventory_grid
        if grid is None or not self.item_matcher.is_ready:
            return []

        fh, fw = frame_bgr.shape[:2]
        screen_w, screen_h = full_screen_size or (fw, fh)
        detected: list[tuple[int, str, float, tuple[int, int, int, int]]] = []

        for r in range(grid.rows):
            for c in range(grid.cols):
                idx = r * grid.cols + c
                norm_tile = NormalizedRoi(
                    x=grid.start_x + c * grid.step_x,
                    y=grid.start_y + r * grid.step_y,
                    w=grid.slot_w,
                    h=grid.slot_h,
                )
                tx, ty, tw, th = scale_roi(norm_tile, screen_w, screen_h)
                if tx + tw > fw or ty + th > fh:
                    continue
                tile = frame_bgr[ty : ty + th, tx : tx + tw]
                match = self.item_matcher.match_tile(tile, min_score=min_score)
                if match is not None:
                    detected.append((idx, match[0], match[1], (tx, ty, tw, th)))
        return detected

    def extract_player_scoreboard_items(
        self,
        frame_bgr: np.ndarray,
        player_cfg: PlayerRoiConfig,
        frame_origin: tuple[int, int] = (0, 0),
        full_screen_size: tuple[int, int] | None = None,
        min_score: float = 0.52,
    ) -> list[str]:
        """Detect purchased items in a player's 2x6 TAB scoreboard item grid."""
        grid = self.roi_config.scoreboard_item_grid
        if grid is None or not self.item_matcher.is_ready or player_cfg.player_name_roi is None:
            return []

        fh, fw = frame_bgr.shape[:2]
        screen_w, screen_h = full_screen_size or (fw, fh)
        ox, oy = frame_origin
        base_x = player_cfg.player_name_roi.x + grid.offset_x

        items: list[str] = []
        seen: set[str] = set()
        for c in range(grid.cols):
            for r in range(grid.rows):
                norm_tile = NormalizedRoi(
                    x=base_x + c * grid.step_x,
                    y=grid.start_y + r * grid.step_y,
                    w=grid.slot_w,
                    h=grid.slot_h,
                )
                px, py, pw, ph = scale_roi(norm_tile, screen_w, screen_h)
                lx, ly = px - ox, py - oy
                if lx < 0 or ly < 0 or lx + pw > fw or ly + ph > fh:
                    break
                tile = frame_bgr[ly : ly + ph, lx : lx + pw]
                res = self.item_matcher.match_tile(tile, min_score=min_score)
                if res is None:
                    break
                if res[0] not in seen:
                    seen.add(res[0])
                    items.append(res[0])

        return items

    def extract_from_frame(
        self,
        frame_bgr: np.ndarray,
        frame_origin: tuple[int, int] = (0, 0),
        full_screen_size: tuple[int, int] | None = None,
        dump_debug_dir: Path | None = None,
        now: float | None = None,
        match_minutes_hint: float | None = None,
    ) -> dict[int, int]:
        """Extract souls for all 12 scoreboard slots from a BGR image."""
        fh, fw = frame_bgr.shape[:2]
        screen_w, screen_h = full_screen_size or (fw, fh)
        ox, oy = frame_origin

        annotated = frame_bgr.copy() if dump_debug_dir is not None else None
        if dump_debug_dir is not None:
            dump_debug_dir.mkdir(parents=True, exist_ok=True)

        raw_candidates: dict[int, int | None] = {}
        debug_crops: dict[int, tuple[tuple[int, int, int, int], np.ndarray, str]] = {}

        for player_cfg in self.roi_config.players:
            px, py, pw, ph = scale_roi(player_cfg.souls_roi, screen_w, screen_h)
            lx, ly = px - ox, py - oy
            if lx < 0 or ly < 0 or lx + pw > fw or ly + ph > fh:
                continue

            crop = frame_bgr[ly : ly + ph, lx : lx + pw]
            processed = preprocess_souls_roi(crop)
            raw_text = self.ocr_backend.recognize_text(processed)
            parsed = parse_souls_text(raw_text)
            raw_candidates[player_cfg.slot_index] = parsed
            debug_crops[player_cfg.slot_index] = ((lx, ly, pw, ph), processed, player_cfg.team.value)

        known_vals = [v for v in raw_candidates.values() if v is not None]
        known_vals.extend(self._last_valid_souls.values())
        max_known = max(known_vals, default=0)
        is_late_economy = max_known >= 4_000 or (match_minutes_hint is not None and match_minutes_hint >= 4.0)
        if is_late_economy:
            for slot, val in list(raw_candidates.items()):
                if val is not None and 10 <= val <= 99:
                    raw_candidates[slot] = val * 1000

        median_pool = [v for v in raw_candidates.values() if v is not None and v >= 500]
        lobby_median = float(statistics.median(median_pool)) if len(median_pool) >= 4 else None

        results: dict[int, int] = {}
        for slot, candidate in raw_candidates.items():
            filtered = self.apply_monotonic_filter(
                slot,
                candidate,
                now=now,
                match_minutes=match_minutes_hint,
                lobby_median=lobby_median,
            )
            if filtered is not None:
                results[slot] = filtered

            if annotated is not None and dump_debug_dir is not None and slot in debug_crops:
                (lx, ly, pw, ph), processed, team_val = debug_crops[slot]
                color = (240, 160, 60) if team_val == "sapphire_flame" else (40, 175, 240)
                cv2.rectangle(annotated, (lx, ly), (lx + pw, ly + ph), color, 2)
                label = f"#{slot}:{filtered if filtered is not None else '?'}"
                cv2.putText(annotated, label, (lx, max(12, ly - 5)), cv2.FONT_HERSHEY_SIMPLEX, 0.42, color, 1, cv2.LINE_AA)
                cv2.imwrite(str(dump_debug_dir / f"slot_{slot:02d}_proc.png"), processed)

        if annotated is not None and dump_debug_dir is not None:
            if self.roi_config.match_timer_roi is not None:
                tx, ty, tw, th = scale_roi(self.roi_config.match_timer_roi, screen_w, screen_h)
                tlx, tly = tx - ox, ty - oy
                if tlx >= 0 and tly >= 0 and tlx + tw <= fw and tly + th <= fh:
                    raw_timer, _ = self.extract_match_timer(frame_bgr, frame_origin, full_screen_size)
                    cv2.rectangle(annotated, (tlx, tly), (tlx + tw, tly + th), (120, 255, 120), 2)
                    cv2.putText(annotated, raw_timer or "?", (tlx, tly + th + 14), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (120, 255, 120), 1, cv2.LINE_AA)
            cv2.imwrite(str(dump_debug_dir / "scoreboard_rois_overlay.png"), annotated)

        return results

    def extract_match_state(
        self,
        frame_bgr: np.ndarray,
        player_pseudo: str | None = None,
        frame_origin: tuple[int, int] = (0, 0),
        full_screen_size: tuple[int, int] | None = None,
        dump_debug_dir: Path | None = None,
        now: float | None = None,
    ) -> MatchState:
        """Extract souls, timer, team sides, dead-state, heroes, items, and `is_self`."""
        fh, fw = frame_bgr.shape[:2]
        screen_size = full_screen_size or (fw, fh)

        left_team, right_team = self.detect_team_sides(frame_bgr, frame_origin, screen_size)
        _, match_minutes = self.extract_match_timer(frame_bgr, frame_origin, screen_size)
        souls_by_slot = self.extract_from_frame(
            frame_bgr=frame_bgr,
            frame_origin=frame_origin,
            full_screen_size=screen_size,
            dump_debug_dir=dump_debug_dir,
            now=now,
            match_minutes_hint=match_minutes,
        )

        debug_boxes: list[tuple[int, tuple[int, int, int, int] | None, tuple[int, int, int, int] | None]] = []
        for player_cfg in self.roi_config.players:
            slot = player_cfg.slot_index
            name_box: tuple[int, int, int, int] | None = None
            hero_box: tuple[int, int, int, int] | None = None

            if slot not in self._locked_player_names and player_cfg.player_name_roi is not None:
                raw_pname, name_box = self._ocr_roi(frame_bgr, player_cfg.player_name_roi, frame_origin, screen_size)
                if raw_pname.strip():
                    self._locked_player_names[slot] = raw_pname.strip()

            if slot not in self._locked_heroes:
                raw_hero, hero_box = self._ocr_roi(frame_bgr, player_cfg.hero_name_roi, frame_origin, screen_size)
                matched_hero = self.hero_matcher.match(raw_hero)
                if matched_hero is None and slot in self._locked_player_names:
                    matched_hero = self.hero_matcher.match(self._locked_player_names[slot])
                if matched_hero is not None:
                    self._locked_heroes[slot] = matched_hero

            debug_boxes.append((slot, name_box, hero_box))

        if player_pseudo and self._locked_self_slot is None:
            self._locked_self_slot = match_player_pseudo(player_pseudo, self._locked_player_names)

        self_is_dead = False
        if self._locked_self_slot is not None:
            self_cfg = next((p for p in self.roi_config.players if p.slot_index == self._locked_self_slot), None)
            if self_cfg is not None:
                self_is_dead = self.is_slot_dead(frame_bgr, self_cfg, frame_origin, screen_size)

        # Protect own inventory when dead / spectating another player's POV
        has_full_bottom_hud = frame_origin == (0, 0) and fh >= int(screen_size[1] * 0.95)
        own_inv_matches: list[tuple[int, str, float, tuple[int, int, int, int]]] = []
        if has_full_bottom_hud and not self_is_dead:
            own_inv_matches = self.extract_own_inventory(frame_bgr, full_screen_size=screen_size)
            scanned_names: list[str] = []
            seen_own: set[str] = set()
            for _, item_name, _, _ in own_inv_matches:
                if item_name not in seen_own:
                    seen_own.add(item_name)
                    scanned_names.append(item_name)

            # Sudden-Swap Guard: if >=4 items were previously known and <40% overlap remains,
            # assume spectator camera transition and retain previous alive inventory.
            if len(self._last_own_items) >= 4 and scanned_names:
                overlap = len(set(self._last_own_items) & set(scanned_names))
                if overlap / len(self._last_own_items) < 0.40:
                    own_inv_names = list(self._last_own_items)
                else:
                    own_inv_names = scanned_names
                    self._last_own_items = scanned_names
            elif scanned_names:
                own_inv_names = scanned_names
                self._last_own_items = scanned_names
            else:
                own_inv_names = list(self._last_own_items)
        else:
            own_inv_names = list(self._last_own_items)

        players: list[PlayerState] = []
        for player_cfg in self.roi_config.players:
            slot = player_cfg.slot_index
            is_self = slot == self._locked_self_slot
            actual_team = left_team if slot < 6 else right_team

            if is_self and own_inv_names:
                items = own_inv_names
            else:
                items = self.extract_player_scoreboard_items(
                    frame_bgr,
                    player_cfg,
                    frame_origin=frame_origin,
                    full_screen_size=screen_size,
                )
                if is_self and items and not self._last_own_items:
                    self._last_own_items = list(items)

            players.append(
                PlayerState(
                    slot_index=slot,
                    team=actual_team,
                    hero_name=self._locked_heroes.get(slot, f"Unknown_{slot:02d}"),
                    souls=souls_by_slot.get(slot, 0),
                    items=items,
                    lane_id=((slot % 6) // 2) + 1,
                    is_self=is_self,
                    player_name=self._locked_player_names.get(slot, ""),
                )
            )

        if dump_debug_dir is not None:
            overlay_path = dump_debug_dir / "scoreboard_rois_overlay.png"
            overlay = cv2.imread(str(overlay_path)) if overlay_path.exists() else frame_bgr.copy()
            if overlay is not None:
                for slot, name_box, hero_box in debug_boxes:
                    is_self = slot == self._locked_self_slot
                    box_color = (80, 255, 80) if is_self else (180, 180, 180)
                    if name_box is not None:
                        nx, ny, nw, nh = name_box
                        cv2.rectangle(overlay, (nx, ny), (nx + nw, ny + nh), box_color, 2 if is_self else 1)
                    if hero_box is not None:
                        hx, hy, hw, hh = hero_box
                        cv2.rectangle(overlay, (hx, hy), (hx + hw, hy + hh), (200, 140, 255), 1)
                        label = self._locked_heroes.get(slot, "?")
                        if is_self:
                            label = f"[TOI{' MORT' if self_is_dead else ''}] {label}"
                        cv2.putText(overlay, label, (hx, hy + hh + 12), cv2.FONT_HERSHEY_SIMPLEX, 0.36, box_color, 1, cv2.LINE_AA)
                for idx, item_name, score, (ix, iy, iw, ih) in own_inv_matches:
                    cv2.rectangle(overlay, (ix, iy), (ix + iw, iy + ih), (80, 255, 80), 2)
                    cv2.putText(overlay, f"{item_name[:10]}", (ix, max(12, iy - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.32, (80, 255, 80), 1, cv2.LINE_AA)
                cv2.imwrite(str(overlay_path), overlay)

        return MatchState(
            timestamp=time.time(),
            match_minutes=match_minutes if match_minutes is not None else 0.0,
            players=players,
            self_is_dead=self_is_dead,
        )

    def poll_souls(self, dump_debug_dir: Path | None = None) -> dict[int, int]:
        """Capture ONLY the scoreboard region on screen and OCR all 12 soul slots."""
        mon_size = self._capture.get_monitor_size()
        sb_roi: NormalizedRoi = self.roi_config.scoreboard_bounds
        frame_bgr, (rx, ry, _, _) = self._capture.grab_region(sb_roi)
        return self.extract_from_frame(
            frame_bgr=frame_bgr,
            frame_origin=(rx, ry),
            full_screen_size=mon_size,
            dump_debug_dir=dump_debug_dir,
        )

    def poll_match_state(
        self,
        player_pseudo: str | None = None,
        dump_debug_dir: Path | None = None,
    ) -> MatchState:
        """Capture full monitor (for bottom-left own inventory + top TAB scoreboard) and extract MatchState."""
        mon_size = self._capture.get_monitor_size()
        frame_bgr = self._capture.grab_full_monitor()
        return self.extract_match_state(
            frame_bgr=frame_bgr,
            player_pseudo=player_pseudo,
            frame_origin=(0, 0),
            full_screen_size=mon_size,
            dump_debug_dir=dump_debug_dir,
        )

    def run_live(self, on_update: Callable[[dict[int, int]], None]) -> None:
        """Start the TAB-triggered live loop for raw souls updates."""
        _ = self.ocr_backend

        def _handle_tab() -> None:
            souls_map = self.poll_souls()
            if souls_map:
                on_update(souls_map)

        listener = TabScoreboardListener(
            on_scoreboard_visible=_handle_tab,
            settle_delay_ms=self.settings.tab_settle_delay_ms,
            min_interval_s=self.settings.tab_min_interval_s,
            hold_poll_interval_s=self.settings.tab_hold_poll_interval_s,
        )
        listener.run_forever()

    def run_live_match(
        self,
        on_match_update: Callable[[MatchState], None],
        player_pseudo: str | None = None,
    ) -> None:
        """Start the TAB-triggered live loop returning full MatchState snapshots."""
        _ = self.ocr_backend
        _ = self.hero_matcher
        _ = self.item_matcher

        def _handle_tab() -> None:
            match_state = self.poll_match_state(player_pseudo=player_pseudo)
            if match_state.players:
                on_match_update(match_state)

        listener = TabScoreboardListener(
            on_scoreboard_visible=_handle_tab,
            settle_delay_ms=self.settings.tab_settle_delay_ms,
            min_interval_s=self.settings.tab_min_interval_s,
            hold_poll_interval_s=self.settings.tab_hold_poll_interval_s,
        )
        listener.run_forever()
