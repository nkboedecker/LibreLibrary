"""Apply Alembic migrations, at startup or from the command line."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, text

# An arbitrary fixed key: PostgreSQL holds this lock while one worker migrates.
_MIGRATION_LOCK = 7_219_004_511


def run_migrations(engine: Engine, directory: Path = Path("migrations")) -> None:
    """Bring the database up to the latest migration."""
    config = Config()
    config.set_main_option("script_location", str(directory))
    with engine.connect() as connection:
        if engine.dialect.name == "postgresql":
            connection.execute(
                text("SELECT pg_advisory_lock(:key)"), {"key": _MIGRATION_LOCK}
            )
            connection.commit()
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        connection.commit()
        if engine.dialect.name == "postgresql":
            connection.execute(
                text("SELECT pg_advisory_unlock(:key)"), {"key": _MIGRATION_LOCK}
            )
            connection.commit()
