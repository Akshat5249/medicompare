"""Integration fixtures: real PostgreSQL, Redis and MinIO from Docker Compose."""

from __future__ import annotations

import io
import os
import uuid
from collections.abc import Iterator
from pathlib import Path

os.environ.setdefault(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://medicompare:devpassword@localhost:5433/medicompare_test",
)
os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
os.environ["S3_BUCKET"] = "medicompare-test"
os.environ["JOBS_SYNCHRONOUS"] = "true"
os.environ["RATE_LIMIT_ENABLED"] = "false"
os.environ["APP_ENV"] = "test"
os.environ.setdefault("OCR_ENGINE", "rapidocr")
os.environ["DATA_DIR"] = str(Path(__file__).resolve().parents[2] / "data")

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core import get_storage, hash_password
from app.db import get_engine, session_factory
from app.imports.seed import seed
from app.main import app
from app.models import Medicine, PharmacistProfile, Role, User

# Deleted in dependency order. TRUNCATE ... CASCADE would follow import_batches.created_by and
# wipe the seeded catalogue.
USER_TABLES = (
    "audit_events",
    "share_links",
    "prescription_shares",
    "verification_events",
    "candidate_matches",
    "extracted_items",
    "processing_jobs",
    "prescriptions",
    "consents",
    "saved_list_items",
    "saved_lists",
    "pharmacist_profiles",
    "auth_sessions",
)
PASSWORD = "correct-horse-battery"


@pytest.fixture(scope="session", autouse=True)
def database() -> Iterator[None]:
    backend = Path(__file__).resolve().parents[1]
    engine = get_engine()
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "migrations"))
    command.upgrade(config, "head")
    get_storage().ensure_bucket()
    with session_factory()() as session:
        seed(session)
    yield


@pytest.fixture(autouse=True)
def clean_user_tables() -> Iterator[None]:
    yield
    with get_engine().begin() as connection:
        for table in USER_TABLES:
            connection.execute(text(f"DELETE FROM {table}"))
        connection.execute(text("UPDATE import_batches SET created_by = NULL"))
        connection.execute(text("DELETE FROM users"))


@pytest.fixture
def db() -> Iterator[Session]:
    with session_factory()() as session:
        yield session


class Api:
    """A test browser: keeps cookies and sends the session's CSRF token on state changes."""

    def __init__(self) -> None:
        self.client = TestClient(app)
        self.csrf: str | None = None
        self.user: dict | None = None

    def _store(self, response):
        if response.status_code < 300:
            body = response.json()
            self.csrf, self.user = body["csrf_token"], body["user"]
        return response

    def register(self, email: str | None = None, password: str = PASSWORD):
        email = email or f"user-{uuid.uuid4().hex[:8]}@example.com"
        return self._store(
            self.client.post("/api/v1/auth/register", json={"email": email, "password": password})
        )

    def login(self, email: str, password: str = PASSWORD):
        return self._store(
            self.client.post("/api/v1/auth/login", json={"email": email, "password": password})
        )

    def guest(self):
        return self._store(self.client.post("/api/v1/auth/guest"))

    def _headers(self) -> dict[str, str]:
        return {"X-CSRF-Token": self.csrf} if self.csrf else {}

    def get(self, path: str, **kwargs):
        return self.client.get(path, **kwargs)

    def post(self, path: str, **kwargs):
        return self.client.post(path, headers=self._headers(), **kwargs)

    def patch(self, path: str, **kwargs):
        return self.client.patch(path, headers=self._headers(), **kwargs)

    def put(self, path: str, **kwargs):
        return self.client.put(path, headers=self._headers(), **kwargs)

    def delete(self, path: str, **kwargs):
        return self.client.delete(path, headers=self._headers(), **kwargs)


@pytest.fixture
def anon() -> Api:
    return Api()


@pytest.fixture
def user() -> Api:
    api = Api()
    assert api.register().status_code == 201
    return api


@pytest.fixture
def other_user() -> Api:
    api = Api()
    assert api.register().status_code == 201
    return api


def make_staff(db: Session, role: Role, email: str | None = None) -> Api:
    address = email or f"{role.value}-{uuid.uuid4().hex[:8]}@example.com"
    account = User(
        email=address,
        password_hash=hash_password(PASSWORD),
        role=role.value,
        display_name=role.value,
    )
    db.add(account)
    db.flush()
    if role == Role.pharmacist:
        db.add(
            PharmacistProfile(
                user_id=account.id,
                registration_number="TEST-1",
                state_council="Test council",
                status="approved",
            )
        )
    db.commit()
    api = Api()
    assert api.login(address).status_code == 200
    return api


@pytest.fixture
def admin(db: Session) -> Api:
    return make_staff(db, Role.admin)


@pytest.fixture
def pharmacist(db: Session) -> Api:
    return make_staff(db, Role.pharmacist)


@pytest.fixture
def other_pharmacist(db: Session) -> Api:
    return make_staff(db, Role.pharmacist)


def medicine_id(db: Session, display_name: str) -> int:
    value = db.scalar(select(Medicine.id).where(Medicine.display_name == display_name))
    assert value is not None, display_name
    return value


def manual_item(api: Api, name: str, strength: str | None = None, form: str | None = None) -> dict:
    response = api.post(
        "/api/v1/prescriptions/manual",
        json={"items": [{"name": name, "strength": strength, "form": form}]},
    )
    assert response.status_code == 201, response.text
    return response.json()


def verify_first(api: Api, prescription: dict) -> dict:
    item = prescription["items"][0]
    candidate = item["candidates"][0]["medicine"]["id"]
    response = api.post(
        f"/api/v1/prescriptions/{prescription['id']}/items/{item['id']}/verify",
        json={"medicine_id": candidate, "lasa_acknowledged": True},
    )
    assert response.status_code == 200, response.text
    return response.json()


def prescription_png(lines: list[str], size: tuple[int, int] = (1200, 900)) -> bytes:
    image = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(image)
    from PIL import ImageFont

    font = ImageFont.load_default(size=36)
    for index, line in enumerate(lines):
        draw.text((60, 60 + index * 70), line, fill="black", font=font)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def pdf_from_lines(lines: list[str], pages: int = 1) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    document = canvas.Canvas(buffer, pagesize=A4)
    document.setAuthor("Secret Author")
    for _ in range(pages):
        document.setFont("Helvetica", 16)
        for index, line in enumerate(lines):
            document.drawString(50, 760 - index * 30, line)
        document.showPage()
    document.save()
    return buffer.getvalue()
