"""Test the command line."""

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from librelibrary.cli import main
from librelibrary.db import make_engine
from librelibrary.models import AuditEvent, User


@pytest.fixture
def database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """Point the command line at a new database."""
    url = f"sqlite:///{tmp_path}/cli.db"
    monkeypatch.setenv("LIBRELIBRARY_DATABASE_URL", url)
    return url


def test_create_admin_makes_the_first_account(
    database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An empty instance gets its first admin, audited, with no secret logged."""
    monkeypatch.setenv("LIBRELIBRARY_ADMIN_PASSWORD", "a long password")
    assert main(["create-admin", "--username", "Root"]) == 0
    engine = make_engine(database)
    with Session(engine) as session:
        user = session.scalars(select(User)).one()
        event = session.scalars(select(AuditEvent)).one()
    engine.dispose()
    assert (user.username, user.role) == ("root", "admin")
    assert user.password_hash is not None
    assert user.password_hash.startswith("$argon2id$")
    assert "a long password" not in str(event.detail)


def test_create_admin_refuses_a_short_password(
    database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The command line keeps the API's password rule."""
    monkeypatch.setenv("LIBRELIBRARY_ADMIN_PASSWORD", "short")
    assert main(["create-admin", "--username", "root"]) == 1


@pytest.mark.parametrize("username", ["admin@example.com", "has space", ""])
def test_create_admin_refuses_a_username_that_could_not_sign_in(
    database: str, monkeypatch: pytest.MonkeyPatch, username: str
) -> None:
    """The command line accepts only names that the sign-in route accepts."""
    monkeypatch.setenv("LIBRELIBRARY_ADMIN_PASSWORD", "a long password")
    assert main(["create-admin", "--username", username]) == 1


def test_create_admin_reports_a_duplicate_username(
    database: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A second admin with the same name gets one clear line, not a traceback."""
    monkeypatch.setenv("LIBRELIBRARY_ADMIN_PASSWORD", "a long password")
    assert main(["create-admin", "--username", "root"]) == 0
    assert main(["create-admin", "--username", "ROOT"]) == 1
    assert "already exists" in capsys.readouterr().err


def test_migrate_builds_the_schema(database: str) -> None:
    """`librelibrary migrate` applies migrations."""
    assert main(["migrate"]) == 0
    engine = make_engine(database)
    with Session(engine) as session:
        assert session.scalars(select(User)).all() == []
    engine.dispose()
