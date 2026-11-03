"""Helpers for tests of the web interface: users, browsers, and a shared scene."""

import re
from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from librelibrary.auth.passwords import hash_password
from librelibrary.models import (
    Copy,
    CopyTag,
    Edition,
    Library,
    LibraryMember,
    Shelf,
    ShelfItem,
    Tag,
    User,
    Work,
)

PASSWORD = "a long test password"


def token_of(page: str) -> str:
    """Read the CSRF token from a page's first form."""
    match = re.search(r'name="csrf_token" value="([^"]+)"', page)
    assert match
    return match.group(1)


def make_user(session: Session, username: str, role: str = "member") -> User:
    """Create a user who can sign in with a password."""
    user = User(
        username=username,
        display_name=username.title(),
        role=role,
        password_hash=hash_password(PASSWORD),
    )
    session.add(user)
    session.commit()
    return user


def new_browser(app: FastAPI) -> TestClient:
    """Create a browser-like client with its own cookies."""
    return TestClient(app, base_url="https://testserver", follow_redirects=False)


@dataclass
class Person:
    """A signed-in user with their own browser."""

    browser: TestClient
    csrf: str
    id: int


def sign_in(
    app: FastAPI, session: Session, username: str, role: str = "member"
) -> Person:
    """Create a user, sign them in, and return them with their CSRF token."""
    user = make_user(session, username, role)
    browser = new_browser(app)
    form = browser.get("/login")
    browser.post(
        "/login",
        data={
            "username": username,
            "password": PASSWORD,
            "csrf_token": token_of(form.text),
        },
    )
    return Person(browser, token_of(browser.get("/works").text), user.id)


@dataclass
class Scene:
    """One library with an owner, an editor, a viewer, and an outsider."""

    owner: Person
    editor: Person
    viewer: Person
    stranger: Person
    library_id: int
    work_id: int
    edition_id: int
    copy_id: int


def build_scene(app: FastAPI, session: Session) -> Scene:
    """Seed a library with a work, an edition, and one personal copy."""
    people = {
        name: sign_in(app, session, name)
        for name in ("owner", "editor", "viewer", "stranger")
    }
    work = Work(title="Dune")
    work.editions = [Edition(title="Dune (paperback)", publisher="Ace")]
    library = Library(
        owner_id=people["owner"].id,
        name="Home",
        default_privacy="personal",
        editors_see_personal=True,
    )
    session.add_all([work, library])
    session.flush()
    for name, role in (("owner", "owner"), ("editor", "editor"), ("viewer", "viewer")):
        session.add(
            LibraryMember(library_id=library.id, user_id=people[name].id, role=role)
        )
    copy = Copy(
        library_id=library.id,
        edition_id=work.editions[0].id,
        privacy="personal",
        location="Hall shelf",
    )
    session.add(copy)
    session.commit()
    return Scene(
        owner=people["owner"],
        editor=people["editor"],
        viewer=people["viewer"],
        stranger=people["stranger"],
        library_id=library.id,
        work_id=work.id,
        edition_id=work.editions[0].id,
        copy_id=copy.id,
    )


def add_copy(
    session: Session, scene: Scene, privacy: str = "library", location: str = "Spare"
) -> int:
    """Add another copy of the scene's edition to its library."""
    copy = Copy(
        library_id=scene.library_id,
        edition_id=scene.edition_id,
        privacy=privacy,
        location=location,
    )
    session.add(copy)
    session.commit()
    return copy.id


def add_shelf(
    session: Session, library_id: int, name: str = "Favorites", kind: str = "shelf"
) -> int:
    """Add a shelf to a library."""
    shelf = Shelf(library_id=library_id, name=name, kind=kind)
    session.add(shelf)
    session.commit()
    return shelf.id


def put_on_shelf(session: Session, shelf_id: int, copy_id: int) -> None:
    """Put a copy on a shelf."""
    session.add(ShelfItem(shelf_id=shelf_id, copy_id=copy_id))
    session.commit()


def add_tags(session: Session, library_id: int, copy_id: int, *names: str) -> None:
    """Tag a copy, creating the tags in its library."""
    for name in names:
        tag = Tag(library_id=library_id, name=name)
        session.add(tag)
        session.flush()
        session.add(CopyTag(copy_id=copy_id, tag_id=tag.id))
    session.commit()
