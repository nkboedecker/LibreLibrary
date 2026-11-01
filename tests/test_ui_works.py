"""Test the work pages: detail, create, edit, and delete."""

import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from librelibrary.auth.passwords import hash_password
from librelibrary.models import (
    Contribution,
    Edition,
    Person,
    User,
    Work,
)

PASSWORD = "a long test password"


def make_user(session: Session, role: str) -> User:
    """Create a user who can sign in with a password."""
    user = User(
        username=role,
        display_name=role.title(),
        role=role,
        password_hash=hash_password(PASSWORD),
    )
    session.add(user)
    session.commit()
    return user


def token_of(page: str) -> str:
    """Read the CSRF token from a page's first form."""
    match = re.search(r'name="csrf_token" value="([^"]+)"', page)
    assert match
    return match.group(1)


@pytest.fixture
def browser(app: FastAPI) -> TestClient:
    """Give a test a browser-like client."""
    return TestClient(app, base_url="https://testserver", follow_redirects=False)


def sign_in_as(browser: TestClient, session: Session, role: str) -> str:
    """Sign in as a new user of the role, and return a CSRF token for forms."""
    make_user(session, role)
    form = browser.get("/login")
    browser.post(
        "/login",
        data={
            "username": role,
            "password": PASSWORD,
            "csrf_token": token_of(form.text),
        },
    )
    return token_of(browser.get("/works").text)


@pytest.fixture
def member(browser: TestClient, session: Session) -> str:
    """Sign in as a member; the value is their CSRF token."""
    return sign_in_as(browser, session, "member")


def test_the_new_work_form_is_shown_to_members(
    browser: TestClient, member: str
) -> None:
    """A member can reach the form, and it carries the session's token."""
    response = browser.get("/works/new")

    assert response.status_code == 200
    assert member in response.text
    assert 'name="title"' in response.text


def test_creating_a_work_redirects_to_its_page(
    browser: TestClient, member: str, session: Session
) -> None:
    """A valid form creates the work, and a blank optional field stays empty."""
    response = browser.post(
        "/works/new",
        data={
            "csrf_token": member,
            "title": "  A new work  ",
            "first_published": "1999",
            "original_language": "",
            "description": "Line one\nLine two",
        },
    )

    work = session.scalars(select(Work)).one()
    assert response.status_code == 303
    assert response.headers["location"] == f"/works/{work.id}"
    assert work.title == "A new work"
    assert work.original_language is None
    page = browser.get(response.headers["location"])
    assert "A new work" in page.text
    assert "1999" in page.text


def test_creating_a_work_needs_the_session_token(
    browser: TestClient, member: str, session: Session
) -> None:
    """A cross-site form is refused, and nothing is created."""
    missing = browser.post("/works/new", data={"title": "Forged"})
    wrong = browser.post("/works/new", data={"title": "Forged", "csrf_token": "x"})

    assert missing.status_code == 403
    assert wrong.status_code == 403
    assert session.scalars(select(Work)).all() == []


def test_a_blank_title_shows_the_form_again(
    browser: TestClient, member: str, session: Session
) -> None:
    """The form explains the problem and keeps what was typed."""
    response = browser.post(
        "/works/new",
        data={"csrf_token": member, "title": " ", "description": "Kept text"},
    )

    assert response.status_code == 422
    assert "Check the title." in response.text
    assert "Kept text" in response.text
    assert session.scalars(select(Work)).all() == []


def test_a_too_long_field_is_refused(
    browser: TestClient, member: str, session: Session
) -> None:
    """The API's limits apply to the form."""
    response = browser.post(
        "/works/new",
        data={"csrf_token": member, "title": "T", "original_language": "x" * 36},
    )

    assert response.status_code == 422
    assert "Check the original language." in response.text


def test_guests_cannot_create_or_edit(browser: TestClient, session: Session) -> None:
    """The policy layer refuses a guest, and the pages hide the buttons."""
    token = sign_in_as(browser, session, "guest")
    session.add(Work(title="Existing"))
    session.commit()
    work = session.scalars(select(Work)).one()

    assert "Add a work" not in browser.get("/works").text
    assert "Edit this work" not in browser.get(f"/works/{work.id}").text
    create = browser.post("/works/new", data={"csrf_token": token, "title": "No"})
    edit = browser.post(
        f"/works/{work.id}/edit", data={"csrf_token": token, "title": "No"}
    )
    assert create.status_code == 403
    assert edit.status_code == 403
    assert session.get(Work, work.id).title == "Existing"  # type: ignore[union-attr]


def test_the_detail_page_shows_contributors_and_editions(
    browser: TestClient, member: str, session: Session
) -> None:
    """Names come from people records, and editions are listed."""
    person = Person(name="Ursula Example")
    work = Work(title="A Book", description="<b>bold</b> text")
    session.add_all([person, work])
    session.flush()
    session.add_all(
        [
            Contribution(person_id=person.id, work_id=work.id, role="author"),
            Edition(work_id=work.id, publisher="Example Press", published="2001"),
        ]
    )
    session.commit()

    text = browser.get(f"/works/{work.id}").text

    assert "Ursula Example (author)" in text
    assert "Example Press" in text
    assert "&lt;b&gt;bold&lt;/b&gt; text" in text


def test_a_missing_work_shows_a_not_found_page(
    browser: TestClient, member: str
) -> None:
    """A page, not JSON, answers a browser."""
    response = browser.get("/works/999")

    assert response.status_code == 404
    assert "Not found" in response.text


def test_the_list_links_to_detail_pages(
    browser: TestClient, member: str, session: Session
) -> None:
    """Each title is a link."""
    session.add(Work(title="Linked"))
    session.commit()
    work = session.scalars(select(Work)).one()

    assert f'href="/works/{work.id}"' in browser.get("/works").text


def test_editing_changes_fields_and_clears_blank_ones(
    browser: TestClient, member: str, session: Session
) -> None:
    """A blank optional field clears it, as a form user expects."""
    session.add(Work(title="Old", first_published="1900", description="Old text"))
    session.commit()
    work = session.scalars(select(Work)).one()
    form = browser.get(f"/works/{work.id}/edit")
    assert 'value="Old"' in form.text

    response = browser.post(
        f"/works/{work.id}/edit",
        data={"csrf_token": member, "title": "New", "first_published": ""},
    )

    session.refresh(work)
    assert response.status_code == 303
    assert (work.title, work.first_published, work.description) == ("New", None, None)


def test_editing_needs_the_token_and_a_title(
    browser: TestClient, member: str, session: Session
) -> None:
    """Forged and incomplete edits change nothing."""
    session.add(Work(title="Keep"))
    session.commit()
    work = session.scalars(select(Work)).one()

    forged = browser.post(f"/works/{work.id}/edit", data={"title": "Bad"})
    blank = browser.post(
        f"/works/{work.id}/edit", data={"csrf_token": member, "title": ""}
    )

    session.refresh(work)
    assert forged.status_code == 403
    assert blank.status_code == 422
    assert "Enter a title." in blank.text
    assert work.title == "Keep"


def test_editing_a_missing_work_is_not_found(browser: TestClient, member: str) -> None:
    """A stale link gets a page."""
    assert browser.get("/works/999/edit").status_code == 404
    response = browser.post(
        "/works/999/edit", data={"csrf_token": member, "title": "x"}
    )
    assert response.status_code == 404


def test_only_admins_see_and_use_delete(
    browser: TestClient, member: str, session: Session
) -> None:
    """A member's delete is refused, and the form isn't offered."""
    session.add(Work(title="Stays"))
    session.commit()
    work = session.scalars(select(Work)).one()

    assert "Delete this work" not in browser.get(f"/works/{work.id}/edit").text
    response = browser.post(
        f"/works/{work.id}/delete", data={"csrf_token": member, "confirm": "yes"}
    )

    assert response.status_code == 403
    assert session.get(Work, work.id) is not None


def test_an_admin_deletes_a_work_after_confirming(
    browser: TestClient, session: Session
) -> None:
    """The box must be ticked, and then the work is gone."""
    token = sign_in_as(browser, session, "admin")
    session.add(Work(title="Doomed"))
    session.commit()
    work = session.scalars(select(Work)).one()
    work_id = work.id
    assert "Delete this work" in browser.get(f"/works/{work_id}/edit").text

    unconfirmed = browser.post(f"/works/{work.id}/delete", data={"csrf_token": token})
    confirmed = browser.post(
        f"/works/{work_id}/delete", data={"csrf_token": token, "confirm": "yes"}
    )

    assert unconfirmed.status_code == 422
    assert "Tick the box" in unconfirmed.text
    assert confirmed.status_code == 303
    assert confirmed.headers["location"] == "/works"
    session.expire_all()
    assert session.get(Work, work_id) is None


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/works/new"),
        ("POST", "/works/new"),
        ("GET", "/works/1"),
        ("GET", "/works/1/edit"),
        ("POST", "/works/1/edit"),
        ("POST", "/works/1/delete"),
    ],
)
def test_anonymous_visitors_are_sent_to_sign_in(
    browser: TestClient, method: str, path: str
) -> None:
    """No work page answers without a session."""
    response = browser.request(method, path, data={"title": "x"})

    assert response.status_code == 303
    assert response.headers["location"] == "/login"
