# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/), and this project follows [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- A health endpoint at `/api/v1/health`.
- A REST API under `/api/v1` for works, editions, people, series, libraries, copies, tags, shelves, borrowers, loans, readings, ratings, reviews, notes, users, tokens, settings, and the audit trail.
- Password sign-in that issues hashed, revocable personal access tokens, with rate limits that hold across workers.
- Roles, token scopes, library roles, and per-record privacy, enforced by one policy layer.
- Database migrations that run at startup, on SQLite and PostgreSQL.
- The `librelibrary` command, with `create-admin` and `migrate`.
