"""Command-line administration: `librelibrary create-admin` and `migrate`."""

import argparse
import getpass
import os
import sys

from pydantic import TypeAdapter, ValidationError
from sqlalchemy.orm import Session

from librelibrary.db import make_engine
from librelibrary.errors import Conflict
from librelibrary.migrate import run_migrations
from librelibrary.schemas import Username
from librelibrary.services.accounts import create_first_admin
from librelibrary.settings import Settings

MIN_PASSWORD_LENGTH = 12


def _read_password() -> str:
    """Read a password from the environment or a prompt, never from arguments."""
    return os.environ.get("LIBRELIBRARY_ADMIN_PASSWORD") or getpass.getpass()


def main(argv: list[str] | None = None) -> int:
    """Run a command, and return its exit status."""
    parser = argparse.ArgumentParser(prog="librelibrary")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("migrate", help="apply database migrations")
    admin = commands.add_parser("create-admin", help="create an admin account")
    admin.add_argument("--username", required=True)
    admin.add_argument("--display-name")
    arguments = parser.parse_args(argv)

    settings = Settings()
    engine = make_engine(settings.database_url)
    run_migrations(engine, settings.migrations_dir)
    if arguments.command == "create-admin":
        password = _read_password()
        if len(password) < MIN_PASSWORD_LENGTH:
            print(  # noqa: T201
                f"Use at least {MIN_PASSWORD_LENGTH} characters.", file=sys.stderr
            )
            return 1
        try:
            username = TypeAdapter(Username).validate_python(arguments.username)
        except ValidationError:
            print(  # noqa: T201
                "Use only letters, digits, periods, hyphens, and underscores.",
                file=sys.stderr,
            )
            return 1
        with Session(engine) as session:
            try:
                create_first_admin(
                    session, username, arguments.display_name or username, password
                )
            except Conflict:
                print(f"User {username} already exists.", file=sys.stderr)  # noqa: T201
                return 1
    engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
