"""Property-based proofs: unlike products are never compared per unit."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from app.matching.equivalence import (
    IngredientDose,
    MedicineAttributes,
    Strength,
    StrengthParseError,
    compare,
    equivalence_key,
    parse_strength,
)
from app.pricing.comparison import (
    PriceFact,
    check_comparable,
    compute_savings,
    is_stale,
    per_unit_price,
)

pytestmark = pytest.mark.safety
NAMES = st.sampled_from(["metformin", "amlodipine", "atenolol", "losartan"])
SALTS = st.sampled_from(["hydrochloride", "besilate", "succinate", None])
VALUES = st.sampled_from([Decimal(n) for n in ("2.5", "5", "10", "50", "500", "1000")])
UNITS = st.sampled_from(["mg", "mcg", "g"])
FORMS = st.sampled_from(["tablet", "capsule", "oral_liquid"])
ROUTES = st.sampled_from(["oral", "parenteral"])
RELEASES = st.sampled_from(["conventional", "sustained", "extended", "modified"])
DOSE = st.builds(IngredientDose, NAMES, SALTS, st.builds(Strength, VALUES, UNITS))
ATTRS = st.builds(
    MedicineAttributes,
    st.lists(DOSE, min_size=1, max_size=3, unique_by=lambda d: d.ingredient).map(tuple),
    FORMS,
    ROUTES,
    RELEASES,
)
PRICES = st.decimals(min_value=Decimal("0.01"), max_value=Decimal(100000), places=2)
PACKS = st.decimals(min_value=Decimal(1), max_value=Decimal(500), places=0)
DAY = date(2026, 10, 1)


def fact(
    name: str, price_type: str, amount: Decimal, pack: Decimal, unit: str = "tablet"
) -> PriceFact:
    return PriceFact(name, price_type, amount, pack, unit, "Source", DAY)


@given(ATTRS, ATTRS)
def test_compare_is_symmetric(a, b):
    assert compare(a, b).equivalent == compare(b, a).equivalent


@given(ATTRS, ATTRS, st.sampled_from(["tablet", "mL"]), st.sampled_from(["tablet", "mL"]))
def test_comparable_only_when_every_attribute_matches(a, b, unit_a, unit_b):
    verdict = check_comparable(a, b, unit_a, unit_b)
    if verdict.comparable:
        assert unit_a == unit_b
        assert {d.ingredient for d in a.ingredients} == {d.ingredient for d in b.ingredients}
        assert (a.dosage_form, a.route, a.release_type) == (b.dosage_form, b.route, b.release_type)
        pairs = {d.ingredient: d for d in a.ingredients}
        for dose in b.ingredients:
            other = pairs[dose.ingredient]
            assert dose.salt_form == other.salt_form and dose.salt_form is not None
            assert dose.strength.canonical() == other.strength.canonical()
    else:
        assert verdict.reasons, "every refusal must explain itself"


@given(ATTRS, ATTRS, PRICES, PRICES, PACKS, PACKS)
def test_unlike_products_never_produce_a_saving(a, b, price_a, price_b, pack_a, pack_b):
    assume(not compare(a, b).equivalent)
    assert (
        compute_savings(fact("A", "mrp", price_a, pack_a), fact("B", "mrp", price_b, pack_b), a, b)
        is None
    )


@given(ATTRS, PRICES, PRICES, PACKS, PACKS, st.sampled_from(["ceiling", "catalogue", "indicative"]))
def test_different_price_types_never_produce_a_saving(
    a, price_a, price_b, pack_a, pack_b, other_type
):
    assert (
        compute_savings(
            fact("A", "mrp", price_a, pack_a), fact("B", other_type, price_b, pack_b), a, a
        )
        is None
    )


@given(PRICES, PRICES, PACKS, PACKS)
def test_saving_statement_says_what_is_compared(price_a, price_b, pack_a, pack_b):
    a = MedicineAttributes(
        (IngredientDose("metformin", "hydrochloride", Strength(Decimal(500), "mg")),),
        "tablet",
        "oral",
        "conventional",
    )
    saving = compute_savings(
        fact("Ref", "mrp", price_a, pack_a), fact("Opt", "mrp", price_b, pack_b), a, a
    )
    if saving is None:
        assert per_unit_price(price_b, pack_b) >= per_unit_price(price_a, pack_a)
        return
    assert saving.amount_per_unit_inr > 0
    for text in ("Ref", "Opt", "MRP", "per tablet", "Source", str(DAY), "Discuss with your doctor"):
        assert text in saving.statement


@given(ATTRS, PRICES, PRICES, PACKS)
def test_different_pack_units_never_produce_a_saving(a, price_a, price_b, pack):
    assert (
        compute_savings(
            fact("A", "mrp", price_a, pack, "tablet"), fact("B", "mrp", price_b, pack, "mL"), a, a
        )
        is None
    )


@given(ATTRS)
def test_equivalence_key_is_stable(a):
    assert equivalence_key(a) == equivalence_key(
        MedicineAttributes(tuple(reversed(a.ingredients)), a.dosage_form, a.route, a.release_type)
    )


@given(st.integers(min_value=0, max_value=4000), st.integers(min_value=1, max_value=400))
def test_staleness_boundary(age, cadence):
    today = DAY + timedelta(days=age)
    assert is_stale(DAY, cadence, today) == (age > cadence)


@given(PRICES, PACKS)
def test_per_unit_price_is_positive_or_rounds_within_a_paisa(amount, pack):
    value = per_unit_price(amount, pack)
    assert abs(value * pack - amount) <= pack * Decimal("0.005") + Decimal("0.01")


@given(st.text(max_size=20))
def test_strength_parser_never_guesses(text):
    try:
        parsed = parse_strength(text)
    except StrengthParseError:
        return
    assert parsed.value > 0


def test_price_validation_rejects_non_positive():
    with pytest.raises(ValueError):
        per_unit_price(Decimal(0), Decimal(1))
    with pytest.raises(ValueError):
        per_unit_price(Decimal(1), Decimal(0))


@pytest.mark.parametrize(("bad"), ["", "abc", "0 mg", "5", "5 stones", "-5 mg", "5 mg 10 mg"])
def test_strength_parser_rejects(bad):
    with pytest.raises(StrengthParseError):
        parse_strength(bad)


def test_unsupported_units_are_rejected_on_canonicalisation():
    with pytest.raises(StrengthParseError):
        Strength(Decimal(1), "stone").canonical()
    with pytest.raises(StrengthParseError):
        Strength(Decimal(1), "mg", Decimal(1), "stone").canonical()
    with pytest.raises(StrengthParseError):
        Strength(Decimal(1), "mg", Decimal(0), "ml").canonical()
    assert Strength(Decimal(1), "g", Decimal(1), "l").canonical() == (Decimal(1), "mg/ml")
    assert Strength(Decimal(1), "iu", None, "vial").canonical()[1] == "iu/vial"


def test_uncomparable_strength_is_reported_not_raised():
    a = MedicineAttributes(
        (IngredientDose("x", "s", Strength(Decimal(1), "stone")),), "tablet", "oral", "conventional"
    )
    assert "strength" in compare(a, a).codes
    empty = MedicineAttributes((), "tablet", "oral", "conventional")
    assert "composition_unknown" in compare(empty, empty).codes
