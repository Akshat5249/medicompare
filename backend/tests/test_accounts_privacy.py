"""Accounts, authorization, CSRF, rate limits, consent, deletion and retention."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.config import Settings, get_settings
from app.core import get_storage
from app.models import (
    AuditEvent,
    AuthSession,
    CandidateMatch,
    ExtractedItem,
    Prescription,
    User,
    VerificationEvent,
)
from app.prescriptions.service import run_retention
from tests.conftest import PASSWORD, Api, manual_item, prescription_png, verify_first


def upload(api: Api, content: bytes, consent: str = "true"):
    return api.post(
        "/api/v1/prescriptions/upload",
        files={"file": ("rx.png", content, "image/png")},
        data={"consent": consent},
    )


def test_search_needs_no_account(anon):
    assert anon.get("/api/v1/search", params={"q": "metformin"}).status_code == 200


def test_register_login_logout_cycle():
    api = Api()
    email = f"cycle-{uuid.uuid4().hex[:6]}@example.com"
    assert api.register(email).status_code == 201
    assert api.user["role"] == "user"
    assert api.get("/api/v1/auth/me").json()["user"]["email"] == email
    assert api.post("/api/v1/auth/logout").status_code == 204
    assert api.get("/api/v1/auth/me").json()["user"] is None
    fresh = Api()
    assert fresh.login(email).status_code == 200


def test_cookie_flags():
    api = Api()
    response = api.register()
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie


def test_duplicate_email_and_weak_password_are_rejected(user):
    api = Api()
    assert api.register(user.user["email"]).status_code == 409
    assert Api().register(password="short").status_code == 422


def test_password_stored_as_argon2id(user, db):
    stored = db.scalar(select(User.password_hash).where(User.email == user.user["email"]))
    assert stored.startswith("$argon2id$")


def test_login_failure_is_generic_and_locks_with_backoff(user, db):
    email = user.user["email"]
    unknown = Api().client.post(
        "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "x" * 12}
    )
    wrong = Api().client.post("/api/v1/auth/login", json={"email": email, "password": "x" * 12})
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["title"] == wrong.json()["title"]
    for _ in range(get_settings().login_max_failures - 1):
        Api().client.post("/api/v1/auth/login", json={"email": email, "password": "x" * 12})
    locked = Api().client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert locked.status_code == 429 and locked.json()["code"] == "account_locked"
    account = db.scalar(select(User).where(User.email == email))
    assert account.locked_until > datetime.now(UTC)
    account.locked_until = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    assert Api().login(email).status_code == 200


def test_csrf_is_required_for_state_changes(user):
    no_header = user.client.post(
        "/api/v1/prescriptions/manual", json={"items": [{"name": "Metformin"}]}
    )
    assert no_header.status_code == 403 and no_header.json()["code"] == "csrf_failed"
    wrong = user.client.post(
        "/api/v1/prescriptions/manual",
        json={"items": [{"name": "Metformin"}]},
        headers={"X-CSRF-Token": "wrong"},
    )
    assert wrong.status_code == 403


def test_cross_origin_state_change_is_rejected(user):
    response = user.client.post(
        "/api/v1/prescriptions/manual",
        json={"items": [{"name": "Metformin"}]},
        headers={"X-CSRF-Token": user.csrf, "Origin": "https://evil.example"},
    )
    assert response.status_code == 403 and response.json()["code"] == "bad_origin"


def test_anonymous_cannot_use_private_routes(anon):
    assert anon.get("/api/v1/prescriptions").status_code == 401
    assert (
        anon.client.post(
            "/api/v1/prescriptions/manual", json={"items": [{"name": "x"}]}
        ).status_code
        == 401
    )
    assert anon.get("/api/v1/admin/audit").status_code == 401
    assert anon.get("/api/v1/pharmacist/queue").status_code == 401
    assert anon.get("/api/v1/me/export").status_code == 401


def test_roles_are_enforced(user, pharmacist, admin):
    assert user.get("/api/v1/admin/sources").status_code == 403
    assert pharmacist.get("/api/v1/admin/sources").status_code == 403
    assert user.get("/api/v1/pharmacist/queue").status_code == 403
    assert admin.get("/api/v1/pharmacist/queue").status_code == 403
    assert admin.get("/api/v1/admin/sources").status_code == 200


def test_guest_can_use_prescriptions_but_not_lists():
    api = Api()
    assert api.guest().status_code == 201
    assert api.user["is_guest"] is True and api.user["email"] is None
    assert manual_item(api, "Metformin", "500 mg")["items"]
    assert api.post("/api/v1/lists", json={"name": "x"}).status_code == 403


def test_saved_lists_and_ownership(user, other_user, db):
    created = user.post("/api/v1/lists", json={"name": "Family"}).json()
    from tests.conftest import medicine_id

    medicine = medicine_id(db, "DemoCetirAlpha (Cetirizine 10 mg)")
    added = user.post(f"/api/v1/lists/{created['id']}/items", json={"medicine_id": medicine})
    assert added.json()["medicines"][0]["id"] == medicine
    assert (
        user.post(
            f"/api/v1/lists/{created['id']}/items", json={"medicine_id": medicine}
        ).status_code
        == 201
    )
    assert (
        user.post(
            f"/api/v1/lists/{created['id']}/items", json={"medicine_id": 99999999}
        ).status_code
        == 404
    )
    assert len(user.get("/api/v1/lists").json()["lists"]) == 1
    assert (
        other_user.post(
            f"/api/v1/lists/{created['id']}/items", json={"medicine_id": medicine}
        ).status_code
        == 404
    )
    assert other_user.delete(f"/api/v1/lists/{created['id']}").status_code == 404
    assert user.delete(f"/api/v1/lists/{created['id']}").status_code == 204


def test_upload_requires_consent_and_records_it(user, db):
    assert (
        upload(user, prescription_png(["Tab Cetirizine 10 mg OD"]), consent="false").status_code
        == 422
    )
    response = upload(user, prescription_png(["Tab Cetirizine 10 mg OD"]))
    assert response.status_code == 202
    exported = user.get("/api/v1/me/export").json()
    assert exported["consents"][0]["purpose"] == "prescription_upload"
    assert exported["consents"][0]["notice_version"]


def test_consent_notice_says_what_where_and_how_long(anon):
    notice = anon.get("/api/v1/prescriptions/consent-notice").json()
    for key in ("what_is_processed", "engine", "engine_location", "retention_days"):
        assert notice[key]
    assert notice["retention_days"] == 7


def test_export_returns_my_data_only(user, other_user):
    manual_item(other_user, "Cetirizine", "10 mg")
    manual_item(user, "Metformin", "500 mg")
    body = user.get("/api/v1/me/export").json()
    assert body["account"]["email"] == user.user["email"]
    assert [p["items"][0]["name_text"] for p in body["prescriptions"]] == ["Metformin"]


def test_delete_upload_removes_rows_and_objects(user, db):
    body = upload(user, prescription_png(["Tab Cetirizine 10 mg OD"])).json()
    prescription = db.get(Prescription, uuid.UUID(body["id"]))
    keys = [prescription.original_key, *prescription.processed_keys]
    assert keys and all(get_storage().exists(key) for key in keys)
    item_ids = [item.id for item in prescription.items]
    assert item_ids
    db.rollback()
    assert user.delete(f"/api/v1/prescriptions/{body['id']}").status_code == 204
    db.expire_all()
    assert db.get(Prescription, uuid.UUID(body["id"])) is None
    assert not any(get_storage().exists(key) for key in keys)
    assert (
        db.scalar(
            select(func.count()).select_from(ExtractedItem).where(ExtractedItem.id.in_(item_ids))
        )
        == 0
    )
    assert (
        db.scalar(
            select(func.count())
            .select_from(CandidateMatch)
            .where(CandidateMatch.item_id.in_(item_ids))
        )
        == 0
    )
    assert (
        db.scalar(
            select(func.count())
            .select_from(VerificationEvent)
            .where(VerificationEvent.item_id.in_(item_ids))
        )
        == 0
    )


def test_delete_account_removes_everything(user, db):
    body = upload(user, prescription_png(["Tab Cetirizine 10 mg OD"])).json()
    prescription = db.get(Prescription, uuid.UUID(body["id"]))
    keys = [prescription.original_key, *prescription.processed_keys]
    user_id = prescription.user_id
    db.rollback()
    assert user.delete("/api/v1/me").status_code == 204
    db.expire_all()
    assert db.get(User, user_id) is None
    assert db.get(Prescription, uuid.UUID(body["id"])) is None
    assert (
        db.scalar(
            select(func.count()).select_from(AuthSession).where(AuthSession.user_id == user_id)
        )
        == 0
    )
    assert not any(get_storage().exists(key) for key in keys)
    assert (
        db.scalar(
            select(func.count()).select_from(AuditEvent).where(AuditEvent.actor_id == user_id)
        )
        == 0
    )
    assert user.get("/api/v1/prescriptions").status_code == 401


def test_retention_job_deletes_expired_only(user, db):
    expired = upload(user, prescription_png(["Tab Cetirizine 10 mg OD"])).json()
    kept = manual_item(user, "Metformin", "500 mg")
    record = db.get(Prescription, uuid.UUID(expired["id"]))
    keys = [record.original_key, *record.processed_keys]
    record.retention_until = datetime.now(UTC) - timedelta(minutes=1)
    db.commit()
    result = run_retention(db)
    assert result["prescriptions"] == 1
    db.expire_all()
    assert db.get(Prescription, uuid.UUID(expired["id"])) is None
    assert db.get(Prescription, uuid.UUID(kept["id"])) is not None
    assert not any(get_storage().exists(key) for key in keys)


def test_default_retention_period_is_applied(user):
    body = manual_item(user, "Metformin")
    until = datetime.fromisoformat(body["retention_until"])
    assert timedelta(days=6, hours=23) < until - datetime.now(UTC) <= timedelta(days=7)


def test_retention_removes_expired_guests_and_sessions(db):
    api = Api()
    api.guest()
    guest_id = uuid.UUID(api.user["id"])
    manual_item(api, "Metformin")
    account = db.get(User, guest_id)
    account.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db.commit()
    assert run_retention(db)["guests"] == 1
    db.expire_all()
    assert db.get(User, guest_id) is None


def test_audit_log_never_contains_prescription_text(user, admin, db):
    prescription = manual_item(user, "Metformin Uniquetoken", "500 mg")
    prescription = manual_item(user, "Metformin", "500 mg", "Tab")
    verify_first(user, prescription)
    events = admin.get("/api/v1/admin/audit").text
    assert "Uniquetoken" not in events
    assert "Metformin" not in events
    assert "prescription_manual" in events


def test_validation_errors_do_not_echo_input(user):
    response = user.post(
        "/api/v1/prescriptions/manual", json={"items": [{"name": "SecretName" * 40}]}
    )
    assert response.status_code == 422
    assert "SecretName" not in response.text


def test_rate_limit_blocks_after_limit(monkeypatch, anon):
    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_public_per_minute", 3)
    from app.core import redis_client

    redis_client().flushdb()
    codes = [anon.get("/api/v1/search", params={"q": "metformin"}).status_code for _ in range(5)]
    assert codes[:3] == [200, 200, 200]
    assert codes[-1] == 429


def test_rate_limit_fails_open_for_public_and_closed_for_auth(monkeypatch, anon):
    import redis

    from app import core

    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limit_enabled", True)

    class Broken:
        def incr(self, _):
            raise redis.RedisError("down")

    monkeypatch.setattr(core, "redis_client", lambda: Broken())
    assert anon.get("/api/v1/search", params={"q": "metformin"}).status_code == 200
    response = anon.client.post(
        "/api/v1/auth/login", json={"email": "a@example.com", "password": "x" * 12}
    )
    assert response.status_code == 503


def test_production_settings_refuse_unsafe_defaults():
    with pytest.raises(ValueError):
        Settings(app_env="production", cookie_secure=True)
    with pytest.raises(ValueError):
        Settings(app_env="production", secret_key="x" * 40, cookie_secure=False)
    assert Settings(app_env="production", secret_key="x" * 40, cookie_secure=True)


def test_demo_account_addresses_pass_login_validation():
    from pydantic import EmailStr, TypeAdapter

    from app.cli import DEMO_USERS

    for email, _, _ in DEMO_USERS:
        assert TypeAdapter(EmailStr).validate_python(email) == email
