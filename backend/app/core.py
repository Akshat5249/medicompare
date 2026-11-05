"""Cross-cutting API concerns: problem details, auth, CSRF, rate limits, audit and storage."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any

import boto3
import redis
import structlog
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError
from fastapi import Cookie, Depends, Header, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import AuditEvent, AuthSession, Role, User

log = structlog.get_logger()
SESSION_COOKIE = "mc_session"
_hasher = PasswordHasher()


# ------------------------------------------------------------------ problem details (RFC 9457)
class ProblemError(Exception):
    def __init__(self, status: int, code: str, title: str, detail: str = "", **extra: Any) -> None:
        super().__init__(title)
        self.status, self.code, self.title, self.detail, self.extra = (
            status,
            code,
            title,
            detail,
            extra,
        )


def problem_response(
    status: int, code: str, title: str, detail: str = "", **extra: Any
) -> JSONResponse:
    body = {
        "type": f"https://medicompare.invalid/problems/{code}",
        "title": title,
        "status": status,
        "code": code,
    }
    if detail:
        body["detail"] = detail
    body.update(extra)
    return JSONResponse(body, status_code=status, media_type="application/problem+json")


def not_found(what: str = "Resource") -> ProblemError:
    return ProblemError(404, "not_found", f"{what} not found")


PROBLEM_RESPONSE: dict[int | str, dict[str, Any]] = {
    "4XX": {
        "description": "Problem details (RFC 9457)",
        "content": {
            "application/problem+json": {
                "example": {
                    "type": "https://medicompare.invalid/problems/not_found",
                    "title": "Medicine not found",
                    "status": 404,
                    "code": "not_found",
                }
            }
        },
    }
}


# ------------------------------------------------------------------ passwords and tokens
def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(stored_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(stored_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def hash_token(token: str) -> str:
    """Keyed hash so a database leak does not expose usable session or share tokens."""
    key = get_settings().secret_key.encode()
    return hmac.new(key, token.encode(), hashlib.sha256).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(32)


def create_session(db: Session, user: User, hours: int | None = None) -> tuple[str, AuthSession]:
    token = new_token()
    record = AuthSession(
        user_id=user.id,
        token_hash=hash_token(token),
        csrf_token=secrets.token_urlsafe(24),
        expires_at=datetime.now(UTC) + timedelta(hours=hours or get_settings().session_hours),
    )
    db.add(record)
    db.flush()
    return token, record


def set_session_cookie(response: Any, token: str, hours: int | None = None) -> None:
    settings = get_settings()
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=(hours or settings.session_hours) * 3600,
        path="/",
    )


def current_session(
    db: Session = Depends(get_db), mc_session: str | None = Cookie(default=None)
) -> AuthSession | None:
    if not mc_session:
        return None
    record = db.scalar(select(AuthSession).where(AuthSession.token_hash == hash_token(mc_session)))
    if record is None or record.expires_at <= datetime.now(UTC):
        return None
    return record


def require_user(session: AuthSession | None = Depends(current_session)) -> User:
    if session is None:
        raise ProblemError(401, "unauthenticated", "Sign in required")
    return session.user


def require_csrf(
    session: AuthSession | None = Depends(current_session),
    x_csrf_token: str | None = Header(default=None),
) -> None:
    """Every state-changing request from a signed-in browser must echo its session's CSRF token."""
    if session is None:
        raise ProblemError(401, "unauthenticated", "Sign in required")
    if not x_csrf_token or not hmac.compare_digest(x_csrf_token, session.csrf_token):
        raise ProblemError(403, "csrf_failed", "CSRF token missing or invalid")


def require_role(*roles: Role) -> Callable[[User], User]:
    allowed = {role.value for role in roles}

    def check(user: User = Depends(require_user)) -> User:
        if user.role not in allowed:
            raise ProblemError(403, "forbidden", "You do not have access to this resource")
        return user

    return check


# ------------------------------------------------------------------ rate limiting
@lru_cache
def redis_client() -> redis.Redis[bytes]:
    return redis.Redis.from_url(
        get_settings().redis_url, socket_timeout=1, socket_connect_timeout=1
    )


def rate_limit(
    bucket: str, limit_attr: str, window_seconds: int = 60, fail_closed: bool = False
) -> Callable[[Request], None]:
    """Fixed-window limit per client address. Auth and upload fail closed if Redis is unavailable."""

    def check(request: Request) -> None:
        settings = get_settings()
        if not settings.rate_limit_enabled:
            return
        limit = int(getattr(settings, limit_attr))
        client = request.client.host if request.client else "unknown"
        key = f"rl:{bucket}:{client}:{int(time.time() // window_seconds)}"
        try:
            client_redis = redis_client()
            count = client_redis.incr(key)
            if count == 1:
                client_redis.expire(key, window_seconds + 1)
        except redis.RedisError as exc:
            log.warning("rate_limit_unavailable", bucket=bucket)
            if fail_closed:
                raise ProblemError(
                    503, "rate_limit_unavailable", "Please try again shortly"
                ) from exc
            return
        if int(count) > limit:
            raise ProblemError(
                429, "rate_limited", "Too many requests", retry_after_seconds=window_seconds
            )

    return check


public_limit = rate_limit("public", "rate_limit_public_per_minute")
auth_limit = rate_limit("auth", "rate_limit_auth_per_minute", fail_closed=True)
upload_limit = rate_limit(
    "upload", "rate_limit_upload_per_hour", window_seconds=3600, fail_closed=True
)


# ------------------------------------------------------------------ audit
def audit(
    db: Session,
    actor: User | None,
    action: str,
    entity_type: str,
    entity_id: Any = None,
    **meta: Any,
) -> None:
    """Record an action. Callers pass identifiers and counts, never prescription text."""
    db.add(
        AuditEvent(
            actor_id=actor.id if actor else None,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            meta=meta,
        )
    )


# ------------------------------------------------------------------ object storage
class Storage:
    """Private S3-compatible storage. Objects reach browsers only through authorised API routes."""

    def __init__(self) -> None:
        settings = get_settings()
        self.bucket = settings.s3_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
            config=BotoConfig(signature_version="s3v4", retries={"max_attempts": 3}),
        )

    def ensure_bucket(self) -> None:
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError:
            self.client.create_bucket(Bucket=self.bucket)

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)

    def get(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError:
            return False


@lru_cache
def get_storage() -> Storage:
    return Storage()
