"""Skin-proof FR/EN fuzzy hero name resolver and player pseudo matcher."""

from __future__ import annotations

import json
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

from backend.config.settings import DEFAULT_HERO_ALIASES_PATH


def normalize_label(text: str) -> str:
    """Strip accents, uppercase, and keep alphanumeric + spaces for robust matching."""
    decomposed = unicodedata.normalize("NFKD", text)
    ascii_only = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    cleaned = re.sub(r"[^A-Z0-9]+", " ", ascii_only.upper())
    return " ".join(cleaned.split())


class HeroMatcher:
    """Resolves noisy FR/EN OCR hero labels to canonical English hero names."""

    def __init__(self, aliases_path: Path = DEFAULT_HERO_ALIASES_PATH) -> None:
        raw: dict[str, list[str]] = json.loads(aliases_path.read_text(encoding="utf-8"))
        self._alias_to_canonical: dict[str, str] = {}
        for canonical, aliases in raw.items():
            self._alias_to_canonical[normalize_label(canonical)] = canonical
            for alias in aliases:
                self._alias_to_canonical[normalize_label(alias)] = canonical

    def match(self, raw_text: str, min_ratio: float = 0.65) -> str | None:
        """Return canonical hero name for raw OCR text, or None below threshold."""
        norm = normalize_label(raw_text)
        if not norm:
            return None
        if norm in self._alias_to_canonical:
            return self._alias_to_canonical[norm]

        best_canonical: str | None = None
        best_score = 0.0
        for alias_norm, canonical in self._alias_to_canonical.items():
            score = SequenceMatcher(None, norm, alias_norm).ratio()
            if score > best_score:
                best_score = score
                best_canonical = canonical

        return best_canonical if best_score >= min_ratio else None


def match_player_pseudo(
    target_pseudo: str,
    ocr_names_by_slot: dict[int, str],
    min_ratio: float = 0.72,
) -> int | None:
    """Find the slot_index whose OCR'd player name matches the user's pseudo."""
    target_norm = normalize_label(target_pseudo)
    if not target_norm:
        return None

    for slot, raw_name in ocr_names_by_slot.items():
        if normalize_label(raw_name) == target_norm:
            return slot

    best_slot: int | None = None
    best_score = 0.0
    for slot, raw_name in ocr_names_by_slot.items():
        cand_norm = normalize_label(raw_name)
        if not cand_norm:
            continue
        score = SequenceMatcher(None, target_norm, cand_norm).ratio()
        if score > best_score:
            best_score = score
            best_slot = slot

    return best_slot if best_score >= min_ratio else None
