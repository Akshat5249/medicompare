"""Row normalisers and data-quality checks. A row either normalises exactly or fails with reasons.

Nothing here guesses: an unparseable strength, unit or form sends the row to the review queue.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from decimal import Decimal, InvalidOperation
from typing import Any

from app.matching.equivalence import StrengthParseError, parse_strength

PRICE_MIN = Decimal("0.01")
PRICE_MAX = Decimal("1000000")

# Spacing artefacts from PDF line wrapping in the NPPA files, mapped to the same printed word.
_NPPA_NAME_REPAIRS = {
    "TenofovirDisproxilFum arate": "Tenofovir Disoproxil Fumarate",
    "Efavir enz": "Efavirenz",
    "Dolut egravir": "Dolutegravir",
    "InsulinGlargine": "Insulin Glargine",
    "Sodiumnitroprusside": "Sodium Nitroprusside",
    "Insulin(Soluble)": "Insulin (Soluble)",
    "Insulin PremixInjection 30:70(Regular:NPH)": "Insulin Premix 30:70 (Regular:NPH)",
    "HCltrihydrate": "HCl trihydrate",
}
# Salt names are recorded only when the source prints them.
_SALT_SUFFIXES = {
    "tenofovir disoproxil fumarate": ("Tenofovir Disoproxil", "fumarate"),
    "irinotecan hcl trihydrate": ("Irinotecan", "hydrochloride trihydrate"),
}
_FORMS = {
    "tablet": ("tablet", "oral", "conventional"),
    "capsule": ("capsule", "oral", "conventional"),
    "injection": ("injection", "parenteral", "not_applicable"),
    "solution for injection": ("injection", "parenteral", "not_applicable"),
    "powder for injection": ("powder_for_injection", "parenteral", "not_applicable"),
    "powder for iv injection": ("powder_for_injection", "parenteral", "not_applicable"),
    "powderforinjection": ("powder_for_injection", "parenteral", "not_applicable"),
    "oral liquid": ("oral_liquid", "oral", "not_applicable"),
    "granules": ("granules", "oral", "conventional"),
    "modified release tablet": ("tablet", "oral", "modified"),
    "modified release capsule": ("capsule", "oral", "modified"),
    "sr tablet": ("tablet", "oral", "sustained"),
    "er tablet": ("tablet", "oral", "extended"),
}
FORM_LABELS = {
    "tablet": "Tablet",
    "capsule": "Capsule",
    "injection": "Injection",
    "powder_for_injection": "Powder for injection",
    "oral_liquid": "Oral liquid",
    "granules": "Granules",
    "suspension": "Suspension",
}
ROUTE_LABELS = {"oral": "Oral", "parenteral": "Injection", "sublingual": "Under the tongue"}
RELEASE_LABELS = {
    "conventional": "Conventional (no release modifier stated)",
    "modified": "Modified release",
    "sustained": "Sustained release",
    "extended": "Extended release",
    "enteric_coated": "Enteric coated",
    "not_applicable": "Not applicable",
}
_PACK = re.compile(r"^(\d+|each)\s*(tablet|capsule|ml|vial|pack|gm|sachet)s?$", re.IGNORECASE)
_PACK_UNITS = {"ml": "mL", "gm": "g"}


def _decimal(value: Any, field: str, errors: list[str]) -> Decimal | None:
    try:
        return Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        errors.append(f"{field}: not a number")
        return None


def check_price(value: Any, errors: list[str]) -> str | None:
    amount = _decimal(value, "price", errors)
    if amount is None:
        return None
    if not PRICE_MIN <= amount <= PRICE_MAX:
        errors.append(f"price: {amount} outside sanity bounds {PRICE_MIN}..{PRICE_MAX}")
        return None
    return str(amount)


def _repair_name(name: str) -> str:
    for wrong, right in _NPPA_NAME_REPAIRS.items():
        name = name.replace(wrong, right)
    return re.sub(r"\s+", " ", name).strip()


def _split_fdc_names(name: str) -> list[str]:
    parts = re.split(r"\s*\+\s*", name)
    return [re.sub(r"\s*\([A-Ca-c]\)\s*$", "", part).strip() for part in parts]


def _split_fdc_strengths(text: str) -> list[str]:
    text = re.sub(r"\(\s*p\s*\)", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bTablet\b", "", text, flags=re.IGNORECASE)
    parts = re.split(r"\s*\+\s*", text)
    return [re.sub(r"\s*\([A-Ca-c]\)\s*$", "", part).strip() for part in parts]


def normalize_nppa_row(raw: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    name = _repair_name(str(raw.get("name", "")))
    release_override: str | None = None
    route_override: str | None = None
    lowered = name.lower()
    if "enteric coated" in lowered and "conventional" not in lowered:
        name = re.sub(r"\s*enteric coated", "", name, flags=re.IGNORECASE).strip()
        release_override = "enteric_coated"
    if lowered.endswith(" sublingual"):
        name = re.sub(r"\s*sublingual$", "", name, flags=re.IGNORECASE).strip()
        route_override = "sublingual"
    if "conventional /" in lowered or "conventional/" in lowered:
        errors.append("form: source combines several release types in one row; needs manual review")
    form_text = re.sub(r"\s+", " ", str(raw.get("dosage_form", ""))).strip()
    form_key = form_text.lower().replace(".", "")
    form = _FORMS.get(form_key)
    if form is None:
        errors.append(f"dosage_form: unknown value {form_text!r}")
    names = _split_fdc_names(name)
    strength_parts = _split_fdc_strengths(str(raw.get("strength", "")))
    if len(names) != len(strength_parts):
        errors.append(f"strength: {len(names)} ingredients but {len(strength_parts)} strengths")
    ingredients: list[dict[str, Any]] = []
    for position, (ingredient, strength_text) in enumerate(
        zip(names, strength_parts, strict=False)
    ):
        cleaned = re.sub(
            r"\((?:\s*\d+\s*(?:ml|mg)[^)]*|as licensed)\)", "", strength_text, flags=re.I
        )
        cleaned = re.sub(r"\(\s*p\s*\)", "", cleaned, flags=re.I).strip()
        try:
            parsed = parse_strength(cleaned)
        except StrengthParseError:
            errors.append(f"strength: cannot parse {strength_text!r}")
            continue
        base, salt = _SALT_SUFFIXES.get(ingredient.lower(), (ingredient, None))
        ingredients.append(
            {
                "name": base,
                "salt_form": salt,
                "strength_value": str(parsed.value),
                "strength_unit": parsed.unit,
                "per_value": str(parsed.per_value) if parsed.per_value is not None else None,
                "per_unit": parsed.per_unit,
                "strength_text": cleaned,
                "position": position,
            }
        )
    pack = _PACK.match(str(raw.get("unit_text", "")).strip())
    if not pack:
        errors.append(f"unit: cannot parse {raw.get('unit_text')!r}")
    price = check_price(raw.get("ceiling_price_inr"), errors)
    if errors or form is None or pack is None or price is None:
        return None, errors
    quantity = "1" if pack[1].lower() == "each" else pack[1]
    unit = _PACK_UNITS.get(pack[2].lower(), pack[2].lower())
    generic = " + ".join(i["name"] for i in ingredients)
    strength_display = " + ".join(i["strength_text"] for i in ingredients)
    form_code, route, release = form
    return (
        {
            "display_name": f"{generic} {strength_display} {FORM_LABELS[form_code]}",
            "generic_name": generic,
            "brand": None,
            "manufacturer": None,
            "ingredients": ingredients,
            "dosage_form": form_code,
            "route": route_override or route,
            "release_type": release_override or release,
            "therapeutic_category": raw.get("category"),
            "pack_quantity": quantity,
            "pack_unit": unit,
            "price_type": "ceiling",
            "price": price,
            "observed_at": "2026-03-31",
            "source_text": f"{raw.get('name')} | {form_text} | {raw.get('strength')} | {raw.get('unit_text')}",
        },
        [],
    )


def normalize_catalogue_row(raw: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    """Columns: display_name, brand, manufacturer, generic_name, ingredients, dosage_form, route,
    release_type, pack_quantity, pack_unit, price_type, price, observed_at, therapeutic_category.
    `ingredients` is `name:salt:strength` joined by `;`, with an empty salt when unstated."""
    errors: list[str] = []
    for field in (
        "display_name",
        "generic_name",
        "ingredients",
        "dosage_form",
        "route",
        "release_type",
    ):
        if not str(raw.get(field) or "").strip():
            errors.append(f"{field}: required")
    if str(raw.get("dosage_form")) not in FORM_LABELS:
        errors.append(f"dosage_form: unknown value {raw.get('dosage_form')!r}")
    if str(raw.get("route")) not in ROUTE_LABELS:
        errors.append(f"route: unknown value {raw.get('route')!r}")
    if str(raw.get("release_type")) not in RELEASE_LABELS:
        errors.append(f"release_type: unknown value {raw.get('release_type')!r}")
    ingredients: list[dict[str, Any]] = []
    for position, chunk in enumerate(str(raw.get("ingredients") or "").split(";")):
        pieces = chunk.split(":")
        if len(pieces) != 3:
            errors.append(f"ingredients: bad entry {chunk!r}")
            continue
        try:
            parsed = parse_strength(pieces[2])
        except StrengthParseError:
            errors.append(f"strength: cannot parse {pieces[2]!r}")
            continue
        ingredients.append(
            {
                "name": pieces[0].strip(),
                "salt_form": pieces[1].strip() or None,
                "strength_value": str(parsed.value),
                "strength_unit": parsed.unit,
                "per_value": str(parsed.per_value) if parsed.per_value is not None else None,
                "per_unit": parsed.per_unit,
                "strength_text": pieces[2].strip(),
                "position": position,
            }
        )
    quantity = _decimal(raw.get("pack_quantity"), "pack_quantity", errors)
    if quantity is not None and quantity <= 0:
        errors.append("pack_quantity: must be positive")
    price: str | None = None
    if str(raw.get("price") or "").strip():
        price = check_price(raw.get("price"), errors)
        if raw.get("price_type") not in {"ceiling", "catalogue", "mrp", "indicative"}:
            errors.append(f"price_type: unknown value {raw.get('price_type')!r}")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(raw.get("observed_at") or "")):
            errors.append("observed_at: expected YYYY-MM-DD")
    if errors:
        return None, errors
    return (
        {
            "display_name": str(raw["display_name"]).strip(),
            "generic_name": str(raw["generic_name"]).strip(),
            "brand": str(raw.get("brand") or "").strip() or None,
            "manufacturer": str(raw.get("manufacturer") or "").strip() or None,
            "ingredients": ingredients,
            "dosage_form": raw["dosage_form"],
            "route": raw["route"],
            "release_type": raw["release_type"],
            "therapeutic_category": raw.get("therapeutic_category") or None,
            "pack_quantity": str(quantity),
            "pack_unit": str(raw.get("pack_unit") or "").strip(),
            "price_type": raw.get("price_type") if price else None,
            "price": price,
            "observed_at": raw.get("observed_at") if price else None,
            "source_text": None,
        },
        [],
    )


def normalize_ja_product_row(raw: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    code = str(raw.get("drug_code") or "").strip()
    if not code:
        errors.append("drug_code: required")
    name = str(raw.get("generic_name") or "").strip()
    if not name:
        errors.append("generic_name: required")
    mrp = check_price(raw.get("mrp"), errors)
    if not str(raw.get("unit_size") or "").strip():
        errors.append("unit_size: required")
    if errors:
        return None, errors
    return (
        {
            "drug_code": code,
            "generic_name": name,
            "group_name": str(raw.get("group_name") or "").strip() or None,
            "unit_size": str(raw["unit_size"]).strip(),
            "mrp": mrp,
            "observed_at": raw.get("observed_at"),
            "medicine_equivalence_hint": raw.get("display_name") or None,
        },
        [],
    )


def normalize_ja_kendra_row(raw: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    for field in ("kendra_code", "name", "address", "district", "state"):
        if not str(raw.get(field) or "").strip():
            errors.append(f"{field}: required")
    pin = str(raw.get("pin_code") or "").strip()
    if not re.fullmatch(r"[1-9]\d{5}", pin):
        errors.append(f"pin_code: invalid {pin!r}")
    if errors:
        return None, errors
    return (
        {
            "kendra_code": str(raw["kendra_code"]).strip(),
            "name": str(raw["name"]).strip(),
            "address": str(raw["address"]).strip(),
            "district": str(raw["district"]).strip(),
            "state": str(raw["state"]).strip(),
            "pin_code": pin,
            "latitude": float(raw["latitude"]) if raw.get("latitude") else None,
            "longitude": float(raw["longitude"]) if raw.get("longitude") else None,
            "observed_at": raw.get("observed_at"),
        },
        [],
    )


def normalize_flag_row(raw: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    if raw.get("flag_type") not in {
        "prohibited_fdc",
        "quality_alert",
        "schedule_h",
        "schedule_h1",
        "schedule_x",
    }:
        errors.append(f"flag_type: unknown value {raw.get('flag_type')!r}")
    for field in ("medicine_display_name", "description"):
        if not str(raw.get(field) or "").strip():
            errors.append(f"{field}: required")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(raw.get("source_date") or "")):
        errors.append("source_date: expected YYYY-MM-DD")
    if errors:
        return None, errors
    return (
        {
            "medicine_display_name": str(raw["medicine_display_name"]).strip(),
            "flag_type": raw["flag_type"],
            "description": str(raw["description"]).strip(),
            "source_url": str(raw.get("source_url") or "").strip() or None,
            "source_date": raw["source_date"],
        },
        [],
    )


NORMALIZERS = {
    "nppa_ceiling": normalize_nppa_row,
    "catalogue": normalize_catalogue_row,
    "ja_products": normalize_ja_product_row,
    "ja_kendras": normalize_ja_kendra_row,
    "regulatory_flags": normalize_flag_row,
}
DUPLICATE_KEYS: dict[str, Callable[[dict[str, Any]], tuple[Any, ...]]] = {
    "nppa_ceiling": lambda n: (
        n["display_name"],
        n["release_type"],
        n["pack_quantity"],
        n["pack_unit"],
    ),
    "catalogue": lambda n: (n["display_name"], n["pack_quantity"], n["pack_unit"], n["price_type"]),
    "ja_products": lambda n: (n["drug_code"],),
    "ja_kendras": lambda n: (n["kendra_code"],),
    "regulatory_flags": lambda n: (n["medicine_display_name"], n["flag_type"], n["description"]),
}
