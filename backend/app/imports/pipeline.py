"""Staging, validation and publication of datasets, with row-level provenance."""

from __future__ import annotations

import csv
import hashlib
import io
import re
from collections.abc import Iterable
from datetime import UTC, date, datetime
from decimal import Decimal
from itertools import combinations
from typing import Any, cast

from rapidfuzz.distance import JaroWinkler
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.imports.normalize import (
    DUPLICATE_KEYS,
    FORM_LABELS,
    NORMALIZERS,
    RELEASE_LABELS,
    ROUTE_LABELS,
)
from app.matching.equivalence import (
    IngredientDose,
    MedicineAttributes,
    Strength,
    equivalence_key,
    ingredient_key,
)
from app.models import (
    Brand,
    DataSource,
    DosageForm,
    ImportBatch,
    Ingredient,
    IngredientAlias,
    JanAushadhiKendra,
    JanAushadhiProduct,
    LasaPair,
    Manufacturer,
    Medicine,
    MedicineIngredient,
    PackSize,
    PriceObservation,
    RegulatoryFlag,
    ReleaseType,
    Route,
    SaltForm,
    StagedRow,
)

LASA_THRESHOLD = 0.88


class ImportError_(Exception):
    pass


def read_csv(content: bytes) -> list[dict[str, Any]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ImportError_("File is not UTF-8 text") from exc
    return list(csv.DictReader(io.StringIO(text)))


def stage_rows(
    session: Session,
    *,
    source: DataSource,
    kind: str,
    file_name: str,
    content: bytes,
    created_by: Any = None,
) -> ImportBatch:
    """Create a batch and validate every row. Nothing reaches public tables until publish()."""
    if kind not in NORMALIZERS:
        raise ImportError_(f"Unknown import kind {kind}")
    rows = read_csv(content)
    batch = ImportBatch(
        source_id=source.id,
        kind=kind,
        file_name=file_name[:255],
        file_sha256=hashlib.sha256(content).hexdigest(),
        created_by=created_by,
    )
    session.add(batch)
    session.flush()
    seen: set[tuple[Any, ...]] = set()
    valid = failed = 0
    for number, raw in enumerate(rows, start=1):
        normalized, errors = NORMALIZERS[kind](raw)
        if normalized is not None:
            key = DUPLICATE_KEYS[kind](normalized)
            if key in seen:
                errors = [f"duplicate: another row in this file has the same key {key}"]
                normalized = None
            else:
                seen.add(key)
        status = "valid" if normalized is not None else "failed"
        valid += status == "valid"
        failed += status == "failed"
        session.add(
            StagedRow(
                batch_id=batch.id,
                row_number=number,
                raw=raw,
                normalized=normalized,
                status=status,
                errors=errors,
            )
        )
    batch.row_count, batch.valid_count, batch.failed_count = len(rows), valid, failed
    batch.status = "validated"
    session.flush()
    return batch


def correct_row(session: Session, row: StagedRow, raw: dict[str, Any], kind: str) -> StagedRow:
    """Re-validate a failed row after an admin correction. Correction must pass the same checks."""
    normalized, errors = NORMALIZERS[kind](raw)
    row.raw, row.normalized, row.errors = raw, normalized, errors
    row.status = "valid" if normalized is not None else "failed"
    batch = session.get(ImportBatch, row.batch_id)
    assert batch is not None
    session.flush()
    rows = session.scalars(select(StagedRow).where(StagedRow.batch_id == batch.id)).all()
    batch.valid_count = sum(r.status == "valid" for r in rows)
    batch.failed_count = sum(r.status == "failed" for r in rows)
    return row


class _Vocabulary:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.cache: dict[tuple[str, str], Any] = {}

    def _get(self, model: Any, field: str, value: str, **extra: Any) -> Any:
        key = (model.__name__, value)
        if key in self.cache:
            return self.cache[key]
        obj = self.session.scalar(select(model).where(getattr(model, field) == value))
        if obj is None:
            obj = model(**{field: value}, **extra)
            self.session.add(obj)
            self.session.flush()
        self.cache[key] = obj
        return obj

    def ingredient(self, name: str) -> Ingredient:
        return cast(Ingredient, self._get(Ingredient, "name", name))

    def salt(self, name: str) -> SaltForm:
        return cast(SaltForm, self._get(SaltForm, "name", name))

    def form(self, code: str) -> DosageForm:
        return cast(DosageForm, self._get(DosageForm, "code", code, label=FORM_LABELS[code]))

    def route(self, code: str) -> Route:
        return cast(Route, self._get(Route, "code", code, label=ROUTE_LABELS[code]))

    def release(self, code: str) -> ReleaseType:
        return cast(ReleaseType, self._get(ReleaseType, "code", code, label=RELEASE_LABELS[code]))

    def manufacturer(self, name: str, is_demo: bool) -> Manufacturer:
        return cast(Manufacturer, self._get(Manufacturer, "name", name, is_demo=is_demo))

    def brand(self, name: str, manufacturer_id: int | None, is_demo: bool) -> Brand:
        return cast(
            Brand, self._get(Brand, "name", name, manufacturer_id=manufacturer_id, is_demo=is_demo)
        )


def build_search_text(generic: str, display: str, brand: str | None, aliases: Iterable[str]) -> str:
    return " ".join(filter(None, [display, generic, brand, *aliases])).lower()


def _publish_medicine(
    session: Session, vocab: _Vocabulary, batch: ImportBatch, row: StagedRow, source: DataSource
) -> None:
    n = row.normalized
    assert n is not None
    is_demo = source.is_demo
    doses = tuple(
        IngredientDose(
            ingredient=i["name"],
            salt_form=i["salt_form"],
            strength=Strength(
                value=Decimal(i["strength_value"]),
                unit=i["strength_unit"],
                per_value=Decimal(i["per_value"]) if i["per_value"] else None,
                per_unit=i["per_unit"],
            ),
        )
        for i in n["ingredients"]
    )
    attrs = MedicineAttributes(doses, n["dosage_form"], n["route"], n["release_type"])
    existing = session.scalar(
        select(Medicine).where(
            Medicine.display_name == n["display_name"],
            Medicine.source_id == source.id,
            Medicine.equivalence_key == equivalence_key(attrs),
        )
    )
    if existing is None:
        brand_id = None
        if n.get("brand"):
            maker = (
                vocab.manufacturer(n["manufacturer"], is_demo) if n.get("manufacturer") else None
            )
            brand_id = vocab.brand(n["brand"], maker.id if maker else None, is_demo).id
        ingredient_rows = [vocab.ingredient(i["name"]) for i in n["ingredients"]]
        aliases = session.scalars(
            select(IngredientAlias.alias).where(
                IngredientAlias.ingredient_id.in_([i.id for i in ingredient_rows])
            )
        ).all()
        existing = Medicine(
            display_name=n["display_name"],
            generic_name=n["generic_name"],
            brand_id=brand_id,
            dosage_form_id=vocab.form(n["dosage_form"]).id,
            route_id=vocab.route(n["route"]).id,
            release_type_id=vocab.release(n["release_type"]).id,
            therapeutic_category=n.get("therapeutic_category"),
            equivalence_key=equivalence_key(attrs),
            ingredient_key=ingredient_key(doses),
            search_text=build_search_text(
                n["generic_name"], n["display_name"], n.get("brand"), aliases
            ),
            source_id=source.id,
            batch_id=batch.id,
            source_row=row.row_number,
            source_text=n.get("source_text"),
            is_demo=is_demo,
        )
        session.add(existing)
        session.flush()
        for spec, ingredient in zip(n["ingredients"], ingredient_rows, strict=True):
            session.add(
                MedicineIngredient(
                    medicine_id=existing.id,
                    ingredient_id=ingredient.id,
                    salt_form_id=vocab.salt(spec["salt_form"]).id if spec["salt_form"] else None,
                    position=spec["position"],
                    strength_value=Decimal(spec["strength_value"]),
                    strength_unit=spec["strength_unit"],
                    per_value=Decimal(spec["per_value"]) if spec["per_value"] else None,
                    per_unit=spec["per_unit"],
                    strength_text=spec["strength_text"],
                )
            )
    quantity = Decimal(n["pack_quantity"])
    pack = session.scalar(
        select(PackSize).where(
            PackSize.medicine_id == existing.id,
            PackSize.quantity == quantity,
            PackSize.unit == n["pack_unit"],
        )
    )
    if pack is None:
        label = f"{quantity.normalize():f} {n['pack_unit']}"
        pack = PackSize(
            medicine_id=existing.id, quantity=quantity, unit=n["pack_unit"], label=label
        )
        session.add(pack)
        session.flush()
    if n.get("price"):
        observed = date.fromisoformat(n["observed_at"])
        session.add(
            PriceObservation(
                medicine_id=existing.id,
                pack_size_id=pack.id,
                price_type=n["price_type"],
                amount_inr=Decimal(n["price"]),
                source_id=source.id,
                batch_id=batch.id,
                source_row=row.row_number,
                observed_at=observed,
                valid_from=observed,
                is_demo=is_demo,
            )
        )


def publish(session: Session, batch: ImportBatch) -> dict[str, int]:
    """Publish valid rows. Failed rows stay in the review queue and are not published."""
    if batch.status != "validated":
        raise ImportError_(f"Batch status is {batch.status}, expected validated")
    source = session.get(DataSource, batch.source_id)
    assert source is not None
    rows = session.scalars(
        select(StagedRow).where(StagedRow.batch_id == batch.id, StagedRow.status == "valid")
    ).all()
    vocab = _Vocabulary(session)
    observed: date | None = None
    published = 0
    for row in rows:
        n = row.normalized
        assert n is not None
        if batch.kind in {"nppa_ceiling", "catalogue"}:
            _publish_medicine(session, vocab, batch, row, source)
            if n.get("observed_at"):
                observed = max(filter(None, [observed, date.fromisoformat(n["observed_at"])]))
        elif batch.kind == "ja_products":
            when = date.fromisoformat(n["observed_at"])
            observed = max(filter(None, [observed, when]))
            medicine = None
            if n.get("medicine_equivalence_hint"):
                medicine = session.scalar(
                    select(Medicine)
                    .where(Medicine.display_name == n["medicine_equivalence_hint"])
                    .limit(1)
                )
            existing = session.scalar(
                select(JanAushadhiProduct).where(JanAushadhiProduct.drug_code == n["drug_code"])
            )
            target = existing or JanAushadhiProduct(drug_code=n["drug_code"])
            target.generic_name, target.group_name = n["generic_name"], n["group_name"]
            target.unit_size, target.mrp_inr = n["unit_size"], Decimal(n["mrp"])
            target.medicine_id = medicine.id if medicine else None
            target.source_id, target.batch_id = source.id, batch.id
            target.observed_at, target.is_demo = when, source.is_demo
            session.add(target)
        elif batch.kind == "ja_kendras":
            when = date.fromisoformat(n["observed_at"])
            observed = max(filter(None, [observed, when]))
            existing_kendra = session.scalar(
                select(JanAushadhiKendra).where(JanAushadhiKendra.kendra_code == n["kendra_code"])
            )
            kendra = existing_kendra or JanAushadhiKendra(kendra_code=n["kendra_code"])
            for field in (
                "name",
                "address",
                "district",
                "state",
                "pin_code",
                "latitude",
                "longitude",
            ):
                setattr(kendra, field, n[field])
            kendra.source_id, kendra.batch_id = source.id, batch.id
            kendra.observed_at, kendra.is_demo = when, source.is_demo
            session.add(kendra)
        elif batch.kind == "regulatory_flags":
            medicine = session.scalar(
                select(Medicine).where(Medicine.display_name == n["medicine_display_name"]).limit(1)
            )
            if medicine is None:
                row.status, row.errors = "failed", ["medicine_display_name: not in catalogue"]
                batch.valid_count -= 1
                batch.failed_count += 1
                continue
            session.add(
                RegulatoryFlag(
                    medicine_id=medicine.id,
                    flag_type=n["flag_type"],
                    description=n["description"],
                    source_id=source.id,
                    source_url=n["source_url"],
                    source_date=date.fromisoformat(n["source_date"]),
                    is_demo=source.is_demo,
                )
            )
            observed = max(filter(None, [observed, date.fromisoformat(n["source_date"])]))
        published += 1
    batch.status = "published"
    batch.published_at = datetime.now(UTC)
    source.last_imported_at = batch.published_at
    if observed:
        source.data_as_of = observed
    session.flush()
    return {"published": published, "failed": batch.failed_count}


def rebuild_lasa_pairs(session: Session) -> int:
    """Compute look-alike name pairs from catalogue brands and ingredients.

    This is a conservative string-similarity screen. It is not a clinical look-alike/sound-alike
    list (see docs/OPEN_ITEMS.md), and any hit only forces extra human review.
    """
    session.execute(delete(LasaPair).where(LasaPair.origin == "computed"))
    brands = session.execute(select(Brand.name, Brand.is_demo)).all()
    ingredient_names = session.scalars(select(Ingredient.name)).all()
    names: dict[str, bool] = {name.lower(): False for name in ingredient_names}
    # Demo brand families share a generated prefix and suffix, which is not real name confusion.
    names.update(
        {
            name.lower(): is_demo
            for name, is_demo in brands
            if not (is_demo and re.search(r"(alpha|beta|gamma|delta)$", name.lower()))
        }
    )
    created = 0
    for first, second in combinations(sorted(names), 2):
        if first.split()[0] == second.split()[0]:
            continue  # strength variants of one brand or ingredient are not name confusion
        score = JaroWinkler.normalized_similarity(first, second)
        if score >= LASA_THRESHOLD:
            session.add(
                LasaPair(
                    name_a=first,
                    name_b=second,
                    origin="computed",
                    similarity=round(score, 4),
                    is_demo=names[first] or names[second],
                )
            )
            created += 1
    session.flush()
    return created
