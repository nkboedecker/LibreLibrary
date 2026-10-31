"""Test passwords, tokens, sign-in, and rate limits."""

from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response
from limits import parse
from limits.strategies import FixedWindowRateLimiter
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from librelibrary.app import create_app
from librelibrary.auth.passwords import hash_password, verify_password
from librelibrary.auth.ratelimit import DatabaseStorage
from librelibrary.auth.tokens import hash_token, new_token
from librelibrary.db import utcnow
from librelibrary.models import ApiToken, AuditEvent, RateLimitCounter, User
from librelibrary.settings import Settings

from .conftest import MakeAccount

PASSWORD = "correct horse battery"  # noqa: S105


@pytest.fixture
def alice(session: Session) -> User:
    """Create a user who can sign in with a password."""
    user = User(
        username="alice",
        display_name="Alice",
        role="member",
        password_hash=hash_password(PASSWORD),
    )
    session.add(user)
    session.commit()
    return user


def login(client: TestClient, password: str = PASSWORD, **extra: object) -> Response:
    """Post to the sign-in endpoint."""
    body = {"username": "alice", "password": password, **extra}
    response: Response = client.post("/api/v1/auth/login", json=body)
    return response


def test_password_hashes_verify() -> None:
    """A hash accepts its password and nothing else."""
    hashed = hash_password(PASSWORD)
    assert hashed.startswith("$argon2id$")
    assert verify_password(hashed, PASSWORD)
    assert not verify_password(hashed, "wrong password")


def test_tokens_are_prefixed_and_stored_only_as_hashes() -> None:
    """The stored parts of a token can't recreate it."""
    plaintext, token_hash, prefix = new_token()
    assert plaintext.startswith("llpat_")
    assert plaintext.startswith(prefix)
    assert len(prefix) < 16
    assert token_hash == hash_token(plaintext)
    assert plaintext not in token_hash


def test_login_returns_a_working_token(client: TestClient, alice: User) -> None:
    """Sign-in issues a bearer token that identifies the user."""
    response = login(client)
    assert response.status_code == 201
    token = response.json()["token"]
    me = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["username"] == "alice"
    assert "password_hash" not in me.json()


def test_login_ignores_username_case(client: TestClient, alice: User) -> None:
    """Usernames are normalized in the application, on both databases."""
    body = {"username": "ALICE", "password": PASSWORD}
    assert client.post("/api/v1/auth/login", json=body).status_code == 201


def test_wrong_password_is_denied(client: TestClient, alice: User) -> None:
    """A wrong password gets the same answer as an unknown user."""
    wrong = login(client, "not the password")
    unknown = client.post(
        "/api/v1/auth/login", json={"username": "nobody", "password": PASSWORD}
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_failed_login_is_audited_without_the_password(
    client: TestClient, alice: User, session: Session
) -> None:
    """The audit trail records the failure and never the attempt's secret."""
    login(client, "not the password")
    event = session.scalars(select(AuditEvent)).one()
    assert event.action == "login_failed"
    assert "not the password" not in str(event.detail)


def test_inactive_users_cannot_sign_in(
    client: TestClient, alice: User, session: Session
) -> None:
    """Deactivating an account stops password sign-in."""
    alice.is_active = False
    session.commit()
    assert login(client).status_code == 401


def test_member_cannot_request_the_admin_scope(client: TestClient, alice: User) -> None:
    """Sign-in can't grant more than the user's role allows."""
    assert login(client, scopes=["admin"]).status_code == 403


def test_local_auth_can_be_disabled(
    engine: Engine, database_url: str, alice: User
) -> None:
    """An environment setting turns password sign-in off."""
    settings = Settings(database_url=database_url, local_auth_enabled=False)
    response = login(TestClient(create_app(settings, engine=engine)))
    assert response.status_code == 403


@pytest.mark.parametrize(
    "header",
    ["", "Bearer", "Bearer nonsense", "Basic dXNlcjpwYXNz", "Bearer llpat_unknown"],
)
def test_bad_credentials_get_401(client: TestClient, header: str) -> None:
    """A protected route refuses anything but a valid bearer token."""
    headers = {"Authorization": header} if header else {}
    response = client.get("/api/v1/users/me", headers=headers)
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_expired_tokens_stop_working(
    client: TestClient, make_account: MakeAccount, session: Session
) -> None:
    """A token past its expiry gets 401."""
    account = make_account()
    token = session.scalars(select(ApiToken)).one()
    token.expires_at = utcnow() - timedelta(seconds=1)
    session.commit()
    assert client.get("/api/v1/users/me", headers=account.headers).status_code == 401


def test_tokens_of_inactive_users_stop_working(
    client: TestClient, make_account: MakeAccount, session: Session
) -> None:
    """Deactivating a user also stops their tokens."""
    account = make_account()
    user = session.get(User, account.id)
    assert user is not None
    user.is_active = False
    session.commit()
    assert client.get("/api/v1/users/me", headers=account.headers).status_code == 401


def test_token_is_shown_only_once(
    client: TestClient, make_account: MakeAccount, session: Session
) -> None:
    """Creation returns the secret, and later reads never do."""
    account = make_account()
    created = client.post(
        "/api/v1/tokens",
        headers=account.headers,
        json={"name": "phone", "scopes": ["library:read"]},
    )
    assert created.status_code == 201
    secret = created.json()["token"]
    listed = client.get("/api/v1/tokens", headers=account.headers)
    assert secret not in listed.text
    assert "token_hash" not in listed.text
    stored = session.scalars(
        select(ApiToken).where(ApiToken.id == created.json()["id"])
    ).one()
    assert stored.token_hash == hash_token(secret)


def test_token_cannot_mint_more_scopes_than_it_has(
    client: TestClient, make_account: MakeAccount
) -> None:
    """A read-write token can't create a token with the admin scope."""
    account = make_account("admin")
    response = client.post(
        "/api/v1/tokens",
        headers=account.headers,
        json={"name": "up", "scopes": ["admin"]},
    )
    assert response.status_code == 403


def test_revoked_tokens_stop_working(
    client: TestClient, make_account: MakeAccount
) -> None:
    """Revoking a token ends it at once."""
    account = make_account()
    tokens = client.get("/api/v1/tokens", headers=account.headers).json()["items"]
    deleted = client.delete(
        f"/api/v1/tokens/{tokens[0]['id']}", headers=account.headers
    )
    assert deleted.status_code == 204
    assert client.get("/api/v1/users/me", headers=account.headers).status_code == 401


def test_other_users_tokens_are_invisible(
    client: TestClient, make_account: MakeAccount
) -> None:
    """A user can't list or revoke someone else's token."""
    first, second = make_account(), make_account()
    theirs = client.get("/api/v1/tokens", headers=second.headers).json()["items"][0]
    response = client.delete(f"/api/v1/tokens/{theirs['id']}", headers=first.headers)
    assert response.status_code == 404


def test_password_change_needs_the_current_password(
    client: TestClient, alice: User
) -> None:
    """A stolen token alone can't take over the account."""
    token = login(client).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    denied = client.post(
        "/api/v1/users/me/password",
        headers=headers,
        json={"current_password": "wrong", "new_password": "a new long password"},
    )
    assert denied.status_code == 403
    changed = client.post(
        "/api/v1/users/me/password",
        headers=headers,
        json={"current_password": PASSWORD, "new_password": "a new long password"},
    )
    assert changed.status_code == 204
    assert login(client, "a new long password").status_code == 201


def test_password_change_revokes_other_tokens(client: TestClient, alice: User) -> None:
    """Changing a password ends every other session."""
    first = {"Authorization": f"Bearer {login(client).json()['token']}"}
    second = {"Authorization": f"Bearer {login(client).json()['token']}"}
    client.post(
        "/api/v1/users/me/password",
        headers=first,
        json={"current_password": PASSWORD, "new_password": "a new long password"},
    )
    assert client.get("/api/v1/users/me", headers=first).status_code == 200
    assert client.get("/api/v1/users/me", headers=second).status_code == 401


def test_password_change_guesses_are_rate_limited(
    engine: Engine, database_url: str, alice: User
) -> None:
    """A stolen token can't be used to guess the current password forever."""
    settings = Settings(
        database_url=database_url, login_rate_limit_per_username="3/hour"
    )
    client = TestClient(create_app(settings, engine=engine))
    headers = {"Authorization": f"Bearer {login(client).json()['token']}"}

    def change(current: str) -> int:
        body = {"current_password": current, "new_password": "a new long password"}
        response = client.post("/api/v1/users/me/password", headers=headers, json=body)
        return int(response.status_code)

    assert change("wrong one") == 403
    assert change("wrong two") == 403
    assert change(PASSWORD) == 429


def test_validation_errors_never_echo_input(client: TestClient) -> None:
    """A malformed sign-in can't copy a password into a response or a log."""
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "a" * 500, "password": "s3cret-value-here"},
    )
    assert response.status_code == 422
    assert "s3cret-value-here" not in response.text
    assert "aaaa" not in response.text


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_only_health_is_public(client: TestClient, path: str) -> None:
    """Generated docs aren't served, because only health is public."""
    assert client.get(path).status_code == 404


def test_login_is_rate_limited_per_username(
    engine: Engine, database_url: str, alice: User
) -> None:
    """Too many attempts on one account get 429, even with the right password."""
    settings = Settings(
        database_url=database_url, login_rate_limit_per_username="2/hour"
    )
    client = TestClient(create_app(settings, engine=engine))
    assert login(client, "wrong one").status_code == 401
    assert login(client, "wrong two").status_code == 401
    assert login(client).status_code == 429


def test_login_is_rate_limited_per_ip(engine: Engine, database_url: str) -> None:
    """Trying many usernames from one address also hits a limit."""
    settings = Settings(database_url=database_url, login_rate_limit_per_ip="2/hour")
    client = TestClient(create_app(settings, engine=engine))
    for name in ("one", "two"):
        body = {"username": name, "password": PASSWORD}
        assert client.post("/api/v1/auth/login", json=body).status_code == 401
    body = {"username": "three", "password": PASSWORD}
    assert client.post("/api/v1/auth/login", json=body).status_code == 429


def test_forwarded_ip_counts_only_from_trusted_proxies(
    engine: Engine, database_url: str
) -> None:
    """An untrusted client can't dodge the limit with a forged header."""
    settings = Settings(database_url=database_url, login_rate_limit_per_ip="1/hour")
    client = TestClient(create_app(settings, engine=engine))
    body = {"username": "one", "password": PASSWORD}
    first = client.post(
        "/api/v1/auth/login", json=body, headers={"X-Forwarded-For": "192.0.2.1"}
    )
    second = client.post(
        "/api/v1/auth/login", json=body, headers={"X-Forwarded-For": "192.0.2.2"}
    )
    assert (first.status_code, second.status_code) == (401, 429)


def test_forwarded_ip_is_used_behind_a_trusted_proxy(
    engine: Engine, database_url: str
) -> None:
    """Behind a trusted proxy, each client gets its own limit."""
    settings = Settings(
        database_url=database_url,
        login_rate_limit_per_ip="1/hour",
        trusted_proxies=["testclient", "127.0.0.1/32"],
    )
    client = TestClient(
        create_app(settings, engine=engine), client=("127.0.0.1", 50000)
    )
    body = {"username": "one", "password": PASSWORD}
    for address in ("192.0.2.1", "192.0.2.2"):
        response = client.post(
            "/api/v1/auth/login", json=body, headers={"X-Forwarded-For": address}
        )
        assert response.status_code == 401


def test_rate_limit_store_counts_and_expires(engine: Engine) -> None:
    """The store is shared, windowed, and keeps no readable keys."""
    storage = DatabaseStorage(engine)
    limiter = FixedWindowRateLimiter(storage)
    item = parse("2/hour")
    assert limiter.hit(item, "login", "alice")
    assert limiter.hit(item, "login", "alice")
    assert not limiter.hit(item, "login", "alice")
    assert limiter.hit(item, "login", "bob")

    other_worker = FixedWindowRateLimiter(DatabaseStorage(engine))
    assert not other_worker.hit(item, "login", "alice")

    with Session(engine) as session:
        rows = session.scalars(select(RateLimitCounter)).all()
        assert all("alice" not in row.key_hash for row in rows)
        for row in rows:
            row.expires_at = utcnow() - timedelta(seconds=1)
        session.commit()
    assert limiter.hit(item, "login", "alice")


def test_app_fixture_is_usable(app: FastAPI) -> None:
    """The fixture builds the application without running migrations again."""
    assert app.title == "LibreLibrary"
