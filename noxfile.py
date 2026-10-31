"""The project's one task runner: every CI check is a session here."""

import os
import tempfile
from pathlib import Path

import nox

nox.options.default_venv_backend = "none"
nox.options.sessions = ["ci"]

FAST_SESSIONS = ["lint", "format", "typecheck", "workflows"]
ALL_LOCAL_SESSIONS = [
    *FAST_SESSIONS,
    "tests",
    "docs",
    "openapi",
    "migrations",
    "licenses",
]
IMAGE = "librelibrary:dev"


@nox.session
def lint(session: nox.Session) -> None:
    """Run the linter."""
    session.run("ruff", "check", ".", external=True)


@nox.session
def format(session: nox.Session) -> None:  # noqa: A001
    """Check code formatting."""
    session.run("ruff", "format", "--check", ".", external=True)


@nox.session
def typecheck(session: nox.Session) -> None:
    """Run the type checker."""
    session.run("mypy", external=True)


@nox.session
def tests(session: nox.Session) -> None:
    """Run tests with coverage; set LIBRELIBRARY_TEST_DATABASE_URL for PostgreSQL."""
    session.run(
        "pytest", "--cov", "--cov-report=term-missing", *session.posargs, external=True
    )


@nox.session
def docs(session: nox.Session) -> None:
    """Build the documentation, treating warnings as errors."""
    session.run("mkdocs", "build", "--strict", external=True)


@nox.session
def openapi(session: nox.Session) -> None:
    """Check that the committed OpenAPI spec matches the generated one."""
    session.run("python", "tools/export_openapi.py", "--check", external=True)


@nox.session
def openapi_update(session: nox.Session) -> None:
    """Regenerate the committed OpenAPI spec."""
    session.run("python", "tools/export_openapi.py", external=True)


@nox.session
def migrations(session: nox.Session) -> None:
    """Apply migrations, then check for drift; the test URL selects PostgreSQL."""
    with tempfile.TemporaryDirectory() as folder:
        url = os.environ.get(
            "LIBRELIBRARY_TEST_DATABASE_URL",
            f"sqlite:///{Path(folder) / 'migrations.db'}",
        )
        env = {"LIBRELIBRARY_DATABASE_URL": url}
        session.run("alembic", "upgrade", "head", env=env, external=True)
        session.run("alembic", "check", env=env, external=True)


@nox.session
def licenses(session: nox.Session) -> None:
    """Check dependency licenses against the project's rule."""
    session.run("python", "tools/check_licenses.py", external=True)


@nox.session
def workflows(session: nox.Session) -> None:
    """Check the GitHub Actions workflows."""
    session.run("actionlint", external=True)
    session.run("zizmor", "--offline", ".github/workflows", external=True)


@nox.session
def pr_title(session: nox.Session) -> None:
    """Check a pull request title: nox -s pr_title -- "feat: add loans"."""
    session.run("python", "tools/check_pr_title.py", *session.posargs, external=True)


@nox.session
def dco(session: nox.Session) -> None:
    """Check commit sign-offs: nox -s dco -- origin/main..HEAD."""
    session.run("python", "tools/check_dco.py", *session.posargs, external=True)


@nox.session
def image(session: nox.Session) -> None:
    """Build the image; pass --multi-arch to build amd64 and arm64 without loading."""
    if "--multi-arch" in session.posargs:
        session.run(
            "docker",
            "buildx",
            "build",
            "--platform=linux/amd64,linux/arm64",
            ".",
            external=True,
        )
    else:
        session.run("docker", "build", "--tag", IMAGE, ".", external=True)


@nox.session
def smoke(session: nox.Session) -> None:
    """Wait for the built image's healthcheck and confirm it isn't root."""
    session.run("python", "tools/smoke_test.py", IMAGE, external=True)


@nox.session
def ci(session: nox.Session) -> None:
    """Run every check that needs neither Docker nor a pull request."""
    for name in ALL_LOCAL_SESSIONS:
        session.notify(name)
