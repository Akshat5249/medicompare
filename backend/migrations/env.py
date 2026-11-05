"""Alembic environment. The database URL comes from application settings."""
from alembic import context

from app import models  # noqa: F401
from app.config import get_settings
from app.db import Base
from sqlalchemy import create_engine

target_metadata = Base.metadata
engine = create_engine(get_settings().database_url)
with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()
