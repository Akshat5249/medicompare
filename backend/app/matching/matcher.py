"""Deterministic, explainable catalogue matching for text read from a prescription.

Returns candidates with reasons for a human to confirm. It never selects a final medicine.
A similar name is never enough for a high score: exact tokens and visible attributes carry weight.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from rapidfuzz import fuzz
from rapidfuzz.distance import JaroWinkler

from app.matching.equivalence import StrengthParseError, parse_strength

MIN_CANDIDATE_SCORE = 0.62
MAX_CANDIDATES = 5
_RELEASE_MARKERS = {
    "sr": "sustained",
    "er": "extended",
    "xr": "extended",
    "xl": "extended",
    "cr": "modified",
    "mr": "modified",
    "ec": "enteric_coated",
}
_FORM_WORDS = {
    "tab": "tablet",
    "tabs": "tablet",
    "tablet": "tablet",
    "tablets": "tablet",
    "cap": "capsule",
    "caps": "capsule",
    "capsule": "capsule",
    "capsules": "capsule",
    "inj": "injection",
    "injection": "injection",
    "syp": "oral_liquid",
    "syr": "oral_liquid",
    "syrup": "oral_liquid",
    "susp": "suspension",
    "suspension": "suspension",
}


@dataclass(frozen=True)
class CatalogueEntry:
    medicine_id: int
    display_name: str
    brand: str | None
    ingredients: tuple[str, ...]
    strengths: tuple[tuple[Decimal, str], ...]
    dosage_form: str
    release_type: str


@dataclass(frozen=True)
class Candidate:
    medicine_id: int
    display_name: str
    score: float
    reasons: tuple[str, ...]
    is_lasa: bool


def _clean(text: str) -> str:
    return re.sub(r"[^a-z0-9+ ]+", " ", text.lower()).strip()


def _strengths_from_text(text: str | None) -> list[tuple[Decimal, str]] | None:
    """Parse visible strengths. None means absent or not exactly readable."""
    if not text:
        return None
    parts = re.split(r"\s*\+\s*", text)
    parsed: list[tuple[Decimal, str]] = []
    for part in parts:
        try:
            parsed.append(parse_strength(part).canonical())
        except StrengthParseError:
            return None
    return parsed


def _name_score(name: str, entry: CatalogueEntry) -> tuple[float, str]:
    query = _clean(name)
    query_no_release = " ".join(token for token in query.split() if token not in _RELEASE_MARKERS)
    query_parts = [part.strip() for part in re.split(r"\s*\+\s*", query_no_release) if part.strip()]
    best = 0.0
    reason = ""
    if entry.brand:
        brand = _clean(entry.brand)
        score = JaroWinkler.normalized_similarity(query_no_release, brand)
        if query_no_release == brand:
            return 1.0, "Brand name matches exactly."
        best, reason = score, f"Brand name is spelled similarly ({score:.2f})."
    ingredients = [_clean(i) for i in entry.ingredients]
    if len(query_parts) == len(ingredients):
        remaining = list(ingredients)
        total = 0.0
        for part in query_parts:
            scored = [(JaroWinkler.normalized_similarity(part, item), item) for item in remaining]
            value, chosen = max(scored)
            total += value
            remaining.remove(chosen)
        average = total / len(ingredients)
        if average == 1.0:
            return 1.0, "All active ingredients match exactly."
        if average > best:
            best, reason = average, f"Active ingredients are spelled similarly ({average:.2f})."
    elif len(ingredients) > 1 or len(query_parts) > 1:
        # A single-ingredient query must not match an FDC strongly, or the reverse.
        overlap = fuzz.token_set_ratio(query_no_release, " ".join(ingredients)) / 100 * 0.6
        if overlap > best:
            best = overlap
            reason = "Only part of the combination appears to match."
    return best, reason


def match(
    name: str | None,
    strength: str | None,
    form: str | None,
    catalogue: list[CatalogueEntry],
    lasa_names: frozenset[str] = frozenset(),
) -> list[Candidate]:
    """Rank candidates. An unknown name returns nothing, so nothing is guessed."""
    if not name or not name.strip():
        return []
    strengths = _strengths_from_text(strength)
    form_code = _FORM_WORDS.get((form or "").strip().lower().rstrip("."))
    tokens = _clean(name).split()
    release_code = next(
        (_RELEASE_MARKERS[token] for token in tokens if token in _RELEASE_MARKERS), None
    )
    results: list[Candidate] = []
    for entry in catalogue:
        name_value, name_reason = _name_score(name, entry)
        if name_value < 0.75:
            continue
        score = name_value * 0.7
        reasons = [name_reason]
        if strengths is not None:
            if sorted(strengths) == sorted(entry.strengths):
                score += 0.2
                reasons.append("Strength matches what is written.")
            else:
                score -= 0.25
                reasons.append("Strength differs from what is written.")
        else:
            reasons.append("Strength is not readable, so it was not used.")
        if form_code is not None:
            if form_code == entry.dosage_form:
                score += 0.05
                reasons.append("Dosage form matches what is written.")
            else:
                score -= 0.1
                reasons.append("Dosage form differs from what is written.")
        if release_code is not None:
            if release_code == entry.release_type.split(":")[0]:
                score += 0.05
                reasons.append("Release type matches what is written.")
            else:
                score -= 0.15
                reasons.append("Release type differs from what is written.")
        elif entry.release_type not in {"conventional", "not_applicable"}:
            score -= 0.05
            reasons.append("This product has a special release type that is not written.")
        score = round(max(0.0, min(1.0, score)), 4)
        if score < MIN_CANDIDATE_SCORE:
            continue
        names = {n.lower() for n in entry.ingredients} | (
            {entry.brand.lower()} if entry.brand else set()
        )
        is_lasa = bool(names & lasa_names)
        if is_lasa:
            reasons.append("This name looks like another medicine's name. Check carefully.")
        results.append(
            Candidate(entry.medicine_id, entry.display_name, score, tuple(reasons), is_lasa)
        )
    results.sort(key=lambda c: (-c.score, c.display_name))
    return results[:MAX_CANDIDATES]


def strength_conflict(
    written: str | None, entry_strengths: tuple[tuple[Decimal, str], ...]
) -> bool:
    """True when a readable written strength disagrees with the medicine being confirmed."""
    parsed = _strengths_from_text(written)
    return parsed is not None and sorted(parsed) != sorted(entry_strengths)
