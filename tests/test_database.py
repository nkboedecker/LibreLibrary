"""Test that the configured database can be reached."""

import os

from sqlalchemy import create_engine, text


def test_database_connects() -> None:
    """Connect to SQLite, or to the database that the environment names."""
    url = os.environ.get("LIBRELIBRARY_TEST_DATABASE_URL", "sqlite:///:memory:")

    with create_engine(url).connect() as connection:
        assert connection.execute(text("SELECT 1")).scalar_one() == 1
