"""VAC-safe screen capture using mss restricted to the scoreboard region."""

from __future__ import annotations

import mss
import numpy as np

from backend.config.settings import NormalizedRoi, scale_roi


class ScreenCapture:
    """Fast bounding-box screen grabber via Desktop Duplication / BitBlt (no game hooks)."""

    def __init__(self, monitor_index: int = 1) -> None:
        self.monitor_index = monitor_index

    def get_monitor_size(self) -> tuple[int, int]:
        """Return (width, height) of the target monitor."""
        with mss.mss() as sct:
            mon = sct.monitors[self.monitor_index]
            return int(mon["width"]), int(mon["height"])

    def grab_full_monitor(self) -> np.ndarray:
        """Capture the target monitor in BGR format."""
        with mss.mss() as sct:
            mon = sct.monitors[self.monitor_index]
            shot = np.array(sct.grab(mon), dtype=np.uint8)
            return shot[:, :, :3]  # BGRA -> BGR

    def grab_region(self, norm_roi: NormalizedRoi) -> tuple[np.ndarray, tuple[int, int, int, int]]:
        """Capture only a normalized sub-region of the target monitor.

        Returns:
            Tuple of (BGR frame array, (left, top, width, height) in monitor-relative pixels).
        """
        with mss.mss() as sct:
            mon = sct.monitors[self.monitor_index]
            mon_w, mon_h = int(mon["width"]), int(mon["height"])
            rx, ry, rw, rh = scale_roi(norm_roi, mon_w, mon_h)
            region = {
                "left": int(mon["left"]) + rx,
                "top": int(mon["top"]) + ry,
                "width": rw,
                "height": rh,
            }
            shot = np.array(sct.grab(region), dtype=np.uint8)
            return shot[:, :, :3], (rx, ry, rw, rh)
