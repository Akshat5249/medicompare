"""Accounts: registration, sessions, guest sessions, saved lists, data export and account deletion."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.catalogue.service import get_medicine, medicine_summary
from app.config import get_settings
from app.core import (
    PROBLEM_RESPONSE,
    SESSION_COOKIE,
    ProblemError,
    audit,
    auth_limit,
    create_session,
    current_session,
    hash_password,
    not_found,
    require_csrf,
    require_user,
    set_session_cookie,
    verify_password,
)
from app.db import get_db
from app.models import (
    AuthSession,
    Consent,
    PharmacistProfile,
    Prescription,
    Role,
    SavedList,
    SavedListItem,
    User,
)
from app.prescriptions.service import delete_prescription

router = APIRouter(prefix="/api/v1", responses=PROBLEM_RESPONSE, tags=["accounts"])
Db = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(require_user)]
Csrf = Depends(require_csrf)
AuthLimited = Depends(auth_limit)
# A precomputed hash lets unknown emails take the same time as wrong passwords.
_DUMMY_HASH = hash_password("timing-equaliser-not-a-real-password")


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=200)
    display_name: str | None = Field(default=None, max_length=120)


class PharmacistRegisterIn(RegisterIn):
    registration_number: str = Field(min_length=3, max_length=64)
    state_council: str = Field(min_length=2, max_length=120)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=200)


def session_payload(user: User, record: AuthSession, db: Session) -> dict[str, Any]:
    profile = db.get(PharmacistProfile, user.id)
    return {
        "user": {
            "id": str(user.id),
            "email": user.email,
            "role": user.role,
            "display_name": user.display_name,
            "is_guest": user.is_guest,
            "pharmacist_status": profile.status if profile else None,
        },
        "csrf_token": record.csrf_token,
    }


def _create_user(db: Session, body: RegisterIn, role: Role = Role.user) -> User:
    user = User(
        email=body.email.lower(),
        password_hash=hash_password(body.password),
        role=role.value,
        display_name=body.display_name,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ProblemError(409, "email_taken", "An account with this email already exists") from exc
    return user


@router.post("/auth/register", status_code=201, dependencies=[AuthLimited])
def register(db: Db, body: RegisterIn, response: Response) -> dict[str, Any]:
    user = _create_user(db, body)
    token, record = create_session(db, user)
    audit(db, user, "account_registered", "user", user.id)
    db.commit()
    set_session_cookie(response, token)
    return session_payload(user, record, db)


@router.post("/auth/register-pharmacist", status_code=201, dependencies=[AuthLimited])
def register_pharmacist(db: Db, body: PharmacistRegisterIn, response: Response) -> dict[str, Any]:
    """The number is self-declared. An admin checks it by hand before approval: none is automated."""
    user = _create_user(db, body)
    db.add(
        PharmacistProfile(
            user_id=user.id,
            registration_number=body.registration_number.strip(),
            state_council=body.state_council.strip(),
            status="pending",
        )
    )
    token, record = create_session(db, user)
    audit(db, user, "pharmacist_registered", "user", user.id)
    db.commit()
    set_session_cookie(response, token)
    return session_payload(user, record, db)


@router.post("/auth/login", dependencies=[AuthLimited])
def login(db: Db, body: LoginIn, response: Response) -> dict[str, Any]:
    settings = get_settings()
    failure = ProblemError(401, "invalid_credentials", "Email or password is incorrect")
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    now = datetime.now(UTC)
    if user is None or user.password_hash is None:
        verify_password(_DUMMY_HASH, body.password)
        raise failure
    if user.locked_until and user.locked_until > now:
        raise ProblemError(429, "account_locked", "Too many failed attempts. Try again later.")
    if not verify_password(user.password_hash, body.password):
        user.failed_logins += 1
        if user.failed_logins >= settings.login_max_failures:
            # Each further failure doubles the lock period, up to one day.
            excess = user.failed_logins - settings.login_max_failures
            minutes = min(settings.login_lock_minutes * (2**excess), 24 * 60)
            user.locked_until = now + timedelta(minutes=minutes)
            audit(db, user, "account_locked", "user", user.id)
        db.commit()
        raise failure
    user.failed_logins, user.locked_until = 0, None
    token, record = create_session(db, user)
    audit(db, user, "login", "user", user.id)
    db.commit()
    set_session_cookie(response, token)
    return session_payload(user, record, db)


@router.post("/auth/guest", status_code=201, dependencies=[AuthLimited])
def guest(db: Db, response: Response) -> dict[str, Any]:
    """A throwaway identity, so prescriptions work without an account. Removed by retention."""
    settings = get_settings()
    user = User(
        is_guest=True,
        role=Role.user.value,
        expires_at=datetime.now(UTC) + timedelta(hours=settings.guest_session_hours),
    )
    db.add(user)
    db.flush()
    token, record = create_session(db, user, settings.guest_session_hours)
    db.commit()
    set_session_cookie(response, token, settings.guest_session_hours)
    return session_payload(user, record, db)


@router.get("/auth/me")
def me(db: Db, session: Annotated[AuthSession | None, Depends(current_session)]) -> dict[str, Any]:
    if session is None:
        return {"user": None, "csrf_token": None}
    return session_payload(session.user, session, db)


@router.post("/auth/logout", status_code=204, dependencies=[Csrf])
def logout(
    db: Db, session: Annotated[AuthSession | None, Depends(current_session)], response: Response
) -> None:
    if session is not None:
        db.delete(session)
        db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")


class ListIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class ListItemIn(BaseModel):
    medicine_id: int


def _own_list(db: Session, user: User, list_id: uuid.UUID) -> SavedList:
    saved = db.get(SavedList, list_id)
    if saved is None or saved.user_id != user.id:
        raise not_found("List")
    return saved


def _list_dict(db: Session, saved: SavedList) -> dict[str, Any]:
    medicines = [get_medicine(db, item.medicine_id) for item in saved.items]
    return {
        "id": str(saved.id),
        "name": saved.name,
        "medicines": [medicine_summary(medicine) for medicine in medicines if medicine],
    }


@router.get("/lists", tags=["lists"])
def lists(db: Db, user: CurrentUser) -> dict[str, Any]:
    rows = db.scalars(
        select(SavedList).where(SavedList.user_id == user.id).order_by(SavedList.created_at)
    ).all()
    return {"lists": [_list_dict(db, row) for row in rows]}


@router.post("/lists", status_code=201, tags=["lists"], dependencies=[Csrf])
def create_list(db: Db, user: CurrentUser, body: ListIn) -> dict[str, Any]:
    if user.is_guest:
        raise ProblemError(403, "account_required", "Create an account to save lists")
    saved = SavedList(user_id=user.id, name=body.name)
    db.add(saved)
    db.commit()
    return _list_dict(db, saved)


@router.post("/lists/{list_id}/items", status_code=201, tags=["lists"], dependencies=[Csrf])
def add_list_item(
    db: Db, user: CurrentUser, list_id: uuid.UUID, body: ListItemIn
) -> dict[str, Any]:
    saved = _own_list(db, user, list_id)
    if get_medicine(db, body.medicine_id) is None:
        raise not_found("Medicine")
    if not any(item.medicine_id == body.medicine_id for item in saved.items):
        saved.items.append(SavedListItem(medicine_id=body.medicine_id))
        db.commit()
    return _list_dict(db, saved)


@router.delete("/lists/{list_id}", status_code=204, tags=["lists"], dependencies=[Csrf])
def delete_list(db: Db, user: CurrentUser, list_id: uuid.UUID) -> None:
    db.delete(_own_list(db, user, list_id))
    db.commit()


@router.get("/me/export", tags=["privacy"])
def export_data(db: Db, user: CurrentUser) -> dict[str, Any]:
    prescriptions = db.scalars(select(Prescription).where(Prescription.user_id == user.id)).all()
    consents = db.scalars(select(Consent).where(Consent.user_id == user.id)).all()
    saved = db.scalars(select(SavedList).where(SavedList.user_id == user.id)).all()
    audit(db, user, "data_exported", "user", user.id)
    db.commit()
    return {
        "exported_at": datetime.now(UTC).isoformat(),
        "account": {
            "id": str(user.id),
            "email": user.email,
            "display_name": user.display_name,
            "role": user.role,
            "created_at": user.created_at.isoformat(),
        },
        "consents": [
            {
                "purpose": consent.purpose,
                "notice_version": consent.notice_version,
                "ocr_engine": consent.ocr_engine,
                "created_at": consent.created_at.isoformat(),
            }
            for consent in consents
        ],
        "prescriptions": [
            {
                "id": str(prescription.id),
                "source_type": prescription.source_type,
                "status": prescription.status,
                "created_at": prescription.created_at.isoformat(),
                "retention_until": prescription.retention_until.isoformat()
                if prescription.retention_until
                else None,
                "items": [
                    {
                        "source_text": item.source_text,
                        "name_text": item.name_text,
                        "strength_text": item.strength_text,
                        "form_text": item.form_text,
                        "frequency_text": item.frequency_text,
                        "duration_text": item.duration_text,
                        "status": item.status,
                        "verified_medicine_id": item.verified_medicine_id,
                        "verified_by_type": item.verified_by_type,
                    }
                    for item in prescription.items
                ],
            }
            for prescription in prescriptions
        ],
        "saved_lists": [_list_dict(db, row) for row in saved],
    }


@router.delete("/me", status_code=204, tags=["privacy"], dependencies=[Csrf])
def delete_account(db: Db, user: CurrentUser, response: Response) -> None:
    """Hard delete: objects, prescription rows, and the account. Audit rows lose the actor link."""
    prescriptions = db.scalars(select(Prescription).where(Prescription.user_id == user.id)).all()
    for prescription in prescriptions:
        delete_prescription(db, prescription)
    audit(db, None, "account_deleted", "user", None, prescriptions=len(prescriptions))
    db.delete(user)
    db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
