"""Pluggable OCR backends and Deadlock souls & match timer parsers."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod

import numpy as np

_OCR_CHAR_MAP = str.maketrans({
    "O": "0",
    "o": "0",
    "D": "0",
    "l": "1",
    "I": "1",
    "S": "5",
    "s": "5",
    "G": "6",
    "B": "8",
})

_COMPACT_K_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*[kK]")
_IMPLICIT_K_RE = re.compile(r"^(\d{1,3})[.,](\d)$")
_DIGITS_RE = re.compile(r"\d[\d\s,.]*\d|\d")
_TIMER_RE = re.compile(r"(\d{1,2})\s*[:;.]\s*(\d{2})")
_TIMER_COMPACT_RE = re.compile(r"^(\d{1,2})(\d{2})$")

MAX_PLAUSIBLE_SOULS = 110_000


def parse_match_timer(raw_text: str) -> float | None:
    """Parse a match clock string (e.g. '3:34', '28:04', or '334') into minutes."""
    if not raw_text or not raw_text.strip():
        return None
    cleaned = raw_text.strip().translate(_OCR_CHAR_MAP)
    match = _TIMER_RE.search(cleaned)
    if not match:
        digits_only = re.sub(r"\D", "", cleaned)
        match = _TIMER_COMPACT_RE.match(digits_only)
    if not match:
        return None
    minutes = int(match.group(1))
    seconds = int(match.group(2))
    if seconds >= 60 or minutes > 180:
        return None
    return round(minutes + seconds / 60.0, 2)


def parse_souls_text(raw_text: str) -> int | None:
    """Parse OCR text into an integer souls count.

    Handles border artifacts ('|35k', '30:'), compact 'k' formats ('12.4k', '35k'),
    implicit decimal thousands ('5.0' -> 5000), and full integer formats ('4,250').
    """
    if not raw_text or not raw_text.strip():
        return None

    stripped = raw_text.strip().strip("|[](){}:;\"' ")
    if not re.search(r"\d", stripped):
        return None

    alpha_chars = re.findall(r"[A-Za-z]", stripped)
    non_k_alpha = [c for c in alpha_chars if c.lower() != "k"]
    if len(non_k_alpha) > 2:
        return None

    cleaned = stripped.translate(_OCR_CHAR_MAP)

    compact_match = _COMPACT_K_RE.search(cleaned)
    if compact_match:
        num_part = compact_match.group(1).replace(",", ".")
        try:
            value = int(round(float(num_part) * 1000))
        except ValueError:
            return None
        # Pill left-border vertical stroke sometimes reads as leading '1' (e.g. '135k' -> 35000)
        if 110_000 < value <= 199_999 and num_part.startswith("1") and "." not in num_part:
            value -= 100_000
        return value if 0 <= value <= MAX_PLAUSIBLE_SOULS else None

    digits_match = _DIGITS_RE.search(cleaned)
    if not digits_match:
        return None

    token = digits_match.group(0).strip()
    implicit_k_match = _IMPLICIT_K_RE.match(token)
    if implicit_k_match:
        value = int(round(float(f"{implicit_k_match.group(1)}.{implicit_k_match.group(2)}") * 1000))
        return value if 0 <= value <= MAX_PLAUSIBLE_SOULS else None

    digits_only = re.sub(r"[\s,.]", "", token)
    if not digits_only.isdigit():
        return None

    value = int(digits_only)
    return value if 0 <= value <= MAX_PLAUSIBLE_SOULS else None


class OcrBackend(ABC):
    """Abstract OCR engine interface."""

    @abstractmethod
    def recognize_text(self, image_bgr: np.ndarray) -> str:
        """Return recognized text string from a preprocessed BGR image."""


class RapidOcrBackend(OcrBackend):
    """Fast local ONNX OCR backend powered by rapidocr-onnxruntime."""

    def __init__(self) -> None:
        from rapidocr_onnxruntime import RapidOCR

        self._engine = RapidOCR()

    def recognize_text(self, image_bgr: np.ndarray) -> str:
        # Bypass text detection on pre-cropped single-line ROIs across rapidocr-onnxruntime versions.
        for attr in ("text_recognizer", "text_rec"):
            rec_fn = getattr(self._engine, attr, None)
            if callable(rec_fn):
                rec_res, _ = rec_fn([image_bgr])
                if rec_res and rec_res[0]:
                    return str(rec_res[0][0]).strip()

        try:
            result, _ = self._engine(image_bgr, use_det=False, use_cls=False, use_rec=True)
        except TypeError:
            result, _ = self._engine(image_bgr)

        if not result:
            return ""
        texts: list[str] = []
        for entry in result:
            if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                # [box, text, score] vs (text, score)
                candidate = entry[1] if isinstance(entry[0], (list, tuple)) else entry[0]
                if candidate:
                    texts.append(str(candidate))
        return "".join(texts).strip()


class TesseractOcrBackend(OcrBackend):
    """Optional fallback backend using pytesseract when Tesseract binary is installed."""

    def __init__(self, tesseract_cmd: str | None = None) -> None:
        import pytesseract

        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
        self._pytesseract = pytesseract

    def recognize_text(self, image_bgr: np.ndarray) -> str:
        config = "--psm 7 -c tessedit_char_whitelist=0123456789.,kK"
        return str(self._pytesseract.image_to_string(image_bgr, config=config)).strip()
