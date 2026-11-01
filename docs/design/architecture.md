# LibreLibrary architecture

**Status:** approved by the maintainer on 2026-10-31. Every source was checked on 2026-10-31.

## How to read this document

- **Decided** items are settled, either by the project's requirements or by the maintainer.
- **How sources were checked:** most facts were read through a summarizing fetch tool, so check an exact quote against its source before relying on it. Facts marked **(direct)** were re-read from the primary source.
- **Unverified** means the fact could not be confirmed. Nothing here depends on an unverified fact without saying so.
- **Versions** are the latest seen on 2026-10-31. They are not pins. Phase 1 pins exact versions in lockfiles, and action commit SHAs are resolved then.

## Goals and scope

LibreLibrary is a free, self-hosted personal library server with features similar to LibraryThing. It has a web interface that non-technical people can use, and an API that does everything the interface can do.

Desktop and mobile clients are out of scope, but the API must be able to support them. Features outside the requirements appear only under [Proposed extras](#proposed-extras).

## Stack

| Layer | Choice | Reason |
|---|---|---|
| Language | Python `>=3.13`, tested on 3.13 and 3.14 | Mainstream and easy to read. [3.14 is in bugfix status and 3.13 is security-only](https://peps.python.org/api/release-cycle.json). |
| Image runtime | `python:3.14-slim`, pinned by digest | Published for arm64. Compiled dependencies checked ship `cp314` or abi3 wheels. |
| Web framework | FastAPI on uvicorn | Generates the OpenAPI spec from typed code, which serves the 100% coverage requirement. |
| ORM and migrations | SQLAlchemy 2.1 (sync), Alembic | One model for SQLite and PostgreSQL. Sync sessions avoid the lazy-loading traps of async sessions and are easier to read. FastAPI runs sync handlers in a thread pool. |
| HTML | Jinja2, htmx 2, small vanilla JavaScript | See below. |
| Outbound HTTP | httpx 0.28 behind a thin wrapper | [The last stable release is from 2024-12](https://pypi.org/pypi/httpx/json), so the wrapper keeps it replaceable. It brings `certifi` (MPL-2.0) at run time, which is on the approved list. |

### Web UI approach: server-rendered, not an SPA

**Decided:** server-rendered pages with htmx for partial updates and small JavaScript modules for the barcode scanner and theme switch. There is no Node build step at run time or in the image.

- **Ease of use:** forms, links, and focus order work as browsers intend, which makes WCAG 2.2 AA easier to reach than in an SPA, and pages work on low-end phones.
- **Maintainability:** one language for nearly all the code, which suits contributors.
- **License:** avoiding Vite avoids its [MPL-2.0 `lightningcss` dependency](https://registry.npmjs.org/vite).
- **API-first:** an SPA enforces API parity by construction, and server rendering doesn't. So parity becomes a tested rule:
    - All logic lives in a service layer. API routes and UI routes are both thin callers of it.
    - Each UI route that reads or changes data declares the OpenAPI `operationId` it fulfills, for example `@ui_route(api="books_create")`.
    - A test walks every UI route and fails if the declared operation is missing from the spec or if the declaration is absent.
    - A second test confirms that the UI route and its API operation call the same service function.

Htmx 2.0.11 is [npm's `latest`, while 4.0.0 is tagged `next`](https://registry.npmjs.org/htmx.org). The project uses the 2.x line. [Pico CSS is archived](https://github.com/picocss/pico), so the stylesheet is small and in-house.

## License

**Decided: [Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0.txt)**, with `Copyright (c) 2026 Natalie Boedecker`.

- It is permissive, which matches the dependency rule, and it is compatible with every MIT, BSD, and Apache dependency below.
- Its explicit patent grant suits a project expecting outside contributions. MIT has none.
- Plugins can use any license, because Apache-2.0 places no copyleft conditions on code that loads it.

**Effect on dependencies:** LGPL and GPL packages are excluded. GPL servers (Calibre, Calibre-Web, Kavita, Audiobookshelf) are reached over the network only, and no code is copied from them.

## Database

- **SQLite is the default,** in WAL mode, stored in the data volume. It needs no separate service.
- **PostgreSQL is supported,** and CI tests both. Code avoids dialect-specific features unless a test covers each dialect.
- **Driver:** [psycopg is LGPL-3.0-only](https://pypi.org/pypi/psycopg/json), so it is excluded. The project uses pg8000 (BSD-3-Clause), which fits sync SQLAlchemy. [pg8000 declares Python 3.13 and not 3.14](https://pypi.org/pypi/pg8000/json), so CI must prove 3.14. **Result:** the Phase 2 suite passes with pg8000 on 3.14. pg8000 reports every server error as `ProgrammingError`, so constraint violations are recognized by SQLSTATE class 23 in `db.is_constraint_violation`, never by catching `IntegrityError` alone. **Fallback:** asyncpg, Apache-2.0, if a later run fails. That fallback would mean an async design, so it would come back to the maintainer first.
- **Search:** SQLite FTS5 and PostgreSQL full-text search, behind one search service, in Phase 3. Until then, the API matches part of a title or name.
- **Migrations:** Alembic, forward-only, applied automatically at startup. Startup logs a reminder to back up, and a failed migration stops the server.

## Data model

Names are logical. **Decided:** each table arrives with the phase that uses it, so no schema is guessed ahead of its feature. Phase 2 builds the bibliographic and personal records, except `ExternalLink` and the Kosync tables, plus the group tables, `User`, `ApiToken`, `AuditEvent`, `Setting`, and a `RateLimitCounter` for shared limits. `Session` waits for Phase 3, `Job` for Phase 5, `ExternalIdentity` for Phase 6, `PluginState` for Phase 7, `OAuthClient` and `OAuthGrant` for Phase 8, and `ExternalLink`, the Kosync tables, and `KosyncCredential` for Phase 9.

### Bibliographic records (shared within an instance)

| Entity | Purpose | Key fields |
|---|---|---|
| `Work` | The abstract book | title, original language, first published, description |
| `Edition` | A published form of a work | `work_id`, title, subtitle, publisher, date, language, format, pages, cover |
| `Person` | An author or other contributor | name, sort name, external IDs |
| `Contribution` | Links a person to a work or edition, in order | `person_id`, role (author, editor, translator, illustrator, narrator, and others), position |
| `Series`, `SeriesEntry` | Series and ordering | name; `work_id`, position as text ("2.5") |
| `Subject`, `WorkSubject` | Subjects | scheme (LCSH, BISAC, free text), label |
| `Classification` | Class numbers | scheme (DDC, LCC), value |
| `Identifier` | IDs for an edition | scheme (ISBN-13, ISBN-10, LCCN, OCLC, OLID, Wikidata, ASIN, LibraryThing work), value; unique per scheme and value |
| `MetadataSource` | Provenance | provider, external ID, fetched at, license note |

ISBNs are stored normalized as ISBN-13 where possible. An ISBN-10 is derivable, and the original form is kept for faithful export.

### Personal records (owned)

| Entity | Purpose | Key fields |
|---|---|---|
| `Library` | A user's or household's collection | owner, name, default privacy |
| `LibraryMember` | Household sharing | `library_id`, `user_id`, role (owner, editor, viewer) |
| `Copy` | A physical or digital item you own | `library_id`, `edition_id`, condition, location, acquired date, source, price, privacy |
| `ReadingState` | A user's reading of a work | `user_id`, `work_id`, status, started, finished; several reads allowed |
| `Rating`, `Review`, `Note` | A user's responses | `user_id`, `work_id`, value or text, privacy |
| `Tag`, `CopyTag` | Per-library free tags | name |
| `Shelf`, `ShelfItem` | Collections and shelves | `library_id`, name, kind |
| `Loan`, `Borrower` | Lending | `copy_id`, borrower, lent, due, returned |
| `ExternalLink` | Link to a server's ebook or audiobook | `edition_id`, plugin, external ID, URL |
| `KosyncDocument`, `KosyncProgress` | KOReader sync | hash, `edition_id` (nullable); user, progress, device, timestamp |

**Groups:** `Group`, `GroupMember`, and `GroupLibrary`. A group holds users and libraries, and both can belong to several groups. Admins create groups and manage their members. A library owner can add their own library to a group they belong to. The owner or an admin can take it out.

**Privacy (decided):** each copy, rating, review, and note has one of four levels. A server serves one household, and groups don't separate households, because all groups share one catalog and one set of admins.

| Level | Copy | Rating, review, or note |
|---|---|---|
| `personal` | The library's owner, and its editors unless the owner turns off the library's `editors_see_personal` setting. It is on by default. | The author |
| `library` | Adds the library's members | Members of a library the author chooses |
| `group` | Adds members of any group that includes the library | Members of a group the author chooses |
| `server` | Everyone signed in | Everyone signed in |

- **Defaults:** new libraries default to `personal`.
- **Audience:** a rating, review, or note at `library` or `group` level names its audience, and the author must belong to it.
- **Leaving:** someone removed from a library or group loses access at once. What they wrote there stays shared until they change it or an admin deactivates their account. Records whose audience is deleted stay visible to their authors.
- **Admins:** the admin role gives no routine access to personal records, and managing a group gives no access to what is shared in it. This isn't a guarantee: an admin can reset a password, which the audit trail records, and whoever runs the server can read its database.
- **Ownership:** an admin can transfer a library to a new owner, so that a departure can't strand it. The old owner stays on as an editor.

**Shared catalog (decided for now):** any user who isn't a guest can create and edit works, editions, people, and series. Deleting them needs the admin scope. Catalog edits aren't audited yet. Changing this rule later needs no data migration.

**Prices (decided):** a copy's price has two decimal places and a currency code. The API sends it as a string, such as `"12.99"`, and it is stored as a whole number of hundredths, so it stays exact on both databases.

**Ratings (decided):** half stars, stored as a whole number from 1 to 10, so 7 means 3½ stars.

### System records

`User`, `ExternalIdentity` (OIDC issuer and subject), `Session`, `ApiToken` (stored hashed), `OAuthClient`, `OAuthGrant`, `KosyncCredential`, `Job` (imports and bulk actions), `AuditEvent`, `PluginState`, and `Setting`.

## Authentication and authorization

### Sign-in

- **Local accounts:** passwords hashed with argon2-cffi. An environment setting can disable them.
- **OIDC client:** Authlib 1.9 with discovery, PKCE, group-to-role mapping, and optional automatic account creation. Accounts are matched on issuer and subject, never on email alone.
- **Tests** run against [navikt/mock-oauth2-server](https://github.com/navikt/mock-oauth2-server/blob/master/LICENSE.md) (MIT, published image).

### Two separate OAuth roles

LibreLibrary is an OIDC **client** of an external provider for sign-in. It is also an OAuth **authorization server** for its own API and MCP clients. Tokens from the external provider are never accepted by the API, because the [MCP security guidance forbids token passthrough](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization/security-considerations.md).

The authorization server provides:

- Authorization code with PKCE (S256 only).
- Authorization server metadata, including `code_challenge_methods_supported`.
- [RFC 9728 protected resource metadata, and RFC 8707 `resource` values](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization) (direct), with audience checks on every token.
- Client ID Metadata Documents. [Dynamic Client Registration is deprecated in the current MCP revision](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization/client-registration.md) (direct), so it is not built.

**Unverified:** how much of this Authlib covers, especially Client ID Metadata Documents, which may need in-house code. Phase 8 checks this first.

### Tokens and scopes

Personal access tokens have a prefix, are stored hashed, can expire, and are shown once. Scopes:

| Scope | Allows |
|---|---|
| `library:read` | Read what the user can see |
| `library:write` | Change what the user can change |
| `admin` | Administration, and only for admin users |
| `opds` | OPDS feeds |

A token never exceeds its user's permissions. KOReader uses separate credentials, because its client [sends an MD5 of the password](https://raw.githubusercontent.com/pid1/kosync-conformance/main/SPEC.md).

### One authorization layer

Every service function takes an `Actor` (user, roles, token scopes) and calls `policy.require(actor, action, resource)` before acting. This one module, `librelibrary/authz/policy.py`, serves the UI, API, MCP, OPDS, and plugins. Queries use policy-aware scoping helpers so that private rows can't appear in lists. A test confirms each service operation declares a policy action.

Roles are `admin`, `member`, and `guest` (read-only). Library roles (owner, editor, viewer) add per-library rights.

### Web protections

- **Cookie sessions:** arrive in Phase 3 with the pages that use them. Server-side, `Secure`, `HttpOnly`, `SameSite=Lax`, with a synchronizer CSRF token on every state-changing request. Bearer-token requests don't use cookies and skip CSRF. **Built:** the `web_session` table holds a hash of the cookie value and the session's CSRF token. A page accepts only the cookie, and the API accepts only a bearer token, so one can't be used for the other. The sign-in form has no session yet, so it uses a double-submit token: a short-lived `SameSite=Lax` cookie that the form must repeat. A session lasts 14 days, set by `LIBRELIBRARY_SESSION_LIFETIME_DAYS`, and signing out deletes it on the server.
- **Rate limiting:** the [`limits`](https://pypi.org/pypi/limits/json) library (MIT) in middleware, per IP and per username for sign-in. slowapi is not used because [it does not declare 3.14 support](https://pypi.org/pypi/slowapi/json). **Decided:** counters live in the application's database, so limits hold across workers with no new service. Each counted attempt writes a row, so per-token limits on ordinary API requests are not built yet, and need their own decision before they are.
- **Reverse proxy:** forwarded headers are honored only from `TRUSTED_PROXIES`. `BASE_URL` sets generated links, including a path prefix.
- **Importers:** size limits, no XML entity expansion, and outbound fetches restricted to approved providers, blocking private addresses unless an admin allows them.

## Metadata providers

Every provider uses the plugin interface and the shared client, which sends `LibreLibrary/VERSION (BASE_URL; CONTACT)`. `CONTACT` is set per deployment.

| Provider | Default | Limits and terms | Source |
|---|---|---|---|
| Open Library | On, no key | User-Agent with app name and email. 1 request per second, or 3 if identified. Covers by ISBN: 100 per IP per 5 minutes; by cover ID: not limited. No bulk download through the API. | [API](https://openlibrary.org/developers/api), [covers](https://openlibrary.org/dev/docs/api/covers) |
| Library of Congress | Off | JSON API: 20 per minute, but [general automated guidance says 10](https://www.loc.gov/legal/), so the client uses 10. [The JSON API excludes catalog records](https://www.loc.gov/apis/json-and-yaml/); catalog access is [SRU](https://www.loc.gov/standards/sru/resources/lcServers.html). | [Limits](https://www.loc.gov/apis/json-and-yaml/working-within-limits/) |
| Wikidata | Off | Descriptive User-Agent with contact details. SPARQL: 60-second timeout, 5 parallel queries per IP, honor 429 and `Retry-After`. Data is CC0. | [User-Agent policy](https://foundation.wikimedia.org/wiki/Policy:Wikimedia_Foundation_User-Agent_Policy), [query limits](https://www.mediawiki.org/wiki/Wikidata_Query_Service/User_Manual), [license](https://www.wikidata.org/wiki/Wikidata:Licensing) |
| Google Books | Off, admin's own key | Key or token required. No key ships in the repository, and caching follows the cache headers, so results are live lookups with no stored copy by default. Attribution required. | [Using the API](https://developers.google.com/books/docs/v1/using), [API terms](https://developers.google.com/terms), [branding](https://developers.google.com/books/branding) |

**Unverified:** Open Library's data license ([its licensing page](https://openlibrary.org/developers/licensing) asserts no new rights, with possible existing rights), Google Books quota and cover hotlinking rules, Library of Congress SRU limits and ISBN query support.

**Not included:** LibraryThing's own APIs. The server never contacts LibraryThing.

## ISBN handling

**Decided:** in-house ISBN-10 and ISBN-13 validation and conversion, tested with property tests. [python-stdnum](https://pypi.org/pypi/python-stdnum/json) and [isbnlib](https://pypi.org/pypi/isbnlib/json) are LGPL.

**Barcode entry:**

- **Camera:** [`barcode-detector`](https://registry.npmjs.org/barcode-detector) with [`zxing-wasm`](https://registry.npmjs.org/zxing-wasm), both MIT. Browsers allow camera access only in a secure context, so the reverse-proxy docs must require HTTPS.
- **USB and Bluetooth scanners:** they act as keyboards. A focused input treats fast digits ending in Enter as a scan.
- **Batch paste:** one ISBN per line, validated, with a per-line result.

## Plugin interface

Plugins are installed by an admin only, and they run in the server process with its full privileges. The docs state plainly that a plugin is fully trusted code.

- **Discovery:** Python entry points in the group `librelibrary.plugins`, read with `importlib.metadata`. pluggy is not needed.
- **Installation:** an admin installs a plugin from a plugin library (below), or adds one through a documented derived image. Each install is a pure-Python wheel unpacked into a versioned folder in the data volume, with no install scripts run. A restart activates it.
- **Versioning:** `PLUGIN_API_VERSION` is an integer. Each plugin declares the version it supports, and an incompatible plugin is skipped with a logged error, so the server still starts.

Interfaces are `typing.Protocol` classes in `librelibrary.plugin_api`:

| Interface | Methods |
|---|---|
| `MetadataProvider` | `lookup_isbn`, `search`, `fetch_cover` |
| `Importer`, `Exporter` | `detect`, `read`; `write` |
| `EbookServer` | `test_connection`, `sync_index`, `find_matches`, `link_for`, `import_metadata` |
| `NotificationTarget` | `send` |

Plugins get a narrow `PluginContext` (settings, logger, HTTP client, and service calls that enforce policy for an explicit actor). Built-in and community plugins use this same interface.

**Trust limit:** `PluginContext` is a convenience, not a sandbox.

### Plugin libraries

A plugin library is a catalog of plugins that an admin can browse and install from. Browsing, installing, enabling, disabling, and removing are admin-only, with API operations behind the UI. MCP has no tools for them.

- **Catalog format:** a versioned JSON index. Each entry gives the plugin's name, version, summary, license, maintainers, supported `PLUGIN_API_VERSION`, and interface types, plus its wheel's location and SHA-256 hash.
- **Installing:** the server refuses a wheel if its hash doesn't match, if it declares dependencies, if it isn't pure Python, if it doesn't support the running API version, or if any of its paths would land outside its folder.
- **Dependencies:** plugins from a library may use only LibreLibrary's own locked dependencies and the standard library. This avoids version conflicts and keeps outside packages out of the image's supply chain. A plugin that needs more uses a derived image.
- **Third-party libraries:** an admin adds one by HTTPS URL. The server shows a warning that its plugins run with the server's full privileges, and that the project hasn't reviewed them. None is enabled by default.

### Community plugin library

The repository hosts one library, in `community-plugins/`, and every image ships with it.

- **Layout:** each plugin has its own folder with source, `pyproject.toml`, tests, a README, and named maintainers.
- **Shipping:** release builds turn each plugin into a wheel, generate the index, and place both in the image. The wheels are therefore covered by the image's signature, SBOM, and scans, and installing one needs no network access. Nothing is enabled until an admin chooses it.
- **Updates:** community plugins update with LibreLibrary releases. They have no separate versioned releases.
- **Licensing:** a plugin in this folder uses the project's license and is contributed under the same sign-off rules. Its code must meet the same dependency and copying rules as the rest of the repository.
- **Review:** additions and changes need a lead maintainer's review through `CODEOWNERS`, because this code runs with full privileges once enabled. Review reduces that risk but doesn't remove it, and the docs say so.
- **Continued support:** a plugin stays while it passes CI and has a responsive maintainer. If it doesn't, it is marked unmaintained for one minor release and then removed from the library. Installed copies keep working until they are incompatible.
- **First contents:** project-maintained features that work better as optional plugins: the Library of Congress, Wikidata, and Google Books providers; the Calibre, Calibre-Web, Kavita, Komga, and Audiobookshelf integrations; and notification targets. Features built before Phase 7 move here in Phase 7.
- **Kept built in:** what must work with nothing enabled: Open Library, LibraryThing and generic import and export, OPDS, and KOReader sync.
- **Outside contributions:** new community plugins aren't accepted yet, because of the review they need. `CONTRIBUTING.md` says so, and the integration and plugin request form stays open. The maintainer decides when this changes. Third-party libraries are the way to share plugins until then.

## MCP

[The current revision is 2026-07-28](https://modelcontextprotocol.io/specification/versioning.md) (direct). It [removes protocol sessions and the `initialize` handshake, and requires `server/discover`](https://modelcontextprotocol.io/specification/2026-07-28/changelog.md) (direct).

- **SDK:** [`mcp` 2.3.0](https://pypi.org/pypi/mcp/json), MIT.
- **Streamable HTTP:** [mounted in the main ASGI app](https://py.sdk.modelcontextprotocol.io/run/asgi/) at `/mcp`, with `Origin` validation as [the transport spec requires](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http.md). [Requests are self-contained, so any worker can serve them](https://py.sdk.modelcontextprotocol.io/run/deploy/) (direct).
- **stdio:** `librelibrary mcp stdio`, with the token from `LIBRELIBRARY_TOKEN`. [Only MCP goes to stdout](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/stdio.md), and logs go to stderr.
- **Auth:** the same tokens and policy layer, through the SDK's `TokenVerifier`.

**Unverified:** which MCP clients already speak 2026-07-28. Legacy clients may need the SDK's `auto` version mode and sticky sessions across workers. Phase 8 tests this before the multi-worker docs are written.

### Tool list

| Tool | Scope | Purpose |
|---|---|---|
| `search_books` | read | Search the caller's visible catalog |
| `get_book` | read | Work, edition, and copy details |
| `list_shelves`, `list_tags` | read | Collections and tags |
| `get_reading_state` | read | Status, dates, and rating |
| `list_loans` | read | Current and past loans |
| `lookup_metadata` | read | Look up an ISBN or title through providers |
| `library_stats` | read | Counts and summaries |
| `add_book_by_isbn`, `add_book` | write | Add a book |
| `update_book` | write | Edit fields |
| `set_reading_state`, `set_rating` | write | Status and rating |
| `add_note`, `add_review` | write | Notes and reviews |
| `add_tags`, `remove_tags` | write | Tags |
| `add_to_shelf`, `remove_from_shelf` | write | Shelves |
| `create_loan`, `return_loan` | write | Loans |

Write tools are listed only for tokens with `library:write`, which [the spec allows, since the list may vary by the authorization on the request](https://modelcontextprotocol.io/specification/2026-07-28/server/tools.md) (direct). Policy refuses them anyway. There are no delete or admin tools in `v0.1.0`, as a deliberate limit on automated damage.

## LibraryThing field mapping

**Decided:** the server and its tooling never contact LibraryThing. They read only files that users supply.

**In scope for `v0.1.0`:** JSON and tab-delimited import. Fields are mapped by header name, not position. The column mapping is written in Phase 5 from a real export, and it maps onto the data model above.

**Consequence for the acceptance criterion:** round-trip losslessness can be tested only on what LibreLibrary controls. Tests will prove:

1. A LibraryThing export imported, then exported in LibreLibrary's own format, keeps every mapped field.
2. A LibraryThing-format CSV written by LibreLibrary, then read back, keeps every field the format can carry.
3. A list of fields LibraryThing's import can't carry is published in the docs.

Importing a file into LibraryThing itself is a manual check by the maintainer, because automation is banned there.

### Generic export

JSON and CSV of everything a user owns, plus a full admin export, covering all personal records.

## Integrations plan

All are plugins using HTTP. Because identifier search can't be relied on across these servers, each adapter syncs into a local index, then matches on ISBN first and on normalized title and author second. A person confirms fuzzy matches.

| Server | License | Auth | Approach | Unverified |
|---|---|---|---|---|
| [Calibre](https://manual.calibre-ebook.com/server.html) | [GPLv3](https://raw.githubusercontent.com/kovidgoyal/calibre/master/LICENSE) | Digest or Basic | Content server. [Calibre's FAQ warns against sharing libraries or using network drives](https://manual.calibre-ebook.com/faq.html), so `metadata.db` is never written. The `/ajax` routes appear only in source, without a stated stability promise. | Whether Calibre's OPDS 2 code is in a release |
| [Calibre-Web](https://raw.githubusercontent.com/janeczku/calibre-web/master/README.md) | GPLv3 | OPDS Basic | OPDS feed. No REST API or identifier route found. | Identifier data in entries |
| [Kavita](https://wiki.kavitareader.com/guides/api/) | [GPLv3](https://raw.githubusercontent.com/Kareadita/Kavita/develop/LICENSE) | `x-api-key` | [OpenAPI spec](https://raw.githubusercontent.com/Kareadita/Kavita/develop/openapi.json) | Identifier search; spec only partly read |
| [Komga](https://komga.org/docs/openapi/komga-api/) | [MIT](https://raw.githubusercontent.com/gotson/komga/master/LICENSE) | Basic or `X-API-Key` | Metadata and thumbnails by book ID; ISBN is a metadata field | Whether full-text search covers ISBN |
| [Audiobookshelf](https://api.audiobookshelf.org/) | [GPLv3](https://raw.githubusercontent.com/advplyr/audiobookshelf/master/LICENSE) | Bearer token | `/api/libraries/ID/search`, `/api/items/ID/cover` | Its docs say they are unmaintained, and part was unread. Phase 9 tests against a running server. |

### OPDS

[OPDS 2.0 is a living standard and 1.2 is the previous release](https://specs.opds.io/). LibreLibrary serves both from one internal model, with [1.2's Atom feeds and OpenSearch](https://specs.opds.io/opds-1.2) and [2.0's JSON feeds](https://specs.opds.io/opds-2.0.md), using HTTP Basic over TLS first. The [authentication document is still a draft](https://drafts.opds.io/authentication-for-opds-1.0), so it comes later.

The [community validators are archived](https://github.com/opds-community), so "the feed validates" is defined as:

- 2.0 feeds pass the [feed](https://specs.opds.io/schema/feed.schema.json) and [publication](https://specs.opds.io/schema/publication.schema.json) JSON Schemas.
- 1.2 feeds are well-formed Atom with the required links and media types, per a project test.
- Manual open in [KOReader](https://raw.githubusercontent.com/koreader/koreader/master/plugins/opds.koplugin/opdsbrowser.lua) or [Thorium](https://www.edrlab.org/software/thorium-reader/).

Feeds link to catalog entries and to linked servers' acquisition URLs. LibreLibrary does not store ebook files.

### KOReader progress sync: feasible, with limits

- **No official spec exists.** The [third-party conformance spec](https://raw.githubusercontent.com/pid1/kosync-conformance/main/README.md) is CC0, but its `vectors/samples.lua` is AGPL and the [reference server](https://github.com/koreader/koreader-sync-server) is AGPL. Only the CC0 material is used.
- **Document hashes can't be derived from catalog data.** They are computed from the file's bytes, and LibreLibrary doesn't hold files. So progress for an unknown hash is stored, and the user links it to a book, with [optional client metadata](https://raw.githubusercontent.com/koreader/koreader/master/plugins/kosync.koplugin/main.lua) as a hint.
- **Credentials are sync-only,** because the client sends an MD5 of the password. [Komga's maintainer noted the same issue](https://github.com/gotson/komga/discussions/1760).

**Unverified:** how the client serializes metadata, and its default setting.

## Dependencies

Versions are the latest seen. Licenses are from package metadata, and from the license file where marked **(file)**.

### Run time

| Package | Version | License |
|---|---|---|
| fastapi | 0.162.0 | MIT |
| starlette | 1.10.0 | BSD-3-Clause |
| uvicorn | 0.54.0 | BSD-3-Clause |
| pydantic | 2.14.2 | MIT |
| pydantic-settings | 2.16.2 | MIT |
| SQLAlchemy | 2.1.6 | MIT |
| alembic | 1.20.1 | MIT |
| pg8000 | 1.31.6 | BSD-3-Clause |
| httpx | 0.28.1 | BSD-3-Clause |
| certifi (through httpx) | 2026.10.23 | MPL-2.0, approved exception |
| Authlib | 1.9.1 | BSD-3-Clause (file) |
| argon2-cffi | 25.1.0 | MIT |
| Jinja2 | 3.1.6 | BSD-3-Clause |
| structlog | 26.1.0 | MIT OR Apache-2.0 |
| limits | 5.8.0 | MIT |
| python-multipart | 0.0.33 | Apache-2.0 |
| mcp | 2.3.0 | MIT |
| pillow | 13.0.0 or later | MIT-CMU. [Version floor from a critical advisory](https://github.com/advisories/GHSA-5x8w-8jj5-q52h). |
| defusedxml | 0.7.1 | PSF. Last release 2021. |
| htmx.org | 2.0.11 | 0BSD (file) |
| barcode-detector | 3.2.3 | MIT |
| zxing-wasm | 3.1.6 | MIT |

Transitive licenses for the Python packages were sampled by a PyPI walk. Npm trees were not walked. The license check in Phase 1 is the authority.

### Development and CI

| Tool | Version | License |
|---|---|---|
| uv | 0.13.6 | MIT OR Apache-2.0 |
| nox | 2026.10.20 | Apache-2.0 |
| ruff | 0.17.3 | MIT |
| mypy | 2.4.1 | MIT; pulls in `pathspec`, an approved exception |
| pytest | 9.2.0 | MIT |
| pytest-cov, coverage | 7.1.0, 7.17.0 | MIT, Apache-2.0 |
| hypothesis | 6.170.14 | MPL-2.0, approved exception |
| schemathesis | 4.32.7 | MIT; pulls in hypothesis |
| pre-commit | 4.7.0 | MIT |
| pip-licenses | 5.5.5 | MIT (file) |
| actionlint (`actionlint-py`) | 1.7.12 | MIT |
| zizmor | 1.31.1 | MIT (file) |
| MkDocs | 1.6.1, kept below 2.0 | BSD-2-Clause; requires `pathspec`, an approved exception (direct) |
| mike | 2.2.0 | BSD-3-Clause |
| mkdocs-material | 9.8.0 | MIT (direct). [End of life 2027-05-05](https://raw.githubusercontent.com/squidfunk/mkdocs-material/master/README.md): evaluate [Zensical](https://zensical.org/upcoming-changes/) before that date. |
| Playwright | 1.64.1 | Apache-2.0 |
| axe-core | 4.14.0 | MPL-2.0 (file), approved exception |
| vitest | 5.0.5 | MIT, if frontend units need it |
| Grype, Syft | 0.121.0, 1.55.0 | Apache-2.0 |
| mock-oauth2-server | 6.1.4 | MIT |

**Sources:** Python packages at `https://pypi.org/pypi/NAME/json`, npm packages at `https://registry.npmjs.org/NAME`, and other tools on their GitHub release and license pages: [actionlint](https://github.com/rhysd/actionlint), [zizmor](https://github.com/zizmorcore/zizmor), [Grype](https://github.com/anchore/grype), [Syft](https://github.com/anchore/syft), and [mock-oauth2-server](https://github.com/navikt/mock-oauth2-server).

### License exceptions

Dependencies must be permissive, with one named exception list. The license check fails on any other MPL-2.0 package, and each addition needs the maintainer's approval. All must stay unmodified.

| Package | License | Where it is used |
|---|---|---|
| `pathspec` | MPL-2.0 | Development: MkDocs and mypy |
| `hypothesis` | MPL-2.0 | Development: tests |
| `axe-core` | MPL-2.0 | Development: accessibility tests |
| `certifi` | MPL-2.0 | Run time, through httpx, and the docs build. It is the only MPL-2.0 package in the image, and the docs list it. |

The [CodeQL engine](https://raw.githubusercontent.com/github/codeql-cli-binaries/main/LICENSE.md) is a second, separate exception: it is proprietary and used only in CI. Its terms cover automated analysis of open-source code hosted and maintained on GitHub.com, so check them before any change of forge, and drop CodeQL if they no longer fit.

### GitHub Actions

Commit SHAs are resolved in Phase 1 with `git ls-remote`. **Sources:** each action's page at `https://github.com/OWNER/ACTION/releases`, and its license through `https://api.github.com/repos/OWNER/ACTION/license`.

| Action | Tag seen | License |
|---|---|---|
| actions/checkout | v7.0.1 | MIT |
| actions/setup-python | v7.1.0 | MIT |
| astral-sh/setup-uv | v10.3.3 | MIT |
| docker/setup-qemu-action | v4.4.0 | Apache-2.0 |
| docker/setup-buildx-action | v4.4.1 | Apache-2.0 |
| docker/build-push-action | v7.4.0 | Apache-2.0 |
| docker/login-action | v4.7.0 | Apache-2.0 |
| docker/metadata-action | v6.2.0 | Apache-2.0 |
| github/codeql-action | v4.39.1 | MIT; the engine is proprietary, an approved exception |
| actions/dependency-review-action | v5.0.0 | MIT |
| ossf/scorecard-action | v2.5.0 | Apache-2.0 |
| anchore/scan-action | v7.4.2 | MIT |
| anchore/sbom-action | v0.24.3 | Apache-2.0 |
| [actions/attest](https://github.com/actions/attest) | v4.2.2 | MIT (direct) |
| sigstore/cosign-installer | v4.1.2 | Apache-2.0 |

## Repository layout

```text
.github/                 workflows, issue forms, templates, CODEOWNERS, labels.yml
docs/                    MkDocs site
    design/              this document
    maintainers/         release checklist, repository settings, labels
community-plugins/       community plugin library, one folder per plugin
migrations/              Alembic migrations (applied ones are never edited)
openapi/                 generated OpenAPI spec (never edited by hand)
src/librelibrary/
    api/v1/              REST routes
    ui/                  HTML routes, templates, static files
    services/            business logic, called by every surface
    authz/               policy module
    auth/                sessions, tokens, OIDC client, OAuth server
    models/              SQLAlchemy models
    plugin_api/          versioned plugin interfaces
    plugins/             built-in providers, importers, integrations
    mcp/                 MCP tools and transports
    opds/                OPDS feeds
    kosync/              KOReader sync routes
    isbn.py              ISBN validation and conversion
tests/                   unit, API, UI, contract, and migration tests
    fixtures/            synthetic or anonymized data only
noxfile.py               the one task runner
pyproject.toml, uv.lock  dependencies
Dockerfile, compose.yaml, .env.example
AGENTS.md, CLAUDE.md, CHANGELOG.md, CONTRIBUTING.md, CODE_OF_CONDUCT.md
SECURITY.md, SUPPORT.md, GOVERNANCE.md, LICENSE, README.md
```

## Test strategy

- **Unit:** services, ISBN code (property tests), mappers.
- **API:** every endpoint, on SQLite and PostgreSQL, with an authorization-denied test each. A contract test fails if a route lacks one. Schemathesis fuzzes the spec.
- **Authorization:** a matrix of roles, scopes, and privacy levels against each policy action.
- **UI:** Playwright for main journeys on phone and desktop sizes, and axe-core for automated accessibility checks. Automated checks can't prove WCAG 2.2 AA, so a manual keyboard and screen-reader pass is on the release checklist.
- **Parity:** the UI and API checks above, plus a check that every API route appears in the committed spec.
- **Plugin libraries:** refusal of bad hashes, declared dependencies, compiled wheels, incompatible versions, and paths that escape the folder. Each community plugin runs its own tests in CI against the current plugin interface.
- **MCP:** an SDK client over both transports, with read-only and write tokens.
- **OIDC:** mock provider with group-to-role mapping.
- **Round-trip:** the LibraryThing tests above, using synthetic fixtures shaped from the real export.
- **Migrations:** upgrade from empty and from each release's schema on both databases, and a check for model drift.
- **Container:** a smoke test waits for the healthcheck and confirms a non-root user.
- **Provider tests:** recorded responses, so CI makes no calls to providers.

## Project governance decisions

| Decision | Outcome | Reason |
|---|---|---|
| Task runner | **Decided:** nox | Apache-2.0, Python, and installs in the project virtualenv. [just](https://pypi.org/pypi/rust-just/json) is CC0 and needs a binary. |
| Merge strategy | **Decided for now:** squash or merge commit, chosen per PR, with the PR title as the Conventional Commit, linted in CI; rebase merges off. Revisit in Phase 10. | [GitHub signs the squash commit, and rebase merges aren't signature-verified](https://docs.github.com/en/authentication/managing-commit-signature-verification/about-commit-signature-verification). |
| Sign-off | **Decided:** DCO 1.1, humans only, checked by a nox session | [DCO text](https://developercertificate.org/). A nox check works on any forge, unlike the [DCO app](https://github.com/apps/dco). |
| AI-assisted contributions | **Decided:** allowed, with an `Assisted-by:` trailer, PR disclosure, and full human responsibility; agents never sign off | [LLVM's policy](https://releases.llvm.org/23.1.0/docs/_sources/AIToolPolicy.md.txt) is the model. See the note below. |
| Update bot | **Decided:** Dependabot | [MIT core](https://github.com/dependabot/dependabot-core), covers [uv, npm, Docker, and Actions](https://docs.github.com/en/code-security/dependabot/ecosystems-supported-by-dependabot/supported-ecosystems-and-repositories), and [regenerates `actions.lock`](https://github.blog/changelog/2026-10-28-github-actions-workflow-lockfiles-are-generally-available/). [Renovate is AGPL-3.0](https://github.com/renovatebot/renovate). **Unverified:** updates to digest-pinned `FROM` lines, and alerts on SHA-pinned actions. The maintainer confirms both after the first push. |
| Container scanner | **Decided:** Grype, with Syft for SBOMs | [Trivy's action tags were hijacked in March 2026](https://github.com/advisories/GHSA-69fq-xp46-6x23) (direct). Grype had a [past credential-disclosure advisory](https://github.com/advisories/GHSA-6gxw-85q2-q646), and the affected range is checked in Phase 1. |
| `edge` image tag | **Decided:** not before `v0.1.0` | Less to secure and support until then. |
| Docs hosting | **Decided:** GitHub Pages, versioned: each release publishes its version, each push to `main` updates a `dev` version, and the default is the latest release | Readers get docs for the version they run, and fixes show up early. Uses [mike](https://github.com/jimporter/mike) (BSD-3-Clause), which [Material supports](https://squidfunk.github.io/mkdocs-material/setup/setting-up-versioning/). **Costs:** mike publishes to a `gh-pages` branch, so that one job needs `contents: write`. mike declares Python up to 3.13, and Phase 1 checks its dependencies' licenses. **Unverified:** whether Zensical supports versioning this way; check when evaluating it. |
| Plugin SDK on PyPI | **Decided:** not during `0.x` | The interface will change, and publishing needs an account. |
| Docker Hub mirror | **Decided:** yes | Easier to discover. See [Image tags](#image-tags) for how the added secret is contained. |
| FUNDING file | **Decided:** not yet | Add it when there is something to fund. |

**Required signed commits (decided):** the repository requires them, and `CONTRIBUTING.md` explains SSH signing. [Unsigned head-branch commits can block a squash merge](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets), so the rule is relaxed if it proves a real barrier to contributors.

**On `Assisted-by`:** the [Linux kernel removed its `Assisted-by` rule on 2026-10-14](https://github.com/torvalds/linux/commit/1e035297ffdadf2184c3c773b8c098e372324aaf) (direct commit; reasons via summary) because too few commits carried it to be a reliable signal. Its [rule that only humans sign off stands](https://raw.githubusercontent.com/torvalds/linux/master/Documentation/process/coding-assistants.rst) (direct). So a missing trailer is not treated as proof of human authorship. Human responsibility is the real control, and the trailer is a courtesy to reviewers. [Docs.kernel.org still showed the old text](https://docs.kernel.org/process/coding-assistants.html). Fedora's policy could not be read (access blocked), so it is not cited.

**Other conventions:**

- [Semantic Versioning 2.0.0](https://semver.org/).
- [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/).
- [Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/).
- [Contributor Covenant 3.0](https://www.contributor-covenant.org/version/3/0/code_of_conduct/) (direct for "latest"). Its text is CC BY-SA 4.0, so it keeps its attribution, and the reporting contact is a placeholder for the maintainer.
- [AGENTS.md](https://agents.md/) is the one source of agent rules. [Claude Code's documented way to share it is `@AGENTS.md` in `CLAUDE.md`](https://code.claude.com/docs/en/memory), and paths resolve against the importing file. Files inside the project don't trigger the approval dialog for external imports.

## Workflows and hardening

As specified in the requirements. These facts shaped the details:

- **Pinning:** full commit SHAs with version comments, as [GitHub recommends](https://docs.github.com/en/actions/reference/security/secure-use). The repository setting [`sha_pinning_required`](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository) goes in the maintainer's settings list.
- **Proposed addition:** [`actions.lock`](https://docs.github.com/en/actions/concepts/security/workflow-dependency-lockfiles), generally available since 2026-10-28, also pins transitive actions. It would sit alongside SHAs, not replace them. **Unverified:** availability of the "require lockfile" policy on free plans.
- **Forks:** [`pull_request` runs from forks get no secrets and a read-only token](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows). No workflow uses `pull_request_target`.
- **Attestations:** [`actions/attest`](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations) for provenance and SBOM. [GitHub's action README says new work should use it](https://github.com/actions/attest-build-provenance). [This gives SLSA Build Level 2; Level 3 needs a reusable workflow](https://docs.github.com/en/actions/concepts/security/artifact-attestations).
- **Signing:** [cosign keyless with GitHub OIDC](https://github.com/sigstore/cosign-installer).
- **Forge neutrality:** every check is a nox session, and workflows only call them.
- **Security reporting:** [private vulnerability reporting](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/configure-vulnerability-reporting/configuring-private-vulnerability-reporting-for-a-repository) is enabled by the maintainer, and `SECURITY.md` points to it.
- **Community files:** [issue forms](https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/syntax-for-issue-forms) are still in public preview. The [community profile API](https://docs.github.com/en/rest/metrics/community) lists code of conduct, license, contributing, README, and issue and PR templates. **Unverified:** the exact checklist page. Security and support files are included regardless.

## Versioning and compatibility policy

The project uses Semantic Versioning 2.0.0, with tags `vX.Y.Z` and pre-releases `-alpha.N`, `-beta.N`, and `-rc.N`.

| Public surface | Breaking change | Versioned by |
|---|---|---|
| REST API | Removing or renaming a route or field, changing a type, requiring a new input, narrowing accepted values | URL (`/api/v1`) |
| Plugin interface | Removing or changing a method or context call a plugin relies on | `PLUGIN_API_VERSION` |
| Plugin library index | Removing or renaming a field, or changing its meaning | Index format version |
| MCP tools | Renaming or removing a tool, or an incompatible schema change | Project version, listed in the changelog |
| Environment and configuration | Removing or renaming a variable, or changing a default's meaning | Project version |
| OPDS feed | Moving a feed URL, or removing a required link | Project version |
| Database | Migrations are forward-only and automatic at startup. Back up before upgrading. Downgrades mean restoring a backup. | Project version |

Adding optional fields, routes, and tools isn't breaking. Clients must ignore unknown fields.

- **Deprecation:** warn for at least one minor release before removal, in the changelog and, where possible, at run time.
- **While at `0.x`:** a minor release may break a surface, with a `Changed` or `Removed` changelog note and upgrade steps, and the deprecation warning still applies where practical. A patch release never breaks a surface.
- **`1.0.0` rules:** breaking changes need a major release, and the REST API moves to `/api/v2` while `/api/v1` keeps working for a stated period.
- **Supported versions:** during `0.x`, only the latest minor gets fixes. `SECURITY.md` states the same.

## Release process

1. The maintainer moves `Unreleased` to a new version section and updates the version in the code, by a reviewed PR.
2. The maintainer pushes a signed tag `vX.Y.Z`.
3. `release.yml` refuses to run if the tag and code versions differ, or if the changelog section is missing.
4. It builds and pushes the multi-arch image to `ghcr.io/OWNER/librelibrary`, using `GITHUB_TOKEN`.
5. It generates an SBOM and provenance attestations, and signs by digest with keyless cosign.
6. A separate mirror job copies the image by digest to `docker.io/OWNER/librelibrary`.
7. It creates a GitHub Release with that version's changelog section as notes, and publishes the docs.

### Image tags

- `X.Y.Z` is immutable and never overwritten.
- **Docker Hub mirror:** GHCR is the primary registry. Docker Hub gets the same digests and tags, so signatures and attestations verify by digest. Only the mirror job can read the `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` secrets, through a protected `release` environment. No fork or PR build can reach them, and the job runs no project code. A mirror failure is reported and retried by hand; it doesn't undo the GHCR release. **Unverified:** the narrowest token scope Docker Hub offers, and whether signatures copy across unchanged. Phase 10 checks both.
- `X.Y`, `X`, and `latest` move on stable releases only. Pre-releases get only their exact tag.
- OCI labels: source, version, revision, licenses, documentation URL.
- Base images are pinned by digest.
- **Security rebuilds:** a new patch release, never a re-pushed tag.

## Phase plan

Every phase also meets the same end-of-phase checklist: checks pass, endpoints documented and tested, docs and changelog updated, `AGENTS.md` current, workflows clean under `actionlint` and `zizmor`, then a stop for review and commit.

| Phase | Deliverable | Acceptance criteria |
|---|---|---|
| 1. Scaffolding | Task runner, contributor docs, templates, hygiene files, `pre-commit`, `CHANGELOG.md`, update bot, `ci.yml`, security workflows | Each CI check runs through one nox session. Action SHAs are resolved and pinned. The license check enforces the approved allowlist. After the maintainer's first push, the maintainer confirms how Dependabot handles digests and SHA-pinned actions. |
| 2. Core | Data model, migrations, API, local sign-in with bearer tokens, tokens, policy layer | Both databases pass on 3.13 and 3.14, including pg8000. Spec drift check passes. Every endpoint has a denied test. |
| 3. Web UI | Cookie sessions and CSRF protection, full-text search, catalog, search, filter, sort, tags, shelves, status, ratings, reviews, notes, loans, bulk edit, themes | Parity tests pass. Axe finds no violations on main pages. Manual keyboard pass is done. |
| 4. Metadata and ISBN | Providers, covers, camera, scanner, batch entry | Typed and scanned ISBNs each add a book with a cover, using recorded responses. Rate limits are tested. A real camera scan is confirmed on a phone. |
| 5. LibraryThing | Import and export | Round-trip tests pass. Mapping is verified against the real export. Non-portable fields are documented. |
| 6. Multi-user and OIDC | Roles, privacy, household, OIDC client | Group-to-role mapping passes against the mock provider. The privacy matrix passes. Setup guides exist for Pocket ID, Authentik, Keycloak, and Authelia. |
| 7. Plugins | Versioned interface, loader, plugin libraries, community library | Built-ins use it, and the first community plugins have moved in. A sample plugin for each type passes. An incompatible plugin is refused without stopping startup. An admin can install from the shipped library with no network access, and from a third-party library by URL. A non-admin is refused. Unsafe wheels are refused. |
| 8. MCP | OAuth server, tools, both transports | Read-only tokens can't write. Write tokens can add books. Client compatibility is recorded. |
| 9. Ebook integrations | OPDS, KOReader sync, and server adapters in the community library | Schemas pass, a reader opens the feed, and each adapter runs against a real server image after an admin enables it. |
| 10. Release preparation | Docker, docs, `release.yml`, image strategy | All Final Acceptance Criteria pass, and the release path runs locally without publishing. |

## Proposed extras

None of these will be built without approval.

- `actions.lock` alongside SHA pins.
- Excel and MARC import, deferred past `v0.1.0`.
- An OPDS authentication document.
- A public, anonymous library page.
- SLSA Build Level 3 through a reusable workflow.
