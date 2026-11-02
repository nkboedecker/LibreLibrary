"""Test the copy pages, and the add-edition page that copies depend on."""

from decimal import Decimal

import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session

from librelibrary.models import Copy, Edition

from .ui_support import Scene, sign_in


def new_copy(scene: Scene, who: str = "owner", **fields: str) -> dict[str, str]:
    """Build the fields of a new-copy form."""
    person = getattr(scene, who)
    return {
        "csrf_token": person.csrf,
        "library_id": str(scene.library_id),
        "edition_id": str(scene.edition_id),
        **fields,
    }


def test_the_new_copy_form_names_the_edition_and_my_libraries(
    scene: Scene,
) -> None:
    """The form shows what is being added and where I may add it."""
    page = scene.editor.browser.get(f"/copies/new?edition_id={scene.edition_id}").text

    assert "Dune (paperback)" in page
    assert f'<option value="{scene.library_id}"' in page
    assert 'name="price"' in page


def test_the_new_copy_form_omits_libraries_i_can_only_read(
    scene: Scene,
) -> None:
    """A viewer is told there is nowhere to add a copy."""
    page = scene.viewer.browser.get(f"/copies/new?edition_id={scene.edition_id}").text

    assert f'<option value="{scene.library_id}"' not in page
    assert "can't add copies" in page


def test_the_new_copy_form_needs_a_real_edition(scene: Scene) -> None:
    """A missing edition is a 404, and a bad ID is refused."""
    assert scene.owner.browser.get("/copies/new?edition_id=99999").status_code == 404
    assert scene.owner.browser.get("/copies/new?edition_id=0").status_code == 422
    assert scene.owner.browser.get("/copies/new").status_code == 422


def test_adding_a_copy_uses_the_librarys_default_sharing(
    scene: Scene, session: Session
) -> None:
    """A blank sharing choice falls back to the library's default."""
    response = scene.owner.browser.post(
        "/copies/new",
        data=new_copy(
            scene,
            location="  Study  ",
            condition="Good",
            price="12.99",
            currency="usd",
            acquired="2026-01-05",
            privacy="",
        ),
    )

    copy = session.scalars(select(Copy).where(Copy.location == "Study")).one()
    assert response.status_code == 303
    assert response.headers["location"] == f"/copies/{copy.id}"
    assert copy.privacy == "personal"
    assert copy.currency == "USD"
    assert copy.price == Decimal("12.99")
    assert str(copy.acquired) == "2026-01-05"


def test_adding_a_copy_with_a_chosen_sharing_level(
    scene: Scene, session: Session
) -> None:
    """The chosen level is kept."""
    scene.owner.browser.post(
        "/copies/new", data=new_copy(scene, location="Lent out", privacy="server")
    )

    copy = session.scalars(select(Copy).where(Copy.location == "Lent out")).one()
    assert copy.privacy == "server"


def test_a_viewer_cannot_add_a_copy(scene: Scene, session: Session) -> None:
    """The server refuses what the form never offered."""
    before = len(session.scalars(select(Copy)).all())

    response = scene.viewer.browser.post(
        "/copies/new", data=new_copy(scene, "viewer", location="Sneaky")
    )

    assert response.status_code == 403
    assert len(session.scalars(select(Copy)).all()) == before


def test_a_stranger_cannot_add_a_copy_or_learn_the_library_exists(
    scene: Scene, session: Session
) -> None:
    """An outsider gets the answer for a library that isn't there."""
    real = scene.stranger.browser.post(
        "/copies/new", data=new_copy(scene, "stranger", location="Sneaky")
    )
    missing = scene.stranger.browser.post(
        "/copies/new",
        data={**new_copy(scene, "stranger"), "library_id": "99999"},
    )

    assert real.status_code == missing.status_code == 404
    assert real.text == missing.text


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("price", "1.999", "Check the price."),
        ("price", "-1", "Check the price."),
        ("price", "NaN", "Check the price."),
        ("acquired", "yesterday", "Check the date acquired."),
        ("currency", "US", "Check the currency."),
        ("privacy", "everyone", "Check the sharing."),
    ],
)
def test_a_bad_copy_form_explains_and_keeps_what_was_typed(
    scene: Scene, session: Session, field: str, value: str, message: str
) -> None:
    """The form is shown again with a reason, and nothing is created."""
    before = len(session.scalars(select(Copy)).all())

    response = scene.owner.browser.post(
        "/copies/new",
        data=new_copy(scene, location="Kept text", **{field: value}),
    )

    assert response.status_code == 422
    assert message in response.text
    assert "Kept text" in response.text
    assert len(session.scalars(select(Copy)).all()) == before


def test_a_copy_page_shows_its_details(scene: Scene, session: Session) -> None:
    """The page names the work, the edition, and where the copy is."""
    copy = session.get(Copy, scene.copy_id)
    assert copy
    copy.price = 12.5  # type: ignore[assignment]
    copy.currency = "USD"
    session.commit()

    page = scene.owner.browser.get(f"/copies/{scene.copy_id}").text

    assert "Dune" in page
    assert "Dune (paperback)" in page
    assert "Hall shelf" in page
    assert "12.50 USD" in page
    assert f'href="/libraries/{scene.library_id}"' in page
    assert f'href="/works/{scene.work_id}"' in page


def test_a_copy_page_escapes_what_was_typed(scene: Scene, session: Session) -> None:
    """Typed text can't add markup."""
    copy = session.get(Copy, scene.copy_id)
    assert copy
    copy.location = "<b>bold</b>"
    session.commit()

    page = scene.owner.browser.get(f"/copies/{scene.copy_id}").text

    assert "<b>bold</b>" not in page
    assert "&lt;b&gt;bold&lt;/b&gt;" in page


def test_a_stranger_gets_the_same_page_for_a_hidden_copy_as_a_missing_one(
    scene: Scene,
) -> None:
    """A private copy looks like it doesn't exist."""
    real = scene.stranger.browser.get(f"/copies/{scene.copy_id}")
    missing = scene.stranger.browser.get("/copies/99999")

    assert real.status_code == missing.status_code == 404
    assert real.text == missing.text


def test_a_viewer_sees_shared_copies_but_gets_no_edit_link(
    scene: Scene, session: Session
) -> None:
    """Reading is allowed by the sharing level, and editing needs a role."""
    copy = session.get(Copy, scene.copy_id)
    assert copy
    copy.privacy = "library"
    session.commit()

    page = scene.viewer.browser.get(f"/copies/{scene.copy_id}")

    assert page.status_code == 200
    assert f"/copies/{scene.copy_id}/edit" not in page.text
    assert scene.viewer.browser.get(f"/copies/{scene.copy_id}/edit").status_code == 403


def test_an_editor_can_change_a_copy(scene: Scene, session: Session) -> None:
    """Fields change, and a blank optional field is cleared."""
    response = scene.editor.browser.post(
        f"/copies/{scene.copy_id}/edit",
        data={
            "csrf_token": scene.editor.csrf,
            "location": "",
            "condition": "Worn",
            "price": "8",
            "currency": "eur",
            "privacy": "library",
        },
    )

    session.expire_all()
    copy = session.get(Copy, scene.copy_id)
    assert copy
    assert response.status_code == 303
    assert copy.location is None
    assert copy.condition == "Worn"
    assert copy.price == Decimal("8")
    assert copy.currency == "EUR"
    assert copy.privacy == "library"


def test_the_edit_form_starts_from_what_is_saved(scene: Scene) -> None:
    """The form shows the current values."""
    page = scene.owner.browser.get(f"/copies/{scene.copy_id}/edit").text

    assert 'value="Hall shelf"' in page
    assert "selected" in page


def test_a_bad_copy_edit_changes_nothing(scene: Scene, session: Session) -> None:
    """A bad price is refused with a reason."""
    response = scene.owner.browser.post(
        f"/copies/{scene.copy_id}/edit",
        data={
            "csrf_token": scene.owner.csrf,
            "location": "Moved",
            "price": "lots",
            "privacy": "personal",
        },
    )

    session.expire_all()
    copy = session.get(Copy, scene.copy_id)
    assert copy
    assert response.status_code == 422
    assert "Check the price." in response.text
    assert copy.location == "Hall shelf"


def test_a_stranger_cannot_edit_or_delete_a_copy(
    scene: Scene, session: Session
) -> None:
    """The server hides the copy from anyone it isn't shared with."""
    edit = scene.stranger.browser.post(
        f"/copies/{scene.copy_id}/edit",
        data={"csrf_token": scene.stranger.csrf, "location": "Mine now"},
    )
    delete = scene.stranger.browser.post(
        f"/copies/{scene.copy_id}/delete",
        data={"csrf_token": scene.stranger.csrf, "confirm": "yes"},
    )

    assert edit.status_code == delete.status_code == 404
    assert session.get(Copy, scene.copy_id) is not None


def test_deleting_a_copy_needs_the_box_ticked(scene: Scene, session: Session) -> None:
    """Without confirmation the copy stays."""
    response = scene.owner.browser.post(
        f"/copies/{scene.copy_id}/delete", data={"csrf_token": scene.owner.csrf}
    )

    assert response.status_code == 422
    assert "Tick the box" in response.text
    assert session.get(Copy, scene.copy_id) is not None


def test_an_editor_can_delete_a_copy(scene: Scene, session: Session) -> None:
    """A confirmed delete removes the copy and returns to its library."""
    response = scene.editor.browser.post(
        f"/copies/{scene.copy_id}/delete",
        data={"csrf_token": scene.editor.csrf, "confirm": "yes"},
    )

    session.expire_all()
    assert response.status_code == 303
    assert response.headers["location"] == f"/libraries/{scene.library_id}"
    assert session.get(Copy, scene.copy_id) is None


def test_the_work_page_offers_to_add_a_copy_of_each_edition(scene: Scene) -> None:
    """Copies are added from an edition, so the work page links to the form."""
    page = scene.owner.browser.get(f"/works/{scene.work_id}").text

    assert f"/copies/new?edition_id={scene.edition_id}" in page
    assert f"/works/{scene.work_id}/editions/new" in page


def test_guests_are_offered_neither_link(
    app: FastAPI, scene: Scene, session: Session
) -> None:
    """A guest can read the catalog but is shown no editing links."""
    guest = sign_in(app, session, "guest", "guest")

    page = guest.browser.get(f"/works/{scene.work_id}").text

    assert "/copies/new" not in page
    assert "/editions/new" not in page


def test_adding_an_edition_creates_it_and_returns_to_the_work(
    scene: Scene, session: Session
) -> None:
    """A valid form adds an edition to the work."""
    response = scene.editor.browser.post(
        f"/works/{scene.work_id}/editions/new",
        data={
            "csrf_token": scene.editor.csrf,
            "title": "Dune (hardback)",
            "publisher": "Chilton",
            "published": "1965",
            "language": "en",
            "format": "Hardback",
            "pages": "412",
        },
    )

    edition = session.scalars(
        select(Edition).where(Edition.title == "Dune (hardback)")
    ).one()
    assert response.status_code == 303
    assert response.headers["location"] == f"/works/{scene.work_id}"
    assert edition.pages == 412
    assert edition.work_id == scene.work_id


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("pages", "many", "Check the page count."),
        ("pages", "-3", "Check the page count."),
    ],
)
def test_a_bad_edition_form_explains_and_creates_nothing(
    scene: Scene, session: Session, field: str, value: str, message: str
) -> None:
    """The form is shown again with a reason."""
    before = len(session.scalars(select(Edition)).all())

    response = scene.owner.browser.post(
        f"/works/{scene.work_id}/editions/new",
        data={"csrf_token": scene.owner.csrf, "title": "Kept text", field: value},
    )

    assert response.status_code == 422
    assert message in response.text
    assert "Kept text" in response.text
    assert len(session.scalars(select(Edition)).all()) == before


def test_the_new_edition_form_for_a_missing_work_is_a_404(scene: Scene) -> None:
    """A bad work ID gets the usual page."""
    assert scene.owner.browser.get("/works/99999/editions/new").status_code == 404


def test_libraries_with_no_copies_say_so(scene: Scene, session: Session) -> None:
    """An empty library explains what to do."""
    session.delete(session.get(Copy, scene.copy_id))
    session.commit()

    page = scene.owner.browser.get(f"/libraries/{scene.library_id}").text

    assert "no copies" in page
    assert "/works" in page
