"""Test the web interface: sign-in, sessions, CSRF, and the catalog page."""

import re
from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from librelibrary.auth.passwords import hash_password
from librelibrary.db import utcnow
from librelibrary.models import AuditEvent, User, Work

from .conftest import MakeAccount

PASSWORD = "a long test password"
HTTPS = "https://testserver"


@pytest.fixture
def browser(app: FastAPI) -> TestClient:
    """Give a test a client that sends Secure cookies back, as a browser does."""
    return TestClient(app, base_url=HTTPS, follow_redirects=False)


@pytest.fixture
def user(session: Session) -> User:
    """Create a member who can sign in with a password."""
    account = User(
        username="reader",
        display_name="Reader",
        role="member",
        password_hash=hash_password(PASSWORD),
    )
    session.add(account)
    session.commit()
    return account


def _token(page: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', page)
    assert match
    return match.group(1)


def sign_in(browser: TestClient, username: str = "reader", password: str = PASSWORD):  # type: ignore[no-untyped-def]  # noqa: ANN201
    """Submit the sign-in form the way a browser would."""
    form = browser.get("/login")
    return browser.post(
        "/login",
        data={
            "username": username,
            "password": password,
            "csrf_token": _token(form.text),
        },
    )


def add_works(session: Session, *titles: str) -> None:
    """Create works directly."""
    session.add_all(Work(title=title) for title in titles)
    session.commit()


def test_sign_in_opens_a_session_with_safe_cookie_flags(
    browser: TestClient, user: User
) -> None:
    """A correct password redirects to the catalog and sets a hardened cookie."""
    response = sign_in(browser)

    assert response.status_code == 303
    assert response.headers["location"] == "/works"
    cookies = [
        value
        for name, value in response.headers.multi_items()
        if name == "set-cookie" and value.startswith("librelibrary_session=")
    ]
    assert len(cookies) == 1
    flags = cookies[0].lower()
    assert "httponly" in flags
    assert "secure" in flags
    assert "samesite=lax" in flags
    assert browser.get("/works").status_code == 200


def test_the_database_keeps_only_a_hash_of_the_cookie(
    browser: TestClient, user: User, session: Session
) -> None:
    """A stolen database can't be replayed as a cookie."""
    sign_in(browser)
    cookie = browser.cookies["librelibrary_session"]

    from librelibrary.models import WebSession  # noqa: PLC0415

    stored = session.scalars(select(WebSession)).all()
    assert len(stored) == 1
    assert cookie not in (stored[0].session_hash, stored[0].csrf_token)


@pytest.mark.parametrize(
    ("username", "password"),
    [("reader", "wrong password"), ("nobody", PASSWORD)],
)
def test_bad_credentials_show_one_message_and_no_session(
    browser: TestClient, user: User, username: str, password: str
) -> None:
    """A wrong password and an unknown user look the same."""
    response = sign_in(browser, username, password)

    assert response.status_code == 401
    assert "The username or password is wrong." in response.text
    assert "librelibrary_session" not in browser.cookies
    assert browser.get("/works").status_code == 303


def test_sign_in_without_the_login_token_is_refused(
    browser: TestClient, user: User
) -> None:
    """A forged cross-site sign-in has no matching token."""
    response = browser.post("/login", data={"username": "reader", "password": PASSWORD})

    assert response.status_code == 403
    assert "librelibrary_session" not in browser.cookies


def test_sign_in_with_a_mismatched_login_token_is_refused(
    browser: TestClient, user: User
) -> None:
    """The form token has to match the cookie, not merely exist."""
    browser.get("/login")
    response = browser.post(
        "/login",
        data={"username": "reader", "password": PASSWORD, "csrf_token": "forged"},
    )

    assert response.status_code == 403


def test_sign_in_is_rate_limited(browser: TestClient, user: User) -> None:
    """Page sign-in shares the API's limits."""
    for _ in range(10):
        sign_in(browser, password="wrong password")

    response = sign_in(browser)

    assert response.status_code == 429


def test_inactive_users_cannot_sign_in(
    browser: TestClient, user: User, session: Session
) -> None:
    """A deactivated account is refused even with the right password."""
    user.is_active = False
    session.commit()

    assert sign_in(browser).status_code == 401


def test_sign_in_is_audited(browser: TestClient, user: User, session: Session) -> None:
    """Sign-ins and failures leave audit events without secrets."""
    sign_in(browser, password="wrong password")
    sign_in(browser)

    actions = {event.action for event in session.scalars(select(AuditEvent))}
    assert {"login_failed", "web_login"} <= actions


def test_a_session_id_is_not_reused_after_sign_in(
    browser: TestClient, user: User
) -> None:
    """Signing in twice issues a different cookie each time."""
    sign_in(browser)
    first = browser.cookies["librelibrary_session"]
    browser.cookies.clear()
    sign_in(browser)

    assert browser.cookies["librelibrary_session"] != first


def test_the_catalog_needs_a_session(browser: TestClient) -> None:
    """An anonymous visitor is sent to sign in."""
    for path in ("/works", "/"):
        response = browser.get(path, follow_redirects=path == "/")
        if path == "/works":
            assert response.status_code == 303
            assert response.headers["location"] == "/login"
        else:
            assert str(response.url).endswith("/login")


def test_a_bearer_token_is_not_a_session(
    browser: TestClient, make_account: MakeAccount
) -> None:
    """Pages answer only to cookies."""
    account = make_account()

    assert browser.get("/works", headers=account.headers).status_code == 303


def test_a_session_cookie_is_not_an_api_credential(
    browser: TestClient, user: User
) -> None:
    """The API still wants a bearer token, so a cookie can't be ridden by a page."""
    sign_in(browser)

    assert browser.get("/api/v1/works").status_code == 401


def test_a_forged_cookie_is_refused(browser: TestClient) -> None:
    """An unknown cookie value is the same as none."""
    browser.cookies.set("librelibrary_session", "forged", domain="testserver")

    assert browser.get("/works").status_code == 303


def test_an_expired_session_is_refused(
    browser: TestClient, user: User, session: Session
) -> None:
    """A session ends when its lifetime does."""
    from librelibrary.models import WebSession  # noqa: PLC0415

    sign_in(browser)
    stored = session.scalars(select(WebSession)).one()
    stored.expires_at = utcnow() - timedelta(seconds=1)
    session.commit()

    assert browser.get("/works").status_code == 303


def test_deactivating_a_user_ends_their_session(
    browser: TestClient, user: User, session: Session
) -> None:
    """A deactivated user's open browser stops working at once."""
    sign_in(browser)
    user.is_active = False
    session.commit()

    assert browser.get("/works").status_code == 303


def test_sign_out_needs_the_session_token(browser: TestClient, user: User) -> None:
    """A cross-site form can't sign someone out, or do anything else."""
    sign_in(browser)

    missing = browser.post("/logout")
    wrong = browser.post("/logout", data={"csrf_token": "forged"})

    assert missing.status_code == 403
    assert wrong.status_code == 403
    assert browser.get("/works").status_code == 200


def test_sign_out_without_a_session_goes_to_sign_in(browser: TestClient) -> None:
    """An anonymous post is redirected, not served."""
    assert browser.post("/logout").status_code == 303


def test_sign_out_closes_the_session_on_the_server(
    browser: TestClient, user: User
) -> None:
    """The old cookie is dead even if a browser keeps it."""
    sign_in(browser)
    cookie = browser.cookies["librelibrary_session"]
    token = _token(browser.get("/works").text)

    response = browser.post("/logout", data={"csrf_token": token})

    assert response.status_code == 303
    assert response.headers["location"] == "/login"
    browser.cookies.set("librelibrary_session", cookie, domain="testserver")
    assert browser.get("/works").status_code == 303


def test_pages_carry_browser_protections(browser: TestClient, user: User) -> None:
    """Pages forbid framing, sniffing, and caching, and limit where scripts load."""
    response = browser.get("/login")

    assert "default-src 'self'" in response.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "no-store"


def test_works_page_lists_searches_and_pages(
    browser: TestClient, user: User, session: Session
) -> None:
    """The catalog page shows works, filters by title, and pages through."""
    add_works(session, *(f"Book {number:02d}" for number in range(30)), "Odd one")
    sign_in(browser)

    first = browser.get("/works")
    second = browser.get("/works?page=2")
    found = browser.get("/works?q=odd")

    assert "Book 00" in first.text
    assert "Odd one" not in first.text
    assert "Page 1 of 2" in first.text
    assert "Odd one" in second.text
    assert "Odd one" in found.text
    assert "Book 00" not in found.text
    assert "No works match" in browser.get("/works?q=zzz").text


def test_works_page_escapes_titles(
    browser: TestClient, user: User, session: Session
) -> None:
    """Catalog text can't inject markup."""
    add_works(session, "<script>alert(1)</script>")
    sign_in(browser)

    text = browser.get("/works").text

    assert "<script>alert(1)</script>" not in text
    assert "&lt;script&gt;" in text


def test_works_page_rejects_a_bad_page_number(browser: TestClient, user: User) -> None:
    """Out-of-range input gets an error page, not a crash."""
    sign_in(browser)

    assert browser.get("/works?page=0").status_code == 422


def test_guests_can_read_the_catalog(browser: TestClient, session: Session) -> None:
    """Read-only users see pages but hold no write scope."""
    session.add(
        User(
            username="guest",
            display_name="Guest",
            role="guest",
            password_hash=hash_password(PASSWORD),
        )
    )
    session.commit()
    sign_in(browser, "guest")

    assert browser.get("/works").status_code == 200
