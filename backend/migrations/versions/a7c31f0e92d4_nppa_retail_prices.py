"""NPPA notified retail prices: new price type, marketed_by, longer release codes.

Revision ID: a7c31f0e92d4
Revises: 5b4cdba81d46
"""
import sqlalchemy as sa
from alembic import op

revision = "a7c31f0e92d4"
down_revision = "5b4cdba81d46"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("medicines", sa.Column("marketed_by", sa.String(length=400), nullable=True))
    op.alter_column("release_types", "code", type_=sa.String(length=240))
    op.alter_column("release_types", "label", type_=sa.String(length=300))
    op.alter_column("price_observations", "price_type", type_=sa.String(length=24))
    op.drop_constraint("ck_price_type", "price_observations", type_="check")
    op.create_check_constraint(
        "ck_price_type",
        "price_observations",
        "price_type IN ('ceiling','notified_retail','catalogue','mrp','indicative')",
    )


def downgrade() -> None:
    op.execute("DELETE FROM price_observations WHERE price_type = 'notified_retail'")
    op.drop_constraint("ck_price_type", "price_observations", type_="check")
    op.create_check_constraint(
        "ck_price_type", "price_observations", "price_type IN ('ceiling','catalogue','mrp','indicative')"
    )
    op.alter_column("price_observations", "price_type", type_=sa.String(length=16))
    op.drop_column("medicines", "marketed_by")
