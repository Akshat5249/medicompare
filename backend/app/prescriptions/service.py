"""Prescription lifecycle: intake, processing, human verification, deletion and retention."""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.catalogue.service import attrs_of
from app.config import get_settings
from app.core import ProblemError, Storage, audit, get_storage
from app.matching.matcher import CatalogueEntry, match, strength_conflict
from app.models import (
    Brand,
    CandidateMatch,
    Consent,
    ExtractedItem,
    ItemStatus,
    LasaPair,
    Medicine,
    MedicineIngredient,
    Prescription,
    ProcessingJob,
    User,
    VerificationEvent,
)
from app.prescriptions import imaging
from app.prescriptions.extraction import ExtractedField, ExtractedLine, extract
from app.prescriptions.ocr import get_engine, spans_to_lines
from app.safety.emergency import detect_emergency

log = structlog.get_logger()
NOTICE_VERSION = "2026-11"
RESOLVED = {ItemStatus.verified.value, ItemStatus.rejected.value, ItemStatus.unresolved.value}


def load_catalogue(db: Session) -> list[CatalogueEntry]:
    medicines = db.scalars(
        select(Medicine).options(
            selectinload(Medicine.ingredients).selectinload(MedicineIngredient.ingredient),
            selectinload(Medicine.ingredients).selectinload(MedicineIngredient.salt_form),
            selectinload(Medicine.brand),
            selectinload(Medicine.dosage_form),
            selectinload(Medicine.route),
            selectinload(Medicine.release_type),
        )
    ).all()
    return [catalogue_entry(medicine) for medicine in medicines]


def catalogue_entry(medicine: Medicine) -> CatalogueEntry:
    attributes = attrs_of(medicine)
    return CatalogueEntry(
        medicine_id=medicine.id,
        display_name=medicine.display_name,
        brand=medicine.brand.name if medicine.brand else None,
        ingredients=tuple(dose.ingredient for dose in attributes.ingredients),
        strengths=tuple(sorted(dose.strength.canonical() for dose in attributes.ingredients)),
        dosage_form=attributes.dosage_form,
        release_type=attributes.release_type,
    )


def lasa_names(db: Session) -> frozenset[str]:
    rows = db.execute(select(LasaPair.name_a, LasaPair.name_b)).all()
    return frozenset(name for row in rows for name in row)


def record_consent(db: Session, user: User, purpose: str, ocr_engine: str | None = None) -> Consent:
    consent = Consent(
        user_id=user.id, purpose=purpose, notice_version=NOTICE_VERSION, ocr_engine=ocr_engine
    )
    db.add(consent)
    db.flush()
    return consent


def create_upload(
    db: Session, user: User, data: bytes, storage: Storage | None = None
) -> Prescription:
    settings = get_settings()
    sanitised = imaging.sanitise_upload(data)
    if settings.clamav_address:
        imaging.scan_for_malware(data, settings.clamav_address)
    store = storage or get_storage()
    consent = record_consent(db, user, "prescription_upload", settings.ocr_engine)
    prescription = Prescription(
        id=uuid.uuid4(),
        user_id=user.id,
        source_type="upload",
        status="received",
        mime_type=sanitised.mime,
        page_count=len(sanitised.pages),
        consent_id=consent.id,
        retention_until=datetime.now(UTC) + timedelta(days=settings.retention_days),
        processed_keys=[],
    )
    extension = "pdf" if sanitised.mime == "application/pdf" else "png"
    prescription.original_key = f"{prescription.id}/original.{extension}"
    store.put(prescription.original_key, sanitised.original, sanitised.mime)
    db.add(prescription)
    db.add(
        ProcessingJob(prescription_id=prescription.id, status="queued", engine=settings.ocr_engine)
    )
    db.flush()
    return prescription


def _set_item_from_line(item: ExtractedItem, line: ExtractedLine) -> None:
    item.source_text = line.source_text
    item.bbox = line.bbox
    item.page = line.page
    item.ocr_quality = line.quality
    for attribute in ("name", "strength", "form", "frequency", "duration"):
        field: ExtractedField = getattr(line, attribute)
        setattr(item, f"{attribute}_text", field.value)
        setattr(item, f"{attribute}_state", field.state)


def attach_candidates(
    item: ExtractedItem, catalogue: list[CatalogueEntry], lasa: frozenset[str]
) -> None:
    """Replace an item's candidates. Identity stays unverified whatever the scores are."""
    item.candidates.clear()
    candidates = match(item.name_text, item.strength_text, item.form_text, catalogue, lasa)
    for rank, candidate in enumerate(candidates, start=1):
        item.candidates.append(
            CandidateMatch(
                medicine_id=candidate.medicine_id,
                rank=rank,
                score=candidate.score,
                reasons=list(candidate.reasons),
                is_lasa=candidate.is_lasa,
            )
        )
    item.match_quality = candidates[0].score if candidates else None
    item.requires_lasa_review = any(candidate.is_lasa for candidate in candidates)
    item.status = ItemStatus.needs_verification.value
    item.verified_medicine_id = None
    item.verified_by_type = None
    item.verified_at = None


def process_prescription(
    db: Session, prescription_id: uuid.UUID, storage: Storage | None = None
) -> None:
    """Worker entry point. Failures leave a clear status and never a guessed item."""
    settings = get_settings()
    store = storage or get_storage()
    prescription = db.get(Prescription, prescription_id)
    if prescription is None or prescription.original_key is None:
        return
    job = db.scalar(
        select(ProcessingJob)
        .where(ProcessingJob.prescription_id == prescription_id)
        .order_by(ProcessingJob.created_at.desc())
    )
    if job is None:
        job = ProcessingJob(prescription_id=prescription_id, engine=settings.ocr_engine)
        db.add(job)
    started = time.perf_counter()
    prescription.status, job.status = "processing", "running"
    db.commit()
    try:
        raw = store.get(prescription.original_key)
        sanitised = imaging.sanitise_upload(raw)
        engine = get_engine(settings.ocr_engine)
        job.engine, job.engine_version = engine.name, engine.version
        processed_keys: list[str] = []
        lines = []
        for page, page_bytes in enumerate(sanitised.pages):
            processed = imaging.preprocess(page_bytes)
            key = f"{prescription.id}/processed-{page}.png"
            store.put(key, imaging.encode_png(processed), "image/png")
            processed_keys.append(key)
            lines += spans_to_lines(engine.recognize(processed), page=page)
        prescription.processed_keys = processed_keys
        full_text = "\n".join(line.text for line in lines)
        prescription.emergency_flagged = detect_emergency(full_text).detected
        result = extract(lines)
        prescription.redacted_line_count = result.redacted_lines
        catalogue = load_catalogue(db)
        lasa = lasa_names(db)
        for position, line in enumerate(result.items):
            item = ExtractedItem(prescription_id=prescription.id, position=position)
            _set_item_from_line(item, line)
            attach_candidates(item, catalogue, lasa)
            db.add(item)
        prescription.status = "needs_verification" if result.items else "unreadable"
        job.status = "succeeded"
    except imaging.UploadRejected as exc:
        prescription.status, job.status, job.error_code = "failed", "failed", exc.code
    except Exception:
        log.exception("prescription_processing_failed", prescription_id=str(prescription_id))
        db.rollback()
        prescription = db.get(Prescription, prescription_id)
        assert prescription is not None
        prescription.status = "failed"
        job = db.scalar(
            select(ProcessingJob)
            .where(ProcessingJob.prescription_id == prescription_id)
            .order_by(ProcessingJob.created_at.desc())
        )
        assert job is not None
        job.status, job.error_code = "failed", "internal_error"
    job.duration_ms = int((time.perf_counter() - started) * 1000)
    job.finished_at = datetime.now(UTC)
    db.commit()


def create_manual(db: Session, user: User, entries: list[dict[str, Any]]) -> Prescription:
    """Manual entry is a first-class path, and goes through the same verification gate."""
    prescription = Prescription(
        user_id=user.id,
        source_type="manual",
        status="needs_verification",
        page_count=0,
        retention_until=datetime.now(UTC) + timedelta(days=get_settings().retention_days),
        processed_keys=[],
    )
    db.add(prescription)
    db.flush()
    catalogue = load_catalogue(db)
    lasa = lasa_names(db)
    for position, entry in enumerate(entries):
        name = (entry.get("name") or "").strip() or None
        item = ExtractedItem(
            prescription_id=prescription.id,
            position=position,
            source_text=" ".join(
                filter(None, [entry.get("name"), entry.get("strength"), entry.get("form")])
            ),
            name_text=name,
            name_state="visible" if name else "unknown",
        )
        for attribute in ("strength", "form", "frequency", "duration"):
            value = (entry.get(attribute) or "").strip() or None
            setattr(item, f"{attribute}_text", value)
            setattr(item, f"{attribute}_state", "visible" if value else "unknown")
        attach_candidates(item, catalogue, lasa)
        db.add(item)
    if any(detect_emergency(str(entry.get(k) or "")).detected for entry in entries for k in entry):
        prescription.emergency_flagged = True
    db.flush()
    return prescription


def _refresh_status(db: Session, prescription: Prescription) -> None:
    db.flush()
    db.refresh(prescription, ["items"])
    if prescription.items and all(item.status in RESOLVED for item in prescription.items):
        prescription.status = "verified"
    elif prescription.source_type == "upload" and not prescription.items:
        return
    else:
        prescription.status = "needs_verification"


def correct_item(
    db: Session,
    item: ExtractedItem,
    changes: dict[str, str | None],
    verifier_type: str,
    verifier: User,
) -> ExtractedItem:
    """Apply a human text correction and re-run matching. Any earlier verification is cleared."""
    diff: dict[str, Any] = {}
    for field, value in changes.items():
        cleaned = (value or "").strip() or None
        current = getattr(item, f"{field}_text")
        if cleaned != current:
            diff[field] = {"from": current, "to": cleaned}
            setattr(item, f"{field}_text", cleaned)
            setattr(item, f"{field}_state", "visible" if cleaned else "unknown")
    if diff:
        attach_candidates(item, load_catalogue(db), lasa_names(db))
        db.add(
            VerificationEvent(
                item_id=item.id,
                verifier_type=verifier_type,
                verifier_user_id=verifier.id,
                action="corrected",
                diff=diff,
            )
        )
        prescription = db.get(Prescription, item.prescription_id)
        assert prescription is not None
        _refresh_status(db, prescription)
    return item


def verify_item(
    db: Session,
    item: ExtractedItem,
    medicine_id: int,
    verifier_type: str,
    verifier: User,
    lasa_acknowledged: bool = False,
    note: str | None = None,
) -> ExtractedItem:
    """Confirm an identity. The medicine must be one of the item's candidates after any correction."""
    candidate = next((c for c in item.candidates if c.medicine_id == medicine_id), None)
    if candidate is None:
        raise ProblemError(
            422,
            "not_a_candidate",
            "This medicine is not a candidate for this item",
            "Correct the text so it can be matched, or mark the item unresolved.",
        )
    if item.requires_lasa_review and not lasa_acknowledged:
        raise ProblemError(
            409,
            "lasa_review_required",
            "Look-alike name check required",
            "A candidate's name looks like another medicine's name. Confirm you compared them.",
        )
    medicine = db.get(Medicine, medicine_id)
    assert medicine is not None
    if strength_conflict(item.strength_text, catalogue_entry(medicine).strengths):
        raise ProblemError(
            409,
            "strength_conflict",
            "The written strength differs from this medicine",
            "Correct the strength if it was misread, or choose another candidate.",
        )
    item.status = ItemStatus.verified.value
    item.verified_medicine_id = medicine_id
    item.verified_by_type = verifier_type
    item.verified_at = datetime.now(UTC)
    db.add(
        VerificationEvent(
            item_id=item.id,
            verifier_type=verifier_type,
            verifier_user_id=verifier.id,
            action="verified",
            diff={"medicine_id": medicine_id, "lasa_acknowledged": lasa_acknowledged},
            note=note,
        )
    )
    prescription = db.get(Prescription, item.prescription_id)
    assert prescription is not None
    _refresh_status(db, prescription)
    return item


def close_item(
    db: Session,
    item: ExtractedItem,
    status: ItemStatus,
    verifier_type: str,
    verifier: User,
    note: str | None = None,
) -> ExtractedItem:
    """Reject an extracted line, or mark it unresolved so the user is sent to their prescriber."""
    item.status = status.value
    item.verified_medicine_id = None
    item.verified_by_type = None
    item.verified_at = None
    db.add(
        VerificationEvent(
            item_id=item.id,
            verifier_type=verifier_type,
            verifier_user_id=verifier.id,
            action=status.value,
            diff={},
            note=note,
        )
    )
    prescription = db.get(Prescription, item.prescription_id)
    assert prescription is not None
    _refresh_status(db, prescription)
    return item


def delete_prescription(
    db: Session, prescription: Prescription, storage: Storage | None = None
) -> None:
    """Hard delete: stored objects first, so a failure leaves a row that can be retried."""
    store = storage or get_storage()
    for key in [prescription.original_key, *(prescription.processed_keys or [])]:
        if key:
            store.delete(key)
    db.delete(prescription)
    db.flush()


def _deleted(result: Any) -> int:
    return int(result.rowcount)


def run_retention(
    db: Session, now: datetime | None = None, storage: Storage | None = None
) -> dict[str, int]:
    """Delete prescriptions past retention, expired guest accounts and expired sessions."""
    from app.models import AuthSession, ShareLink

    moment = now or datetime.now(UTC)
    store = storage or get_storage()
    expired = db.scalars(select(Prescription).where(Prescription.retention_until <= moment)).all()
    for prescription in expired:
        delete_prescription(db, prescription, store)
    guests = db.scalars(
        select(User).where(User.is_guest.is_(True), User.expires_at <= moment)
    ).all()
    for guest in guests:
        owned = db.scalars(select(Prescription).where(Prescription.user_id == guest.id)).all()
        for prescription in owned:
            delete_prescription(db, prescription, store)
        db.delete(guest)
    sessions = _deleted(db.execute(delete(AuthSession).where(AuthSession.expires_at <= moment)))
    links = _deleted(
        db.execute(delete(ShareLink).where(ShareLink.expires_at <= moment - timedelta(days=30)))
    )
    audit(
        db,
        None,
        "retention_run",
        "system",
        prescriptions=len(expired),
        guests=len(guests),
        sessions=sessions,
        share_links=links,
    )
    db.commit()
    return {
        "prescriptions": len(expired),
        "guests": len(guests),
        "sessions": sessions,
        "share_links": links,
    }


__all__ = ["Brand"]
