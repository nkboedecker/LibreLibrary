# Contributing to LibreLibrary

Thanks for your interest in LibreLibrary. This guide covers setup, checks, and how changes get accepted.

## Set up

You need [uv](https://docs.astral.sh/uv/) and Git. For image checks, you also need Docker.

```sh
uv sync
```

This one command installs Python if needed, along with every dependency at its locked version.

## Run the checks

CI runs the same commands you can run locally:

```sh
uv run nox              # every check that needs neither Docker nor a PR
uv run nox -s tests     # one check
uv run nox --list       # every check
```

To run the fast checks before each commit:

```sh
uv run pre-commit install
git config commit.template .gitmessage
```

## Code style

- Follow PEP 8 and PEP 257. Ruff enforces them.
- Use type hints. Mypy runs in strict mode.
- Use American spelling.
- Follow the [Google developer documentation style guide](https://developers.google.com/style) for docs and UI text, including sentence-case headings.
- Prefer plain code with tests over clever code.

## Propose a change

- **Bugs:** open a bug report. For a security problem, follow [SECURITY.md](SECURITY.md) instead.
- **Features:** open a feature request before writing a lot of code, so that we can agree on the approach.
- **Community plugins:** the library isn't accepting new plugins yet, because each needs maintainer review. You can still request an integration, or share a plugin through your own plugin library.

## Open a pull request

1. Add tests, including an authorization-denied test for each endpoint.
2. Regenerate the OpenAPI spec if the API changed: `uv run nox -s openapi_update`.
3. Update the docs, and add a line under `Unreleased` in `CHANGELOG.md` for any user-visible change.
4. Title the PR as a [Conventional Commit](https://www.conventionalcommits.org/en/v1.0.0/), such as `feat: add loan reminders`.
5. Fill in the PR template.

A maintainer aims to give a first response within 7 days. Review checks correctness, tests, security, and fit with the [architecture](docs/design/architecture.md). Breaking changes must follow the compatibility policy in that document.

## Sign your work

**Commit signatures:** the repository requires signed commits. GitHub documents [how to sign with an SSH key](https://docs.github.com/en/authentication/managing-commit-signature-verification/about-commit-signature-verification).

**Sign-off:** add a `Signed-off-by` line to each commit with `git commit -s`. It certifies the [Developer Certificate of Origin 1.1](https://developercertificate.org/), which says you have the right to submit the work.

## AI-assisted contributions

AI assistance is allowed, under these rules:

- Disclose it in the PR, and add an `Assisted-by:` trailer to the commit, such as `Assisted-by: Tool name`.
- You're responsible for every line. Read it, understand it, and be able to explain it.
- Only a human can add `Signed-off-by`. AI tools must never add it.

AI agents also follow [AGENTS.md](AGENTS.md).

## Conduct

Everyone taking part follows the [Code of Conduct](CODE_OF_CONDUCT.md).
