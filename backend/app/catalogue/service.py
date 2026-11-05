"""Catalogue search, medicine presentation, price comparison and lower-cost options."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from rapidfuzz import fuzz
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, selectinload

from app.matching.equivalence import (
    IngredientDose,
    MedicineAttributes,
    Strength,
    compare,
    normalise_token,
)
from app.models import (
    Brand,
    Ingredient,
    IngredientAlias,
    JanAushadhiProduct,
    Medicine,
    MedicineIngredient,
    PriceObservation,
)
from app.pricing.comparison import (
    PRICE_TYPE_LABELS,
    PriceFact,
    check_comparable,
    compute_savings,
    is_stale,
    per_unit_price,
)

DISCUSS_STATEMENT = "Discuss with your doctor or pharmacist before changing any medicine."
POSSIBLE_THRESHOLD = 0.3
_LOAD = (
    selectinload(Medicine.ingredients).selectinload(MedicineIngredient.ingredient),
    selectinload(Medicine.ingredients).selectinload(MedicineIngredient.salt_form),
    selectinload(Medicine.pack_sizes),
    selectinload(Medicine.prices).selectinload(PriceObservation.source),
    selectinload(Medicine.prices).selectinload(PriceObservation.pack_size),
    selectinload(Medicine.flags),
    selectinload(Medicine.brand).selectinload(Brand.manufacturer),
    selectinload(Medicine.dosage_form),
    selectinload(Medicine.route),
    selectinload(Medicine.release_type),
    selectinload(Medicine.source),
)
_INDIC_VOWELS = {
    "ा": "a",
    "ि": "i",
    "ी": "i",
    "ु": "u",
    "ू": "u",
    "े": "e",
    "ै": "ai",
    "ो": "o",
    "ौ": "au",
    "ॉ": "o",
    "ெ": "e",
    "ே": "e",
    "ை": "ai",
    "ொ": "o",
    "ோ": "o",
    "ௌ": "au",
    "ீ": "i",
    "ூ": "u",
    "ு": "u",
    "ி": "i",
    "ா": "a",
}
_INDIC_CONSONANTS = {
    "क": "k",
    "ख": "kh",
    "ग": "g",
    "घ": "gh",
    "च": "ch",
    "छ": "chh",
    "ज": "j",
    "झ": "jh",
    "ट": "t",
    "ठ": "th",
    "ड": "d",
    "ढ": "dh",
    "ण": "n",
    "त": "t",
    "थ": "th",
    "द": "d",
    "ध": "dh",
    "न": "n",
    "प": "p",
    "फ": "f",
    "ब": "b",
    "भ": "bh",
    "म": "m",
    "य": "y",
    "र": "r",
    "ल": "l",
    "व": "v",
    "श": "sh",
    "ष": "sh",
    "स": "s",
    "ह": "h",
    "க": "k",
    "ங": "ng",
    "ச": "s",
    "ஞ": "n",
    "ட": "t",
    "ண": "n",
    "த": "t",
    "ந": "n",
    "ப": "p",
    "ம": "m",
    "ய": "y",
    "ர": "r",
    "ல": "l",
    "வ": "v",
    "ழ": "l",
    "ள": "l",
    "ற": "r",
    "ன": "n",
    "ஜ": "j",
    "ஷ": "sh",
    "ஸ": "s",
    "ஹ": "h",
}
_INDIC_VIRAMA = {"्", "்"}
_INDIC_INDEPENDENT_VOWELS = {
    "अ": "a",
    "आ": "a",
    "इ": "i",
    "ई": "i",
    "उ": "u",
    "ऊ": "u",
    "ए": "e",
    "ऐ": "ai",
    "ओ": "o",
    "औ": "au",
    "ऑ": "o",
    "அ": "a",
    "ஆ": "a",
    "இ": "i",
    "ஈ": "i",
    "உ": "u",
    "ஊ": "u",
    "எ": "e",
    "ஏ": "e",
    "ஐ": "ai",
    "ஒ": "o",
    "ஓ": "o",
}


def transliterate(query: str) -> str:
    """Rough Devanagari and Tamil to Latin for search recall. It never decides identity."""
    if not re.search(r"[ऀ-ॿ஀-௿]", query):
        return query
    out: list[str] = []
    chars = list(query)
    for index, char in enumerate(chars):
        next_char = chars[index + 1] if index + 1 < len(chars) else ""
        if char in _INDIC_CONSONANTS:
            out.append(_INDIC_CONSONANTS[char])
            is_final = not next_char or next_char.isspace()
            if next_char not in _INDIC_VOWELS and next_char not in _INDIC_VIRAMA and not is_final:
                out.append("a")
        elif char in _INDIC_VOWELS:
            out.append(_INDIC_VOWELS[char])
        elif char in _INDIC_INDEPENDENT_VOWELS:
            out.append(_INDIC_INDEPENDENT_VOWELS[char])
        elif char in _INDIC_VIRAMA or "ऀ" <= char <= "ॿ" or "஀" <= char <= "௿":
            continue
        else:
            out.append(char)
    return "".join(out)


def _generic_base(name: str) -> str:
    return re.sub(r"\s+\d.*$", "", name).strip()


@dataclass
class SearchHit:
    medicine: Medicine
    match_type: str
    reason: str
    score: float


def search(db: Session, raw_query: str, limit: int = 30) -> list[SearchHit]:
    query = normalise_token(raw_query)
    latin = normalise_token(transliterate(query))
    terms = list(dict.fromkeys([query, latin]))
    # Script aliases resolve to their ingredient name so non-Latin input finds English records.
    alias_targets = db.execute(
        select(IngredientAlias.alias, Ingredient.name)
        .join(Ingredient, IngredientAlias.ingredient_id == Ingredient.id)
        .where(func.lower(IngredientAlias.alias) == query)
    ).all()
    alias_name = alias_targets[0][1].lower() if alias_targets else None
    effective = alias_name or latin
    similarity = func.greatest(
        func.word_similarity(effective, Medicine.search_text),
        func.similarity(effective, Medicine.search_text),
    ).label("score")
    fts = func.to_tsvector(text("'simple'"), Medicine.search_text).bool_op("@@")(
        func.plainto_tsquery(text("'simple'"), effective)
    )
    rows = db.execute(
        select(Medicine, similarity)
        .options(*_LOAD)
        .where((func.word_similarity(effective, Medicine.search_text) >= POSSIBLE_THRESHOLD) | fts)
        .order_by(similarity.desc(), Medicine.display_name)
        .limit(limit * 3)
    ).all()
    hits: list[SearchHit] = []
    for medicine, score in rows:
        hits.append(
            _classify_hit(medicine, effective, terms, float(score), alias_name is not None, query)
        )
    exact = [hit for hit in hits if hit.match_type == "exact"]
    possible = [hit for hit in hits if hit.match_type == "possible"]
    exact.sort(key=lambda hit: (hit.medicine.is_demo, hit.medicine.display_name))
    return (exact + possible)[:limit]


def _classify_hit(
    medicine: Medicine, effective: str, terms: list[str], score: float, via_alias: bool, query: str
) -> SearchHit:
    brand = medicine.brand.name.lower() if medicine.brand else None
    display = medicine.display_name.lower()
    generic = medicine.generic_name.lower()
    ingredient_names = [link.ingredient.name.lower() for link in medicine.ingredients]
    alias_note = f" (from your search “{query}”)" if via_alias else ""
    if brand and brand == effective:
        return SearchHit(medicine, "exact", "Brand name matches exactly.", 1.0)
    if effective in (display, generic, _generic_base(generic)):
        return SearchHit(medicine, "exact", f"Generic name matches exactly{alias_note}.", 1.0)
    if effective in ingredient_names:
        kind = "an active ingredient" if len(ingredient_names) > 1 else "the active ingredient"
        return SearchHit(medicine, "exact", f"{effective.title()} is {kind}{alias_note}.", 1.0)
    # Whole words only: "met" must never be an exact match for metformin or metoprolol.
    if effective and re.search(rf"(?<![a-z0-9]){re.escape(effective)}(?![a-z0-9])", display):
        return SearchHit(
            medicine, "exact", "Your search appears in the medicine name.", max(score, 0.9)
        )
    candidates = [c for c in [brand, *ingredient_names, generic] if c]
    closest = max(candidates, key=lambda c: fuzz.WRatio(effective, c), default=generic)
    return SearchHit(
        medicine,
        "possible",
        f"Similar spelling to “{closest}”. A similar name does not mean the same medicine.",
        score,
    )


def attrs_of(medicine: Medicine) -> MedicineAttributes:
    doses = tuple(
        IngredientDose(
            ingredient=link.ingredient.name,
            salt_form=link.salt_form.name if link.salt_form else None,
            strength=Strength(
                link.strength_value, link.strength_unit, link.per_value, link.per_unit
            ),
        )
        for link in medicine.ingredients
    )
    return MedicineAttributes(
        doses, medicine.dosage_form.code, medicine.route.code, medicine.release_type.code
    )


def source_dict(source: Any) -> dict[str, Any]:
    return {
        "code": source.code,
        "name": source.name,
        "owner": source.owner,
        "url": source.url,
        "licence_note": source.licence_note,
        "update_cadence_days": source.update_cadence_days,
        "is_demo": source.is_demo,
    }


def flag_dict(flag: Any) -> dict[str, Any]:
    return {
        "flag_type": flag.flag_type,
        "description": flag.description,
        "source_name": flag.source.name,
        "source_url": flag.source_url,
        "source_date": flag.source_date.isoformat(),
        "is_demo": flag.is_demo,
    }


def medicine_summary(medicine: Medicine) -> dict[str, Any]:
    return {
        "id": medicine.id,
        "display_name": medicine.display_name,
        "generic_name": medicine.generic_name,
        "brand": medicine.brand.name if medicine.brand else None,
        "dosage_form": medicine.dosage_form.label,
        "release_type": medicine.release_type.label,
        "route": medicine.route.label,
        "is_demo": medicine.is_demo,
    }


def medicine_detail(medicine: Medicine) -> dict[str, Any]:
    return {
        **medicine_summary(medicine),
        "ingredients": [
            {
                "name": link.ingredient.name,
                "salt_form": link.salt_form.name if link.salt_form else None,
                "salt_form_stated": link.salt_form is not None,
                "strength": link.strength_text,
            }
            for link in medicine.ingredients
        ],
        "pack_sizes": [pack.label for pack in medicine.pack_sizes],
        "manufacturer": (
            medicine.brand.manufacturer.name
            if medicine.brand and medicine.brand.manufacturer
            else None
        ),
        "therapeutic_category": medicine.therapeutic_category,
        "regulatory_flags": [flag_dict(flag) for flag in medicine.flags],
        "source": source_dict(medicine.source),
        "source_text": medicine.source_text,
        "source_date": medicine.source.data_as_of.isoformat()
        if medicine.source.data_as_of
        else None,
    }


def get_medicine(db: Session, medicine_id: int) -> Medicine | None:
    return db.scalar(select(Medicine).options(*_LOAD).where(Medicine.id == medicine_id))


def price_dict(price: PriceObservation, today: Any = None) -> dict[str, Any]:
    day = today or datetime.now(UTC).date()
    pack = price.pack_size
    return {
        "price_type": price.price_type,
        "price_type_label": PRICE_TYPE_LABELS[price.price_type],
        "amount_inr": str(price.amount_inr),
        "pack": pack.label,
        "pack_quantity": str(pack.quantity),
        "pack_unit": pack.unit,
        "per_unit_inr": str(per_unit_price(price.amount_inr, pack.quantity)),
        "source": source_dict(price.source),
        "observed_at": price.observed_at.isoformat(),
        "last_updated": price.observed_at.isoformat(),
        "is_stale": is_stale(price.observed_at, price.source.update_cadence_days, day),
        "is_demo": price.is_demo,
    }


def _latest_prices(medicine: Medicine) -> list[PriceObservation]:
    latest: dict[tuple[str, int], PriceObservation] = {}
    for price in sorted(medicine.prices, key=lambda p: p.observed_at):
        latest[(price.price_type, price.pack_size_id)] = price
    return list(latest.values())


def price_comparison(medicine: Medicine) -> dict[str, Any]:
    prices = [price_dict(price) for price in _latest_prices(medicine)]
    return {"medicine": medicine_summary(medicine), "prices": prices, "has_price": bool(prices)}


def _fact(medicine: Medicine, price: PriceObservation) -> PriceFact:
    return PriceFact(
        product_name=medicine.display_name,
        price_type=price.price_type,
        amount_inr=Decimal(price.amount_inr),
        pack_quantity=Decimal(price.pack_size.quantity),
        pack_unit=price.pack_size.unit,
        source_name=price.source.name,
        observed_at=price.observed_at,
    )


def lower_cost_options(db: Session, medicine: Medicine) -> dict[str, Any]:
    """Options use verified catalogue attributes only. Ordering is by price then name.

    There is no sponsorship or partner input: nothing commercial exists in this function or schema.
    """
    relatives = db.scalars(
        select(Medicine)
        .options(*_LOAD)
        .where(Medicine.ingredient_key == medicine.ingredient_key, Medicine.id != medicine.id)
    ).all()
    # A medicine sharing at least one ingredient may be an FDC mismatch worth flagging.
    ingredient_ids = [link.ingredient_id for link in medicine.ingredients]
    overlapping = db.scalars(
        select(Medicine)
        .join(MedicineIngredient, MedicineIngredient.medicine_id == Medicine.id)
        .options(*_LOAD)
        .where(MedicineIngredient.ingredient_id.in_(ingredient_ids), Medicine.id != medicine.id)
        .distinct()
        .limit(60)
    ).all()
    seen = {other.id: other for other in [*relatives, *overlapping]}
    attrs = attrs_of(medicine)
    reference_prices = _latest_prices(medicine)
    equivalents: list[dict[str, Any]] = []
    not_equivalent: list[dict[str, Any]] = []
    for other in seen.values():
        other_attrs = attrs_of(other)
        result = compare(attrs, other_attrs)
        if not result.equivalent:
            not_equivalent.append(
                {
                    "medicine": medicine_summary(other),
                    "difference_codes": result.codes,
                    "reasons": [d.detail for d in result.differences],
                    "regulatory_flags": [flag_dict(flag) for flag in other.flags],
                    "comparable": False,
                }
            )
            continue
        other_prices = _latest_prices(other)
        savings: list[dict[str, Any]] = []
        for reference in reference_prices:
            for candidate in other_prices:
                saving = compute_savings(
                    _fact(medicine, reference), _fact(other, candidate), attrs, other_attrs
                )
                if saving is not None:
                    savings.append(
                        {
                            "price_type": candidate.price_type,
                            "amount_per_unit_inr": str(saving.amount_per_unit_inr),
                            "percent": str(saving.percent),
                            "statement": saving.statement,
                        }
                    )
        pack_differences = _pack_differences(medicine, other)
        unit_prices = [Decimal(price_dict(price)["per_unit_inr"]) for price in other_prices]
        equivalents.append(
            {
                "medicine": medicine_summary(other),
                "prices": [price_dict(price) for price in other_prices],
                "differences": pack_differences,
                "savings": savings,
                "regulatory_flags": [flag_dict(flag) for flag in other.flags],
                "comparable": all(
                    check_comparable(
                        attrs, other_attrs, a.pack_size.unit, b.pack_size.unit
                    ).comparable
                    for a in reference_prices
                    for b in other_prices
                ),
                "_sort": min(unit_prices) if unit_prices else Decimal("Infinity"),
            }
        )
    equivalents.sort(key=lambda item: (item.pop("_sort"), item["medicine"]["display_name"]))
    not_equivalent.sort(key=lambda item: item["medicine"]["display_name"])
    ja_products = db.scalars(
        select(JanAushadhiProduct).where(JanAushadhiProduct.medicine_id.in_([medicine.id, *seen]))
    ).all()
    ja_rows = []
    for product in ja_products:
        target = seen.get(product.medicine_id or -1)
        same = product.medicine_id == medicine.id or (
            target is not None and compare(attrs, attrs_of(target)).equivalent
        )
        if same:
            ja_rows.append(ja_product_dict(product))
    return {
        "reference": {
            "medicine": medicine_detail(medicine),
            "prices": [price_dict(p) for p in reference_prices],
        },
        "equivalents": equivalents,
        "not_equivalent": not_equivalent,
        "jan_aushadhi": ja_rows,
        "disclaimer": f"These are options, not recommendations. {DISCUSS_STATEMENT}",
    }


def _pack_differences(a: Medicine, b: Medicine) -> list[dict[str, str]]:
    labels_a, labels_b = {p.label for p in a.pack_sizes}, {p.label for p in b.pack_sizes}
    if labels_a == labels_b:
        return []
    return [
        {
            "code": "pack_size",
            "detail": f"Pack sizes differ: {', '.join(sorted(labels_a))} vs {', '.join(sorted(labels_b))}.",
        }
    ]


def ja_product_dict(product: JanAushadhiProduct) -> dict[str, Any]:
    today = datetime.now(UTC).date()
    return {
        "drug_code": product.drug_code,
        "generic_name": product.generic_name,
        "group_name": product.group_name,
        "unit_size": product.unit_size,
        "mrp_inr": str(product.mrp_inr),
        "price_type": "catalogue",
        "price_type_label": PRICE_TYPE_LABELS["catalogue"],
        "source": source_dict(product.source),
        "observed_at": product.observed_at.isoformat(),
        "last_updated": product.observed_at.isoformat(),
        "is_stale": is_stale(product.observed_at, product.source.update_cadence_days, today),
        "is_demo": product.is_demo,
        "medicine_id": product.medicine_id,
    }


def kendra_dict(kendra: Any) -> dict[str, Any]:
    return {
        "kendra_code": kendra.kendra_code,
        "name": kendra.name,
        "address": kendra.address,
        "district": kendra.district,
        "state": kendra.state,
        "pin_code": kendra.pin_code,
        "source": source_dict(kendra.source),
        "last_updated": kendra.observed_at.isoformat(),
        "is_demo": kendra.is_demo,
    }
