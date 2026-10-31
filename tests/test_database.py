"""Test the database foundations on the configured database."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta, timezone

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import (
    Column,
    Engine,
    ForeignKey,
    Integer,
    MetaData,
    Table,
    select,
    text,
)
from sqlalchemy.exc import DBAPIError, StatementError

from librelibrary.db import Base, UTCDateTime, is_constraint_violation, make_engine
from librelibrary.migrate import run_migrations
from librelibrary.settings import Settings


def test_database_connects(engine: Engine) -> None:
    """The configured database answers a query."""
    with engine.connect() as connection:
        assert connection.execute(text("SELECT 1")).scalar_one() == 1


def test_migrations_match_the_models(engine: Engine) -> None:
    """The migrated schema has no drift from the models."""
    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        assert compare_metadata(context, Base.metadata) == []


def test_migrations_can_run_again(engine: Engine) -> None:
    """Startup can apply migrations to an up-to-date database."""
    run_migrations(engine)


def test_constraint_names_are_predictable() -> None:
    """Migrations rely on a naming convention to alter constraints later."""
    convention = Base.metadata.naming_convention
    assert {"ix", "uq", "ck", "fk", "pk"} <= set(convention)


@pytest.fixture
def stamped(engine: Engine) -> Iterator[Table]:
    """Create a scratch table with a timestamp column."""
    metadata = MetaData()
    table = Table(
        "scratch_stamped",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("at", UTCDateTime),
    )
    metadata.drop_all(engine)
    metadata.create_all(engine)
    yield table
    metadata.drop_all(engine)


def test_datetimes_come_back_aware_in_utc(engine: Engine, stamped: Table) -> None:
    """Both databases return the same instant, in UTC."""
    eastern = timezone(timedelta(hours=-4))
    written = datetime(2026, 10, 31, 12, 0, tzinfo=eastern)
    with engine.begin() as connection:
        connection.execute(stamped.insert().values(id=1, at=written))
    with engine.connect() as connection:
        read = connection.execute(select(stamped.c.at)).scalar_one()
    assert read == written
    assert read.tzinfo == UTC


def test_naive_datetimes_are_refused(engine: Engine, stamped: Table) -> None:
    """A timestamp with no zone is a bug, so it never reaches the database."""
    naive = datetime(2026, 10, 31, 12, 0)  # noqa: DTZ001
    with pytest.raises(StatementError), engine.begin() as connection:
        connection.execute(stamped.insert().values(id=2, at=naive))


def test_foreign_keys_are_enforced(engine: Engine) -> None:
    """SQLite enforces foreign keys only when asked, so the engine asks."""
    metadata = MetaData()
    parent = Table("scratch_parent", metadata, Column("id", Integer, primary_key=True))
    child = Table(
        "scratch_child",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("parent_id", Integer, ForeignKey(parent.c.id)),
    )
    metadata.drop_all(engine)
    metadata.create_all(engine)
    try:
        with pytest.raises(DBAPIError) as caught, engine.begin() as connection:
            connection.execute(child.insert().values(id=1, parent_id=99))
        assert is_constraint_violation(caught.value)
    finally:
        metadata.drop_all(engine)


def test_sqlite_files_use_wal(tmp_path: object) -> None:
    """The default database runs in WAL mode."""
    engine = make_engine(f"sqlite:///{tmp_path}/wal.db")
    with engine.connect() as connection:
        mode = connection.execute(text("PRAGMA journal_mode")).scalar_one()
    engine.dispose()
    assert mode == "wal"


def test_settings_read_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Deployment settings use the LIBRELIBRARY_ prefix."""
    monkeypatch.setenv("LIBRELIBRARY_DATABASE_URL", "sqlite:///elsewhere.db")
    monkeypatch.setenv("LIBRELIBRARY_LOCAL_AUTH_ENABLED", "false")
    settings = Settings()
    assert settings.database_url == "sqlite:///elsewhere.db"
    assert settings.local_auth_enabled is False


def test_other_database_errors_are_not_constraint_violations(engine: Engine) -> None:
    """A syntax error is a server fault, not a conflict to report to the client."""
    with pytest.raises(DBAPIError) as caught, engine.connect() as connection:
        connection.execute(text("SELECT FROM WHERE"))
    assert not is_constraint_violation(caught.value)
