"""Emergency detection for free text in English, Hindi and Tamil.

Deliberately over-inclusive: a false alarm costs one dismissal, and a miss could cost a life.
Applied server-side to searches, manual entry and OCR text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

EMERGENCY_NUMBER = "112"

_PATTERNS = [
    r"\bover\s?dos(e|ed|ing)\b",
    r"\bpoison(ed|ing|ous)?\b",
    r"\bsuicid(e|al)\b",
    r"\bkill\s+(my|him|her|them)sel(f|ves)\b",
    r"\bend\s+my\s+life\b",
    r"\b(took|taken|swallowed|ate|drank)\s+(too\s+many|too\s+much|a\s+lot\s+of|all\s+(my|the)|extra)\b",
    r"\b(child|baby|toddler|kid)\s+(ate|swallowed|took|drank)\b",
    r"\b(can'?t|cannot|not\s+able\s+to)\s+breathe\b",
    r"\bunconscious\b",
    r"\bnot\s+breathing\b",
    r"\bseizures?\b",
    r"\bchest\s+pain\b",
    r"\bheart\s+attack\b",
    r"\bsnake\s?bite\b",
    # Hindi
    r"ओवरडोज़?",
    r"ज़?ज?हर",
    r"आत्महत्या",
    r"बेहोश",
    r"सांस\s*नहीं",
    r"सीने\s*में\s*दर्द",
    r"ज़्यादा\s*दवा",
    r"ज्यादा\s*दवा",
    # Tamil
    r"அதிக\s*(அளவு|மருந்து)",
    r"விஷம்",
    r"நஞ்சு",
    r"தற்கொலை",
    r"மயக்கம்",
    r"மூச்சு\s*விட\s*முடியவில்லை",
    r"நெஞ்சு\s*வலி",
]
_REGEX = re.compile("|".join(_PATTERNS), re.IGNORECASE)


@dataclass(frozen=True)
class EmergencySignal:
    detected: bool
    number: str = EMERGENCY_NUMBER
    message: str = (
        "This may be an emergency. Call 112 now or go to the nearest hospital. "
        "Do not wait for this app. MediCompare cannot give emergency advice."
    )


def detect_emergency(text: str | None) -> EmergencySignal:
    if not text:
        return EmergencySignal(detected=False)
    return EmergencySignal(detected=_REGEX.search(text) is not None)
