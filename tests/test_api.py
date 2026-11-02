"""Test what the API does, on the configured database."""

from dataclasses import dataclass
from typing import Any

import pytest
from fastapi.testclient import TestClient

from .conftest import Account, MakeAccount

API = "/api/v1"


@dataclass
class Api:
    """A small helper that sends authenticated requests."""

    client: TestClient

    def call(
        self,
        account: Account,
        method: str,
        path: str,
        body: Any = None,
        expect: int = 200,
    ) -> Any:
        """Send a request, check its status, and return its JSON."""
        response = self.client.request(
            method, API + path, headers=account.headers, json=body
        )
        assert response.status_code == expect, response.text
        return response.json() if response.content else None


@pytest.fixture
def api(client: TestClient) -> Api:
    """Give a test the helper."""
    return Api(client)


@pytest.fixture
def owner(make_account: MakeAccount) -> Account:
    """Give a test a user who owns a library."""
    return make_account()


def make_edition(api: Api, account: Account) -> int:
    """Create a work with one edition."""
    work = api.call(account, "POST", "/works", {"title": "Dune"}, 201)
    edition = api.call(account, "POST", f"/works/{work['id']}/editions", {}, 201)
    return int(edition["id"])


def make_library(api: Api, account: Account, **fields: Any) -> int:
    """Create a library."""
    body = {"name": "Home", **fields}
    return int(api.call(account, "POST", "/libraries", body, 201)["id"])


def make_copy(
    api: Api, account: Account, library: int, privacy: str = "personal"
) -> int:
    """Create a copy in a library."""
    body = {
        "library_id": library,
        "edition_id": make_edition(api, account),
        "privacy": privacy,
    }
    return int(api.call(account, "POST", "/copies", body, 201)["id"])


def join(api: Api, owner: Account, member: Account, library: int, role: str) -> None:
    """Add a member to a library."""
    path = f"/libraries/{library}/members/{member.id}"
    api.call(owner, "PUT", path, {"role": role})


# Catalog


def test_work_round_trip_with_related_records(api: Api, owner: Account) -> None:
    """A work keeps its contributors, subjects, class numbers, and series."""
    person = api.call(owner, "POST", "/people", {"name": "Frank Herbert"}, 201)
    series = api.call(owner, "POST", "/series", {"name": "Dune"}, 201)
    body = {
        "title": "Dune",
        "contributions": [{"person_id": person["id"], "role": "author"}],
        "subjects": [{"scheme": "LCSH", "label": "Science fiction"}],
        "classifications": [{"scheme": "DDC", "value": "813.54"}],
        "series_entries": [{"series_id": series["id"], "position": "1"}],
    }
    work = api.call(owner, "POST", "/works", body, 201)
    read = api.call(owner, "GET", f"/works/{work['id']}")
    assert read["contributions"][0]["person_id"] == person["id"]
    assert read["subjects"] == [{"scheme": "LCSH", "label": "Science fiction"}]
    assert read["classifications"] == [{"scheme": "DDC", "value": "813.54"}]
    assert read["series_entries"] == [{"series_id": series["id"], "position": "1"}]


def test_patching_a_list_replaces_it(api: Api, owner: Account) -> None:
    """Resending the same unique rows must not trip their constraints."""
    classes = [{"scheme": "DDC", "value": "813.54"}]
    body = {"title": "Dune", "classifications": classes}
    work = api.call(owner, "POST", "/works", body, 201)
    path = f"/works/{work['id']}"
    assert (
        api.call(owner, "PATCH", path, {"classifications": classes})["classifications"]
        == classes
    )
    assert (
        api.call(owner, "PATCH", path, {"classifications": []})["classifications"] == []
    )


def test_patch_leaves_unsent_fields_alone(api: Api, owner: Account) -> None:
    """Only the fields in the request change."""
    body = {"title": "Dune", "description": "Spice"}
    work = api.call(owner, "POST", "/works", body, 201)
    changed = api.call(owner, "PATCH", f"/works/{work['id']}", {"title": "Dune 2"})
    assert changed["description"] == "Spice"


def test_editions_replace_identifiers(api: Api, owner: Account) -> None:
    """Resending an identifier on its own edition isn't a conflict."""
    work = api.call(owner, "POST", "/works", {"title": "Dune"}, 201)
    ids = [{"scheme": "ISBN-13", "value": "9780000000002"}]
    edition = api.call(
        owner, "POST", f"/works/{work['id']}/editions", {"identifiers": ids}, 201
    )
    path = f"/editions/{edition['id']}"
    assert api.call(owner, "PATCH", path, {"identifiers": ids})["identifiers"] == ids


def test_duplicate_identifiers_conflict(api: Api, owner: Account) -> None:
    """An identifier belongs to one edition, on both databases."""
    work = api.call(owner, "POST", "/works", {"title": "Dune"}, 201)
    path = f"/works/{work['id']}/editions"
    body = {"identifiers": [{"scheme": "ISBN-13", "value": "9780000000002"}]}
    api.call(owner, "POST", path, body, 201)
    api.call(owner, "POST", path, body, 409)


def test_contribution_to_a_missing_person_conflicts(api: Api, owner: Account) -> None:
    """A bad foreign key is the caller's error, not a server error."""
    body = {"title": "Dune", "contributions": [{"person_id": 999999}]}
    api.call(owner, "POST", "/works", body, 409)


def test_search_treats_wildcards_literally(api: Api, owner: Account) -> None:
    """A percent sign in a search is just a percent sign."""
    api.call(owner, "POST", "/works", {"title": "100% Dune"}, 201)
    api.call(owner, "POST", "/works", {"title": "Plain"}, 201)
    assert api.call(owner, "GET", "/works?q=%25")["total"] == 1
    assert api.call(owner, "GET", "/works?q=dune")["total"] == 1


def test_lists_are_paged(api: Api, owner: Account) -> None:
    """A page reports the total across all pages."""
    for number in range(3):
        api.call(owner, "POST", "/series", {"name": f"Series {number}"}, 201)
    page = api.call(owner, "GET", "/series?limit=2&offset=2")
    assert (len(page["items"]), page["total"]) == (1, 3)


def test_deleting_an_edition_with_copies_conflicts(
    api: Api, owner: Account, make_account: MakeAccount
) -> None:
    """Shared records can't be deleted out from under someone's copy."""
    admin = make_account("admin", scopes=("admin",))
    library = make_library(api, owner)
    copy = make_copy(api, owner, library)
    edition = api.call(owner, "GET", f"/copies/{copy}")["edition_id"]
    api.call(admin, "DELETE", f"/editions/{edition}", expect=409)


def test_person_in_use_conflicts_on_delete(
    api: Api, owner: Account, make_account: MakeAccount
) -> None:
    """A credited person can't be deleted."""
    admin = make_account("admin", scopes=("admin",))
    person = api.call(owner, "POST", "/people", {"name": "Author"}, 201)
    body = {"title": "Dune", "contributions": [{"person_id": person["id"]}]}
    api.call(owner, "POST", "/works", body, 201)
    api.call(admin, "DELETE", f"/people/{person['id']}", expect=409)


# Libraries and roles


def test_new_library_belongs_to_its_creator(api: Api, owner: Account) -> None:
    """The creator gets a member row with the owner role."""
    library = make_library(api, owner)
    members = api.call(owner, "GET", f"/libraries/{library}/members")["items"]
    assert members == [
        {"user_id": owner.id, "role": "owner", "display_name": owner.username}
    ]


def test_non_members_cannot_learn_a_library_exists(
    api: Api, owner: Account, make_account: MakeAccount
) -> None:
    """A stranger's answer is the same as for a library that doesn't exist."""
    stranger = make_account()
    library = make_library(api, owner)
    api.call(stranger, "GET", f"/libraries/{library}", expect=404)
    api.call(stranger, "GET", "/libraries/999999", expect=404)
    api.call(stranger, "PATCH", f"/libraries/{library}", {"name": "Mine"}, 404)
    assert api.call(stranger, "GET", "/libraries")["items"] == []


def test_admins_cannot_read_other_peoples_libraries(
    api: Api, owner: Account, make_account: MakeAccount
) -> None:
    """Instance administration doesn't open personal records."""
    admin = make_account("admin", scopes=("library:read", "library:write", "admin"))
    library = make_library(api, owner)
    copy = make_copy(api, owner, library)
    api.call(admin, "GET", f"/libraries/{library}", expect=404)
    api.call(admin, "GET", f"/copies/{copy}", expect=404)


@pytest.mark.parametrize(
    ("role", "can_read", "can_edit", "can_manage"),
    [("viewer", 200, 403, 403), ("editor", 200, 201, 403)],
)
def test_member_roles(  # noqa: PLR0913
    api: Api,
    owner: Account,
    make_account: MakeAccount,
    role: str,
    can_read: int,
    can_edit: int,
    can_manage: int,
) -> None:
    """Viewers read, editors also edit, and only the owner manages."""
    member = make_account()
    library = make_library(api, owner)
    join(api, owner, member, library, role)
    api.call(member, "GET", f"/libraries/{library}", expect=can_read)
    api.call(member, "POST", f"/libraries/{library}/tags", {"name": "a"}, can_edit)
    api.call(member, "PATCH", f"/libraries/{library}", {"name": "b"}, can_manage)
    api.call(member, "DELETE", f"/libraries/{library}", expect=can_manage)


def test_library_owner_cannot_be_changed_or_removed(
    api: Api, owner: Account, make_account: MakeAccount
) -> None:
    """A library always keeps its one owner."""
    other = make_account()
    library = make_library(api, owner)
    own = f"/libraries/{library}/members/{owner.id}"
    api.call(owner, "PUT", own, {"role": "viewer"}, 409)
    api.call(owner, "DELETE", own, expect=409)
    theirs = f"/libraries/{library}/members/{other.id}"
    api.call(owner, "PUT", theirs, {"role": "owner"}, 409)


def test_removed_member_loses_access(
    api: Api, owner: Account, make_account: MakeAccount
) -> None:
    """Access ends with membership."""
    member = make_account()
    library = make_library(api, owner)
    join(api, owner, member, library, "viewer")
    api.call(owner, "DELETE", f"/libraries/{library}/members/{member.id}", expect=204)
    api.call(member, "GET", f"/libraries/{library}", expect=404)


def test_deleting_a_library_removes_its_loans(api: Api, owner: Account) -> None:
    """A library delete cascades through copies, borrowers, and loans."""
    library = make_library(api, owner)
    copy = make_copy(api, owner, library)
    borrower = api.call(
        owner, "POST", f"/libraries/{library}/borrowers", {"name": "Friend"}, 201
    )
    body = {"copy_id": copy, "borrower_id": borrower["id"], "lent": "2026-01-01"}
    api.call(owner, "POST", "/loans", body, 201)
    api.call(owner, "DELETE", f"/libraries/{library}", expect=204)
    api.call(owner, "GET", f"/copies/{copy}", expect=404)


def test_deleting_a_borrower_with_loans_conflicts(api: Api, owner: Account) -> None:
    """Loan history keeps its borrower until the loans are deleted."""
    library = make_library(api, owner)
    copy = make_copy(api, owner, library)
    borrower = api.call(
        owner, "POST", f"/libraries/{library}/borrowers", {"name": "Friend"}, 201
    )
    body = {"copy_id": copy, "borrower_id": borrower["id"], "lent": "2026-01-01"}
    loan = api.call(owner, "POST", "/loans", body, 201)
    api.call(owner, "DELETE", f"/borrowers/{borrower['id']}", expect=409)
    api.call(owner, "DELETE", f"/loans/{loan['id']}", expect=204)
    api.call(owner, "DELETE", f"/borrowers/{borrower['id']}", expect=204)


# The privacy matrix: (privacy, relationship) -> can they see it?

COPY_MATRIX = [
    ("personal", "owner", True),
    ("personal", "editor", True),
    ("personal", "viewer", False),
    ("personal", "group_member", False),
    ("personal", "stranger", False),
    ("library", "owner", True),
    ("library", "editor", True),
    ("library", "viewer", True),
    ("library", "group_member", False),
    ("library", "stranger", False),
    ("group", "owner", True),
    ("group", "editor", True),
    ("group", "viewer", True),
    ("group", "group_member", True),
    ("group", "stranger", False),
    ("server", "owner", True),
    ("server", "editor", True),
    ("server", "viewer", True),
    ("server", "group_member", True),
    ("server", "stranger", True),
]


def make_group(api: Api, make_account: MakeAccount, *members: Account) -> int:
    """Have an admin create a group with these members."""
    admin = make_account("admin", scopes=("admin",))
    group = api.call(admin, "POST", "/groups", {"name": f"Group {admin.id}"}, 201)["id"]
    for member in members:
        api.call(admin, "PUT", f"/groups/{group}/members/{member.id}", expect=204)
    return int(group)


@pytest.mark.parametrize(("privacy", "relation", "visible"), COPY_MATRIX)
def test_copy_privacy_matrix(  # noqa: PLR0913
    api: Api,
    owner: Account,
    make_account: MakeAccount,
    privacy: str,
    relation: str,
    visible: bool,
) -> None:
    """A copy's privacy decides who gets it, by ID and in lists."""
    library = make_library(api, owner)
    copy = make_copy(api, owner, library, privacy)
    reader = owner
    if relation == "group_member":
        reader = make_account()
        group = make_group(api, make_account, owner, reader)
        api.call(owner, "PUT", f"/groups/{group}/libraries/{library}", expect=204)
    elif relation != "owner":
        reader = make_account()
        if relation != "stranger":
            join(api, owner, reader, library, relation)
    api.call(reader, "GET", f"/copies/{copy}", expect=200 if visible else 404)
    listed = [item["id"] for item in api.call(reader, "GET", "/copies")["items"]]
    assert (copy in listed) is visible
    api.call(reader, "GET", f"/copies/{copy}/tags", expect=200 if visible else 404)


@pytest.mark.parametrize(
    ("setting", "editor_status"), [(True, 200), (False, 404), (None, 200)]
)
def test_library_setting_decides_if_editors_see_personal_copies(
    api: Api,
    owner: Account,
    make_account: MakeAccount,
    setting: bool | None,
    editor_status: int,
) -> None:
    """Each library chooses, and a viewer never sees a private copy either way."""
    fields = {} if setting is None else {"editors_see_personal": setting}
    library = make_library(api, owner, **fields)
    copy = make_copy(api, owner, library)
    editor, viewer = make_account(), make_account()
    join(api, owner, editor, library, "editor")
    join(api, owner, viewer, library, "viewer")
    api.call(owner, "GET", f"/copies/{copy}")
    api.call(editor, "GET", f"/copies/{copy}", expect=editor_status)
    api.call(editor, "PATCH", f"/copies/{copy}", {"location": "Hall"}, editor_status)
    api.call(viewer, "GET", f"/copies/{copy}", expect=404)


def test_turning_the_setting_off_hides_private_copies_at_once(
    api: Api, owner: Account, make_account: MakeAccount
) -> None:
    """The owner can change the setting, and it applies to existing copies."""
    library = make_library(api, owner)
    copy = make_copy(api, owner, library)
    editor = make_account()
    join(api, owner, editor, library, "editor")
    api.call(editor, "GET", f"/copies/{copy}")
    changes = {"editors_see_personal": False}
    api.call(editor, "PATCH", f"/libraries/{library}", changes, 403)
    api.call(owner, "PATCH", f"/libraries/{library}", changes)
    api.call(editor, "GET", f"/copies/{copy}", expect=404)


def test_setting_in_one_library_does_not_open_another(
    api: Api, owner: Account, make_account: MakeAccount
) -> None:
    """An editor of one library gets nothing from a different library."""
    open_library = make_library(api, owner)
    closed_library = make_library(api, owner, editors_see_personal=False)
    copy = make_copy(api, owner, closed_library)
    editor = make_account()
    join(api, owner, editor, open_library, "editor")
    api.call(editor, "GET", f"/copies/{copy}", expect=404)


RESPONSE_MATRIX = [
    ("personal", "author", True),
    ("personal", "insider", False),
    ("personal", "stranger", False),
    ("library", "author", True),
    ("library", "insider", True),
    ("library", "stranger", False),
    ("group", "author", True),
    ("group", "insider", True),
    ("group", "stranger", False),
    ("server", "author", True),
    ("server", "insider", True),
    ("server", "stranger", True),
]


def audience_for(
    api: Api,
    make_account: MakeAccount,
    author: Account,
    privacy: str,
    insider: Account,
) -> dict[str, int]:
    """Create the audience a privacy level needs, with the insider in it."""
    if privacy == "group":
        group = make_group(api, make_account, author, insider)
        return {"audience_group_id": group}
    library = make_library(api, author)
    join(api, author, insider, library, "viewer")
    return {"audience_library_id": library} if privacy == "library" else {}


@pytest.mark.parametrize("kind", ["reviews", "notes"])
@pytest.mark.parametrize(("privacy", "relation", "visible"), RESPONSE_MATRIX)
def test_response_privacy_matrix(  # noqa: PLR0913
    api: Api,
    owner: Account,
    make_account: MakeAccount,
    kind: str,
    privacy: str,
    relation: str,
    visible: bool,
) -> None:
    """A review's or note's level and audience decide who can read it."""
    insider, stranger = make_account(), make_account()
    audience = audience_for(api, make_account, owner, privacy, insider)
    work = api.call(owner, "POST", "/works", {"title": "Dune"}, 201)["id"]
    body = {"text": "Good", "privacy": privacy, **audience}
    record = api.call(owner, "POST", f"/works/{work}/{kind}", body, 201)["id"]
    reader = {"author": owner, "insider": insider, "stranger": stranger}[relation]
    api.call(reader, "GET", f"/{kind}/{record}", expect=200 if visible else 404)
    listed = api.call(reader, "GET", f"/works/{work}/{kind}")["items"]
    assert (record in [item["id"] for item in listed]) is visible


@pytest.mark.parametrize(("privacy", "relation", "visible"), RESPONSE_MATRIX)
def test_rating_privacy_matrix(  # noqa: PLR0913
    api: Api,
    owner: Account,
    make_account: MakeAccount,
    privacy: str,
    relation: str,
    visible: bool,
) -> None:
    """A rating's level and audience decide who can see it in the list."""
    insider, stranger = make_account(), make_account()
    audience = audience_for(api, make_account, owner, privacy, insider)
    work = api.call(owner, "POST", "/works", {"title": "Dune"}, 201)["id"]
    body = {"value": 8, "privacy": privacy, **audience}
    api.call(owner, "PUT", f"/works/{work}/rating", body)
    reader = {"author": owner, "insider": insider, "stranger": stranger}[relation]
    assert bool(api.call(reader, "GET", f"/works/{work}/ratings")["total"]) is visible


# Prices


def test_price_keeps_two_decimal_places_exactly(api: Api, owner: Account) -> None:
    """A value that binary floats can't hold comes back unchanged."""
    library = make_library(api, owner)
    copy = make_copy(api, owner, library)
    path = f"/copies/{copy}"
    body = {"price": "12.99", "currency": "USD"}
    assert api.call(owner, "PATCH", path, body)["price"] == "12.99"
    assert api.call(owner, "GET", path)["price"] == "12.99"
    assert api.call(owner, "PATCH", path, {"price": 0.1})["price"] == "0.10"
    assert api.call(owner, "PATCH", path, {"price": "1000"})["price"] == "1000.00"
    assert api.call(owner, "PATCH", path, {"price": None})["price"] is None


@pytest.mark.parametrize("price", ["1.999", "-1.00", "NaN", "Infinity", "1e30"])
def test_bad_prices_are_refused(api: Api, owner: Account, price: str) -> None:
    """A price has at most two decimal places and can't be negative."""
    library = make_library(api, owner)
    copy = make_copy(api, owner, library)
    api.call(owner, "PATCH", f"/copies/{copy}", {"price": price}, 422)


def test_largest_price_fits_on_both_databases(api: Api, owner: Account) -> None:
    """The top of the accepted range is stored without error."""
    library = make_library(api, owner)
    copy = make_copy(api, owner, library)
    body = {"price": "9999999999.99"}
    assert api.call(owner, "PATCH", f"/copies/{copy}", body)["price"] == "9999999999.99"


# Audiences and groups


@pytest.mark.parametrize("privacy", ["library", "group"])
def test_shared_levels_need_an_audience(api: Api, owner: Account, privacy: str) -> None:
    """Nothing reaches a library or group by accident."""
    work = api.call(owner, "POST", "/works", {"title": "Dune"}, 201)["id"]
    body = {"text": "Good", "privacy": privacy}
    api.call(owner, "POST", f"/works/{work}/reviews", body, 409)


def test_cannot_share_to_a_library_you_are_not_in(
    api: Api, owner: Account, make_account: MakeAccount
) -> None:
    """An audience must be one you belong to."""
    other = make_account()
    library = make_library(api, other)
    work = api.call(owner, "POST", "/works", {"title": "Dune"}, 201)["id"]
    body = {"text": "Good", "privacy": "library", "audience_library_id": library}
    api.call(owner, "POST", f"/works/{work}/reviews", body, 404)


def test_cannot_share_to_a_group_you_are_not_in(
    api: Api, owner: Account, make_account: MakeAccount
) -> None:
    """Admins' groups aren't open to everyone."""
    group = make_group(api, make_account)
    work = api.call(owner, "POST", "/works", {"title": "Dune"}, 201)["id"]
    body = {"text": "Good", "privacy": "group", "audience_group_id": group}
    api.call(owner, "POST", f"/works/{work}/reviews", body, 404)


def test_patch_to_personal_clears_the_audience(
    api: Api, owner: Account, make_account: MakeAccount
) -> None:
    """Pulling a review back removes it from its audience."""
    insider = make_account()
    group = make_group(api, make_account, owner, insider)
    work = api.call(owner, "POST", "/works", {"title": "Dune"}, 201)["id"]
    body = {"text": "Good", "privacy": "group", "audience_group_id": group}
    review = api.call(owner, "POST", f"/works/{work}/reviews", body, 201)
    api.call(insider, "GET", f"/reviews/{review['id']}")
    changed = api.call(
        owner, "PATCH", f"/reviews/{review['id']}", {"privacy": "personal"}
    )
    assert changed["audience_group_id"] is None
    api.call(insider, "GET", f"/reviews/{review['id']}", expect=404)


def test_patch_cannot_share_to_a_group_you_left(
    api: Api, owner: Account, make_account: MakeAccount
) -> None:
    """Changing the audience checks membership again."""
    other_group = make_group(api, make_account)
    work = api.call(owner, "POST", "/works", {"title": "Dune"}, 201)["id"]
    review = api.call(owner, "POST", f"/works/{work}/reviews", {"text": "Good"}, 201)
    body = {"privacy": "group", "audience_group_id": other_group}
    api.call(owner, "PATCH", f"/reviews/{review['id']}", body, 404)


def test_removed_group_member_loses_access_at_once(
    api: Api, owner: Account, make_account: MakeAccount
) -> None:
    """Membership decides access on every request."""
    admin = make_account("admin", scopes=("admin",))
    reader = make_account()
    group = api.call(admin, "POST", "/groups", {"name": "Friends"}, 201)["id"]
    for member in (owner, reader):
        api.call(admin, "PUT", f"/groups/{group}/members/{member.id}", expect=204)
    work = api.call(owner, "POST", "/works", {"title": "Dune"}, 201)["id"]
    body = {"text": "Good", "privacy": "group", "audience_group_id": group}
    review = api.call(owner, "POST", f"/works/{work}/reviews", body, 201)["id"]
    api.call(reader, "GET", f"/reviews/{review}")
    api.call(admin, "DELETE", f"/groups/{group}/members/{reader.id}", expect=204)
    api.call(reader, "GET", f"/reviews/{review}", expect=404)


def test_author_who_leaves_a_group_stays_shared_and_can_edit(
    api: Api, owner: Account, make_account: MakeAccount
) -> None:
    """Leaving doesn't delete what someone wrote there."""
    admin = make_account("admin", scopes=("admin",))
    reader = make_account()
    group = api.call(admin, "POST", "/groups", {"name": "Friends"}, 201)["id"]
    for member in (owner, reader):
        api.call(admin, "PUT", f"/groups/{group}/members/{member.id}", expect=204)
    work = api.call(owner, "POST", "/works", {"title": "Dune"}, 201)["id"]
    body = {"text": "Good", "privacy": "group", "audience_group_id": group}
    review = api.call(owner, "POST", f"/works/{work}/reviews", body, 201)["id"]
    api.call(admin, "DELETE", f"/groups/{group}/members/{owner.id}", expect=204)
    api.call(reader, "GET", f"/reviews/{review}")
    api.call(owner, "PATCH", f"/reviews/{review}", {"text": "Better"})


def test_deactivated_authors_records_stop_being_shared(
    api: Api, owner: Account, make_account: MakeAccount
) -> None:
    """Deactivating an account takes its shared writing out of view."""
    admin = make_account("admin", scopes=("admin",))
    reader = make_account()
    work = api.call(owner, "POST", "/works", {"title": "Dune"}, 201)["id"]
    body = {"text": "Good", "privacy": "server"}
    review = api.call(owner, "POST", f"/works/{work}/reviews", body, 201)["id"]
    api.call(reader, "GET", f"/reviews/{review}")
    api.call(admin, "PATCH", f"/users/{owner.id}", {"is_active": False})
    api.call(reader, "GET", f"/reviews/{review}", expect=404)


def test_deleting_a_group_leaves_its_records_with_their_authors(
    api: Api, owner: Account, make_account: MakeAccount
) -> None:
    """With no audience left, a group record is visible only to its author."""
    admin = make_account("admin", scopes=("admin",))
    reader = make_account()
    group = api.call(admin, "POST", "/groups", {"name": "Friends"}, 201)["id"]
    for member in (owner, reader):
        api.call(admin, "PUT", f"/groups/{group}/members/{member.id}", expect=204)
    work = api.call(owner, "POST", "/works", {"title": "Dune"}, 201)["id"]
    body = {"text": "Good", "privacy": "group", "audience_group_id": group}
    review = api.call(owner, "POST", f"/works/{work}/reviews", body, 201)["id"]
    api.call(admin, "DELETE", f"/groups/{group}", expect=204)
    api.call(owner, "GET", f"/reviews/{review}")
    api.call(reader, "GET", f"/reviews/{review}", expect=404)


def test_only_a_library_owner_in_the_group_can_add_the_library(
    api: Api, owner: Account, make_account: MakeAccount
) -> None:
    """A library joins a group only by its owner's choice, and only their group."""
    editor = make_account()
    library = make_library(api, owner)
    join(api, owner, editor, library, "editor")
    group = make_group(api, make_account, editor)
    path = f"/groups/{group}/libraries/{library}"
    api.call(editor, "PUT", path, expect=403)
    api.call(owner, "PUT", path, expect=404)


def test_library_owner_or_admin_can_take_a_library_out_of_a_group(
    api: Api, owner: Account, make_account: MakeAccount
) -> None:
    """Members can't remove someone else's library."""
    admin = make_account("admin", scopes=("library:write", "admin"))
    member = make_account()
    library = make_library(api, owner)
    group = make_group(api, make_account, owner, member)
    path = f"/groups/{group}/libraries/{library}"
    api.call(owner, "PUT", path, expect=204)
    api.call(member, "DELETE", path, expect=403)
    api.call(owner, "DELETE", path, expect=204)
    api.call(owner, "PUT", path, expect=204)
    api.call(admin, "DELETE", path, expect=204)


def test_groups_are_listed_only_for_their_members(
    api: Api, owner: Account, make_account: MakeAccount
) -> None:
    """A stranger can't see a group, its members, or its libraries."""
    stranger = make_account()
    library = make_library(api, owner)
    group = make_group(api, make_account, owner)
    api.call(owner, "PUT", f"/groups/{group}/libraries/{library}", expect=204)
    assert api.call(owner, "GET", "/groups")["total"] == 1
    assert api.call(stranger, "GET", "/groups")["total"] == 0
    for suffix in ("", "/members", "/libraries"):
        api.call(stranger, "GET", f"/groups/{group}{suffix}", expect=404)
    members = api.call(owner, "GET", f"/groups/{group}/members")["items"]
    assert [item["user_id"] for item in members] == [owner.id]
    libraries = api.call(owner, "GET", f"/groups/{group}/libraries")["items"]
    assert [item["library_id"] for item in libraries] == [library]


def test_admin_manages_groups_without_reading_their_records(
    api: Api, owner: Account, make_account: MakeAccount
) -> None:
    """Managing a group gives no access to what is shared in it."""
    admin = make_account("admin", scopes=("library:read", "admin"))
    group = api.call(admin, "POST", "/groups", {"name": "Friends"}, 201)["id"]
    api.call(admin, "PUT", f"/groups/{group}/members/{owner.id}", expect=204)
    assert api.call(admin, "GET", "/groups/all")["total"] == 1
    api.call(admin, "PATCH", f"/groups/{group}", {"name": "Family"})
    assert api.call(admin, "GET", f"/groups/{group}/members")["total"] == 1
    work = api.call(owner, "POST", "/works", {"title": "Dune"}, 201)["id"]
    body = {"text": "Good", "privacy": "group", "audience_group_id": group}
    review = api.call(owner, "POST", f"/works/{work}/reviews", body, 201)["id"]
    api.call(admin, "GET", f"/reviews/{review}", expect=404)


# Ownership transfer


def test_admin_can_transfer_a_stranded_library(
    api: Api, owner: Account, make_account: MakeAccount
) -> None:
    """A library doesn't get stuck when its owner leaves."""
    admin = make_account("admin", scopes=("admin",))
    heir = make_account()
    library = make_library(api, owner)
    path = f"/libraries/{library}/transfer"
    moved = api.call(admin, "POST", path, {"owner_id": heir.id})
    assert moved["owner_id"] == heir.id
    api.call(heir, "PATCH", f"/libraries/{library}", {"name": "Mine now"})
    api.call(owner, "PATCH", f"/libraries/{library}", {"name": "Back"}, 403)
    members = api.call(heir, "GET", f"/libraries/{library}/members")["items"]
    roles = {item["user_id"]: item["role"] for item in members}
    assert roles == {heir.id: "owner", owner.id: "editor"}
    events = api.call(admin, "GET", "/audit-events")["items"]
    assert events[0]["action"] == "library_transferred"


def test_transfer_needs_an_active_user(
    api: Api, owner: Account, make_account: MakeAccount
) -> None:
    """Ownership can't move to an account that can't use it."""
    admin = make_account("admin", scopes=("admin",))
    gone = make_account()
    api.call(admin, "PATCH", f"/users/{gone.id}", {"is_active": False})
    library = make_library(api, owner)
    path = f"/libraries/{library}/transfer"
    api.call(admin, "POST", path, {"owner_id": gone.id}, 409)
    api.call(admin, "POST", path, {"owner_id": 999999}, 404)


# Cross-record checks


def test_visible_reviews_can_only_be_changed_by_their_author(
    api: Api, owner: Account, make_account: MakeAccount
) -> None:
    """Being able to read a review doesn't let you edit it."""
    other = make_account()
    work = api.call(owner, "POST", "/works", {"title": "Dune"}, 201)["id"]
    body = {"text": "Good", "privacy": "server"}
    review = api.call(owner, "POST", f"/works/{work}/reviews", body, 201)["id"]
    api.call(other, "PATCH", f"/reviews/{review}", {"text": "Bad"}, 403)
    api.call(other, "DELETE", f"/reviews/{review}", expect=403)


def test_reading_states_are_personal(
    api: Api, owner: Account, make_account: MakeAccount
) -> None:
    """Someone else's reading looks like it doesn't exist."""
    other = make_account()
    work = api.call(owner, "POST", "/works", {"title": "Dune"}, 201)["id"]
    body = {"work_id": work, "status": "reading"}
    state = api.call(owner, "POST", "/reading-states", body, 201)["id"]
    assert api.call(other, "GET", "/reading-states")["total"] == 0
    api.call(other, "PATCH", f"/reading-states/{state}", {"status": "want"}, 404)
    api.call(other, "DELETE", f"/reading-states/{state}", expect=404)


def test_several_readings_of_a_work_are_allowed(api: Api, owner: Account) -> None:
    """Rereading is normal."""
    work = api.call(owner, "POST", "/works", {"title": "Dune"}, 201)["id"]
    body = {"work_id": work, "status": "finished"}
    api.call(owner, "POST", "/reading-states", body, 201)
    api.call(owner, "POST", "/reading-states", body, 201)
    assert api.call(owner, "GET", f"/reading-states?work_id={work}")["total"] == 2


def test_rating_is_replaced_not_duplicated(api: Api, owner: Account) -> None:
    """A user has one rating per work."""
    work = api.call(owner, "POST", "/works", {"title": "Dune"}, 201)["id"]
    path = f"/works/{work}/rating"
    api.call(owner, "PUT", path, {"value": 4})
    assert api.call(owner, "PUT", path, {"value": 9})["value"] == 9
    assert api.call(owner, "GET", f"/works/{work}/ratings")["total"] == 1
    api.call(owner, "PUT", path, {"value": 11}, 422)


def test_loan_cannot_use_another_librarys_borrower(
    api: Api, owner: Account, make_account: MakeAccount
) -> None:
    """IDs from a library you don't control can't be mixed into yours."""
    other = make_account()
    other_library = make_library(api, other)
    theirs = api.call(
        other, "POST", f"/libraries/{other_library}/borrowers", {"name": "Them"}, 201
    )
    library = make_library(api, owner)
    copy = make_copy(api, owner, library)
    body = {"copy_id": copy, "borrower_id": theirs["id"], "lent": "2026-01-01"}
    api.call(owner, "POST", "/loans", body, 404)


def test_loan_cannot_lend_a_copy_you_cannot_edit(
    api: Api, owner: Account, make_account: MakeAccount
) -> None:
    """An instance-visible copy isn't yours to lend."""
    other = make_account()
    other_library = make_library(api, other)
    borrower = api.call(
        other, "POST", f"/libraries/{other_library}/borrowers", {"name": "Them"}, 201
    )
    library = make_library(api, owner)
    copy = make_copy(api, owner, library, "server")
    body = {"copy_id": copy, "borrower_id": borrower["id"], "lent": "2026-01-01"}
    api.call(other, "POST", "/loans", body, 404)
    api.call(other, "PATCH", f"/copies/{copy}", {"location": "Mine"}, 404)
    api.call(other, "DELETE", f"/copies/{copy}", expect=404)


def test_shelf_only_holds_its_own_librarys_copies(api: Api, owner: Account) -> None:
    """A copy from another library can't go on a shelf."""
    first, second = make_library(api, owner), make_library(api, owner)
    shelf = api.call(owner, "POST", f"/libraries/{first}/shelves", {"name": "Top"}, 201)
    copy = make_copy(api, owner, second)
    api.call(owner, "PUT", f"/shelves/{shelf['id']}/copies/{copy}", expect=409)


def test_shelf_hides_private_copies_from_viewers(
    api: Api, owner: Account, make_account: MakeAccount
) -> None:
    """A shelf's list follows each copy's privacy."""
    viewer = make_account()
    library = make_library(api, owner)
    join(api, owner, viewer, library, "viewer")
    shelf = api.call(owner, "POST", f"/libraries/{library}/shelves", {"name": "T"}, 201)
    copy = make_copy(api, owner, library)
    api.call(owner, "PUT", f"/shelves/{shelf['id']}/copies/{copy}", expect=204)
    path = f"/shelves/{shelf['id']}/copies"
    assert api.call(owner, "GET", path)["total"] == 1
    assert api.call(viewer, "GET", path)["total"] == 0


def test_viewers_cannot_see_borrowers_or_loans(
    api: Api, owner: Account, make_account: MakeAccount
) -> None:
    """Borrowers' contact details are for editors and the owner."""
    viewer = make_account()
    library = make_library(api, owner)
    join(api, owner, viewer, library, "viewer")
    api.call(viewer, "GET", f"/libraries/{library}/borrowers", expect=403)
    api.call(viewer, "GET", f"/libraries/{library}/loans", expect=403)


def test_a_copy_has_one_open_loan(api: Api, owner: Account) -> None:
    """Returning a loan lets the copy be lent again."""
    library = make_library(api, owner)
    copy = make_copy(api, owner, library)
    borrower = api.call(
        owner, "POST", f"/libraries/{library}/borrowers", {"name": "Friend"}, 201
    )
    body = {"copy_id": copy, "borrower_id": borrower["id"], "lent": "2026-01-01"}
    loan = api.call(owner, "POST", "/loans", body, 201)
    api.call(owner, "POST", "/loans", body, 409)
    returned = {"returned": "2026-02-01"}
    api.call(owner, "POST", f"/loans/{loan['id']}/return", returned)
    api.call(owner, "POST", f"/loans/{loan['id']}/return", returned, 409)
    api.call(owner, "POST", "/loans", body, 201)


def test_copy_tags_replace_and_stay_in_their_library(api: Api, owner: Account) -> None:
    """Tags are per library, and a set replaces the old one."""
    library = make_library(api, owner)
    copy = make_copy(api, owner, library)
    path = f"/copies/{copy}/tags"
    api.call(owner, "PUT", path, {"names": ["a", "b", "a"]})
    tags = api.call(owner, "PUT", path, {"names": ["b", "c"]})
    assert [tag["name"] for tag in tags] == ["b", "c"]
    assert api.call(owner, "GET", f"/libraries/{library}/tags")["total"] == 3


# Administration


def test_admin_creates_a_user_who_can_sign_in(
    api: Api, client: TestClient, make_account: MakeAccount
) -> None:
    """Accounts come from admins; there is no open registration."""
    admin = make_account("admin", scopes=("admin",))
    body = {
        "username": "NewUser",
        "display_name": "New",
        "password": "a long password",
    }
    created = api.call(admin, "POST", "/users", body, 201)
    assert created["username"] == "newuser"
    assert "password" not in str(created)
    login = {"username": "newuser", "password": "a long password"}
    assert client.post(f"{API}/auth/login", json=login).status_code == 201


def test_short_passwords_are_refused(make_account: MakeAccount, api: Api) -> None:
    """New passwords need at least 12 characters."""
    admin = make_account("admin", scopes=("admin",))
    body = {"username": "a", "display_name": "A", "password": "short"}
    api.call(admin, "POST", "/users", body, 422)


def test_duplicate_usernames_conflict(make_account: MakeAccount, api: Api) -> None:
    """Usernames differing only by case are the same user."""
    admin = make_account("admin", scopes=("admin",))
    body = {"username": "same", "display_name": "A", "password": "a long password"}
    api.call(admin, "POST", "/users", body, 201)
    api.call(admin, "POST", "/users", {**body, "username": "SAME"}, 409)


@pytest.mark.parametrize("change", [{"role": "member"}, {"is_active": False}])
def test_the_last_admin_cannot_be_removed(
    make_account: MakeAccount, api: Api, change: dict[str, Any]
) -> None:
    """An instance always keeps one active admin."""
    admin = make_account("admin", scopes=("admin",))
    api.call(admin, "PATCH", f"/users/{admin.id}", change, 409)


def test_a_second_admin_can_be_demoted(make_account: MakeAccount, api: Api) -> None:
    """The check counts active admins."""
    admin = make_account("admin", scopes=("admin",))
    other = make_account("admin", scopes=("admin",))
    api.call(admin, "PATCH", f"/users/{other.id}", {"role": "member"})
    api.call(other, "GET", "/users", expect=403)


def test_admin_password_reset_ends_tokens(make_account: MakeAccount, api: Api) -> None:
    """A reset password stops whoever had the old credentials."""
    admin = make_account("admin", scopes=("admin",))
    member = make_account()
    body = {"password": "a replacement password"}
    api.call(admin, "PATCH", f"/users/{member.id}", body)
    api.call(member, "GET", "/users/me", expect=401)


def test_audit_trail_records_admin_changes_without_secrets(
    make_account: MakeAccount, api: Api
) -> None:
    """Admins can see what changed, and never a password."""
    admin = make_account("admin", scopes=("admin",))
    member = make_account()
    body = {"password": "a replacement password"}
    api.call(admin, "PATCH", f"/users/{member.id}", body)
    events = api.call(admin, "GET", "/audit-events")["items"]
    assert events[0]["action"] == "user_updated"
    assert events[0]["detail"] == {"fields": ["password"]}
    assert "replacement" not in str(events)


def test_settings_round_trip(make_account: MakeAccount, api: Api) -> None:
    """Admins can set a run-time setting and read it back."""
    admin = make_account("admin", scopes=("admin",))
    api.call(admin, "PUT", "/settings/theme", {"value": "dark"})
    api.call(admin, "PUT", "/settings/theme", {"value": {"name": "light"}})
    items = api.call(admin, "GET", "/settings")["items"]
    assert [(item["key"], item["value"]) for item in items] == [
        ("theme", {"name": "light"})
    ]


@pytest.mark.parametrize("value", ["a\x00b"])
def test_nul_characters_are_refused(api: Api, owner: Account, value: str) -> None:
    """PostgreSQL can't store NUL, so both databases refuse it up front."""
    api.call(owner, "POST", "/works", {"title": value}, 422)


def test_huge_ids_are_refused(api: Api, owner: Account) -> None:
    """An ID beyond the column's range gets 422, not a database error."""
    api.call(owner, "GET", f"/works/{2**40}", expect=422)
