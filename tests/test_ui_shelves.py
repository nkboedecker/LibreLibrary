"""Test the shelf pages: create, view, edit, delete, and remove a copy."""

import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session

from librelibrary.models import Copy, Library, Shelf, ShelfItem

from .ui_support import Scene, add_copy, add_shelf, new_browser, put_on_shelf


def routes(scene: Scene, shelf: int) -> dict[str, str]:
    """Name each shelf page's path for a scene."""
    return {
        "new": f"/libraries/{scene.library_id}/shelves/new",
        "detail": f"/shelves/{shelf}",
        "edit": f"/shelves/{shelf}/edit",
        "delete": f"/shelves/{shelf}/delete",
        "remove": f"/shelves/{shelf}/copies/{scene.copy_id}/remove",
        "tags": f"/copies/{scene.copy_id}/tags",
        "to_shelf": f"/copies/{scene.copy_id}/shelves",
    }


@pytest.fixture
def shelf(scene: Scene, session: Session) -> int:
    """Give a test an empty shelf in the scene's library."""
    return add_shelf(session, scene.library_id)


@pytest.mark.parametrize("name", ["new", "detail", "edit"])
def test_pages_need_a_session(
    app: FastAPI, scene: Scene, shelf: int, name: str
) -> None:
    """A visitor with no session is sent to sign in."""
    visitor = new_browser(app)

    response = visitor.get(routes(scene, shelf)[name])

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


@pytest.mark.parametrize(
    "name", ["new", "edit", "delete", "remove", "tags", "to_shelf"]
)
def test_forms_need_a_session(
    app: FastAPI, scene: Scene, shelf: int, name: str
) -> None:
    """A form from a visitor with no session is sent to sign in."""
    visitor = new_browser(app)

    response = visitor.post(routes(scene, shelf)[name], data={"name": "Forged"})

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


@pytest.mark.parametrize(
    "name", ["new", "edit", "delete", "remove", "tags", "to_shelf"]
)
def test_forms_need_the_session_token(scene: Scene, shelf: int, name: str) -> None:
    """A cross-site form is refused, whatever the page."""
    response = scene.owner.browser.post(
        routes(scene, shelf)[name], data={"name": "Forged"}
    )

    assert response.status_code == 403


@pytest.mark.parametrize(
    ("who", "status"), [("owner", 200), ("editor", 200), ("viewer", 403)]
)
def test_the_new_shelf_form_is_for_editors(scene: Scene, who: str, status: int) -> None:
    """The form needs the editor role, and the server enforces it."""
    person = getattr(scene, who)

    response = person.browser.get(f"/libraries/{scene.library_id}/shelves/new")

    assert response.status_code == status


def test_the_new_shelf_form_hides_the_library_from_outsiders(scene: Scene) -> None:
    """An outsider gets the answer for a library that isn't there."""
    real = scene.stranger.browser.get(f"/libraries/{scene.library_id}/shelves/new")
    missing = scene.stranger.browser.get("/libraries/99999/shelves/new")

    assert real.status_code == missing.status_code == 404
    assert real.text == missing.text


def test_an_editor_creates_a_shelf(scene: Scene, session: Session) -> None:
    """A valid form creates the shelf with a trimmed name."""
    response = scene.editor.browser.post(
        f"/libraries/{scene.library_id}/shelves/new",
        data={
            "csrf_token": scene.editor.csrf,
            "name": "  Sci-fi  ",
            "kind": "collection",
        },
    )

    created = session.scalars(select(Shelf).where(Shelf.name == "Sci-fi")).one()
    assert response.status_code == 303
    assert response.headers["location"] == f"/shelves/{created.id}"
    assert created.kind == "collection"
    assert created.library_id == scene.library_id


def test_a_blank_kind_means_shelf(scene: Scene, session: Session) -> None:
    """The kind defaults to a plain shelf."""
    scene.owner.browser.post(
        f"/libraries/{scene.library_id}/shelves/new",
        data={"csrf_token": scene.owner.csrf, "name": "Plain"},
    )

    created = session.scalars(select(Shelf).where(Shelf.name == "Plain")).one()
    assert created.kind == "shelf"


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"name": " "}, "Check the name."),
        ({"name": "x" * 201}, "Check the name."),
        ({"name": "Ok", "kind": "bookcase"}, "Check the kind."),
    ],
)
def test_a_bad_shelf_form_explains_and_creates_nothing(
    scene: Scene, session: Session, data: dict[str, str], message: str
) -> None:
    """The form is shown again with a reason."""
    response = scene.owner.browser.post(
        f"/libraries/{scene.library_id}/shelves/new",
        data={"csrf_token": scene.owner.csrf, **data},
    )

    assert response.status_code == 422
    assert message in response.text
    assert session.scalars(select(Shelf)).all() == []


def test_a_viewer_cannot_create_a_shelf(scene: Scene, session: Session) -> None:
    """The server refuses what the form never offered."""
    response = scene.viewer.browser.post(
        f"/libraries/{scene.library_id}/shelves/new",
        data={"csrf_token": scene.viewer.csrf, "name": "Sneaky"},
    )

    assert response.status_code == 403
    assert session.scalars(select(Shelf)).all() == []


def test_a_stranger_cannot_create_a_shelf(scene: Scene, session: Session) -> None:
    """An outsider is told the library doesn't exist."""
    response = scene.stranger.browser.post(
        f"/libraries/{scene.library_id}/shelves/new",
        data={"csrf_token": scene.stranger.csrf, "name": "Sneaky"},
    )

    assert response.status_code == 404
    assert session.scalars(select(Shelf)).all() == []


def test_a_shelf_lists_only_copies_the_reader_may_see(
    scene: Scene, session: Session, shelf: int
) -> None:
    """A shelf follows each copy's sharing level."""
    shared = add_copy(session, scene, "library", "Spare room")
    put_on_shelf(session, shelf, scene.copy_id)
    put_on_shelf(session, shelf, shared)

    owner_page = scene.owner.browser.get(f"/shelves/{shelf}").text
    viewer_page = scene.viewer.browser.get(f"/shelves/{shelf}").text

    assert "Hall shelf" in owner_page
    assert "Spare room" in owner_page
    assert "Hall shelf" not in viewer_page
    assert "Spare room" in viewer_page


def test_a_shelf_page_shows_its_name_and_kind(scene: Scene, session: Session) -> None:
    """The page names the shelf, its kind, and its library."""
    collection = add_shelf(session, scene.library_id, "Reread soon", "collection")

    page = scene.viewer.browser.get(f"/shelves/{collection}").text

    assert "Reread soon" in page
    assert "Collection" in page
    assert f'href="/libraries/{scene.library_id}"' in page


def test_an_empty_shelf_says_so(scene: Scene, shelf: int) -> None:
    """The page explains what to do."""
    page = scene.owner.browser.get(f"/shelves/{shelf}").text

    assert "nothing on this shelf" in page


def test_a_stranger_gets_the_same_page_for_a_shelf_as_for_a_missing_one(
    scene: Scene, shelf: int
) -> None:
    """An outsider can't tell a real shelf from one that doesn't exist."""
    real = scene.stranger.browser.get(f"/shelves/{shelf}")
    missing = scene.stranger.browser.get("/shelves/99999")

    assert real.status_code == missing.status_code == 404
    assert real.text == missing.text


def test_a_shelf_name_is_escaped(scene: Scene, session: Session) -> None:
    """Typed text can't add markup."""
    tricky = add_shelf(session, scene.library_id, "<script>alert(1)</script>")

    page = scene.owner.browser.get(f"/shelves/{tricky}").text

    assert "<script>alert" not in page
    assert "&lt;script&gt;" in page


@pytest.mark.parametrize(
    ("who", "can_edit"),
    [("owner", True), ("editor", True), ("viewer", False)],
)
def test_editing_links_follow_the_role(
    scene: Scene, shelf: int, who: str, can_edit: bool
) -> None:
    """The page offers what the policy layer allows, and the server enforces it."""
    person = getattr(scene, who)

    page = person.browser.get(f"/shelves/{shelf}").text
    form = person.browser.get(f"/shelves/{shelf}/edit")

    assert (f"/shelves/{shelf}/edit" in page) is can_edit
    assert form.status_code == (200 if can_edit else 403)


def test_an_editor_renames_a_shelf(scene: Scene, session: Session, shelf: int) -> None:
    """The shelf keeps its copies and gets the new name and kind."""
    put_on_shelf(session, shelf, scene.copy_id)

    response = scene.editor.browser.post(
        f"/shelves/{shelf}/edit",
        data={
            "csrf_token": scene.editor.csrf,
            "name": "Best of",
            "kind": "collection",
        },
    )

    session.expire_all()
    renamed = session.get(Shelf, shelf)
    assert renamed
    assert response.status_code == 303
    assert response.headers["location"] == f"/shelves/{shelf}"
    assert (renamed.name, renamed.kind) == ("Best of", "collection")
    assert session.get(ShelfItem, (shelf, scene.copy_id)) is not None


def test_a_bad_rename_changes_nothing(
    scene: Scene, session: Session, shelf: int
) -> None:
    """A blank name is refused with a reason."""
    response = scene.owner.browser.post(
        f"/shelves/{shelf}/edit",
        data={"csrf_token": scene.owner.csrf, "name": " ", "kind": "shelf"},
    )

    session.expire_all()
    current = session.get(Shelf, shelf)
    assert current
    assert response.status_code == 422
    assert "Check the name." in response.text
    assert current.name == "Favorites"


def test_a_viewer_cannot_rename_or_delete_a_shelf(
    scene: Scene, session: Session, shelf: int
) -> None:
    """Changing a shelf needs the editor role."""
    rename = scene.viewer.browser.post(
        f"/shelves/{shelf}/edit",
        data={"csrf_token": scene.viewer.csrf, "name": "Hijacked", "kind": "shelf"},
    )
    delete = scene.viewer.browser.post(
        f"/shelves/{shelf}/delete",
        data={"csrf_token": scene.viewer.csrf, "confirm": "yes"},
    )

    session.expire_all()
    assert rename.status_code == delete.status_code == 403
    assert session.get(Shelf, shelf) is not None


def test_deleting_a_shelf_needs_the_box_ticked(
    scene: Scene, session: Session, shelf: int
) -> None:
    """Without confirmation the shelf stays."""
    response = scene.owner.browser.post(
        f"/shelves/{shelf}/delete", data={"csrf_token": scene.owner.csrf}
    )

    assert response.status_code == 422
    assert "Tick the box" in response.text
    assert session.get(Shelf, shelf) is not None


def test_deleting_a_shelf_keeps_its_copies(
    scene: Scene, session: Session, shelf: int
) -> None:
    """Only the shelf goes, and the page returns to the library."""
    put_on_shelf(session, shelf, scene.copy_id)

    response = scene.editor.browser.post(
        f"/shelves/{shelf}/delete",
        data={"csrf_token": scene.editor.csrf, "confirm": "yes"},
    )

    session.expire_all()
    assert response.status_code == 303
    assert response.headers["location"] == f"/libraries/{scene.library_id}"
    assert session.get(Shelf, shelf) is None
    assert session.get(Copy, scene.copy_id) is not None


def test_a_stranger_cannot_edit_or_delete_a_shelf(
    scene: Scene, session: Session, shelf: int
) -> None:
    """An outsider is told the shelf doesn't exist."""
    edit = scene.stranger.browser.get(f"/shelves/{shelf}/edit")
    delete = scene.stranger.browser.post(
        f"/shelves/{shelf}/delete",
        data={"csrf_token": scene.stranger.csrf, "confirm": "yes"},
    )

    assert edit.status_code == delete.status_code == 404
    assert session.get(Shelf, shelf) is not None


def test_an_editor_removes_a_copy_from_a_shelf(
    scene: Scene, session: Session, shelf: int
) -> None:
    """The copy stays in the library and leaves the shelf."""
    put_on_shelf(session, shelf, scene.copy_id)

    response = scene.editor.browser.post(
        f"/shelves/{shelf}/copies/{scene.copy_id}/remove",
        data={"csrf_token": scene.editor.csrf},
    )

    session.expire_all()
    assert response.status_code == 303
    assert response.headers["location"] == f"/shelves/{shelf}"
    assert session.get(ShelfItem, (shelf, scene.copy_id)) is None
    assert session.get(Copy, scene.copy_id) is not None


def test_removing_a_copy_that_is_not_on_the_shelf_is_a_404(
    scene: Scene, shelf: int
) -> None:
    """There is nothing to remove."""
    response = scene.owner.browser.post(
        f"/shelves/{shelf}/copies/{scene.copy_id}/remove",
        data={"csrf_token": scene.owner.csrf},
    )

    assert response.status_code == 404


def test_an_editor_cannot_probe_a_shelf_for_a_hidden_copy(
    scene: Scene, session: Session, shelf: int
) -> None:
    """With the setting off, removing a hidden copy looks like removing nothing."""
    library = session.get(Library, scene.library_id)
    assert library
    library.editors_see_personal = False
    put_on_shelf(session, shelf, scene.copy_id)
    session.commit()

    response = scene.editor.browser.post(
        f"/shelves/{shelf}/copies/{scene.copy_id}/remove",
        data={"csrf_token": scene.editor.csrf},
    )

    session.expire_all()
    assert response.status_code == 404
    assert session.get(ShelfItem, (shelf, scene.copy_id)) is not None


def test_a_viewer_cannot_remove_a_copy_from_a_shelf(
    scene: Scene, session: Session, shelf: int
) -> None:
    """Removing needs the editor role, and the viewer sees no button."""
    shared = add_copy(session, scene, "library")
    put_on_shelf(session, shelf, shared)

    page = scene.viewer.browser.get(f"/shelves/{shelf}").text
    response = scene.viewer.browser.post(
        f"/shelves/{shelf}/copies/{shared}/remove",
        data={"csrf_token": scene.viewer.csrf},
    )

    assert "Remove" not in page
    assert response.status_code == 403
    assert session.get(ShelfItem, (shelf, shared)) is not None


def test_the_editor_sees_a_remove_button_for_each_copy(
    scene: Scene, session: Session, shelf: int
) -> None:
    """Editors can take copies off the shelf from the shelf page."""
    put_on_shelf(session, shelf, scene.copy_id)

    page = scene.editor.browser.get(f"/shelves/{shelf}").text

    assert f"/shelves/{shelf}/copies/{scene.copy_id}/remove" in page


def test_the_library_page_lists_its_shelves(
    scene: Scene, session: Session, shelf: int
) -> None:
    """Shelves are reachable from their library, and only editors get the button."""
    owner_page = scene.owner.browser.get(f"/libraries/{scene.library_id}").text
    viewer_page = scene.viewer.browser.get(f"/libraries/{scene.library_id}").text

    assert f'href="/shelves/{shelf}"' in owner_page
    assert "Favorites" in viewer_page
    assert "Add a shelf" in owner_page
    assert "Add a shelf" not in viewer_page
