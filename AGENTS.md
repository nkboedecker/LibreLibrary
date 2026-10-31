# AGENTS.md

Rules for any AI coding agent working in this repository. Human contributors: see `CONTRIBUTING.md`.

## Project overview

LibreLibrary is a self-hosted personal library server with a web interface, a versioned REST API, and a built-in MCP server. The design is in `docs/design/architecture.md`; read it rather than relying on a copy here.

**Status:** early development. Only the project scaffolding, a health endpoint, and an empty database setup exist.

## Repository layout

- `src/librelibrary/`: the application.
- `tests/`: tests. Fixtures must be synthetic or anonymized.
- `tools/`: check scripts that nox runs.
- `noxfile.py`: every check, as a session.
- `migrations/`: Alembic migrations.
- `openapi/openapi.json`: the generated API spec.
- `docs/`: the MkDocs site, including `design/architecture.md` and `maintainers/`.
- `.github/`: workflows and templates.

The full planned layout is in the architecture doc. Add folders here as they are built.

## Commands

Run every check through nox. If `uv` isn't installed, follow `CONTRIBUTING.md`.

```sh
uv sync                                     # set up the project
uv run nox                                  # every check that needs neither Docker nor a PR
uv run nox -s lint format                   # lint and format check
uv run nox -s typecheck                     # type check
uv run nox -s tests                         # tests with coverage
uv run nox -s docs                          # mkdocs build --strict
uv run nox -s openapi                       # check the committed spec
uv run nox -s openapi_update                # regenerate the spec
uv run nox -s migrations                    # migration check
uv run nox -s licenses                      # dependency license report
uv run nox -s workflows                     # actionlint and zizmor
uv run nox -s pr_title -- "feat: add loans" # PR title check
uv run nox -s dco -- origin/main..HEAD      # sign-off check
uv run nox -s image                         # image build (needs Docker)
uv run nox -s smoke                         # healthcheck and non-root check (needs Docker)
```

## Style

- Use American spelling everywhere: code, comments, docs, UI text, and commit messages.
- Follow the Google developer documentation style guide for docs and UI text, including sentence-case headings.
- Follow PEP 8 and PEP 257. The formatter and linter enforce them.
- In Markdown under `docs/`, indent nested list content by 4 spaces and leave a blank line after nested blocks.
- Use type hints, clear module boundaries, docstrings, and tests. Prefer plain code over clever code.

## Definition of done

A change is done when:

- All checks pass through the task runner.
- Tests are added. Every endpoint has an authorization-denied test. The only public endpoint is `/api/v1/health`.
- The OpenAPI spec is regenerated.
- Docs are updated, and `CHANGELOG.md` has a line under `Unreleased` for any user-visible change.

## Do not edit by hand

- The generated OpenAPI spec.
- Lockfiles, except through the package manager.
- Applied migrations.
- `LICENSE`.

## Hard boundaries

- No secrets or real personal data in code, fixtures, or logs. Never print or log tokens or passwords.
- No real hostnames, domains, IP addresses, or account names. Use `example.com`-style placeholders.
- No new dependency, action, or CI tool without maintainer approval and a compatible license.
- No changes to public API, plugin, or MCP contracts without following the compatibility policy.
- No code copied from incompatibly licensed projects.
- Never contact LibraryThing from code, tests, or tooling. Importers read only files that users supply.

## AI-assisted contributions

- AI assistance is allowed and is disclosed in the PR and with an `Assisted-by:` commit trailer.
- The human contributor is responsible for every line and must read and understand it.
- Agents never add a `Signed-off-by` line. Only a human can certify the Developer Certificate of Origin.

## Security-sensitive areas

These need extra tests and a call-out in the PR:

- Authentication.
- Authorization.
- Token handling.
- Plugin loading, plugin library installs, and everything in `community-plugins/`.
- File and URL handling in importers.
