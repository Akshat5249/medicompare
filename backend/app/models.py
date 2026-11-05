"""SQLAlchemy models. Catalogue rows carry provenance (source, batch, row) and is_demo."""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

Json = JSON().with_variant(JSONB(), "postgresql")


def utcnow() -> datetime:
    return datetime.now(UTC)


class PriceType(enum.StrEnum):
    ceiling = "ceiling"
    notified_retail = "notified_retail"
    catalogue = "catalogue"
    mrp = "mrp"
    indicative = "indicative"


class Role(enum.StrEnum):
    user = "user"
    pharmacist = "pharmacist"
    admin = "admin"


class ItemStatus(enum.StrEnum):
    needs_verification = "needs_verification"
    verified = "verified"
    rejected = "rejected"
    unresolved = "unresolved"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


# ---------------------------------------------------------------- data provenance
class DataSource(Base, TimestampMixin):
    __tablename__ = "data_sources"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    owner: Mapped[str] = mapped_column(String(255))
    url: Mapped[str] = mapped_column(Text)
    licence_note: Mapped[str] = mapped_column(Text)
    update_cadence_days: Mapped[int] = mapped_column(Integer)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    last_imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    data_as_of: Mapped[date | None] = mapped_column(Date)


class ImportBatch(Base, TimestampMixin):
    __tablename__ = "import_batches"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"))
    status: Mapped[str] = mapped_column(String(20), default="staged")
    file_name: Mapped[str] = mapped_column(String(255))
    file_sha256: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(40))
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    valid_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[DataSource] = relationship()
    __table_args__ = (
        CheckConstraint(
            "status IN ('staged','validated','published','rejected')", name="ck_batch_status"
        ),
    )


class StagedRow(Base):
    __tablename__ = "staged_rows"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("import_batches.id", ondelete="CASCADE"), index=True
    )
    row_number: Mapped[int] = mapped_column(Integer)
    raw: Mapped[dict[str, Any]] = mapped_column(Json)
    normalized: Mapped[dict[str, Any] | None] = mapped_column(Json)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    errors: Mapped[list[str]] = mapped_column(Json, default=list)
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','valid','failed','rejected')", name="ck_staged_status"
        ),
        UniqueConstraint("batch_id", "row_number"),
    )


# ---------------------------------------------------------------- catalogue vocabulary
class Manufacturer(Base):
    __tablename__ = "manufacturers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)


class Brand(Base):
    __tablename__ = "brands"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    manufacturer_id: Mapped[int | None] = mapped_column(ForeignKey("manufacturers.id"))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    manufacturer: Mapped[Manufacturer | None] = relationship()


class Ingredient(Base):
    __tablename__ = "ingredients"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    __table_args__ = (
        Index(
            "ix_ingredients_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
    )


class IngredientAlias(Base):
    """Search-only alternative spellings (for example Hindi or Tamil script). Never used for equivalence."""

    __tablename__ = "ingredient_aliases"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ingredient_id: Mapped[int] = mapped_column(
        ForeignKey("ingredients.id", ondelete="CASCADE"), index=True
    )
    alias: Mapped[str] = mapped_column(String(255))
    language: Mapped[str] = mapped_column(String(8))
    ingredient: Mapped[Ingredient] = relationship()
    __table_args__ = (UniqueConstraint("ingredient_id", "alias"),)


class SaltForm(Base):
    __tablename__ = "salt_forms"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)


class DosageForm(Base):
    __tablename__ = "dosage_forms"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(60), unique=True)
    label: Mapped[str] = mapped_column(String(120))


class Route(Base):
    __tablename__ = "routes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    label: Mapped[str] = mapped_column(String(80))


class ReleaseType(Base):
    __tablename__ = "release_types"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # A code can name the ingredient it applies to, for example "extended:metformin".
    code: Mapped[str] = mapped_column(String(240), unique=True)
    label: Mapped[str] = mapped_column(String(300))


# ---------------------------------------------------------------- medicines
class Medicine(Base, TimestampMixin):
    __tablename__ = "medicines"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    display_name: Mapped[str] = mapped_column(String(400))
    generic_name: Mapped[str] = mapped_column(String(400))
    brand_id: Mapped[int | None] = mapped_column(ForeignKey("brands.id"))
    dosage_form_id: Mapped[int] = mapped_column(ForeignKey("dosage_forms.id"))
    route_id: Mapped[int] = mapped_column(ForeignKey("routes.id"))
    release_type_id: Mapped[int] = mapped_column(ForeignKey("release_types.id"))
    therapeutic_category: Mapped[str | None] = mapped_column(String(80))
    marketed_by: Mapped[str | None] = mapped_column(String(400))
    # Canonical key of composition, form, route, release; candidates only. equivalence.py decides.
    equivalence_key: Mapped[str] = mapped_column(String(800), index=True)
    ingredient_key: Mapped[str] = mapped_column(String(400), index=True)
    search_text: Mapped[str] = mapped_column(Text)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"))
    batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("import_batches.id", ondelete="SET NULL")
    )
    source_row: Mapped[int | None] = mapped_column(Integer)
    source_text: Mapped[str | None] = mapped_column(Text)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    brand: Mapped[Brand | None] = relationship()
    dosage_form: Mapped[DosageForm] = relationship()
    route: Mapped[Route] = relationship()
    release_type: Mapped[ReleaseType] = relationship()
    source: Mapped[DataSource] = relationship()
    ingredients: Mapped[list[MedicineIngredient]] = relationship(
        cascade="all, delete-orphan", order_by="MedicineIngredient.position"
    )
    pack_sizes: Mapped[list[PackSize]] = relationship(cascade="all, delete-orphan")
    prices: Mapped[list[PriceObservation]] = relationship(cascade="all, delete-orphan")
    flags: Mapped[list[RegulatoryFlag]] = relationship(cascade="all, delete-orphan")
    __table_args__ = (
        Index(
            "ix_medicines_search_trgm",
            "search_text",
            postgresql_using="gin",
            postgresql_ops={"search_text": "gin_trgm_ops"},
        ),
        Index(
            "ix_medicines_search_fts",
            __import__("sqlalchemy").text("to_tsvector('simple', search_text)"),
            postgresql_using="gin",
        ),
    )


class MedicineIngredient(Base):
    __tablename__ = "medicine_ingredients"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    medicine_id: Mapped[int] = mapped_column(
        ForeignKey("medicines.id", ondelete="CASCADE"), index=True
    )
    ingredient_id: Mapped[int] = mapped_column(ForeignKey("ingredients.id"), index=True)
    salt_form_id: Mapped[int | None] = mapped_column(ForeignKey("salt_forms.id"))
    position: Mapped[int] = mapped_column(Integer, default=0)
    strength_value: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    strength_unit: Mapped[str] = mapped_column(String(16))
    per_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    per_unit: Mapped[str | None] = mapped_column(String(16))
    strength_text: Mapped[str] = mapped_column(String(80))
    ingredient: Mapped[Ingredient] = relationship()
    salt_form: Mapped[SaltForm | None] = relationship()
    __table_args__ = (
        UniqueConstraint("medicine_id", "ingredient_id", "salt_form_id"),
        CheckConstraint("strength_value > 0", name="ck_strength_positive"),
    )


class PackSize(Base):
    __tablename__ = "pack_sizes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    medicine_id: Mapped[int] = mapped_column(
        ForeignKey("medicines.id", ondelete="CASCADE"), index=True
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    unit: Mapped[str] = mapped_column(String(24))
    label: Mapped[str] = mapped_column(String(80))
    __table_args__ = (
        UniqueConstraint("medicine_id", "quantity", "unit"),
        CheckConstraint("quantity > 0", name="ck_pack_positive"),
    )


class PriceObservation(Base):
    __tablename__ = "price_observations"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    medicine_id: Mapped[int] = mapped_column(
        ForeignKey("medicines.id", ondelete="CASCADE"), index=True
    )
    pack_size_id: Mapped[int] = mapped_column(ForeignKey("pack_sizes.id", ondelete="CASCADE"))
    price_type: Mapped[str] = mapped_column(String(24))
    amount_inr: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"))
    batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("import_batches.id", ondelete="SET NULL")
    )
    source_row: Mapped[int | None] = mapped_column(Integer)
    observed_at: Mapped[date] = mapped_column(Date)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    source: Mapped[DataSource] = relationship()
    pack_size: Mapped[PackSize] = relationship()
    __table_args__ = (
        CheckConstraint(
            "price_type IN ('ceiling','notified_retail','catalogue','mrp','indicative')",
            name="ck_price_type",
        ),
        CheckConstraint("amount_inr > 0", name="ck_price_positive"),
    )


class RegulatoryFlag(Base):
    __tablename__ = "regulatory_flags"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    medicine_id: Mapped[int] = mapped_column(
        ForeignKey("medicines.id", ondelete="CASCADE"), index=True
    )
    flag_type: Mapped[str] = mapped_column(String(32))
    description: Mapped[str] = mapped_column(Text)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"))
    source_url: Mapped[str | None] = mapped_column(Text)
    source_date: Mapped[date] = mapped_column(Date)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[DataSource] = relationship()
    __table_args__ = (
        CheckConstraint(
            "flag_type IN ('prohibited_fdc','quality_alert','schedule_h','schedule_h1','schedule_x')",
            name="ck_flag_type",
        ),
    )


class LasaPair(Base):
    __tablename__ = "lasa_pairs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name_a: Mapped[str] = mapped_column(String(255), index=True)
    name_b: Mapped[str] = mapped_column(String(255), index=True)
    origin: Mapped[str] = mapped_column(String(32))
    similarity: Mapped[float | None] = mapped_column(Float)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (UniqueConstraint("name_a", "name_b"),)


class JanAushadhiProduct(Base):
    __tablename__ = "jan_aushadhi_products"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    drug_code: Mapped[str] = mapped_column(String(32), unique=True)
    generic_name: Mapped[str] = mapped_column(String(400))
    group_name: Mapped[str | None] = mapped_column(String(160))
    unit_size: Mapped[str] = mapped_column(String(80))
    mrp_inr: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    medicine_id: Mapped[int | None] = mapped_column(
        ForeignKey("medicines.id", ondelete="SET NULL"), index=True
    )
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"))
    batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("import_batches.id", ondelete="SET NULL")
    )
    observed_at: Mapped[date] = mapped_column(Date)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[DataSource] = relationship()
    __table_args__ = (
        Index(
            "ix_ja_products_generic_trgm",
            "generic_name",
            postgresql_using="gin",
            postgresql_ops={"generic_name": "gin_trgm_ops"},
        ),
    )


class JanAushadhiKendra(Base):
    __tablename__ = "jan_aushadhi_kendras"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kendra_code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    address: Mapped[str] = mapped_column(Text)
    district: Mapped[str] = mapped_column(String(120), index=True)
    state: Mapped[str] = mapped_column(String(120))
    pin_code: Mapped[str] = mapped_column(String(6), index=True)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"))
    batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("import_batches.id", ondelete="SET NULL")
    )
    observed_at: Mapped[date] = mapped_column(Date)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[DataSource] = relationship()
    __table_args__ = (CheckConstraint("pin_code ~ '^[1-9][0-9]{5}$'", name="ck_kendra_pin"),)


# ---------------------------------------------------------------- accounts
class User(Base, TimestampMixin):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Guests have no email; they are a throwaway identity removed by the retention job.
    email: Mapped[str | None] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str | None] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(16), default=Role.user.value)
    is_guest: Mapped[bool] = mapped_column(Boolean, default=False)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    display_name: Mapped[str | None] = mapped_column(String(120))
    __table_args__ = (
        CheckConstraint("role IN ('user','pharmacist','admin')", name="ck_user_role"),
    )


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    user: Mapped[User] = relationship()


class PharmacistProfile(Base, TimestampMixin):
    __tablename__ = "pharmacist_profiles"
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    registration_number: Mapped[str] = mapped_column(String(64))
    state_council: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user: Mapped[User] = relationship(foreign_keys=[user_id])
    __table_args__ = (
        CheckConstraint("status IN ('pending','approved','rejected')", name="ck_pharmacist_status"),
    )


class Consent(Base):
    __tablename__ = "consents"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    purpose: Mapped[str] = mapped_column(String(40))
    notice_version: Mapped[str] = mapped_column(String(16))
    ocr_engine: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SavedList(Base, TimestampMixin):
    __tablename__ = "saved_lists"
    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    items: Mapped[list[SavedListItem]] = relationship(cascade="all, delete-orphan")


class SavedListItem(Base):
    __tablename__ = "saved_list_items"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    list_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("saved_lists.id", ondelete="CASCADE"), index=True
    )
    medicine_id: Mapped[int] = mapped_column(ForeignKey("medicines.id", ondelete="CASCADE"))
    medicine: Mapped[Medicine] = relationship()
    __table_args__ = (UniqueConstraint("list_id", "medicine_id"),)


# ---------------------------------------------------------------- prescriptions
class Prescription(Base, TimestampMixin):
    __tablename__ = "prescriptions"
    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    source_type: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(24), default="received")
    original_key: Mapped[str | None] = mapped_column(Text)
    processed_keys: Mapped[list[str]] = mapped_column(Json, default=list)
    mime_type: Mapped[str | None] = mapped_column(String(40))
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    consent_id: Mapped[int | None] = mapped_column(ForeignKey("consents.id", ondelete="SET NULL"))
    emergency_flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    redacted_line_count: Mapped[int] = mapped_column(Integer, default=0)
    items: Mapped[list[ExtractedItem]] = relationship(
        cascade="all, delete-orphan", order_by="ExtractedItem.position"
    )
    jobs: Mapped[list[ProcessingJob]] = relationship(cascade="all, delete-orphan")
    shares: Mapped[list[PrescriptionShare]] = relationship(cascade="all, delete-orphan")
    __table_args__ = (
        CheckConstraint("source_type IN ('upload','manual')", name="ck_rx_source"),
        CheckConstraint(
            "status IN ('received','processing','needs_verification','verified','unreadable','failed')",
            name="ck_rx_status",
        ),
    )


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"
    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    prescription_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("prescriptions.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(16), default="queued")
    engine: Mapped[str | None] = mapped_column(String(40))
    engine_version: Mapped[str | None] = mapped_column(String(60))
    error_code: Mapped[str | None] = mapped_column(String(60))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExtractedItem(Base, TimestampMixin):
    __tablename__ = "extracted_items"
    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    prescription_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("prescriptions.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer, default=0)
    page: Mapped[int] = mapped_column(Integer, default=0)
    source_text: Mapped[str] = mapped_column(Text, default="")
    bbox: Mapped[list[float] | None] = mapped_column(Json)
    # Each field is a visible fragment, or null with a *_state of unknown / unclear. Never inferred.
    name_text: Mapped[str | None] = mapped_column(String(255))
    name_state: Mapped[str] = mapped_column(String(10), default="unknown")
    strength_text: Mapped[str | None] = mapped_column(String(80))
    strength_state: Mapped[str] = mapped_column(String(10), default="unknown")
    form_text: Mapped[str | None] = mapped_column(String(80))
    form_state: Mapped[str] = mapped_column(String(10), default="unknown")
    frequency_text: Mapped[str | None] = mapped_column(String(80))
    frequency_state: Mapped[str] = mapped_column(String(10), default="unknown")
    duration_text: Mapped[str | None] = mapped_column(String(80))
    duration_state: Mapped[str] = mapped_column(String(10), default="unknown")
    ocr_quality: Mapped[float | None] = mapped_column(Float)
    match_quality: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(
        String(24), default=ItemStatus.needs_verification.value, index=True
    )
    requires_lasa_review: Mapped[bool] = mapped_column(Boolean, default=False)
    verified_medicine_id: Mapped[int | None] = mapped_column(
        ForeignKey("medicines.id", ondelete="SET NULL")
    )
    verified_by_type: Mapped[str | None] = mapped_column(String(12))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    candidates: Mapped[list[CandidateMatch]] = relationship(
        cascade="all, delete-orphan", order_by="CandidateMatch.rank"
    )
    events: Mapped[list[VerificationEvent]] = relationship(
        cascade="all, delete-orphan", order_by="VerificationEvent.created_at"
    )
    verified_medicine: Mapped[Medicine | None] = relationship()
    __table_args__ = (
        CheckConstraint(
            "status IN ('needs_verification','verified','rejected','unresolved')",
            name="ck_item_status",
        ),
        # The database itself refuses a verified item with no confirmed medicine or verifier.
        CheckConstraint(
            "status <> 'verified' OR (verified_medicine_id IS NOT NULL AND verified_by_type IS NOT NULL)",
            name="ck_verified_requires_identity",
        ),
    )


class CandidateMatch(Base):
    __tablename__ = "candidate_matches"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("extracted_items.id", ondelete="CASCADE"), index=True
    )
    medicine_id: Mapped[int] = mapped_column(ForeignKey("medicines.id", ondelete="CASCADE"))
    rank: Mapped[int] = mapped_column(Integer)
    score: Mapped[float] = mapped_column(Float)
    reasons: Mapped[list[str]] = mapped_column(Json, default=list)
    is_lasa: Mapped[bool] = mapped_column(Boolean, default=False)
    medicine: Mapped[Medicine] = relationship()


class VerificationEvent(Base):
    __tablename__ = "verification_events"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("extracted_items.id", ondelete="CASCADE"), index=True
    )
    verifier_type: Mapped[str] = mapped_column(String(12))
    verifier_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    action: Mapped[str] = mapped_column(String(20))
    diff: Mapped[dict[str, Any]] = mapped_column(Json, default=dict)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (
        CheckConstraint("verifier_type IN ('user','pharmacist')", name="ck_verifier_type"),
    )


class PrescriptionShare(Base):
    __tablename__ = "prescription_shares"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    prescription_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("prescriptions.id", ondelete="CASCADE"), index=True
    )
    pharmacist_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(16), default="pending")
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("prescription_id", "pharmacist_id"),)


class ShareLink(Base):
    __tablename__ = "share_links"
    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    prescription_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("prescriptions.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    label: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditEvent(Base):
    """Never holds prescription contents: identifiers and action metadata only."""

    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    action: Mapped[str] = mapped_column(String(60), index=True)
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    meta: Mapped[dict[str, Any]] = mapped_column(Json, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
