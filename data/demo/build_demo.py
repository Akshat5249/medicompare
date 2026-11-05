"""Generate the demo dataset. EVERYTHING WRITTEN HERE IS FICTIONAL.

Brand names, manufacturers, prices, Kendras, product codes and alerts below are invented for
demonstration. Every brand starts with "Demo" so it cannot be mistaken for a real product. It is
loaded under an is_demo=true data source and is labelled "Demo data" in the UI.

Run: python data/demo/build_demo.py
"""

from __future__ import annotations

import csv
import random
from decimal import Decimal
from pathlib import Path

OUT = Path(__file__).parent
SEED = 20261105
TODAY_OBSERVED = "2026-10-01"
STALE_OBSERVED = "2025-06-01"

# (generic, ingredients "name:salt:strength;...", form, route, release, category, pack qty, unit, base price per pack)
FAMILIES = [
    (
        "Metformin 500 mg",
        "Metformin:hydrochloride:500 mg",
        "tablet",
        "oral",
        "conventional",
        "anti-diabetes",
        10,
        "tablet",
        18,
    ),
    (
        "Metformin 500 mg SR",
        "Metformin:hydrochloride:500 mg",
        "tablet",
        "oral",
        "sustained",
        "anti-diabetes",
        10,
        "tablet",
        26,
    ),
    (
        "Metformin 1000 mg",
        "Metformin:hydrochloride:1000 mg",
        "tablet",
        "oral",
        "conventional",
        "anti-diabetes",
        10,
        "tablet",
        32,
    ),
    (
        "Glimepiride 1 mg",
        "Glimepiride::1 mg",
        "tablet",
        "oral",
        "conventional",
        "anti-diabetes",
        10,
        "tablet",
        30,
    ),
    (
        "Glimepiride 1 mg + Metformin 500 mg",
        "Glimepiride::1 mg;Metformin:hydrochloride:500 mg",
        "tablet",
        "oral",
        "sustained",
        "anti-diabetes",
        10,
        "tablet",
        48,
    ),
    (
        "Glimepiride 2 mg + Metformin 500 mg",
        "Glimepiride::2 mg;Metformin:hydrochloride:500 mg",
        "tablet",
        "oral",
        "sustained",
        "anti-diabetes",
        10,
        "tablet",
        62,
    ),
    (
        "Metoprolol Succinate 50 mg ER",
        "Metoprolol:succinate:50 mg",
        "tablet",
        "oral",
        "extended",
        "cardiovascular",
        10,
        "tablet",
        72,
    ),
    (
        "Metoprolol Tartrate 50 mg",
        "Metoprolol:tartrate:50 mg",
        "tablet",
        "oral",
        "conventional",
        "cardiovascular",
        10,
        "tablet",
        40,
    ),
    (
        "Amlodipine 5 mg",
        "Amlodipine:besilate:5 mg",
        "tablet",
        "oral",
        "conventional",
        "cardiovascular",
        10,
        "tablet",
        22,
    ),
    (
        "Amlodipine 10 mg",
        "Amlodipine:besilate:10 mg",
        "tablet",
        "oral",
        "conventional",
        "cardiovascular",
        10,
        "tablet",
        40,
    ),
    (
        "Amlodipine 5 mg + Atenolol 50 mg",
        "Amlodipine:besilate:5 mg;Atenolol::50 mg",
        "tablet",
        "oral",
        "conventional",
        "cardiovascular",
        10,
        "tablet",
        36,
    ),
    (
        "Atorvastatin 10 mg",
        "Atorvastatin:calcium:10 mg",
        "tablet",
        "oral",
        "conventional",
        "cardiovascular",
        10,
        "tablet",
        45,
    ),
    (
        "Atorvastatin 20 mg",
        "Atorvastatin:calcium:20 mg",
        "tablet",
        "oral",
        "conventional",
        "cardiovascular",
        10,
        "tablet",
        88,
    ),
    (
        "Telmisartan 40 mg",
        "Telmisartan::40 mg",
        "tablet",
        "oral",
        "conventional",
        "cardiovascular",
        10,
        "tablet",
        55,
    ),
    (
        "Telmisartan 40 mg + Hydrochlorothiazide 12.5 mg",
        "Telmisartan::40 mg;Hydrochlorothiazide::12.5 mg",
        "tablet",
        "oral",
        "conventional",
        "cardiovascular",
        10,
        "tablet",
        76,
    ),
    (
        "Losartan 50 mg",
        "Losartan:potassium:50 mg",
        "tablet",
        "oral",
        "conventional",
        "cardiovascular",
        10,
        "tablet",
        42,
    ),
    (
        "Paracetamol 500 mg",
        "Paracetamol::500 mg",
        "tablet",
        "oral",
        "conventional",
        "pain-fever",
        15,
        "tablet",
        15,
    ),
    (
        "Paracetamol 650 mg",
        "Paracetamol::650 mg",
        "tablet",
        "oral",
        "conventional",
        "pain-fever",
        15,
        "tablet",
        28,
    ),
    (
        "Paracetamol 250 mg/5 mL Suspension",
        "Paracetamol::250 mg/5 ml",
        "suspension",
        "oral",
        "not_applicable",
        "pain-fever",
        60,
        "mL",
        34,
    ),
    (
        "Azithromycin 500 mg",
        "Azithromycin:dihydrate:500 mg",
        "tablet",
        "oral",
        "conventional",
        "anti-infective",
        3,
        "tablet",
        72,
    ),
    (
        "Amoxicillin 500 mg",
        "Amoxicillin:trihydrate:500 mg",
        "capsule",
        "oral",
        "conventional",
        "anti-infective",
        10,
        "capsule",
        68,
    ),
    (
        "Amoxicillin 500 mg + Clavulanic Acid 125 mg",
        "Amoxicillin:trihydrate:500 mg;Clavulanic Acid:potassium:125 mg",
        "tablet",
        "oral",
        "conventional",
        "anti-infective",
        10,
        "tablet",
        180,
    ),
    (
        "Pantoprazole 40 mg",
        "Pantoprazole:sodium sesquihydrate:40 mg",
        "tablet",
        "oral",
        "enteric_coated",
        "gastro",
        10,
        "tablet",
        75,
    ),
    (
        "Omeprazole 20 mg",
        "Omeprazole::20 mg",
        "capsule",
        "oral",
        "enteric_coated",
        "gastro",
        15,
        "capsule",
        45,
    ),
    (
        "Cetirizine 10 mg",
        "Cetirizine:dihydrochloride:10 mg",
        "tablet",
        "oral",
        "conventional",
        "allergy",
        10,
        "tablet",
        16,
    ),
    (
        "Levothyroxine 50 mcg",
        "Levothyroxine:sodium:50 mcg",
        "tablet",
        "oral",
        "conventional",
        "thyroid",
        30,
        "tablet",
        42,
    ),
    (
        "Levothyroxine 100 mcg",
        "Levothyroxine:sodium:100 mcg",
        "tablet",
        "oral",
        "conventional",
        "thyroid",
        30,
        "tablet",
        58,
    ),
    (
        "Salbutamol 4 mg",
        "Salbutamol:sulfate:4 mg",
        "tablet",
        "oral",
        "conventional",
        "respiratory",
        10,
        "tablet",
        12,
    ),
    (
        "Sitagliptin 100 mg",
        "Sitagliptin:phosphate:100 mg",
        "tablet",
        "oral",
        "conventional",
        "anti-diabetes",
        10,
        "tablet",
        160,
    ),
    (
        "Ibuprofen 400 mg",
        "Ibuprofen::400 mg",
        "tablet",
        "oral",
        "conventional",
        "pain-fever",
        15,
        "tablet",
        20,
    ),
]
STEMS = ["Alpha", "Beta", "Gamma", "Delta"]
MAKERS = ["Demo Labs One", "Demo Labs Two", "Demo Pharma Three", "Demo Generics Four"]
# Deliberate look-alike demo brands for matching and safety tests.
LASA = [
    (
        "DemoLosar",
        "Losartan 50 mg",
        "Losartan:potassium:50 mg",
        "cardiovascular",
        "tablet",
        "conventional",
        10,
        "tablet",
        41,
    ),
    (
        "DemoLosec",
        "Omeprazole 20 mg",
        "Omeprazole::20 mg",
        "gastro",
        "capsule",
        "enteric_coated",
        15,
        "capsule",
        47,
    ),
    (
        "DemoMetacin",
        "Metformin 500 mg",
        "Metformin:hydrochloride:500 mg",
        "anti-diabetes",
        "tablet",
        "conventional",
        10,
        "tablet",
        25,
    ),
    (
        "DemoMetocin",
        "Metoprolol Tartrate 50 mg",
        "Metoprolol:tartrate:50 mg",
        "cardiovascular",
        "tablet",
        "conventional",
        10,
        "tablet",
        44,
    ),
    (
        "DemoCetril",
        "Cetirizine 10 mg",
        "Cetirizine:dihydrochloride:10 mg",
        "allergy",
        "tablet",
        "conventional",
        10,
        "tablet",
        18,
    ),
    (
        "DemoCitril",
        "Levothyroxine 50 mcg",
        "Levothyroxine:sodium:50 mcg",
        "thyroid",
        "tablet",
        "conventional",
        30,
        "tablet",
        40,
    ),
]
CATALOGUE_FIELDS = [
    "display_name",
    "brand",
    "manufacturer",
    "generic_name",
    "ingredients",
    "dosage_form",
    "route",
    "release_type",
    "therapeutic_category",
    "pack_quantity",
    "pack_unit",
    "price_type",
    "price",
    "observed_at",
]


def build_catalogue(rng: random.Random) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for generic, ingredients, form, route, release, category, qty, unit, base in FAMILIES:
        for index, stem in enumerate(STEMS):
            first_word = generic.split()[0]
            brand = f"Demo{first_word[:5]}{stem}"
            price = Decimal(base) * Decimal(str(round(rng.uniform(0.75, 2.4), 2)))
            observed = STALE_OBSERVED if rng.random() < 0.12 else TODAY_OBSERVED
            with_price = rng.random() > 0.05
            rows.append(
                {
                    "display_name": f"{brand} ({generic})",
                    "brand": brand,
                    "manufacturer": MAKERS[index],
                    "generic_name": generic,
                    "ingredients": ingredients,
                    "dosage_form": form,
                    "route": route,
                    "release_type": release,
                    "therapeutic_category": category,
                    "pack_quantity": qty,
                    "pack_unit": unit,
                    "price_type": "mrp" if with_price else "",
                    "price": f"{price:.2f}" if with_price else "",
                    "observed_at": observed if with_price else "",
                }
            )
    for brand, generic, ingredients, category, form, release, qty, unit, price in LASA:
        rows.append(
            {
                "display_name": f"{brand} ({generic})",
                "brand": brand,
                "manufacturer": MAKERS[0],
                "generic_name": generic,
                "ingredients": ingredients,
                "dosage_form": form,
                "route": "oral",
                "release_type": release,
                "therapeutic_category": category,
                "pack_quantity": qty,
                "pack_unit": unit,
                "price_type": "mrp",
                "price": f"{price}.00",
                "observed_at": TODAY_OBSERVED,
            }
        )
    return rows


def build_ja_products() -> list[dict[str, object]]:
    rows = []
    for number, (
        generic,
        _ingredients,
        _form,
        _route,
        _release,
        category,
        qty,
        unit,
        base,
    ) in enumerate(FAMILIES, start=1):
        if number % 3 == 0:
            continue
        brand = f"Demo{generic.split()[0][:5]}Alpha"
        rows.append(
            {
                "drug_code": f"DEMO-{number:04d}",
                "generic_name": f"{generic} (Demo data)",
                "group_name": category,
                "unit_size": f"{qty} {unit}",
                "mrp": f"{Decimal(base) * Decimal('0.45'):.2f}",
                "observed_at": TODAY_OBSERVED,
                "display_name": f"{brand} ({generic})",
            }
        )
    return rows


def build_kendras() -> list[dict[str, object]]:
    places = [
        ("Chennai", "Tamil Nadu", "600001", 13.09, 80.27),
        ("Chennai", "Tamil Nadu", "600017", 13.04, 80.23),
        ("Coimbatore", "Tamil Nadu", "641001", 11.00, 76.96),
        ("Madurai", "Tamil Nadu", "625001", 9.92, 78.12),
        ("New Delhi", "Delhi", "110001", 28.63, 77.22),
        ("New Delhi", "Delhi", "110016", 28.55, 77.20),
        ("Lucknow", "Uttar Pradesh", "226001", 26.85, 80.95),
        ("Patna", "Bihar", "800001", 25.61, 85.14),
        ("Mumbai", "Maharashtra", "400001", 18.94, 72.84),
        ("Pune", "Maharashtra", "411001", 18.52, 73.86),
        ("Bengaluru", "Karnataka", "560001", 12.98, 77.60),
        ("Hyderabad", "Telangana", "500001", 17.39, 78.47),
        ("Kolkata", "West Bengal", "700001", 22.57, 88.35),
        ("Jaipur", "Rajasthan", "302001", 26.92, 75.82),
    ]
    return [
        {
            "kendra_code": f"DEMO-K{index:03d}",
            "name": f"Demo Kendra {index} (fictional)",
            "address": f"Demo Street {index}, {district} (fictional address)",
            "district": district,
            "state": state,
            "pin_code": pin,
            "latitude": lat,
            "longitude": lon,
            "observed_at": TODAY_OBSERVED,
        }
        for index, (district, state, pin, lat, lon) in enumerate(places, start=1)
    ]


def build_flags() -> list[dict[str, object]]:
    return [
        {
            "medicine_display_name": "DemoSalbuBeta (Salbutamol 4 mg)",
            "flag_type": "quality_alert",
            "description": "DEMO ONLY: fictional batch DEMO123 used to show how a quality alert is displayed.",
            "source_url": "",
            "source_date": TODAY_OBSERVED,
        },
        {
            "medicine_display_name": "DemoIbuprGamma (Ibuprofen 400 mg)",
            "flag_type": "prohibited_fdc",
            "description": "DEMO ONLY: fictional notice used to show how a regulatory prohibition is displayed.",
            "source_url": "",
            "source_date": TODAY_OBSERVED,
        },
        {
            "medicine_display_name": "DemoAzithAlpha (Azithromycin 500 mg)",
            "flag_type": "schedule_h1",
            "description": "DEMO ONLY: fictional example of how a schedule classification is displayed.",
            "source_url": "",
            "source_date": TODAY_OBSERVED,
        },
    ]


def write(name: str, rows: list[dict[str, object]], fields: list[str] | None = None) -> None:
    with open(OUT / name, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields or list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(name, len(rows))


if __name__ == "__main__":
    generator = random.Random(SEED)  # noqa: S311 - reproducible demo data, not security
    write("demo_catalogue.csv", build_catalogue(generator), CATALOGUE_FIELDS)
    write("demo_ja_products.csv", build_ja_products())
    write("demo_ja_kendras.csv", build_kendras())
    write("demo_regulatory_flags.csv", build_flags())
