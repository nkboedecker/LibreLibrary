# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/), and this project follows [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- Redirects behind a reverse proxy now keep `https://`. The server reads `X-Forwarded-Proto`, but only from `LIBRELIBRARY_TRUSTED_PROXIES`.
- A library's tag list no longer reveals tag names that only hidden copies used, including after a tag has been removed from a copy.
- Taking a copy off a shelf no longer tells someone whether a copy they can't see is on it.

### Added

- A health endpoint at `/api/v1/health`.
- A REST API under `/api/v1` for works, editions, people, series, libraries, copies, tags, shelves, borrowers, loans, readings, ratings, reviews, notes, users, tokens, settings, and the audit trail.
- Password sign-in that issues hashed, revocable personal access tokens, with rate limits that hold across workers.
- Roles, token scopes, library roles, and per-record privacy, enforced by one policy layer.
- Four privacy levels (personal, library, group, and server), groups of users and libraries, and admin transfer of library ownership.
- Database migrations that run at startup, on SQLite and PostgreSQL.
- The `librelibrary` command, with `create-admin` and `migrate`.
- A web interface foundation: browser sign-in and sign-out with server-side cookie sessions, CSRF protection, a searchable, paged list of works, and work pages to view, add, edit, and delete.
- Web pages for libraries, copies, and editions: list and open the libraries you belong to, add and change a library and its settings, add copies from an edition, and edit or delete a copy. Each page offers only what your role allows.
- Library member lists in the API now include each member's display name.
- Web pages for tags and shelves: set a copy's tags from its page, create, rename, and delete shelves, put copies on shelves and take them off, and see a library's shelves and tags.
- An API operation, `GET /api/v1/copies/{copy_id}/shelves`, that lists the shelves holding a copy. Only members of the copy's library see them.
