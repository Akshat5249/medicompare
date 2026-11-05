"""Public routes: health, search, medicine detail, prices, options, Jan Aushadhi, summaries by link."""

from __future__ import annotations

import math
import re
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from app.catalogue import service as catalogue
from app.core import (
    PROBLEM_RESPONSE,
    ProblemError,
    get_storage,
    hash_token,
    not_found,
    public_limit,
    redis_client,
)
from app.db import get_db
from app.models import JanAushadhiKendra, JanAushadhiProduct, Medicine, Prescription, ShareLink
from app.safety.emergency import detect_emergency
from app.summaries.service import build_summary, render_pdf

router = APIRouter(prefix="/api/v1", responses=PROBLEM_RESPONSE)
Db = Annotated[Session, Depends(get_db)]
Limited = Depends(public_limit)


class EmergencyOut(BaseModel):
    detected: bool
    number: str
    message: str


class MedicineSummary(BaseModel):
    id: int
    display_name: str
    generic_name: str
    brand: str | None
    dosage_form: str
    release_type: str
    route: str
    is_demo: bool


class SearchResult(BaseModel):
    medicine: MedicineSummary
    match_type: str
    reason: str


class SearchResponse(BaseModel):
    query: str
    emergency: EmergencyOut
    exact_matches: list[SearchResult]
    possible_matches: list[SearchResult]

    model_config = {
        "json_schema_extra": {
            "example": {
                "query": "metformn",
                "emergency": {"detected": False, "number": "112", "message": "..."},
                "exact_matches": [],
                "possible_matches": [
                    {
                        "medicine": {
                            "id": 1,
                            "display_name": "Metformin 500mg Tablet",
                            "generic_name": "Metformin",
                            "brand": None,
                            "dosage_form": "Tablet",
                            "release_type": "Conventional (no release modifier stated)",
                            "route": "Oral",
                            "is_demo": False,
                        },
                        "match_type": "possible",
                        "reason": "Similar spelling to “metformin”. A similar name does not mean the same medicine.",
                    }
                ],
            }
        }
    }


def _emergency(text_value: str) -> dict[str, Any]:
    signal = detect_emergency(text_value)
    return {"detected": signal.detected, "number": signal.number, "message": signal.message}


@router.get("/health/live", tags=["health"])
def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready", tags=["health"])
def ready(db: Db) -> dict[str, str]:
    db.execute(text("SELECT 1"))
    redis_client().ping()
    get_storage().ensure_bucket()
    return {"status": "ready"}


@router.get("/meta", tags=["health"])
def meta(db: Db) -> dict[str, bool]:
    """Lets the UI explain what kind of data it is showing."""
    demo = (
        db.scalar(select(func.count()).select_from(Medicine).where(Medicine.is_demo.is_(True))) or 0
    )
    return {"demo_data_loaded": demo > 0}


@router.get("/search", response_model=SearchResponse, tags=["catalogue"], dependencies=[Limited])
def search(
    db: Db,
    q: Annotated[
        str, Query(min_length=2, max_length=120, description="Brand, generic or ingredient")
    ],
    limit: Annotated[int, Query(ge=1, le=50)] = 30,
) -> dict[str, Any]:
    emergency = _emergency(q)
    hits = [] if emergency["detected"] else catalogue.search(db, q, limit)
    results = [
        {
            "medicine": catalogue.medicine_summary(h.medicine),
            "match_type": h.match_type,
            "reason": h.reason,
        }
        for h in hits
    ]
    return {
        "query": q,
        "emergency": emergency,
        "exact_matches": [r for r in results if r["match_type"] == "exact"],
        "possible_matches": [r for r in results if r["match_type"] == "possible"],
    }


def _medicine_or_404(db: Session, medicine_id: int) -> Any:
    medicine = catalogue.get_medicine(db, medicine_id)
    if medicine is None:
        raise not_found("Medicine")
    return medicine


@router.get("/medicines/{medicine_id}", tags=["catalogue"], dependencies=[Limited])
def medicine_detail(db: Db, medicine_id: int) -> dict[str, Any]:
    return catalogue.medicine_detail(_medicine_or_404(db, medicine_id))


@router.get("/medicines/{medicine_id}/prices", tags=["prices"], dependencies=[Limited])
def medicine_prices(db: Db, medicine_id: int) -> dict[str, Any]:
    return catalogue.price_comparison(_medicine_or_404(db, medicine_id))


@router.get("/medicines/{medicine_id}/options", tags=["prices"], dependencies=[Limited])
def medicine_options(db: Db, medicine_id: int) -> dict[str, Any]:
    return catalogue.lower_cost_options(db, _medicine_or_404(db, medicine_id))


class SafetyCheckIn(BaseModel):
    text: str = Field(max_length=2000)


@router.post("/safety/check", response_model=EmergencyOut, tags=["safety"], dependencies=[Limited])
def safety_check(body: SafetyCheckIn) -> dict[str, Any]:
    return _emergency(body.text)


@router.get("/jan-aushadhi/products", tags=["jan-aushadhi"], dependencies=[Limited])
def ja_products(
    db: Db,
    q: Annotated[str | None, Query(max_length=120)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> dict[str, Any]:
    statement = select(JanAushadhiProduct)
    if q and len(q.strip()) >= 2:
        term = q.strip().lower()
        statement = statement.where(
            or_(
                func.word_similarity(term, func.lower(JanAushadhiProduct.generic_name)) >= 0.35,
                JanAushadhiProduct.drug_code.ilike(f"%{term}%"),
            )
        ).order_by(func.word_similarity(term, func.lower(JanAushadhiProduct.generic_name)).desc())
    else:
        statement = statement.order_by(JanAushadhiProduct.generic_name)
    products = db.scalars(statement.limit(limit)).all()
    return {
        "products": [catalogue.ja_product_dict(product) for product in products],
        "notice": "Catalogue listing only. Check with the Kendra before you travel.",
    }


def _distance_km(lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
    phi_a, phi_b = math.radians(lat_a), math.radians(lat_b)
    d_phi, d_lambda = phi_b - phi_a, math.radians(lon_b - lon_a)
    value = (
        math.sin(d_phi / 2) ** 2 + math.cos(phi_a) * math.cos(phi_b) * math.sin(d_lambda / 2) ** 2
    )
    return 6371 * 2 * math.asin(math.sqrt(value))


@router.get("/jan-aushadhi/kendras", tags=["jan-aushadhi"], dependencies=[Limited])
def ja_kendras(
    db: Db,
    pin: Annotated[str | None, Query(pattern=r"^[1-9]\d{5}$")] = None,
    area: Annotated[str | None, Query(min_length=2, max_length=80)] = None,
    lat: Annotated[float | None, Query(ge=-90, le=90)] = None,
    lon: Annotated[float | None, Query(ge=-180, le=180)] = None,
) -> dict[str, Any]:
    """Coordinates are used for this one calculation only. They are not stored or logged."""
    statement = select(JanAushadhiKendra)
    if pin:
        # Same PIN first, then the same three-digit sorting district.
        statement = statement.where(JanAushadhiKendra.pin_code.like(f"{pin[:3]}%"))
    elif area:
        pattern = f"%{area.strip()}%"
        statement = statement.where(
            or_(JanAushadhiKendra.district.ilike(pattern), JanAushadhiKendra.state.ilike(pattern))
        )
    elif lat is None or lon is None:
        raise ProblemError(422, "location_required", "Provide a PIN code, an area or a location")
    kendras = db.scalars(statement.limit(500)).all()
    rows: list[dict[str, Any]] = []
    for kendra in kendras:
        row = catalogue.kendra_dict(kendra)
        if (
            lat is not None
            and lon is not None
            and kendra.latitude is not None
            and kendra.longitude is not None
        ):
            row["distance_km"] = round(_distance_km(lat, lon, kendra.latitude, kendra.longitude), 1)
        rows.append(row)
    if pin:
        rows.sort(key=lambda r: (r["pin_code"] != pin, r["pin_code"]))
    elif lat is not None and lon is not None:
        rows.sort(key=lambda r: r.get("distance_km", math.inf))
    return {
        "kendras": rows[:50],
        "notice": "This directory does not show what a Kendra has. Contact the Kendra before you travel.",
    }


def _active_link(db: Session, token: str) -> ShareLink:
    if not re.fullmatch(r"[A-Za-z0-9_-]{20,100}", token):
        raise not_found("Share link")
    link = db.scalar(select(ShareLink).where(ShareLink.token_hash == hash_token(token)))
    if link is None:
        raise not_found("Share link")
    if link.revoked_at is not None or link.expires_at <= datetime.now(UTC):
        raise ProblemError(410, "link_expired", "This share link has expired")
    return link


@router.get("/shared/{token}", tags=["summaries"], dependencies=[Limited])
def shared_summary(db: Db, token: str, response: Response) -> dict[str, Any]:
    link = _active_link(db, token)
    prescription = db.get(Prescription, link.prescription_id)
    if prescription is None:
        raise ProblemError(410, "link_expired", "This share link has expired")
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Robots-Tag"] = "noindex"
    return build_summary(db, prescription, link.label)


@router.get("/shared/{token}/pdf", tags=["summaries"], dependencies=[Limited])
def shared_summary_pdf(db: Db, token: str) -> Response:
    link = _active_link(db, token)
    prescription = db.get(Prescription, link.prescription_id)
    if prescription is None:
        raise ProblemError(410, "link_expired", "This share link has expired")
    pdf = render_pdf(build_summary(db, prescription, link.label))
    return Response(
        pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'attachment; filename="medicompare-summary.pdf"',
            "Cache-Control": "no-store",
        },
    )
