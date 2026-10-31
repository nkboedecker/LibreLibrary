"""Shared fixtures: every database test runs on the migrated schema.

Set LIBRELIBRARY_TEST_DATABASE_URL to run against PostgreSQL. That database is
for tests only: the fixtures delete everything in it.
"""

import os
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

from librelibrary.app import create_app  # noqa: E402
from librelibrary.auth.tokens import new_token  # noqa: E402
from librelibrary.db import Base, make_engine  # noqa: E402
from librelibrary.migrate import run_migrations  # noqa: E402
from librelibrary.models import ApiToken, User  # noqa: E402
from librelibrary.settings import Settings  # noqa: E402


@pytest.fixture(scope="session")
def database_url(tmp_path_factory: pytest.TempPathFactory) -> str:
    """Return the database that the tests use."""
    configured = os.environ.get("LIBRELIBRARY_TEST_DATABASE_URL")
    if configured:
        return configured
    return f"sqlite:///{tmp_path_factory.mktemp('db') / 'test.db'}"


@pytest.fixture(scope="session")
def migrated_engine(database_url: str) -> Iterator[Engine]:
    """Apply every migration to an empty database, once per test run."""
    engine = make_engine(database_url)
    if engine.dialect.name == "postgresql":
        with engine.begin() as connection:
            connection.execute(text("DROP SCHEMA public CASCADE"))
            connection.execute(text("CREATE SCHEMA public"))
    run_migrations(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def engine(migrated_engine: Engine) -> Iterator[Engine]:
    """Give a test the migrated database, and empty it afterward."""
    yield migrated_engine
    with migrated_engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(table.delete())


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    """Give a test one database session."""
    with Session(engine) as database_session:
        yield database_session


@pytest.fixture
def app(engine: Engine, database_url: str) -> FastAPI:
    """Build the application on the test database."""
    settings = Settings(database_url=database_url, run_migrations_on_startup=False)
    return create_app(settings, engine=engine)


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Give a test an unauthenticated HTTP client."""
    return TestClient(app)


ALL_SCOPES = ("library:read", "library:write")


@dataclass
class Account:
    """A test user with a bearer token."""

    id: int
    username: str
    headers: dict[str, str]


MakeAccount = Callable[..., Account]


@pytest.fixture
def make_account(session: Session) -> MakeAccount:
    """Create users directly, so tests don't pay for password hashing."""
    created = 0

    def make(
        role: str = "member",
        scopes: tuple[str, ...] = ALL_SCOPES,
        username: str | None = None,
    ) -> Account:
        nonlocal created
        created += 1
        name = username or f"user{created}"
        user = User(username=name, display_name=name, role=role)
        session.add(user)
        session.flush()
        plaintext, token_hash, prefix = new_token()
        session.add(
            ApiToken(
                user_id=user.id,
                name="test",
                token_hash=token_hash,
                display_prefix=prefix,
                scopes=list(scopes),
            )
        )
        session.commit()
        return Account(user.id, name, {"Authorization": f"Bearer {plaintext}"})

    return make
