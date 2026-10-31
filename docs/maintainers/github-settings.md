# GitHub settings

Apply these by hand. They can't be set from files in the repository.

## Placeholders

Replace `OWNER` in these files with the GitHub account:

- `.github/CODEOWNERS`
- `.github/ISSUE_TEMPLATE/config.yml`

Replace the reporting contact placeholder in `CODE_OF_CONDUCT.md`.

## General

- **Merge methods:** allow squash and merge commits, and turn off rebase merges.
- **Default squash and merge commit titles:** use the pull request title.
- **Discussions:** on.
- **Pages:** deploy from the `gh-pages` branch, once the docs workflow exists.

## Ruleset for `main`

- Require a pull request, with one approval and review from code owners.
- Require signed commits.
- Block force pushes and deletions.
- Require these status checks: `checks`, `tests (3.13)`, `tests (3.14)`, `postgres`, `image`, `pr`, and `analyze`.

## Ruleset for tags

Restrict creating, updating, and deleting `v*` tags to the lead maintainer.

## Actions

- Set the default `GITHUB_TOKEN` permission to read-only.
- Require actions to be pinned to a full-length commit SHA.
- Require approval for workflow runs from all outside contributors.

## Security

- Turn on private vulnerability reporting.
- Turn on secret scanning and push protection.
- Turn on Dependabot alerts and security updates.
- Turn on the dependency graph.

## After the first push

Confirm these, which couldn't be tested before the repository was on GitHub:

- All workflows run and pass.
- Dependabot opens update PRs for the digest-pinned base images in `Dockerfile`.
- Dependabot reports alerts for actions pinned to commit SHAs.

## Before the first release

- Create the Docker Hub account and token.
- Create a protected `release` environment that holds `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN`.
