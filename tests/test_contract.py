"""Contract tests: rules that every route and service must keep.

A new route fails here until it has an entry in DENIED_REQUESTS, which is what
makes "every endpoint has an authorization-denied test" enforced, not hoped for.
"""

import importlib
import inspect
import pkgutil
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import librelibrary.services
from librelibrary.app import create_app
from librelibrary.settings import Settings

from .conftest import MakeAccount

# Operation ID -> a request that would succeed or reach the database if allowed.
WORK = {"title": "A title"}
TEXT = {"text": "Some text"}
COPY = {"library_id": 1, "edition_id": 1}
LOAN = {"copy_id": 1, "borrower_id": 1, "lent": "2026-01-01"}
PASSWORDS = {"current_password": "old password", "new_password": "a new long password"}
USER = {"username": "new", "display_name": "New", "password": "a long password"}
READING = {"work_id": 1, "status": "reading"}

DENIED_REQUESTS: dict[str, tuple[str, str, Any]] = {
    "users_me_get": ("GET", "/users/me", None),
    "users_me_password_change": ("POST", "/users/me/password", PASSWORDS),
    "tokens_list": ("GET", "/tokens", None),
    "tokens_create": ("POST", "/tokens", {"name": "t", "scopes": []}),
    "tokens_delete": ("DELETE", "/tokens/1", None),
    "users_list": ("GET", "/users", None),
    "users_create": ("POST", "/users", USER),
    "users_get": ("GET", "/users/1", None),
    "users_update": ("PATCH", "/users/1", {"display_name": "Other"}),
    "works_list": ("GET", "/works", None),
    "works_create": ("POST", "/works", WORK),
    "works_get": ("GET", "/works/1", None),
    "works_update": ("PATCH", "/works/1", WORK),
    "works_delete": ("DELETE", "/works/1", None),
    "editions_list": ("GET", "/works/1/editions", None),
    "editions_create": ("POST", "/works/1/editions", {}),
    "editions_get": ("GET", "/editions/1", None),
    "editions_update": ("PATCH", "/editions/1", {}),
    "editions_delete": ("DELETE", "/editions/1", None),
    "people_list": ("GET", "/people", None),
    "people_create": ("POST", "/people", {"name": "A person"}),
    "people_get": ("GET", "/people/1", None),
    "people_update": ("PATCH", "/people/1", {"name": "Other"}),
    "people_delete": ("DELETE", "/people/1", None),
    "series_list": ("GET", "/series", None),
    "series_create": ("POST", "/series", {"name": "A series"}),
    "series_get": ("GET", "/series/1", None),
    "series_update": ("PATCH", "/series/1", {"name": "Other"}),
    "series_delete": ("DELETE", "/series/1", None),
    "libraries_list": ("GET", "/libraries", None),
    "libraries_create": ("POST", "/libraries", {"name": "Home"}),
    "libraries_get": ("GET", "/libraries/1", None),
    "libraries_update": ("PATCH", "/libraries/1", {"name": "Other"}),
    "libraries_delete": ("DELETE", "/libraries/1", None),
    "library_members_list": ("GET", "/libraries/1/members", None),
    "library_members_set": ("PUT", "/libraries/1/members/2", {"role": "viewer"}),
    "library_members_remove": ("DELETE", "/libraries/1/members/2", None),
    "copies_list": ("GET", "/copies", None),
    "copies_create": ("POST", "/copies", COPY),
    "copies_get": ("GET", "/copies/1", None),
    "copies_update": ("PATCH", "/copies/1", {"location": "Hall"}),
    "copies_delete": ("DELETE", "/copies/1", None),
    "copy_tags_list": ("GET", "/copies/1/tags", None),
    "copy_tags_set": ("PUT", "/copies/1/tags", {"names": ["fiction"]}),
    "tags_list": ("GET", "/libraries/1/tags", None),
    "tags_create": ("POST", "/libraries/1/tags", {"name": "fiction"}),
    "tags_delete": ("DELETE", "/tags/1", None),
    "copy_shelves_list": ("GET", "/copies/1/shelves", None),
    "shelves_list": ("GET", "/libraries/1/shelves", None),
    "shelves_create": ("POST", "/libraries/1/shelves", {"name": "Top"}),
    "shelves_get": ("GET", "/shelves/1", None),
    "shelves_update": ("PATCH", "/shelves/1", {"name": "Other"}),
    "shelves_delete": ("DELETE", "/shelves/1", None),
    "shelf_copies_list": ("GET", "/shelves/1/copies", None),
    "shelf_copies_add": ("PUT", "/shelves/1/copies/1", None),
    "shelf_copies_remove": ("DELETE", "/shelves/1/copies/1", None),
    "borrowers_list": ("GET", "/libraries/1/borrowers", None),
    "borrowers_create": ("POST", "/libraries/1/borrowers", {"name": "Friend"}),
    "borrowers_update": ("PATCH", "/borrowers/1", {"name": "Other"}),
    "borrowers_delete": ("DELETE", "/borrowers/1", None),
    "loans_list": ("GET", "/libraries/1/loans", None),
    "loans_create": ("POST", "/loans", LOAN),
    "loans_return": ("POST", "/loans/1/return", {"returned": "2026-02-01"}),
    "loans_delete": ("DELETE", "/loans/1", None),
    "reading_states_list": ("GET", "/reading-states", None),
    "reading_states_create": ("POST", "/reading-states", READING),
    "reading_states_update": ("PATCH", "/reading-states/1", {"status": "finished"}),
    "reading_states_delete": ("DELETE", "/reading-states/1", None),
    "ratings_list": ("GET", "/works/1/ratings", None),
    "ratings_set": ("PUT", "/works/1/rating", {"value": 5}),
    "ratings_delete": ("DELETE", "/works/1/rating", None),
    "reviews_list": ("GET", "/works/1/reviews", None),
    "reviews_create": ("POST", "/works/1/reviews", TEXT),
    "reviews_get": ("GET", "/reviews/1", None),
    "reviews_update": ("PATCH", "/reviews/1", TEXT),
    "reviews_delete": ("DELETE", "/reviews/1", None),
    "notes_list": ("GET", "/works/1/notes", None),
    "notes_create": ("POST", "/works/1/notes", TEXT),
    "notes_get": ("GET", "/notes/1", None),
    "notes_update": ("PATCH", "/notes/1", TEXT),
    "notes_delete": ("DELETE", "/notes/1", None),
    "libraries_transfer": ("POST", "/libraries/1/transfer", {"owner_id": 2}),
    "groups_list": ("GET", "/groups", None),
    "groups_list_all": ("GET", "/groups/all", None),
    "groups_create": ("POST", "/groups", {"name": "Friends"}),
    "groups_get": ("GET", "/groups/1", None),
    "groups_update": ("PATCH", "/groups/1", {"name": "Family"}),
    "groups_delete": ("DELETE", "/groups/1", None),
    "group_members_list": ("GET", "/groups/1/members", None),
    "group_members_add": ("PUT", "/groups/1/members/2", None),
    "group_members_remove": ("DELETE", "/groups/1/members/2", None),
    "group_libraries_list": ("GET", "/groups/1/libraries", None),
    "group_libraries_add": ("PUT", "/groups/1/libraries/1", None),
    "group_libraries_remove": ("DELETE", "/groups/1/libraries/1", None),
    "audit_events_list": ("GET", "/audit-events", None),
    "settings_list": ("GET", "/settings", None),
    "settings_set": ("PUT", "/settings/theme", {"value": "dark"}),
}

# Public by design; sign-in's denied tests are in test_auth.py.
NOT_BEARER_PROTECTED = {"health_get", "auth_login"}
ADMIN_ONLY = {
    "libraries_transfer",
    "groups_list_all",
    "groups_create",
    "groups_update",
    "groups_delete",
    "group_members_add",
    "group_members_remove",
    "users_list",
    "users_create",
    "users_get",
    "users_update",
    "works_delete",
    "editions_delete",
    "people_delete",
    "series_delete",
    "audit_events_list",
    "settings_list",
    "settings_set",
}
SERVICE_FUNCTIONS_WITHOUT_ACTOR = {
    "accounts.actor_for_token",
    "accounts.sign_in",
    "accounts.issue_login_token",
    "websessions.start",
    "websessions.csrf_matches",
    "websessions.actor_for_session",
    "websessions.end",
    "accounts.create_first_admin",
    "audit.record",
    "common.paginate",
    "common.get_or_404",
    "common.apply_changes",
}
PARAMETRIZED = sorted(DENIED_REQUESTS)


def spec_operations() -> dict[str, tuple[str, str]]:
    """Return every operation in the generated spec."""
    spec = create_app(Settings(database_url="sqlite://")).openapi()
    return {
        operation["operationId"]: (method.upper(), path)
        for path, methods in spec["paths"].items()
        for method, operation in methods.items()
    }


def send(client: TestClient, operation: str, headers: dict[str, str]) -> int:
    """Send an operation's request and return the status."""
    method, path, body = DENIED_REQUESTS[operation]
    response = client.request(method, f"/api/v1{path}", headers=headers, json=body)
    return int(response.status_code)


def test_every_operation_has_a_denied_request() -> None:
    """A route without a denied test fails the build."""
    expected = set(spec_operations()) - NOT_BEARER_PROTECTED
    assert expected == set(DENIED_REQUESTS)


def test_denied_requests_match_the_spec() -> None:
    """The table's methods and paths are real, so its tests can't pass by 404."""
    operations = spec_operations()
    for operation, (method, path, _body) in DENIED_REQUESTS.items():
        spec_method, template = operations[operation]
        assert method == spec_method, operation
        assert len(path.split("/")) == len(template.removeprefix("/api/v1").split("/"))


def test_only_health_and_sign_in_lack_a_bearer_requirement() -> None:
    """The spec tells clients which routes need a token."""
    spec = create_app(Settings(database_url="sqlite://")).openapi()
    open_operations = {
        operation["operationId"]
        for methods in spec["paths"].values()
        for operation in methods.values()
        if not operation.get("security")
    }
    assert open_operations == NOT_BEARER_PROTECTED


@pytest.mark.parametrize("operation", PARAMETRIZED)
def test_no_credentials_get_401(client: TestClient, operation: str) -> None:
    """Every protected operation refuses anonymous callers."""
    assert send(client, operation, {}) == 401


@pytest.mark.parametrize("operation", PARAMETRIZED)
def test_no_scopes_get_403(
    client: TestClient, make_account: MakeAccount, operation: str
) -> None:
    """Every operation refuses a token with no scopes, even an admin's."""
    account = make_account("admin", scopes=())
    assert send(client, operation, account.headers) == 403


@pytest.mark.parametrize(
    "operation",
    [name for name in PARAMETRIZED if DENIED_REQUESTS[name][0] != "GET"],
)
def test_read_tokens_cannot_write(
    client: TestClient, make_account: MakeAccount, operation: str
) -> None:
    """Every operation that changes data refuses a read-only token."""
    account = make_account("admin", scopes=("library:read",))
    assert send(client, operation, account.headers) == 403


@pytest.mark.parametrize("operation", sorted(ADMIN_ONLY))
def test_members_cannot_administer(
    client: TestClient, make_account: MakeAccount, operation: str
) -> None:
    """The admin scope doesn't help a user who isn't an admin."""
    account = make_account("member", scopes=("admin",))
    assert send(client, operation, account.headers) == 403


GUEST_ALLOWED = {
    "users_me_password_change",
    "tokens_create",
    "tokens_delete",
}


@pytest.mark.parametrize(
    "operation",
    [
        name
        for name in PARAMETRIZED
        if DENIED_REQUESTS[name][0] != "GET"
        and name not in GUEST_ALLOWED
        and name not in ADMIN_ONLY
    ],
)
def test_guests_cannot_change_library_data(
    client: TestClient, make_account: MakeAccount, operation: str
) -> None:
    """A guest is read-only, whatever scopes their token has."""
    account = make_account("guest")
    assert send(client, operation, account.headers) == 403


def _service_modules() -> list[str]:
    package = librelibrary.services
    return [module.name for module in pkgutil.iter_modules(package.__path__)]


def test_every_service_operation_declares_a_policy_action() -> None:
    """A service function that skips the policy layer fails the build."""
    missing = []
    for name in _service_modules():
        module = importlib.import_module(f"librelibrary.services.{name}")
        for function_name, function in inspect.getmembers(module, inspect.isfunction):
            if function_name.startswith("_"):
                continue
            if inspect.unwrap(function).__module__ != module.__name__:
                continue
            if f"{name}.{function_name}" in SERVICE_FUNCTIONS_WITHOUT_ACTOR:
                continue
            if not hasattr(function, "__policy_action__"):
                missing.append(f"{name}.{function_name}")
    assert missing == []


def test_app_has_no_unversioned_routes(app: FastAPI) -> None:
    """Everything lives under the versioned prefix."""
    paths = app.openapi()["paths"]
    assert all(path.startswith("/api/v1/") for path in paths)
