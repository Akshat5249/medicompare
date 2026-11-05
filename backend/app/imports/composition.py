"""Parse a printed composition, such as NPPA's "Each tablet contains: X IP 5 mg", without guessing.

Anything not understood raises CompositionError, which sends the row to the review queue.

Why strength basis matters: "Metformin Hydrochloride 500 mg" and "Metformin Hydrochloride eq. to
Metformin 500 mg" contain different amounts of medicine. The basis therefore becomes part of the
recorded salt form, so equivalence treats the two as different.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.matching.equivalence import StrengthParseError, parse_strength

NO_SALT_NAMED = "none named"
SPELLINGS = {
    "amoxycillin": "Amoxicillin",
    "aspirin": "Acetylsalicylic acid",
    "acetylsalicylic acid": "Acetylsalicylic acid",
    "vitamin d3": "Cholecalciferol",
}
# Named exactly as printed, because the usual "base then salt" reading gets them wrong.
_WHOLE_NAMES = {
    "potassium clavulanate diluted": ("Clavulanic Acid", "potassium, diluted"),
    "potassium clavulanate": ("Clavulanic Acid", "potassium"),
}
# Preservatives printed among the actives. They are not part of the medicine's identity.
_NOT_ACTIVE = re.compile(r"^benzalkonium chloride(?: solution)?$", re.I)
_SALTS = {
    "phosphate monohydrate": "phosphate monohydrate",
    "hydrochloride hemihydrate": "hydrochloride hemihydrate",
    "hydrochloride monohydrate": "hydrochloride monohydrate",
    "hydrochloride": "hydrochloride",
    "hcl": "hydrochloride",
    "hci": "hydrochloride",
    "hydrobromide": "hydrobromide",
    "bisulphate": "bisulfate",
    "bisulfate": "bisulfate",
    "ethanolate": "ethanolate",
    "mesilate": "mesylate",
    "sodium phosphate": "sodium phosphate",
    "besilate": "besilate",
    "besylate": "besilate",
    "succinate": "succinate",
    "tartrate": "tartrate",
    "fumarate": "fumarate",
    "maleate": "maleate",
    "mesylate": "mesylate",
    "oxalate": "oxalate",
    "benzoate": "benzoate",
    "phosphate": "phosphate",
    "sulfate": "sulfate",
    "sulphate": "sulfate",
    "acetate": "acetate",
    "citrate": "citrate",
    "potassium": "potassium",
    "sodium": "sodium",
    "calcium": "calcium",
    "magnesium": "magnesium",
    "dihydrate": "dihydrate",
    "trihydrate": "trihydrate",
    "monohydrate": "monohydrate",
}
_HEADER = re.compile(r"^.*?(?:contains?\s*:?|composition\s*:)\s*", re.I)
_PER = re.compile(r"\beach\s+(\d+(?:\.\d+)?)?\s*(ml|gm?|gram)\b", re.I)
_STRENGTH = re.compile(
    r"(?<![\w.])(\d[\d,]*(?:\.\d+)?)\s*(mcg|mg|gm|g|iu|%)(?:\s*w\s*/\s*[vw])?(?![a-z])", re.I
)
_PHARMACOPOEIA = re.compile(r"\b(?:IP|BP|USP|IH|Ph\.?\s*Eur\.?|B\.P\.|I\.P\.)(?=\s|$|,|\))", re.I)
_EQUIVALENT = re.compile(r"\b(?:eq(?:uivalent|v)?\.?)(?:\s*to)?\b\.?", re.I)
_RELEASE_WORDS = [
    (re.compile(r"\b(?:sustained|SR)\b", re.I), "sustained"),
    (re.compile(r"\b(?:extended|prolonged|ER|XR|PR)\b", re.I), "extended"),
    (re.compile(r"\b(?:controlled|CR)\b", re.I), "controlled"),
    (re.compile(r"\b(?:modified|MR)\b", re.I), "modified"),
    (re.compile(r"\b(?:gastro[\s-]*resistant|enteric)\b", re.I), "enteric_coated"),
]
_EXCIPIENT = re.compile(
    r"preservative|excipient|\bcolou?rs?\b|flavou?r|\bq\.?\s*s\b|stabili[sz]er|diluent|solvent",
    re.I,
)
_LEFTOVER_OK = re.compile(
    r"^(?:[\s,.;:()&]|and|in|form|nano|droplet|pellets?|as|white|colou?red|layer)*$", re.I
)
RELEASE_LABEL_NAMES = {
    "sustained": "Sustained release",
    "extended": "Extended release",
    "controlled": "Controlled release",
    "modified": "Modified release",
    "enteric_coated": "Gastro-resistant",
}


class CompositionError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedIngredient:
    name: str
    salt_form: str
    strength_text: str
    release: str | None


def _clean_name(text: str) -> str:
    text = re.sub(r"(?<=[a-z])(?:IP|BP|USP)\b", " ", text)  # "FumarateIP" as printed
    text = _PHARMACOPOEIA.sub(" ", text)
    text = re.sub(r"^\s*sterile\s+", "", text, flags=re.I)
    text = re.sub(r"^(?:[\s,;:&.)(]|and\b)+|(?:[\s,;:&.(]|and\b)+$", "", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip()


def _release_in(text: str) -> str | None:
    found = {code for pattern, code in _RELEASE_WORDS if pattern.search(text)}
    if len(found) > 1:
        raise CompositionError(f"several release types in {text!r}")
    return found.pop() if found else None


def _split_salt(name: str) -> tuple[str, str]:
    lowered = name.lower()
    if lowered in _WHOLE_NAMES:
        return _WHOLE_NAMES[lowered]
    for suffix, salt in sorted(_SALTS.items(), key=lambda item: -len(item[0])):
        if lowered.endswith(f" {suffix}"):
            base = name[: -len(suffix) - 1].strip()
            return base, salt
    return name, NO_SALT_NAMED


def _validated_name(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9\- ]{2,70}", name) or len(name.split()) > 6:
        raise CompositionError(f"not a clear ingredient name: {name!r}")
    return SPELLINGS.get(name.lower(), name[0].upper() + name[1:])


def parse_composition(text: str) -> list[ParsedIngredient]:
    """Return ingredients in printed order, or raise CompositionError."""
    if re.search(r"combi\s*pack|\(A\)|\bkit\b", text, re.I):
        raise CompositionError("multi-part packs need manual review")
    header = _HEADER.match(text)
    if not header:
        raise CompositionError("no 'contains' or 'composition' heading")
    per = _PER.search(header.group(0))
    per_suffix = ""
    if per:
        amount = per[1] or "1"
        unit = per[2].lower()
        per_suffix = f"/{amount} g" if unit in {"g", "gm", "gram"} else f"/{amount} ml"
    body = text[header.end() :]
    tokens = list(_STRENGTH.finditer(body))
    if not tokens:
        raise CompositionError("no strength found")
    parsed: list[ParsedIngredient] = []
    position = 0
    leftovers: list[str] = []
    # A note after a dropped preservative must not remove the ingredient listed before it.
    previous_dropped = False
    for token in tokens:
        chunk = body[position : token.start()]
        position = token.end()
        # A closing bracket straight after a strength belongs to the previous ingredient.
        bracket = re.match(r"\s*\(([^()]*)\)", chunk)
        trailing = ""
        if bracket and not _EQUIVALENT.search(bracket[1]):
            trailing = bracket[1]
            chunk = chunk[bracket.end() :]
        if trailing and parsed:
            if _EXCIPIENT.search(trailing):
                if not previous_dropped:
                    parsed.pop()
            else:
                release = _release_in(trailing)
                if release:
                    last = parsed[-1]
                    parsed[-1] = ParsedIngredient(
                        last.name, last.salt_form, last.strength_text, release
                    )
                elif not _LEFTOVER_OK.match(trailing):
                    leftovers.append(trailing)
        stripped = re.sub(r"^[\s,;:&.()]*(?:and\b)?[\s,;:&.()]*", "", chunk)
        if _EQUIVALENT.match(stripped):
            # "X 23.75 mg eq. to Y 25 mg": the first figure stands, and this restates it.
            if not parsed:
                raise CompositionError("equivalence with no ingredient before it")
            continue
        inner_release = _release_in(stripped)
        stripped = re.sub(r"\([^()]*\)", " ", stripped)
        parts = _EQUIVALENT.split(stripped, maxsplit=1)
        printed = _clean_name(parts[0])
        if not printed:
            raise CompositionError(f"strength with no ingredient near {token[0]!r}")
        base, salt = _split_salt(printed)
        if len(parts) == 2:
            basis = _clean_name(parts[1])
            if not basis:
                raise CompositionError(f"equivalence with no target near {token[0]!r}")
            salt = f"{salt}; strength as {basis.lower()}"
        value = token[1].replace(",", "")
        unit = token[2].lower()
        strength = f"{value} {unit}{per_suffix if unit != '%' else ''}"
        try:
            parse_strength(strength)
        except StrengthParseError as exc:
            raise CompositionError(f"cannot read strength {strength!r}") from exc
        if _NOT_ACTIVE.match(printed):
            previous_dropped = True
            continue
        previous_dropped = False
        parsed.append(ParsedIngredient(_validated_name(base), salt, strength, inner_release))
    tail = body[position:]
    bracket = re.match(r"\s*\(([^()]*)\)", tail)
    if bracket:
        if _EXCIPIENT.search(bracket[1]):
            if parsed and not previous_dropped:
                parsed.pop()
        else:
            release = _release_in(bracket[1])
            if release and parsed:
                last = parsed[-1]
                parsed[-1] = ParsedIngredient(
                    last.name, last.salt_form, last.strength_text, release
                )
            elif not _LEFTOVER_OK.match(bracket[1]):
                leftovers.append(bracket[1])
        tail = tail[bracket.end() :]
    if not _EXCIPIENT.search(tail):
        leftovers.append(tail)
    for leftover in leftovers:
        if not _LEFTOVER_OK.match(leftover):
            raise CompositionError(f"unread text: {leftover.strip()[:60]!r}")
    if not parsed:
        raise CompositionError("no active ingredient found")
    names = [item.name.lower() for item in parsed]
    if len(set(names)) != len(names):
        raise CompositionError("same ingredient listed twice")
    return parsed


def release_code(ingredients: list[ParsedIngredient], formulation: str, default: str) -> str:
    """Release type naming the ingredient it applies to, so "A SR + B" differs from "A + B SR"."""
    marked = [f"{item.release}:{item.name.lower()}" for item in ingredients if item.release]
    if marked:
        return ";".join(sorted(marked))
    named = _release_in(formulation)
    if named:
        if len(ingredients) > 1:
            raise CompositionError("release type does not say which ingredient it applies to")
        return f"{named}:{ingredients[0].name.lower()}"
    return default


def release_label(code: str) -> str:
    parts = []
    for part in code.split(";"):
        kind, _, ingredient = part.partition(":")
        name = RELEASE_LABEL_NAMES.get(kind, kind.replace("_", " ").capitalize())
        parts.append(f"{name} ({ingredient})" if ingredient else name)
    return "; ".join(parts)
