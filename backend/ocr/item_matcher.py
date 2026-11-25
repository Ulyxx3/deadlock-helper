"""Corner-masked vectorized item icon recognizer for Deadlock inventory & scoreboard grids."""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from backend.config.settings import DEFAULT_ITEM_ICONS_DIR

_SLOT_BACKGROUNDS_BGR = {
    "weapon": np.array([34, 62, 102], dtype=np.float32),
    "vitality": np.array([38, 86, 46], dtype=np.float32),
    "spirit": np.array([96, 48, 72], dtype=np.float32),
}
_DEFAULT_BG_BGR = np.array([34, 30, 28], dtype=np.float32)


def _build_corner_mask(size: int) -> np.ndarray:
    """Mask out outer borders, top-right tier badge (II/III/IV), and bottom-right keybind."""
    mask = np.ones((size, size), dtype=bool)
    border = max(2, size // 16)
    mask[:border, :] = False
    mask[-border:, :] = False
    mask[:, :border] = False
    mask[:, -border:] = False

    badge_h = int(round(size * 0.35))
    badge_w = int(round(size * 0.35))
    mask[:badge_h, size - badge_w :] = False  # Top-right Roman tier badge
    mask[size - badge_h :, size - badge_w :] = False  # Bottom-right active keybind/badge
    return mask


class ItemMatcher:
    """Matches Deadlock HUD item tiles against cached official shop icons."""

    def __init__(
        self,
        icons_dir: Path = DEFAULT_ITEM_ICONS_DIR,
        template_size: int = 48,
    ) -> None:
        self.icons_dir = icons_dir
        self.template_size = template_size
        self._mask = _build_corner_mask(template_size)
        self._mask_u8 = self._mask.astype(np.uint8) * 255
        self.item_names: list[str] = []
        self._rgb_matrix: np.ndarray | None = None
        self._gray_matrix: np.ndarray | None = None
        self._hist_matrix: np.ndarray | None = None
        self._load_templates()

    @property
    def is_ready(self) -> bool:
        """True if at least one item template is loaded in memory."""
        return len(self.item_names) > 0 and self._rgb_matrix is not None

    def _featurize(self, bgr: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        resized = cv2.resize(bgr, (self.template_size, self.template_size), interpolation=cv2.INTER_AREA)

        # 1. Zero-mean unit-norm RGB vector on masked pixels
        rgb_vals = resized[self._mask].astype(np.float32).reshape(-1)
        rgb_vals -= rgb_vals.mean()
        rgb_norm = float(np.linalg.norm(rgb_vals))
        if rgb_norm > 1e-6:
            rgb_vals /= rgb_norm

        # 2. Zero-mean unit-norm grayscale vector (invariant to slot color tint)
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        gray_vals = gray[self._mask].astype(np.float32).reshape(-1)
        gray_vals -= gray_vals.mean()
        gray_norm = float(np.linalg.norm(gray_vals))
        if gray_norm > 1e-6:
            gray_vals /= gray_norm

        # 3. Normalized HSV 2D H-S histogram on masked pixels
        hsv = cv2.cvtColor(resized, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], self._mask_u8, [16, 16], [0, 180, 0, 256]).reshape(-1).astype(np.float32)
        hist_norm = float(np.linalg.norm(hist))
        if hist_norm > 1e-6:
            hist /= hist_norm

        return rgb_vals, gray_vals, hist

    def _composite_icon(self, icon_bgra: np.ndarray, slot_type: str) -> np.ndarray:
        if icon_bgra.ndim == 3 and icon_bgra.shape[2] == 4:
            bg = _SLOT_BACKGROUNDS_BGR.get(slot_type, _DEFAULT_BG_BGR)
            alpha = icon_bgra[:, :, 3:4].astype(np.float32) / 255.0
            fg = icon_bgra[:, :, :3].astype(np.float32)
            blended = fg * alpha + bg * (1.0 - alpha)
            return np.clip(blended, 0, 255).astype(np.uint8)
        return icon_bgra[:, :, :3] if icon_bgra.ndim == 3 else cv2.cvtColor(icon_bgra, cv2.COLOR_GRAY2BGR)

    def _load_templates(self) -> None:
        manifest_path = self.icons_dir / "manifest.json"
        if not manifest_path.exists():
            return

        manifest: dict[str, dict] = json.loads(manifest_path.read_text(encoding="utf-8"))
        rgb_rows: list[np.ndarray] = []
        gray_rows: list[np.ndarray] = []
        hist_rows: list[np.ndarray] = []
        names: list[str] = []

        for meta in manifest.values():
            icon_path = self.icons_dir / meta["filename"]
            if not icon_path.exists():
                continue
            raw = cv2.imread(str(icon_path), cv2.IMREAD_UNCHANGED)
            if raw is None:
                continue
            bgr = self._composite_icon(raw, str(meta.get("slot_type", "weapon")).lower())
            rgb_v, gray_v, hist_v = self._featurize(bgr)
            rgb_rows.append(rgb_v)
            gray_rows.append(gray_v)
            hist_rows.append(hist_v)
            names.append(str(meta["name"]))

        if names:
            self.item_names = names
            self._rgb_matrix = np.vstack(rgb_rows)
            self._gray_matrix = np.vstack(gray_rows)
            self._hist_matrix = np.vstack(hist_rows)

    @staticmethod
    def is_empty_slot(tile_bgr: np.ndarray) -> bool:
        """Fast rejection for empty dark translucent inventory slots."""
        if tile_bgr.size == 0:
            return True
        h, w = tile_bgr.shape[:2]
        center = tile_bgr[max(0, h // 5) : max(1, (4 * h) // 5), max(0, w // 5) : max(1, (4 * w) // 5)]
        hsv = cv2.cvtColor(center, cv2.COLOR_BGR2HSV)
        mean_sat = float(hsv[:, :, 1].mean())
        gray_std = float(cv2.cvtColor(center, cv2.COLOR_BGR2GRAY).std())
        return gray_std < 18.0 or (mean_sat < 22.0 and gray_std < 26.0)

    def match_tile(self, tile_bgr: np.ndarray, min_score: float = 0.45) -> tuple[str, float] | None:
        """Identify the item shown in a cropped tile, or return None if empty/uncertain."""
        if not self.is_ready or self.is_empty_slot(tile_bgr):
            return None

        rgb_v, gray_v, hist_v = self._featurize(tile_bgr)
        rgb_scores = self._rgb_matrix @ rgb_v  # type: ignore[operator]
        gray_scores = self._gray_matrix @ gray_v  # type: ignore[operator]
        hist_scores = self._hist_matrix @ hist_v  # type: ignore[operator]

        combined = 0.50 * rgb_scores + 0.30 * gray_scores + 0.20 * hist_scores
        best_idx = int(np.argmax(combined))
        best_score = float(combined[best_idx])
        if best_score < min_score:
            return None
        return self.item_names[best_idx], round(best_score, 3)

    def match_grid(self, tiles: list[np.ndarray], min_score: float = 0.45) -> list[str]:
        """Match all tiles in a grid and return deduplicated item names in order."""
        items: list[str] = []
        seen: set[str] = set()
        for tile in tiles:
            res = self.match_tile(tile, min_score=min_score)
            if res is not None and res[0] not in seen:
                seen.add(res[0])
                items.append(res[0])
        return items
