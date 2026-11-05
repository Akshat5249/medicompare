"""Deterministic medicine equivalence. The single authority on "same medicine".

Pure functions over explicit attributes. Names are never an input: two products with look-alike
or identical names are not equivalent unless their attributes match. An unstated attribute can
never prove a match, so a missing salt form makes products not equivalent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

_MASS_TO_MG = {
    "mcg": Decimal("0.001"),
    "ug": Decimal("0.001"),
    "mg": Decimal(1),
    "g": Decimal(1000),
    "gm": Decimal(1000),
}
_VOLUME_TO_ML = {"ml": Decimal(1), "l": Decimal(1000)}
_PLAIN_UNITS = {"iu", "%", "vial", "dose", "unit"}


class StrengthParseError(ValueError):
    """A strength could not be parsed exactly. Callers must not guess."""


@dataclass(frozen=True)
class Strength:
    value: Decimal
    unit: str
    per_value: Decimal | None = None
    per_unit: str | None = None

    def canonical(self) -> tuple[Decimal, str]:
        """Convert to a comparable value: mg or IU, per 1 mL when a concentration."""
        unit = self.unit.lower()
        value = self.value
        if unit in _MASS_TO_MG:
            value, unit = value * _MASS_TO_MG[unit], "mg"
        elif unit not in _PLAIN_UNITS:
            raise StrengthParseError(f"unsupported unit {self.unit!r}")
        if self.per_unit is None:
            return value.normalize(), unit
        per_unit = self.per_unit.lower()
        per_value = self.per_value if self.per_value is not None else Decimal(1)
        if per_value <= 0:
            raise StrengthParseError("per-value must be positive")
        if per_unit in _VOLUME_TO_ML:
            per_value, per_unit = per_value * _VOLUME_TO_ML[per_unit], "ml"
        elif per_unit in _MASS_TO_MG:
            per_value, per_unit = per_value * _MASS_TO_MG[per_unit], "mg"
        elif per_unit not in _PLAIN_UNITS:
            raise StrengthParseError(f"unsupported per-unit {self.per_unit!r}")
        return (value / per_value).normalize(), f"{unit}/{per_unit}"


_STRENGTH = re.compile(
    r"^\s*(?P<value>\d[\d,]*(?:\.\d+)?)\s*(?P<unit>mcg|ug|mg|gm|g|iu|%)"
    r"(?:\s*/\s*(?P<per_value>\d+(?:\.\d+)?)?\s*(?P<per_unit>ml|l|mg|g|vial|dose))?\s*$",
    re.IGNORECASE,
)


def parse_strength(text: str) -> Strength:
    """Parse one strength such as '500 mg', '250mg/5mL' or '15,00,000 IU'. Raises if inexact."""
    match = _STRENGTH.match(text)
    if not match:
        raise StrengthParseError(f"cannot parse strength {text!r}")
    try:
        value = Decimal(match["value"].replace(",", ""))
        per_value = Decimal(match["per_value"]) if match["per_value"] else None
    except InvalidOperation as exc:  # pragma: no cover - the regex admits only valid decimals
        raise StrengthParseError(text) from exc
    if value <= 0:
        raise StrengthParseError(f"non-positive strength {text!r}")
    per_unit = match["per_unit"].lower() if match["per_unit"] else None
    if per_unit and per_value is None:
        per_value = Decimal(1)
    return Strength(value=value, unit=match["unit"].lower(), per_value=per_value, per_unit=per_unit)


@dataclass(frozen=True)
class IngredientDose:
    ingredient: str
    salt_form: str | None
    strength: Strength

    def key(self) -> tuple[str, str | None, Decimal, str]:
        value, unit = self.strength.canonical()
        return (normalise_token(self.ingredient), _salt(self.salt_form), value, unit)


@dataclass(frozen=True)
class MedicineAttributes:
    ingredients: tuple[IngredientDose, ...]
    dosage_form: str
    route: str
    release_type: str


@dataclass(frozen=True)
class Difference:
    code: str
    detail: str


@dataclass(frozen=True)
class EquivalenceResult:
    differences: tuple[Difference, ...]

    @property
    def equivalent(self) -> bool:
        return not self.differences

    @property
    def codes(self) -> list[str]:
        return [d.code for d in self.differences]


def normalise_token(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


def _salt(value: str | None) -> str | None:
    return normalise_token(value) if value else None


def compare(a: MedicineAttributes, b: MedicineAttributes) -> EquivalenceResult:
    """Return every difference between two medicines. Equivalent only if there are none."""
    differences: list[Difference] = []
    names_a = {normalise_token(i.ingredient): i for i in a.ingredients}
    names_b = {normalise_token(i.ingredient): i for i in b.ingredients}
    if not a.ingredients or not b.ingredients:
        differences.append(Difference("composition_unknown", "A composition is not stated."))
    if set(names_a) != set(names_b):
        only_a = sorted(set(names_a) - set(names_b))
        only_b = sorted(set(names_b) - set(names_a))
        is_fdc = len(names_a) > 1 or len(names_b) > 1
        differences.append(
            Difference(
                "fdc_composition" if is_fdc else "ingredient",
                f"Different active ingredients: only in first {only_a}; only in second {only_b}.",
            )
        )
    for name in sorted(set(names_a) & set(names_b)):
        first, second = names_a[name], names_b[name]
        salt_a, salt_b = _salt(first.salt_form), _salt(second.salt_form)
        if salt_a is None or salt_b is None:
            differences.append(
                Difference(
                    "salt_form_not_stated", f"{name}: the source does not state the salt form."
                )
            )
        elif salt_a != salt_b:
            differences.append(Difference("salt_form", f"{name}: {salt_a} vs {salt_b}."))
        try:
            if first.strength.canonical() != second.strength.canonical():
                differences.append(Difference("strength", f"{name}: strengths differ."))
        except StrengthParseError:
            differences.append(Difference("strength", f"{name}: strength cannot be compared."))
    for code, left, right in (
        ("dosage_form", a.dosage_form, b.dosage_form),
        ("route", a.route, b.route),
        ("release_type", a.release_type, b.release_type),
    ):
        if normalise_token(left) != normalise_token(right):
            differences.append(Difference(code, f"{left} vs {right}."))
    return EquivalenceResult(tuple(differences))


def ingredient_key(ingredients: tuple[IngredientDose, ...]) -> str:
    """Key shared by anything with the same active ingredients: finds 'not equivalent' relatives."""
    return "+".join(sorted(normalise_token(i.ingredient) for i in ingredients))


def equivalence_key(attrs: MedicineAttributes) -> str:
    """Candidate-lookup key. compare() still makes the final decision."""
    parts = sorted(
        f"{name}:{salt or chr(63)}:{value:f}:{unit}"
        for name, salt, value, unit in (i.key() for i in attrs.ingredients)
    )
    tail = [normalise_token(x) for x in (attrs.dosage_form, attrs.route, attrs.release_type)]
    return "|".join(["+".join(parts), *tail])
