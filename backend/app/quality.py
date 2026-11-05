"""Data-quality checks on published catalogue data. Each check returns offending row counts."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

CHECKS = {
    "price_without_source": "SELECT count(*) FROM price_observations p LEFT JOIN data_sources s ON s.id = p.source_id "
    "WHERE s.id IS NULL",
    "price_out_of_bounds": "SELECT count(*) FROM price_observations WHERE amount_inr < 0.01 OR amount_inr > 1000000",
    "price_demo_flag_mismatch": "SELECT count(*) FROM price_observations p JOIN data_sources s ON s.id = p.source_id "
    "WHERE p.is_demo <> s.is_demo",
    "medicine_demo_flag_mismatch": "SELECT count(*) FROM medicines m JOIN data_sources s ON s.id = m.source_id "
    "WHERE m.is_demo <> s.is_demo",
    "medicine_without_ingredient": "SELECT count(*) FROM medicines m WHERE NOT EXISTS "
    "(SELECT 1 FROM medicine_ingredients i WHERE i.medicine_id = m.id)",
    "bad_strength_unit": "SELECT count(*) FROM medicine_ingredients WHERE lower(strength_unit) NOT IN "
    "('mcg','ug','mg','g','gm','iu','%','unit','vial','dose')",
    "duplicate_medicine": "SELECT count(*) FROM (SELECT display_name, source_id, equivalence_key FROM medicines "
    "GROUP BY 1, 2, 3 HAVING count(*) > 1) d",
    "demo_brand_not_prefixed": "SELECT count(*) FROM brands WHERE is_demo AND name NOT LIKE 'Demo%'",
    "real_medicine_uses_demo_brand": "SELECT count(*) FROM medicines m JOIN brands b ON b.id = m.brand_id "
    "WHERE NOT m.is_demo AND b.is_demo",
}


COUNTS = {
    "medicines": "SELECT count(*) FROM medicines",
    "price_observations": "SELECT count(*) FROM price_observations",
    "jan_aushadhi_products": "SELECT count(*) FROM jan_aushadhi_products",
    "jan_aushadhi_kendras": "SELECT count(*) FROM jan_aushadhi_kendras",
    "lasa_pairs": "SELECT count(*) FROM lasa_pairs",
}


def run_quality_checks(db: Session) -> dict[str, Any]:
    results = {name: int(db.execute(text(sql)).scalar_one()) for name, sql in CHECKS.items()}
    counts = {name: int(db.execute(text(sql)).scalar_one()) for name, sql in COUNTS.items()}
    return {
        "passed": all(value == 0 for value in results.values()),
        "checks": results,
        "counts": counts,
    }
