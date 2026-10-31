"""Database metadata, column types, and engine setup."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, Engine, MetaData, create_engine, event
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import TypeDecorator

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """The base class of every database model."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UTCDateTime(TypeDecorator[datetime]):
    """A timestamp that is always aware, and always UTC when read.

    SQLite drops time zones, so this type stores UTC on both databases and
    refuses naive values instead of guessing their zone.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(
        self, value: datetime | None, dialect: Dialect
    ) -> datetime | None:
        """Convert a value to UTC before storing it."""
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime refused")  # noqa: TRY003
        return value.astimezone(UTC)

    def process_result_value(
        self, value: datetime | None, dialect: Dialect
    ) -> datetime | None:
        """Mark a stored value as UTC."""
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


def utcnow() -> datetime:
    """Return the current time, aware and in UTC."""
    return datetime.now(UTC)


def _configure_sqlite(connection: Any, _record: Any) -> None:
    """Turn on foreign keys and WAL, which SQLite leaves off by default."""
    cursor = connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


def make_engine(url: str) -> Engine:
    """Create an engine with the settings each database needs."""
    if url.startswith("sqlite"):
        engine = create_engine(url, connect_args={"check_same_thread": False})
        event.listen(engine, "connect", _configure_sqlite)
        return engine
    return create_engine(url, pool_pre_ping=True)


def is_constraint_violation(error: DBAPIError) -> bool:
    """Say whether a database error means a constraint refused the write.

    pg8000 raises ProgrammingError for every server error, so SQLAlchemy's
    IntegrityError never appears on PostgreSQL. SQLSTATE class 23 identifies
    these errors there.
    """
    if isinstance(error, IntegrityError):
        return True
    details = error.orig.args[0] if error.orig and error.orig.args else None
    return isinstance(details, dict) and str(details.get("C", "")).startswith("23")
