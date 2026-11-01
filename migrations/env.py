"""Run Alembic migrations against the configured database."""

from typing import Any, Literal

from alembic import context
from alembic.autogenerate.api import AutogenContext
from sqlalchemy.engine import Connection

import librelibrary.models  # noqa: F401
from librelibrary.db import Base, Hundredths, UTCDateTime, make_engine
from librelibrary.settings import Settings


def render_item(
    type_: str, obj: Any, _autogen_context: AutogenContext
) -> str | Literal[False]:
    """Write app column types as plain SQLAlchemy ones.

    An applied migration must keep working when application code changes, so it
    imports nothing from the application.
    """
    if type_ == "type" and isinstance(obj, UTCDateTime):
        return "sa.DateTime(timezone=True)"
    if type_ == "type" and isinstance(obj, Hundredths):
        return "sa.BigInteger()"
    return False


def run(connection: Connection) -> None:
    """Apply migrations using one database connection."""
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        render_as_batch=True,
        render_item=render_item,
    )
    with context.begin_transaction():
        context.run_migrations()


def main() -> None:
    """Use the caller's connection, or connect to the configured database."""
    connection: Connection | None = context.config.attributes.get("connection")
    if connection is not None:
        run(connection)
        return
    with make_engine(Settings().database_url).connect() as own_connection:
        run(own_connection)
        own_connection.commit()


main()
