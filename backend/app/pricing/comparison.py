"""Price logic: per-unit normalisation, staleness and savings statements. Pure functions.

Rules:
- A per-unit figure exists only for an exact pack quantity.
- Two products are compared per unit only when equivalence.compare() finds no differences and the
  pack units match.
- A savings figure is computed only within one price type: a ceiling price is a legal maximum, not
  a retail price, so ceiling versus MRP is never presented as a saving.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from app.matching.equivalence import MedicineAttributes, compare

PRICE_TYPE_LABELS = {
    "ceiling": "Government ceiling price (legal maximum, not a shop price)",
    "notified_retail": "NPPA notified retail price (legal maximum for this product, not a shop price)",
    "catalogue": "Catalogue price (listed price, not confirmed at any store)",
    "mrp": "MRP (printed maximum retail price)",
    "indicative": "Indicative price (approximate)",
}


@dataclass(frozen=True)
class PriceFact:
    product_name: str
    price_type: str
    amount_inr: Decimal
    pack_quantity: Decimal
    pack_unit: str
    source_name: str
    observed_at: date


@dataclass(frozen=True)
class Comparability:
    comparable: bool
    reasons: tuple[str, ...]


def per_unit_price(amount_inr: Decimal, pack_quantity: Decimal) -> Decimal:
    if amount_inr <= 0 or pack_quantity <= 0:
        raise ValueError("amount and pack quantity must be positive")
    return (amount_inr / pack_quantity).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def is_stale(observed_at: date, cadence_days: int, today: date) -> bool:
    """A price is stale once it is older than its source's expected update cadence."""
    return today > observed_at + timedelta(days=cadence_days)


def check_comparable(
    a: MedicineAttributes, b: MedicineAttributes, pack_unit_a: str, pack_unit_b: str
) -> Comparability:
    """Decide whether two products may be compared per unit, with every reason if not."""
    reasons = [d.detail for d in compare(a, b).differences]
    if pack_unit_a.strip().lower() != pack_unit_b.strip().lower():
        reasons.append(f"Packs are counted in different units: {pack_unit_a} vs {pack_unit_b}.")
    return Comparability(comparable=not reasons, reasons=tuple(reasons))


@dataclass(frozen=True)
class Savings:
    amount_per_unit_inr: Decimal
    percent: Decimal
    statement: str


def compute_savings(
    reference: PriceFact,
    option: PriceFact,
    attrs_reference: MedicineAttributes,
    attrs_option: MedicineAttributes,
) -> Savings | None:
    """Saving of option over reference, or None unless the comparison is truly like-for-like."""
    if reference.price_type != option.price_type:
        return None
    verdict = check_comparable(attrs_reference, attrs_option, reference.pack_unit, option.pack_unit)
    if not verdict.comparable:
        return None
    unit_reference = per_unit_price(reference.amount_inr, reference.pack_quantity)
    unit_option = per_unit_price(option.amount_inr, option.pack_quantity)
    if unit_option >= unit_reference:
        return None
    difference = unit_reference - unit_option
    percent = (difference / unit_reference * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    unit = reference.pack_unit
    statement = (
        f"Comparing {PRICE_TYPE_NAMES[reference.price_type]} per {unit}: "
        f"{option.product_name} at Rs {unit_option} ({option.source_name}, {option.observed_at}) "
        f"vs {reference.product_name} at Rs {unit_reference} "
        f"({reference.source_name}, {reference.observed_at}). "
        f"Difference: Rs {difference} per {unit} ({percent}%). "
        "Discuss with your doctor or pharmacist before changing any medicine."
    )
    return Savings(amount_per_unit_inr=difference, percent=percent, statement=statement)


PRICE_TYPE_NAMES = {
    "ceiling": "ceiling price",
    "notified_retail": "NPPA notified retail price",
    "catalogue": "catalogue price",
    "mrp": "MRP",
    "indicative": "indicative price",
}
