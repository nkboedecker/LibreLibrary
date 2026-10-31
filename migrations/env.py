"""Run Alembic migrations against the configured database."""

import os

from alembic import context
from sqlalchemy import create_engine

from librelibrary.db import Base

DEFAULT_URL = "sqlite:///librelibrary.db"


def run_migrations() -> None:
    """Apply migrations using one database connection."""
    url = os.environ.get("LIBRELIBRARY_DATABASE_URL", DEFAULT_URL)
    with create_engine(url).connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()


run_migrations()
