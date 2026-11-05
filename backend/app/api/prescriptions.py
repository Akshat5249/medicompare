"""Prescription routes: intake, verification, the downstream gate, sharing and the pharmacist portal."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalogue.service import (
    get_medicine,
    lower_cost_options,
    medicine_summary,
    price_comparison,
)
from app.config import get_settings
from app.core import (
    PROBLEM_RESPONSE,
    ProblemError,
    audit,
    get_storage,
    hash_token,
    new_token,
    not_found,
    require_csrf,
    require_role,
    require_user,
    upload_limit,
)
from app.db import get_db
from app.jobs import enqueue_processing
from app.models import (
    ExtractedItem,
    ItemStatus,
    PharmacistProfile,
    Prescription,
    PrescriptionShare,
    Role,
    ShareLink,
    User,
)
from app.prescriptions import imaging, service
from app.prescriptions.confidence import display_level, load_thresholds
from app.safety.emergency import detect_emergency
from app.safety.gate import UnverifiedItemError, require_verified
from app.summaries.service import build_summary, render_pdf

router = APIRouter(prefix="/api/v1", responses=PROBLEM_RESPONSE)
Db = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(require_user)]
Csrf = Depends(require_csrf)
PharmacistUser = Annotated[User, Depends(require_role(Role.pharmacist))]


class ManualItemIn(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    strength: str | None = Field(default=None, max_length=80)
    form: str | None = Field(default=None, max_length=80)
    frequency: str | None = Field(default=None, max_length=80)
    duration: str | None = Field(default=None, max_length=80)


class ManualIn(BaseModel):
    items: list[ManualItemIn] = Field(min_length=1, max_length=30)


class CorrectIn(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    strength: str | None = Field(default=None, max_length=80)
    form: str | None = Field(default=None, max_length=80)
    frequency: str | None = Field(default=None, max_length=80)
    duration: str | None = Field(default=None, max_length=80)


class VerifyIn(BaseModel):
    medicine_id: int
    lasa_acknowledged: bool = False
    note: str | None = Field(default=None, max_length=1000)


class CloseIn(BaseModel):
    note: str | None = Field(default=None, max_length=1000)


class ShareIn(BaseModel):
    pharmacist_id: uuid.UUID


class LinkIn(BaseModel):
    label: str | None = Field(default=None, max_length=120)
    days: int | None = Field(default=None, ge=1, le=30)


def _item_dict(item: ExtractedItem) -> dict[str, Any]:
    thresholds = load_thresholds(engine=get_settings().ocr_engine)
    return {
        "id": str(item.id),
        "position": item.position,
        "page": item.page,
        "source_text": item.source_text,
        "bbox": item.bbox,
        "fields": {
            field: {
                "value": getattr(item, f"{field}_text"),
                "state": getattr(item, f"{field}_state"),
            }
            for field in ("name", "strength", "form", "frequency", "duration")
        },
        "ocr_quality": item.ocr_quality,
        "match_quality": item.match_quality,
        "confidence_level": display_level(item.ocr_quality, item.match_quality, thresholds),
        "status": item.status,
        "requires_lasa_review": item.requires_lasa_review,
        "verified_medicine_id": item.verified_medicine_id,
        "verified_by_type": item.verified_by_type,
        "verified_at": item.verified_at.isoformat() if item.verified_at else None,
        "candidates": [
            {
                "medicine": medicine_summary(candidate.medicine),
                "rank": candidate.rank,
                "score": candidate.score,
                "reasons": candidate.reasons,
                "is_lasa": candidate.is_lasa,
            }
            for candidate in item.candidates
        ],
        "events": [
            {
                "action": event.action,
                "verifier_type": event.verifier_type,
                "diff": event.diff,
                "note": event.note,
                "created_at": event.created_at.isoformat(),
            }
            for event in item.events
        ],
    }


def _prescription_dict(prescription: Prescription) -> dict[str, Any]:
    signal = detect_emergency("overdose") if prescription.emergency_flagged else None
    return {
        "id": str(prescription.id),
        "source_type": prescription.source_type,
        "status": prescription.status,
        "page_count": prescription.page_count,
        "created_at": prescription.created_at.isoformat(),
        "retention_until": prescription.retention_until.isoformat()
        if prescription.retention_until
        else None,
        "redacted_line_count": prescription.redacted_line_count,
        "emergency": (
            {"detected": True, "number": signal.number, "message": signal.message}
            if signal
            else {"detected": False}
        ),
        "items": [_item_dict(item) for item in prescription.items],
        "shares": [
            {"pharmacist_id": str(share.pharmacist_id), "status": share.status, "note": share.note}
            for share in prescription.shares
            if share.revoked_at is None
        ],
    }


def _own(db: Session, user: User, prescription_id: uuid.UUID) -> Prescription:
    """Owners only. Other people's prescriptions look absent, not forbidden."""
    prescription = db.get(Prescription, prescription_id)
    if prescription is None or prescription.user_id != user.id:
        raise not_found("Prescription")
    return prescription


def _own_item(
    db: Session, user: User, prescription_id: uuid.UUID, item_id: uuid.UUID
) -> ExtractedItem:
    _own(db, user, prescription_id)
    item = db.get(ExtractedItem, item_id)
    if item is None or item.prescription_id != prescription_id:
        raise not_found("Item")
    return item


@router.get("/prescriptions/consent-notice", tags=["prescriptions"])
def consent_notice() -> dict[str, Any]:
    settings = get_settings()
    return {
        "version": service.NOTICE_VERSION,
        "what_is_processed": "The image or PDF you upload, and the text read from it.",
        "engine": settings.ocr_engine,
        "engine_location": "On MediCompare's own server. Nothing is sent to a third-party AI service."
        if not settings.llm_extraction_enabled
        else "On MediCompare's server, and filtered text is sent to an external AI model.",
        "storage": "In a private storage bucket. Photo metadata such as GPS location is removed first.",
        "retention_days": settings.retention_days,
        "your_controls": "You can delete an upload, export your data or delete your account at any time.",
    }


@router.post(
    "/prescriptions/upload",
    status_code=202,
    tags=["prescriptions"],
    dependencies=[Csrf, Depends(upload_limit)],
)
def upload(
    db: Db,
    user: CurrentUser,
    file: Annotated[UploadFile, File()],
    consent: Annotated[bool, Form()] = False,
) -> dict[str, Any]:
    if not consent:
        raise ProblemError(
            422, "consent_required", "Please read and accept the notice before uploading"
        )
    limit = get_settings().max_upload_bytes
    data = file.file.read(limit + 1)
    try:
        prescription = service.create_upload(db, user, data)
    except imaging.UploadRejected as exc:
        status = (
            413 if exc.code == "file_too_large" else 415 if exc.code == "unsupported_type" else 422
        )
        raise ProblemError(status, exc.code, exc.message) from exc
    audit(
        db,
        user,
        "prescription_uploaded",
        "prescription",
        prescription.id,
        pages=prescription.page_count,
    )
    db.commit()
    enqueue_processing(prescription.id)
    db.refresh(prescription)
    return _prescription_dict(prescription)


@router.post("/prescriptions/manual", status_code=201, tags=["prescriptions"], dependencies=[Csrf])
def manual(db: Db, user: CurrentUser, body: ManualIn) -> dict[str, Any]:
    prescription = service.create_manual(db, user, [item.model_dump() for item in body.items])
    audit(db, user, "prescription_manual", "prescription", prescription.id, items=len(body.items))
    db.commit()
    db.refresh(prescription)
    return _prescription_dict(prescription)


@router.get("/prescriptions", tags=["prescriptions"])
def history(db: Db, user: CurrentUser) -> dict[str, Any]:
    rows = db.scalars(
        select(Prescription)
        .where(Prescription.user_id == user.id)
        .order_by(Prescription.created_at.desc())
    ).all()
    return {"prescriptions": [_prescription_dict(row) for row in rows]}


@router.get("/prescriptions/{prescription_id}", tags=["prescriptions"])
def status(db: Db, user: CurrentUser, prescription_id: uuid.UUID) -> dict[str, Any]:
    return _prescription_dict(_own(db, user, prescription_id))


def _page_response(prescription: Prescription, page: int) -> Response:
    keys = prescription.processed_keys or []
    if page < 0 or page >= len(keys):
        raise not_found("Page")
    return Response(
        get_storage().get(keys[page]),
        media_type="image/png",
        headers={"Cache-Control": "private, no-store", "Content-Disposition": "inline"},
    )


@router.get("/prescriptions/{prescription_id}/pages/{page}", tags=["prescriptions"])
def page_image(db: Db, user: CurrentUser, prescription_id: uuid.UUID, page: int) -> Response:
    return _page_response(_own(db, user, prescription_id), page)


@router.patch(
    "/prescriptions/{prescription_id}/items/{item_id}", tags=["verification"], dependencies=[Csrf]
)
def correct(
    db: Db, user: CurrentUser, prescription_id: uuid.UUID, item_id: uuid.UUID, body: CorrectIn
) -> dict[str, Any]:
    item = _own_item(db, user, prescription_id, item_id)
    service.correct_item(db, item, body.model_dump(exclude_unset=True), "user", user)
    db.commit()
    db.refresh(item)
    return _item_dict(item)


@router.post(
    "/prescriptions/{prescription_id}/items/{item_id}/verify",
    tags=["verification"],
    dependencies=[Csrf],
)
def verify(
    db: Db, user: CurrentUser, prescription_id: uuid.UUID, item_id: uuid.UUID, body: VerifyIn
) -> dict[str, Any]:
    item = _own_item(db, user, prescription_id, item_id)
    service.verify_item(db, item, body.medicine_id, "user", user, body.lasa_acknowledged, body.note)
    audit(db, user, "item_verified", "extracted_item", item.id, verifier="user")
    db.commit()
    db.refresh(item)
    return _item_dict(item)


@router.post(
    "/prescriptions/{prescription_id}/items/{item_id}/reject",
    tags=["verification"],
    dependencies=[Csrf],
)
def reject(
    db: Db, user: CurrentUser, prescription_id: uuid.UUID, item_id: uuid.UUID, body: CloseIn
) -> dict[str, Any]:
    item = _own_item(db, user, prescription_id, item_id)
    service.close_item(db, item, ItemStatus.rejected, "user", user, body.note)
    db.commit()
    db.refresh(item)
    return _item_dict(item)


@router.post(
    "/prescriptions/{prescription_id}/items/{item_id}/unresolved",
    tags=["verification"],
    dependencies=[Csrf],
)
def unresolved(
    db: Db, user: CurrentUser, prescription_id: uuid.UUID, item_id: uuid.UUID, body: CloseIn
) -> dict[str, Any]:
    item = _own_item(db, user, prescription_id, item_id)
    service.close_item(db, item, ItemStatus.unresolved, "user", user, body.note)
    db.commit()
    db.refresh(item)
    return {
        **_item_dict(item),
        "guidance": "We could not confirm this medicine. Please ask your prescriber or pharmacist.",
    }


def _gated_medicine(db: Session, item: ExtractedItem) -> Any:
    """The downstream gate: only a human-verified identity may reach prices or options."""
    try:
        medicine_id = require_verified(item)
    except UnverifiedItemError as exc:
        raise ProblemError(
            409,
            "item_not_verified",
            "This medicine has not been verified",
            "Confirm the medicine against your prescription first. Prices and options stay hidden until then.",
            item_status=exc.status,
        ) from exc
    medicine = get_medicine(db, medicine_id)
    if medicine is None:
        raise not_found("Medicine")
    return medicine


@router.get("/prescriptions/{prescription_id}/items/{item_id}/prices", tags=["verification"])
def item_prices(
    db: Db, user: CurrentUser, prescription_id: uuid.UUID, item_id: uuid.UUID
) -> dict[str, Any]:
    return price_comparison(_gated_medicine(db, _own_item(db, user, prescription_id, item_id)))


@router.get("/prescriptions/{prescription_id}/items/{item_id}/options", tags=["verification"])
def item_options(
    db: Db, user: CurrentUser, prescription_id: uuid.UUID, item_id: uuid.UUID
) -> dict[str, Any]:
    return lower_cost_options(
        db, _gated_medicine(db, _own_item(db, user, prescription_id, item_id))
    )


@router.delete(
    "/prescriptions/{prescription_id}", status_code=204, tags=["privacy"], dependencies=[Csrf]
)
def delete_upload(db: Db, user: CurrentUser, prescription_id: uuid.UUID) -> None:
    prescription = _own(db, user, prescription_id)
    service.delete_prescription(db, prescription)
    audit(db, user, "prescription_deleted", "prescription", prescription_id)
    db.commit()


@router.get("/prescriptions/{prescription_id}/summary", tags=["summaries"])
def summary(db: Db, user: CurrentUser, prescription_id: uuid.UUID) -> dict[str, Any]:
    return build_summary(db, _own(db, user, prescription_id))


@router.get("/prescriptions/{prescription_id}/summary.pdf", tags=["summaries"])
def summary_pdf(db: Db, user: CurrentUser, prescription_id: uuid.UUID) -> Response:
    pdf = render_pdf(build_summary(db, _own(db, user, prescription_id)))
    return Response(
        pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'attachment; filename="medicompare-summary.pdf"',
            "Cache-Control": "no-store",
        },
    )


@router.post(
    "/prescriptions/{prescription_id}/share-links",
    status_code=201,
    tags=["summaries"],
    dependencies=[Csrf],
)
def create_link(
    db: Db, user: CurrentUser, prescription_id: uuid.UUID, body: LinkIn
) -> dict[str, Any]:
    prescription = _own(db, user, prescription_id)
    if not any(item.status == ItemStatus.verified.value for item in prescription.items):
        raise ProblemError(
            409, "nothing_verified", "Verify at least one medicine before sharing a summary"
        )
    days = body.days or get_settings().share_link_days
    token = new_token()
    link = ShareLink(
        prescription_id=prescription.id,
        token_hash=hash_token(token),
        expires_at=datetime.now(UTC) + timedelta(days=days),
        label=body.label,
    )
    db.add(link)
    audit(db, user, "share_link_created", "share_link", prescription.id, days=days)
    db.commit()
    return {"id": str(link.id), "token": token, "expires_at": link.expires_at.isoformat()}


@router.delete(
    "/prescriptions/{prescription_id}/share-links/{link_id}",
    status_code=204,
    tags=["summaries"],
    dependencies=[Csrf],
)
def revoke_link(db: Db, user: CurrentUser, prescription_id: uuid.UUID, link_id: uuid.UUID) -> None:
    _own(db, user, prescription_id)
    link = db.get(ShareLink, link_id)
    if link is None or link.prescription_id != prescription_id:
        raise not_found("Share link")
    link.revoked_at = datetime.now(UTC)
    db.commit()


# ------------------------------------------------------------------ pharmacist sharing
@router.get("/pharmacists", tags=["pharmacist"])
def approved_pharmacists(db: Db, _: CurrentUser) -> dict[str, Any]:
    profiles = db.scalars(
        select(PharmacistProfile).where(PharmacistProfile.status == "approved")
    ).all()
    return {
        "pharmacists": [
            {
                "id": str(profile.user_id),
                "display_name": profile.user.display_name or "Pharmacist",
                "state_council": profile.state_council,
                "registration_label": "Registration number self-declared, checked manually by admin",
            }
            for profile in profiles
        ]
    }


@router.post(
    "/prescriptions/{prescription_id}/shares",
    status_code=201,
    tags=["pharmacist"],
    dependencies=[Csrf],
)
def share_with_pharmacist(
    db: Db, user: CurrentUser, prescription_id: uuid.UUID, body: ShareIn
) -> dict[str, Any]:
    prescription = _own(db, user, prescription_id)
    profile = db.get(PharmacistProfile, body.pharmacist_id)
    if profile is None or profile.status != "approved":
        raise not_found("Pharmacist")
    existing = db.scalar(
        select(PrescriptionShare).where(
            PrescriptionShare.prescription_id == prescription.id,
            PrescriptionShare.pharmacist_id == body.pharmacist_id,
        )
    )
    if existing:
        existing.revoked_at, existing.status = None, "pending"
    else:
        db.add(PrescriptionShare(prescription_id=prescription.id, pharmacist_id=body.pharmacist_id))
    audit(db, user, "shared_with_pharmacist", "prescription", prescription.id)
    db.commit()
    return {"status": "shared"}


@router.delete(
    "/prescriptions/{prescription_id}/shares/{pharmacist_id}",
    status_code=204,
    tags=["pharmacist"],
    dependencies=[Csrf],
)
def revoke_share(
    db: Db, user: CurrentUser, prescription_id: uuid.UUID, pharmacist_id: uuid.UUID
) -> None:
    _own(db, user, prescription_id)
    share = db.scalar(
        select(PrescriptionShare).where(
            PrescriptionShare.prescription_id == prescription_id,
            PrescriptionShare.pharmacist_id == pharmacist_id,
        )
    )
    if share is None:
        raise not_found("Share")
    share.revoked_at = datetime.now(UTC)
    audit(db, user, "share_revoked", "prescription", prescription_id)
    db.commit()


def _approved(db: Session, user: User) -> None:
    profile = db.get(PharmacistProfile, user.id)
    if profile is None or profile.status != "approved":
        raise ProblemError(
            403, "pharmacist_not_approved", "Your pharmacist account is awaiting admin approval"
        )


def _shared(
    db: Session, user: User, prescription_id: uuid.UUID
) -> tuple[Prescription, PrescriptionShare]:
    """A pharmacist reaches a prescription only through an active share naming them."""
    _approved(db, user)
    share = db.scalar(
        select(PrescriptionShare).where(
            PrescriptionShare.prescription_id == prescription_id,
            PrescriptionShare.pharmacist_id == user.id,
            PrescriptionShare.revoked_at.is_(None),
        )
    )
    prescription = db.get(Prescription, prescription_id)
    if share is None or prescription is None:
        raise not_found("Prescription")
    return prescription, share


def _shared_item(
    db: Session, user: User, prescription_id: uuid.UUID, item_id: uuid.UUID
) -> ExtractedItem:
    _shared(db, user, prescription_id)
    item = db.get(ExtractedItem, item_id)
    if item is None or item.prescription_id != prescription_id:
        raise not_found("Item")
    return item


@router.get("/pharmacist/queue", tags=["pharmacist"])
def queue(db: Db, user: PharmacistUser) -> dict[str, Any]:
    _approved(db, user)
    shares = db.scalars(
        select(PrescriptionShare)
        .where(PrescriptionShare.pharmacist_id == user.id, PrescriptionShare.revoked_at.is_(None))
        .order_by(PrescriptionShare.created_at)
    ).all()
    rows = []
    for share in shares:
        prescription = db.get(Prescription, share.prescription_id)
        if prescription is not None:
            rows.append(
                {
                    "prescription_id": str(prescription.id),
                    "shared_at": share.created_at.isoformat(),
                    "share_status": share.status,
                    "open_items": sum(
                        item.status == "needs_verification" for item in prescription.items
                    ),
                    "total_items": len(prescription.items),
                }
            )
    return {"queue": rows}


@router.get("/pharmacist/prescriptions/{prescription_id}", tags=["pharmacist"])
def pharmacist_view(db: Db, user: PharmacistUser, prescription_id: uuid.UUID) -> dict[str, Any]:
    prescription, _ = _shared(db, user, prescription_id)
    audit(db, user, "pharmacist_viewed", "prescription", prescription_id)
    db.commit()
    return _prescription_dict(prescription)


@router.get("/pharmacist/prescriptions/{prescription_id}/pages/{page}", tags=["pharmacist"])
def pharmacist_page(
    db: Db, user: PharmacistUser, prescription_id: uuid.UUID, page: int
) -> Response:
    prescription, _ = _shared(db, user, prescription_id)
    return _page_response(prescription, page)


@router.patch(
    "/pharmacist/prescriptions/{prescription_id}/items/{item_id}",
    tags=["pharmacist"],
    dependencies=[Csrf],
)
def pharmacist_correct(
    db: Db, user: PharmacistUser, prescription_id: uuid.UUID, item_id: uuid.UUID, body: CorrectIn
) -> dict[str, Any]:
    item = _shared_item(db, user, prescription_id, item_id)
    service.correct_item(db, item, body.model_dump(exclude_unset=True), "pharmacist", user)
    db.commit()
    db.refresh(item)
    return _item_dict(item)


@router.post(
    "/pharmacist/prescriptions/{prescription_id}/items/{item_id}/verify",
    tags=["pharmacist"],
    dependencies=[Csrf],
)
def pharmacist_verify(
    db: Db, user: PharmacistUser, prescription_id: uuid.UUID, item_id: uuid.UUID, body: VerifyIn
) -> dict[str, Any]:
    item = _shared_item(db, user, prescription_id, item_id)
    service.verify_item(
        db, item, body.medicine_id, "pharmacist", user, body.lasa_acknowledged, body.note
    )
    audit(db, user, "item_verified", "extracted_item", item.id, verifier="pharmacist")
    db.commit()
    db.refresh(item)
    return _item_dict(item)


@router.post(
    "/pharmacist/prescriptions/{prescription_id}/items/{item_id}/unresolved",
    tags=["pharmacist"],
    dependencies=[Csrf],
)
def pharmacist_unresolved(
    db: Db, user: PharmacistUser, prescription_id: uuid.UUID, item_id: uuid.UUID, body: CloseIn
) -> dict[str, Any]:
    item = _shared_item(db, user, prescription_id, item_id)
    service.close_item(db, item, ItemStatus.unresolved, "pharmacist", user, body.note)
    db.commit()
    db.refresh(item)
    return _item_dict(item)


class ReviewDoneIn(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


@router.post(
    "/pharmacist/prescriptions/{prescription_id}/complete", tags=["pharmacist"], dependencies=[Csrf]
)
def pharmacist_complete(
    db: Db, user: PharmacistUser, prescription_id: uuid.UUID, body: ReviewDoneIn
) -> dict[str, Any]:
    _, share = _shared(db, user, prescription_id)
    share.status, share.note = "reviewed", body.note
    audit(db, user, "pharmacist_review_completed", "prescription", prescription_id)
    db.commit()
    return {"status": "reviewed"}


__all__ = ["render_pdf", "router"]
