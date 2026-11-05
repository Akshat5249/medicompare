"""Admin routes: dataset import, review queue, freshness, pharmacist approval and the audit log."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import PROBLEM_RESPONSE, ProblemError, audit, not_found, require_csrf, require_role
from app.db import get_db
from app.imports import pipeline
from app.imports.normalize import NORMALIZERS
from app.models import (
    AuditEvent,
    DataSource,
    ImportBatch,
    Medicine,
    PharmacistProfile,
    PriceObservation,
    Role,
    StagedRow,
    User,
)

router = APIRouter(prefix="/api/v1/admin", responses=PROBLEM_RESPONSE, tags=["admin"])
Db = Annotated[Session, Depends(get_db)]
Admin = Annotated[User, Depends(require_role(Role.admin))]
Csrf = Depends(require_csrf)
MAX_IMPORT_BYTES = 25 * 1024 * 1024


def _batch_dict(batch: ImportBatch) -> dict[str, Any]:
    return {
        "id": batch.id,
        "source": batch.source.code,
        "is_demo": batch.source.is_demo,
        "kind": batch.kind,
        "status": batch.status,
        "file_name": batch.file_name,
        "file_sha256": batch.file_sha256,
        "row_count": batch.row_count,
        "valid_count": batch.valid_count,
        "failed_count": batch.failed_count,
        "created_at": batch.created_at.isoformat(),
        "published_at": batch.published_at.isoformat() if batch.published_at else None,
    }


@router.get("/sources")
def sources(db: Db, _: Admin) -> dict[str, Any]:
    """Source freshness dashboard data, with a staleness alert per source."""
    today = datetime.now(UTC).date()
    rows = []
    for source in db.scalars(select(DataSource).order_by(DataSource.code)).all():
        due = (
            source.data_as_of + timedelta(days=source.update_cadence_days)
            if source.data_as_of
            else None
        )
        rows.append(
            {
                "code": source.code,
                "name": source.name,
                "owner": source.owner,
                "url": source.url,
                "licence_note": source.licence_note,
                "update_cadence_days": source.update_cadence_days,
                "is_demo": source.is_demo,
                "data_as_of": source.data_as_of.isoformat() if source.data_as_of else None,
                "last_imported_at": source.last_imported_at.isoformat()
                if source.last_imported_at
                else None,
                "next_update_due": due.isoformat() if due else None,
                "is_stale": due is None or today > due,
                "medicines": db.scalar(
                    select(func.count())
                    .select_from(Medicine)
                    .where(Medicine.source_id == source.id)
                ),
                "prices": db.scalar(
                    select(func.count())
                    .select_from(PriceObservation)
                    .where(PriceObservation.source_id == source.id)
                ),
            }
        )
    return {"sources": rows}


@router.get("/imports")
def list_imports(db: Db, _: Admin) -> dict[str, Any]:
    batches = db.scalars(
        select(ImportBatch).order_by(ImportBatch.created_at.desc()).limit(100)
    ).all()
    return {"batches": [_batch_dict(batch) for batch in batches]}


@router.post("/imports", status_code=201, dependencies=[Csrf])
def stage_import(
    db: Db,
    admin: Admin,
    file: Annotated[UploadFile, File()],
    source_code: Annotated[str, Form()],
    kind: Annotated[str, Form()],
) -> dict[str, Any]:
    source = db.scalar(select(DataSource).where(DataSource.code == source_code))
    if source is None:
        raise not_found("Data source")
    if kind not in NORMALIZERS:
        raise ProblemError(422, "unknown_kind", f"Import kind must be one of {sorted(NORMALIZERS)}")
    content = file.file.read(MAX_IMPORT_BYTES + 1)
    if len(content) > MAX_IMPORT_BYTES:
        raise ProblemError(413, "file_too_large", "Import files can be at most 25 MB")
    try:
        batch = pipeline.stage_rows(
            db,
            source=source,
            kind=kind,
            file_name=file.filename or "upload.csv",
            content=content,
            created_by=admin.id,
        )
    except pipeline.ImportError_ as exc:
        raise ProblemError(422, "import_invalid", str(exc)) from exc
    audit(
        db,
        admin,
        "import_staged",
        "import_batch",
        batch.id,
        rows=batch.row_count,
        failed=batch.failed_count,
    )
    db.commit()
    return _batch_dict(batch)


def _batch(db: Session, batch_id: int) -> ImportBatch:
    batch = db.get(ImportBatch, batch_id)
    if batch is None:
        raise not_found("Import batch")
    return batch


@router.post("/imports/{batch_id}/publish", dependencies=[Csrf])
def publish_import(db: Db, admin: Admin, batch_id: int) -> dict[str, Any]:
    batch = _batch(db, batch_id)
    try:
        result = pipeline.publish(db, batch)
    except pipeline.ImportError_ as exc:
        raise ProblemError(409, "batch_not_publishable", str(exc)) from exc
    pipeline.rebuild_lasa_pairs(db)
    audit(db, admin, "import_published", "import_batch", batch.id, **result)
    db.commit()
    return {**_batch_dict(batch), **result}


@router.post("/imports/{batch_id}/reject", dependencies=[Csrf])
def reject_import(db: Db, admin: Admin, batch_id: int) -> dict[str, Any]:
    batch = _batch(db, batch_id)
    if batch.status == "published":
        raise ProblemError(409, "batch_not_rejectable", "A published batch cannot be rejected")
    batch.status = "rejected"
    audit(db, admin, "import_rejected", "import_batch", batch.id)
    db.commit()
    return _batch_dict(batch)


@router.get("/review-queue")
def review_queue(db: Db, _: Admin, batch_id: int | None = None) -> dict[str, Any]:
    statement = (
        select(StagedRow, ImportBatch)
        .join(ImportBatch, StagedRow.batch_id == ImportBatch.id)
        .where(StagedRow.status == "failed")
        .order_by(StagedRow.batch_id.desc(), StagedRow.row_number)
        .limit(200)
    )
    if batch_id is not None:
        statement = statement.where(StagedRow.batch_id == batch_id)
    return {
        "rows": [
            {
                "id": row.id,
                "batch_id": row.batch_id,
                "kind": batch.kind,
                "batch_status": batch.status,
                "row_number": row.row_number,
                "raw": row.raw,
                "errors": row.errors,
            }
            for row, batch in db.execute(statement).all()
        ]
    }


class RowCorrection(BaseModel):
    raw: dict[str, Any]


@router.put("/review-queue/{row_id}", dependencies=[Csrf])
def correct_row(db: Db, admin: Admin, row_id: int, body: RowCorrection) -> dict[str, Any]:
    row = db.get(StagedRow, row_id)
    if row is None:
        raise not_found("Row")
    batch = _batch(db, row.batch_id)
    if batch.status != "validated":
        raise ProblemError(409, "batch_closed", "Rows can be corrected only before publication")
    pipeline.correct_row(db, row, body.raw, batch.kind)
    audit(db, admin, "import_row_corrected", "staged_row", row.id, status=row.status)
    db.commit()
    return {"id": row.id, "status": row.status, "errors": row.errors}


@router.delete("/review-queue/{row_id}", status_code=204, dependencies=[Csrf])
def dismiss_row(db: Db, admin: Admin, row_id: int) -> None:
    row = db.get(StagedRow, row_id)
    if row is None:
        raise not_found("Row")
    row.status = "rejected"
    audit(db, admin, "import_row_rejected", "staged_row", row.id)
    db.commit()


@router.get("/pharmacists")
def pharmacists(db: Db, _: Admin, status: str | None = None) -> dict[str, Any]:
    statement = select(PharmacistProfile).order_by(PharmacistProfile.created_at)
    if status:
        statement = statement.where(PharmacistProfile.status == status)
    return {
        "pharmacists": [
            {
                "user_id": str(profile.user_id),
                "email": profile.user.email,
                "display_name": profile.user.display_name,
                "registration_number": profile.registration_number,
                "registration_label": "Self-declared. Check manually with the state pharmacy council.",
                "state_council": profile.state_council,
                "status": profile.status,
                "created_at": profile.created_at.isoformat(),
            }
            for profile in db.scalars(statement).all()
        ]
    }


class PharmacistDecision(BaseModel):
    status: str = Field(pattern="^(approved|rejected)$")


@router.post("/pharmacists/{user_id}/decision", dependencies=[Csrf])
def decide_pharmacist(
    db: Db, admin: Admin, user_id: uuid.UUID, body: PharmacistDecision
) -> dict[str, str]:
    profile = db.get(PharmacistProfile, user_id)
    if profile is None:
        raise not_found("Pharmacist")
    profile.status = body.status
    profile.reviewed_by = admin.id
    profile.reviewed_at = datetime.now(UTC)
    profile.user.role = Role.pharmacist.value if body.status == "approved" else Role.user.value
    audit(db, admin, f"pharmacist_{body.status}", "user", user_id)
    db.commit()
    return {"status": profile.status}


@router.get("/audit")
def audit_log(db: Db, _: Admin, limit: int = 100) -> dict[str, Any]:
    rows = db.scalars(
        select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(min(limit, 500))
    ).all()
    return {
        "events": [
            {
                "id": row.id,
                "actor_id": str(row.actor_id) if row.actor_id else None,
                "action": row.action,
                "entity_type": row.entity_type,
                "entity_id": row.entity_id,
                "meta": row.meta,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]
    }
