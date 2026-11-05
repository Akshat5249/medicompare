"""Reproducible seed: real NPPA ceiling prices plus the separate, flagged demo dataset."""

from __future__ import annotations

import csv
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.imports.pipeline import publish, rebuild_lasa_pairs, stage_rows
from app.models import DataSource, Ingredient, IngredientAlias

SOURCES = [
    {
        "code": "nppa_ceiling",
        "name": "NPPA therapeutic-category ceiling price lists",
        "owner": "National Pharmaceutical Pricing Authority, Government of India",
        "url": "https://nppa.gov.in/en/therapeuticcategorywiseceilingpricelist",
        "licence_note": "Reproduction permitted free of charge when accurate and acknowledged "
        "(NPPA copyright policy, verified 2026-11-05).",
        "update_cadence_days": 90,
        "is_demo": False,
    },
    {
        "code": "demo_catalogue",
        "name": "Demo data: fictional brands and prices",
        "owner": "MediCompare demo dataset (fictional)",
        "url": "https://example.invalid/demo",
        "licence_note": "Fictional data created for demonstration.",
        "update_cadence_days": 180,
        "is_demo": True,
    },
    {
        "code": "demo_jan_aushadhi",
        "name": "Demo data: fictional Jan Aushadhi products and Kendras",
        "owner": "MediCompare demo dataset (fictional)",
        "url": "https://example.invalid/demo",
        "licence_note": "Fictional data. Real PMBJP data needs permission from PMBI; see docs/OPEN_ITEMS.md.",
        "update_cadence_days": 180,
        "is_demo": True,
    },
    {
        "code": "demo_regulatory",
        "name": "Demo data: fictional regulatory notices",
        "owner": "MediCompare demo dataset (fictional)",
        "url": "https://example.invalid/demo",
        "licence_note": "Fictional data. Importer accepts CDSCO data; see docs/DATA_SOURCES.md.",
        "update_cadence_days": 180,
        "is_demo": True,
    },
]
SEED_FILES = [
    ("nppa_ceiling", "nppa_ceiling", "sources/nppa_ceiling_prices.csv"),
    ("demo_catalogue", "catalogue", "demo/demo_catalogue.csv"),
    ("demo_jan_aushadhi", "ja_products", "demo/demo_ja_products.csv"),
    ("demo_jan_aushadhi", "ja_kendras", "demo/demo_ja_kendras.csv"),
    ("demo_regulatory", "regulatory_flags", "demo/demo_regulatory_flags.csv"),
]


def ensure_sources(session: Session) -> dict[str, DataSource]:
    result: dict[str, DataSource] = {}
    for spec in SOURCES:
        source = session.scalar(select(DataSource).where(DataSource.code == spec["code"]))
        if source is None:
            source = DataSource(**spec)
            session.add(source)
            session.flush()
        result[str(spec["code"])] = source
    return result


def ensure_aliases(session: Session, data_dir: Path) -> None:
    """Search-only Hindi and Tamil spellings, pre-created so search_text includes them."""
    with open(data_dir / "sources" / "ingredient_aliases.csv", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            ingredient = session.scalar(
                select(Ingredient).where(Ingredient.name == row["ingredient"])
            )
            if ingredient is None:
                ingredient = Ingredient(name=row["ingredient"])
                session.add(ingredient)
                session.flush()
            exists = session.scalar(
                select(IngredientAlias).where(
                    IngredientAlias.ingredient_id == ingredient.id,
                    IngredientAlias.alias == row["alias"],
                )
            )
            if exists is None:
                session.add(
                    IngredientAlias(
                        ingredient_id=ingredient.id, alias=row["alias"], language=row["language"]
                    )
                )
    session.flush()


def seed(session: Session, data_dir: Path | None = None) -> dict[str, dict[str, int]]:
    directory = data_dir or Path(get_settings().data_dir)
    sources = ensure_sources(session)
    ensure_aliases(session, directory)
    report: dict[str, dict[str, int]] = {}
    from app.models import ImportBatch

    for source_code, kind, relative in SEED_FILES:
        path = directory / relative
        already = session.scalar(
            select(ImportBatch).where(
                ImportBatch.source_id == sources[source_code].id,
                ImportBatch.kind == kind,
                ImportBatch.status == "published",
            )
        )
        if already is not None:
            continue
        batch = stage_rows(
            session,
            source=sources[source_code],
            kind=kind,
            file_name=path.name,
            content=path.read_bytes(),
        )
        report[relative] = publish(session, batch)
    report["lasa_pairs"] = {"created": rebuild_lasa_pairs(session)}
    session.commit()
    return report
