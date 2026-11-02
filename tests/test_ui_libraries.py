"""Test the library pages: list, create, detail, edit, and delete."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from librelibrary.models import Copy, Library, LibraryMember

from .ui_support import Person, Scene, sign_in

GET_PAGES = [
    "/libraries",
    "/libraries/new",
    "/libraries/1",
    "/libraries/1/edit",
    "/copies/new?edition_id=1",
    "/copies/1",
    "/copies/1/edit",
    "/works/1/editions/new",
]
POST_PAGES = [
    "/libraries/new",
    "/libraries/1/edit",
    "/libraries/1/delete",
    "/copies/new",
    "/copies/1/edit",
    "/copies/1/delete",
    "/works/1/editions/new",
]


@pytest.mark.parametrize("path", GET_PAGES)
def test_pages_need_a_session(browser: TestClient, path: str) -> None:
    """Every new page sends visitors to the sign-in form."""
    response = browser.get(path)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


@pytest.mark.parametrize("path", POST_PAGES)
def test_forms_need_a_session(browser: TestClient, path: str) -> None:
    """Every new form refuses a visitor with no session."""
    response = browser.post(path, data={"name": "Forged"})

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


@pytest.mark.parametrize("path", [p for p in POST_PAGES if p != "/copies/new"])
def test_forms_need_the_session_token(scene: Scene, path: str) -> None:
    """A cross-site form is refused, whatever the page."""
    target = path.replace("/1", f"/{scene.library_id}", 1)
    response = scene.owner.browser.post(target, data={"name": "Forged"})

    assert response.status_code == 403


def test_the_list_shows_only_my_libraries_with_my_role(
    app: FastAPI, scene: Scene, session: Session
) -> None:
    """Members see their own role, and outsiders see nothing."""
    other = Library(owner_id=scene.stranger.id, name="Private Place")
    session.add(other)
    session.flush()
    session.add(
        LibraryMember(library_id=other.id, user_id=scene.stranger.id, role="owner")
    )
    session.commit()

    owner_page = scene.owner.browser.get("/libraries").text
    viewer_page = scene.viewer.browser.get("/libraries").text
    stranger_page = scene.stranger.browser.get("/libraries").text

    assert "Home" in owner_page
    assert "Private Place" not in owner_page
    assert ">viewer<" in viewer_page
    assert ">owner<" in owner_page
    assert "Home" not in stranger_page
    assert "Private Place" in stranger_page


def test_the_list_is_empty_for_a_new_user(app: FastAPI, session: Session) -> None:
    """The page says what to do when there is nothing to show."""
    person = sign_in(app, session, "newcomer")

    page = person.browser.get("/libraries").text

    assert "aren't in any library" in page
    assert "Add a library" in page


def test_a_library_name_is_escaped(scene: Scene, session: Session) -> None:
    """Typed text can't add markup to a page."""
    library = session.get(Library, scene.library_id)
    assert library
    library.name = "<script>alert(1)</script>"
    session.commit()

    page = scene.owner.browser.get("/libraries").text

    assert "<script>alert" not in page
    assert "&lt;script&gt;" in page


def test_creating_a_library_makes_me_its_owner(scene: Scene, session: Session) -> None:
    """A valid form creates the library, with the settings I chose."""
    response = scene.stranger.browser.post(
        "/libraries/new",
        data={
            "csrf_token": scene.stranger.csrf,
            "name": "  Cabin  ",
            "default_privacy": "library",
        },
    )

    library = session.scalars(select(Library).where(Library.name == "Cabin")).one()
    member = session.get(LibraryMember, (library.id, scene.stranger.id))
    assert response.status_code == 303
    assert response.headers["location"] == f"/libraries/{library.id}"
    assert member is not None
    assert member.role == "owner"
    assert library.default_privacy == "library"
    assert library.editors_see_personal is False


def test_the_editors_checkbox_turns_the_setting_on(
    scene: Scene, session: Session
) -> None:
    """A ticked box sends a value, and an unticked one sends nothing."""
    scene.stranger.browser.post(
        "/libraries/new",
        data={
            "csrf_token": scene.stranger.csrf,
            "name": "Shared",
            "default_privacy": "personal",
            "editors_see_personal": "yes",
        },
    )

    library = session.scalars(select(Library).where(Library.name == "Shared")).one()
    assert library.editors_see_personal is True


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"name": " "}, "Check the name."),
        ({"name": "x" * 201}, "Check the name."),
        ({"name": "Ok", "default_privacy": "everyone"}, "Check the default sharing."),
    ],
)
def test_bad_library_forms_explain_and_keep_what_was_typed(
    scene: Scene, session: Session, data: dict[str, str], message: str
) -> None:
    """The form is shown again with a reason, and nothing is created."""
    before = len(session.scalars(select(Library)).all())

    response = scene.owner.browser.post(
        "/libraries/new", data={"csrf_token": scene.owner.csrf, **data}
    )

    assert response.status_code == 422
    assert message in response.text
    assert len(session.scalars(select(Library)).all()) == before


def test_guests_cannot_create_libraries(app: FastAPI, session: Session) -> None:
    """A guest sees no button, and the server refuses the form anyway."""
    guest = sign_in(app, session, "guest", "guest")

    page = guest.browser.get("/libraries").text
    response = guest.browser.post(
        "/libraries/new", data={"csrf_token": guest.csrf, "name": "Mine"}
    )

    assert "Add a library" not in page
    assert response.status_code == 403
    assert session.scalars(select(Library)).all() == []


def test_the_detail_page_shows_members_and_copies(scene: Scene) -> None:
    """A member sees who else is in the library, and the copies they can see."""
    page = scene.owner.browser.get(f"/libraries/{scene.library_id}").text

    assert "Home" in page
    assert "Your role" in page
    for name in ("Owner", "Editor", "Viewer"):
        assert name in page
    assert "Dune" in page
    assert "Hall shelf" in page


def test_a_non_member_gets_the_same_page_as_a_missing_library(
    scene: Scene,
) -> None:
    """An outsider can't tell a private library from one that doesn't exist."""
    real = scene.stranger.browser.get(f"/libraries/{scene.library_id}")
    missing = scene.stranger.browser.get("/libraries/99999")

    assert real.status_code == missing.status_code == 404
    assert real.text == missing.text


@pytest.mark.parametrize(
    ("who", "sees"),
    [("owner", True), ("editor", True), ("viewer", False)],
)
def test_personal_copies_follow_the_privacy_rules(
    scene: Scene, who: str, sees: bool
) -> None:
    """The copies table shows only the copies the policy layer allows."""
    person: Person = getattr(scene, who)

    page = person.browser.get(f"/libraries/{scene.library_id}").text

    assert ("Hall shelf" in page) is sees


def test_turning_the_editors_setting_off_hides_personal_copies(
    scene: Scene, session: Session
) -> None:
    """The library page and the copy page both obey the setting."""
    library = session.get(Library, scene.library_id)
    assert library
    library.editors_see_personal = False
    session.commit()

    page = scene.editor.browser.get(f"/libraries/{scene.library_id}").text
    copy_page = scene.editor.browser.get(f"/copies/{scene.copy_id}")

    assert "Hall shelf" not in page
    assert copy_page.status_code == 404


def test_the_copies_table_is_paged(scene: Scene, session: Session) -> None:
    """A long list is split, and the pager keeps the library."""
    for number in range(30):
        session.add(
            Copy(
                library_id=scene.library_id,
                edition_id=scene.edition_id,
                privacy="library",
                location=f"Box {number:02d}",
            )
        )
    session.commit()

    first = scene.owner.browser.get(f"/libraries/{scene.library_id}").text
    second = scene.owner.browser.get(f"/libraries/{scene.library_id}?page=2").text

    assert "Page 1 of 2" in first
    assert "Page 2 of 2" in second
    assert first.count("Box ") != second.count("Box ")
    assert (
        scene.owner.browser.get(f"/libraries/{scene.library_id}?page=0").status_code
        == 422
    )


@pytest.mark.parametrize(
    ("who", "can_edit"), [("owner", True), ("editor", False), ("viewer", False)]
)
def test_only_the_owner_is_offered_the_edit_link(
    scene: Scene, who: str, can_edit: bool
) -> None:
    """The page offers what the policy layer allows, and the server enforces it."""
    person: Person = getattr(scene, who)
    path = f"/libraries/{scene.library_id}"

    page = person.browser.get(path).text
    form = person.browser.get(f"{path}/edit")
    change = person.browser.post(
        f"{path}/edit", data={"csrf_token": person.csrf, "name": "Hijacked"}
    )

    assert (f"{path}/edit" in page) is can_edit
    assert form.status_code == (200 if can_edit else 403)
    assert change.status_code == (303 if can_edit else 403)


def test_editing_a_library_changes_its_settings(scene: Scene, session: Session) -> None:
    """The owner can rename it and turn the editors setting off."""
    response = scene.owner.browser.post(
        f"/libraries/{scene.library_id}/edit",
        data={
            "csrf_token": scene.owner.csrf,
            "name": "Home base",
            "default_privacy": "library",
        },
    )

    session.expire_all()
    library = session.get(Library, scene.library_id)
    assert library
    assert response.status_code == 303
    assert library.name == "Home base"
    assert library.default_privacy == "library"
    assert library.editors_see_personal is False


def test_editing_a_library_shows_the_current_settings(scene: Scene) -> None:
    """The edit form starts from what is saved."""
    page = scene.owner.browser.get(f"/libraries/{scene.library_id}/edit").text

    assert 'value="Home"' in page
    assert "checked" in page


def test_a_bad_edit_keeps_the_library_unchanged(scene: Scene, session: Session) -> None:
    """A blank name is refused with a reason."""
    response = scene.owner.browser.post(
        f"/libraries/{scene.library_id}/edit",
        data={"csrf_token": scene.owner.csrf, "name": " "},
    )

    session.expire_all()
    library = session.get(Library, scene.library_id)
    assert library
    assert response.status_code == 422
    assert "Check the name." in response.text
    assert library.name == "Home"


def test_deleting_a_library_needs_the_box_ticked(
    scene: Scene, session: Session
) -> None:
    """Without confirmation the library stays."""
    response = scene.owner.browser.post(
        f"/libraries/{scene.library_id}/delete",
        data={"csrf_token": scene.owner.csrf},
    )

    assert response.status_code == 422
    assert "Tick the box" in response.text
    assert session.get(Library, scene.library_id) is not None


def test_the_owner_can_delete_a_library_with_its_copies(
    scene: Scene, session: Session
) -> None:
    """A confirmed delete removes the library and its copies."""
    response = scene.owner.browser.post(
        f"/libraries/{scene.library_id}/delete",
        data={"csrf_token": scene.owner.csrf, "confirm": "yes"},
    )

    session.expire_all()
    assert response.status_code == 303
    assert response.headers["location"] == "/libraries"
    assert session.get(Library, scene.library_id) is None
    assert session.get(Copy, scene.copy_id) is None


def test_an_editor_cannot_delete_a_library(scene: Scene, session: Session) -> None:
    """Deleting is for the owner."""
    response = scene.editor.browser.post(
        f"/libraries/{scene.library_id}/delete",
        data={"csrf_token": scene.editor.csrf, "confirm": "yes"},
    )

    assert response.status_code == 403
    assert session.get(Library, scene.library_id) is not None


def test_the_navigation_links_to_libraries(scene: Scene) -> None:
    """Libraries are reachable from every page."""
    page = scene.owner.browser.get("/works").text

    assert 'href="/libraries"' in page
