"""Test tags and shelves on the copy page."""

import pytest
from httpx import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from librelibrary.models import Copy, CopyTag, Library, LibraryMember, ShelfItem, Tag

from .ui_support import (
    Person,
    Scene,
    add_copy,
    add_shelf,
    add_tags,
    put_on_shelf,
)


def tag_names(session: Session, copy_id: int) -> set[str]:
    """Return the names of the tags on a copy."""
    session.expire_all()
    rows = session.scalars(
        select(Tag.name)
        .join(CopyTag, CopyTag.tag_id == Tag.id)
        .where(CopyTag.copy_id == copy_id)
    )
    return set(rows)


def post_tags(person: Person, copy_id: int, text: str) -> Response:
    """Submit the tags form."""
    response: Response = person.browser.post(
        f"/copies/{copy_id}/tags", data={"csrf_token": person.csrf, "tags": text}
    )
    return response


def test_a_copy_page_shows_its_tags_to_readers(scene: Scene, session: Session) -> None:
    """Anyone who can see the copy sees its tags."""
    shared = add_copy(session, scene, "library")
    add_tags(session, scene.library_id, shared, "fiction", "to-reread")

    page = scene.viewer.browser.get(f"/copies/{shared}").text

    assert "fiction" in page
    assert "to-reread" in page


def test_only_editors_get_the_tags_form(scene: Scene, session: Session) -> None:
    """Viewers see tags but are offered no way to change them."""
    shared = add_copy(session, scene, "library")

    editor_page = scene.editor.browser.get(f"/copies/{shared}").text
    viewer_page = scene.viewer.browser.get(f"/copies/{shared}").text

    assert 'name="tags"' in editor_page
    assert 'name="tags"' not in viewer_page
    assert "No tags yet." in viewer_page


def test_an_editor_sets_tags_from_a_comma_list(scene: Scene, session: Session) -> None:
    """Spaces and blanks are dropped, and a repeat counts once."""
    response = post_tags(scene.editor, scene.copy_id, "fiction, Sci-Fi ,fiction,, ")

    assert response.status_code == 303
    assert response.headers["location"] == f"/copies/{scene.copy_id}"
    assert tag_names(session, scene.copy_id) == {"fiction", "Sci-Fi"}
    page = scene.editor.browser.get(f"/copies/{scene.copy_id}").text
    assert "Sci-Fi" in page


def test_saving_replaces_the_tags_and_blank_clears_them(
    scene: Scene, session: Session
) -> None:
    """The tags field is the full set."""
    add_tags(session, scene.library_id, scene.copy_id, "old")

    post_tags(scene.owner, scene.copy_id, "new")
    assert tag_names(session, scene.copy_id) == {"new"}
    post_tags(scene.owner, scene.copy_id, "")
    assert tag_names(session, scene.copy_id) == set()


def test_the_form_starts_from_the_current_tags(scene: Scene, session: Session) -> None:
    """Editing doesn't start from a blank box."""
    add_tags(session, scene.library_id, scene.copy_id, "alpha", "beta")

    page = scene.owner.browser.get(f"/copies/{scene.copy_id}").text

    assert 'value="alpha, beta"' in page


def test_a_viewer_cannot_set_tags(scene: Scene, session: Session) -> None:
    """The server refuses what the page never offered."""
    shared = add_copy(session, scene, "library")

    response = post_tags(scene.viewer, shared, "sneaky")

    assert response.status_code == 403
    assert tag_names(session, shared) == set()


def test_a_stranger_cannot_tag_a_hidden_copy(scene: Scene, session: Session) -> None:
    """A private copy looks like it doesn't exist."""
    response = post_tags(scene.stranger, scene.copy_id, "sneaky")

    assert response.status_code == 404
    assert tag_names(session, scene.copy_id) == set()


def test_too_many_tags_are_refused_and_kept_in_the_box(
    scene: Scene, session: Session
) -> None:
    """A long list is refused with a reason."""
    text = ", ".join(f"tag{number}" for number in range(51))

    response = post_tags(scene.owner, scene.copy_id, text)

    assert response.status_code == 422
    assert "Use at most 50 tags." in response.text
    assert "tag50" in response.text
    assert tag_names(session, scene.copy_id) == set()


def test_a_too_long_tag_is_refused(scene: Scene, session: Session) -> None:
    """The API's limit applies to the form."""
    response = post_tags(scene.owner, scene.copy_id, "fine, " + "x" * 201)

    assert response.status_code == 422
    assert "Check the tags." in response.text
    assert tag_names(session, scene.copy_id) == set()


def test_tags_are_escaped(scene: Scene, session: Session) -> None:
    """Typed text can't add markup."""
    add_tags(session, scene.library_id, scene.copy_id, "<b>bold</b>")

    page = scene.owner.browser.get(f"/copies/{scene.copy_id}").text

    assert "<b>bold</b>" not in page
    assert "&lt;b&gt;bold&lt;/b&gt;" in page


def test_the_library_page_lists_its_tags(scene: Scene, session: Session) -> None:
    """Tags in use are visible from the library."""
    shared = add_copy(session, scene, "library")
    add_tags(session, scene.library_id, shared, "favorite")

    page = scene.viewer.browser.get(f"/libraries/{scene.library_id}").text

    assert "favorite" in page


def test_tags_that_only_hidden_copies_use_stay_hidden(
    scene: Scene, session: Session
) -> None:
    """A tag name can reveal a copy, so viewers see only tags on copies they can."""
    shared = add_copy(session, scene, "library")
    add_tags(session, scene.library_id, shared, "visible-tag")
    add_tags(session, scene.library_id, scene.copy_id, "secret-tag")

    viewer = scene.viewer.browser.get(f"/libraries/{scene.library_id}").text
    owner = scene.owner.browser.get(f"/libraries/{scene.library_id}").text

    assert "visible-tag" in viewer
    assert "secret-tag" not in viewer
    assert "secret-tag" in owner


def test_orphaned_tags_stay_hidden_from_those_who_cannot_see_the_copy(
    scene: Scene, session: Session
) -> None:
    """Re-tagging a hidden copy doesn't publish the tag it used to have."""
    post_tags(scene.owner, scene.copy_id, "old-secret")
    post_tags(scene.owner, scene.copy_id, "new-name")
    library = session.get(Library, scene.library_id)
    assert library
    library.editors_see_personal = False
    session.commit()

    viewer = scene.viewer.browser.get(f"/libraries/{scene.library_id}").text
    editor = scene.editor.browser.get(f"/libraries/{scene.library_id}").text
    owner = scene.owner.browser.get(f"/libraries/{scene.library_id}").text

    for page in (viewer, editor):
        assert "old-secret" not in page
        assert "new-name" not in page
    assert "old-secret" in owner
    assert "new-name" in owner


def test_a_copy_page_lists_its_shelves_and_offers_the_others(
    scene: Scene, session: Session
) -> None:
    """Shelves the copy is on are linked, and the rest can be chosen."""
    on = add_shelf(session, scene.library_id, "Currently on")
    off = add_shelf(session, scene.library_id, "Not yet")
    put_on_shelf(session, on, scene.copy_id)

    page = scene.editor.browser.get(f"/copies/{scene.copy_id}").text

    assert f'href="/shelves/{on}"' in page
    assert f'<option value="{off}"' in page
    assert f'<option value="{on}"' not in page


def test_a_copy_on_no_shelf_says_so(scene: Scene, session: Session) -> None:
    """The page explains the empty case."""
    shared = add_copy(session, scene, "library")

    page = scene.viewer.browser.get(f"/copies/{shared}").text

    assert "isn't on a shelf" in page


def test_an_editor_puts_a_copy_on_a_shelf(scene: Scene, session: Session) -> None:
    """The copy joins the shelf and the page returns to the copy."""
    shelf = add_shelf(session, scene.library_id)

    response = scene.editor.browser.post(
        f"/copies/{scene.copy_id}/shelves",
        data={"csrf_token": scene.editor.csrf, "shelf_id": str(shelf)},
    )

    session.expire_all()
    assert response.status_code == 303
    assert response.headers["location"] == f"/copies/{scene.copy_id}"
    assert session.get(ShelfItem, (shelf, scene.copy_id)) is not None


def test_a_viewer_cannot_put_a_copy_on_a_shelf(scene: Scene, session: Session) -> None:
    """Shelving needs the editor role."""
    shelf = add_shelf(session, scene.library_id)
    shared = add_copy(session, scene, "library")

    response = scene.viewer.browser.post(
        f"/copies/{shared}/shelves",
        data={"csrf_token": scene.viewer.csrf, "shelf_id": str(shelf)},
    )

    assert response.status_code == 403
    assert session.get(ShelfItem, (shelf, shared)) is None


def test_a_stranger_cannot_shelve_a_copy(scene: Scene, session: Session) -> None:
    """An outsider is told the shelf doesn't exist."""
    shelf = add_shelf(session, scene.library_id)

    response = scene.stranger.browser.post(
        f"/copies/{scene.copy_id}/shelves",
        data={"csrf_token": scene.stranger.csrf, "shelf_id": str(shelf)},
    )

    assert response.status_code == 404
    assert session.get(ShelfItem, (shelf, scene.copy_id)) is None


def test_a_shelf_from_another_library_conflicts(scene: Scene, session: Session) -> None:
    """A copy only goes on its own library's shelves."""
    other = Library(owner_id=scene.owner.id, name="Cabin")
    session.add(other)
    session.flush()
    session.add(
        LibraryMember(library_id=other.id, user_id=scene.owner.id, role="owner")
    )
    session.commit()
    foreign = add_shelf(session, other.id, "Elsewhere")

    response = scene.owner.browser.post(
        f"/copies/{scene.copy_id}/shelves",
        data={"csrf_token": scene.owner.csrf, "shelf_id": str(foreign)},
    )

    assert response.status_code == 409
    assert session.get(ShelfItem, (foreign, scene.copy_id)) is None


def test_putting_a_copy_on_a_shelf_twice_is_harmless(
    scene: Scene, session: Session
) -> None:
    """A second submit doesn't fail."""
    shelf = add_shelf(session, scene.library_id)
    data = {"csrf_token": scene.owner.csrf, "shelf_id": str(shelf)}

    first = scene.owner.browser.post(f"/copies/{scene.copy_id}/shelves", data=data)
    second = scene.owner.browser.post(f"/copies/{scene.copy_id}/shelves", data=data)

    assert first.status_code == second.status_code == 303


def test_an_outsider_sees_no_shelves_or_forms_on_a_server_wide_copy(
    scene: Scene, session: Session
) -> None:
    """A copy shared with everyone doesn't reveal its library's shelves."""
    shelf = add_shelf(session, scene.library_id, "Private shelf name")
    put_on_shelf(session, shelf, scene.copy_id)
    copy = session.get(Copy, scene.copy_id)
    assert copy
    copy.privacy = "server"
    session.commit()

    page = scene.stranger.browser.get(f"/copies/{scene.copy_id}").text

    assert "Private shelf name" not in page
    assert 'name="tags"' not in page
    assert "/shelves" not in page


@pytest.mark.parametrize("bad", ["abc", "0", "-1", "99999999999"])
def test_a_bad_shelf_id_is_refused(scene: Scene, bad: str) -> None:
    """The shelf choice is validated like any other field."""
    response = scene.owner.browser.post(
        f"/copies/{scene.copy_id}/shelves",
        data={"csrf_token": scene.owner.csrf, "shelf_id": bad},
    )

    assert response.status_code == 422
