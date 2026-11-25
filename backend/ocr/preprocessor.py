"""OpenCV ROI preprocessing tuned for Deadlock HUD soul counters and match timer."""

from __future__ import annotations

import cv2
import numpy as np


def preprocess_souls_roi(roi_bgr: np.ndarray, target_height: int = 48) -> np.ndarray:
    """Normalize a tight HUD pill/timer crop to PaddleOCR's native 48px recognition height.

    Uses cubic upscaling + soft unsharp masking + grayscale luminance instead of
    hard Otsu binarization, which preserves digits on colored (amber/blue) HUD badges.
    """
    if roi_bgr.size == 0:
        raise ValueError("ROI crop is empty.")

    scale = target_height / max(1, roi_bgr.shape[0])
    upscaled = cv2.resize(
        roi_bgr,
        None,
        fx=scale,
        fy=scale,
        interpolation=cv2.INTER_CUBIC,
    )

    blur = cv2.GaussianBlur(upscaled, (0, 0), 1.0)
    sharpened = cv2.addWeighted(upscaled, 1.5, blur, -0.5, 0)
    gray = cv2.cvtColor(sharpened, cv2.COLOR_BGR2GRAY)
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
