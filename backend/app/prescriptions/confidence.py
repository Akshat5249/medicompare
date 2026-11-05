"""Separate OCR and match confidence. These only change how a suggestion is displayed.

A score never verifies an item: every item stays needs_verification until a person confirms it.
Thresholds are loaded from the measured evaluation output. Without that file, nothing is suggested.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

THRESHOLDS_PATH = Path(__file__).with_name("thresholds.json")


@dataclass(frozen=True)
class Thresholds:
    min_ocr_quality: float
    min_match_quality: float
    engine: str


def load_thresholds(path: Path = THRESHOLDS_PATH, engine: str | None = None) -> Thresholds | None:
    """Load thresholds, or None if absent or measured on a different engine than the one in use."""
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    if engine is not None and data["engine"] != engine:
        return None
    return Thresholds(
        float(data["min_ocr_quality"]), float(data["min_match_quality"]), str(data["engine"])
    )


def display_level(
    ocr_quality: float | None, match_quality: float | None, thresholds: Thresholds | None
) -> str:
    """Return 'uncalibrated', 'no_match', 'low_confidence' or 'suggested'. Display only."""
    if thresholds is None:
        return "uncalibrated"
    if match_quality is None:
        return "no_match"
    # Typed entries have no OCR score, so only the match score applies to them.
    read_poorly = ocr_quality is not None and ocr_quality < thresholds.min_ocr_quality
    if read_poorly or match_quality < thresholds.min_match_quality:
        return "low_confidence"
    return "suggested"
