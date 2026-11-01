"""Browser sessions: the server-side record behind the sign-in cookie.

The cookie holds a long random value and the table holds only its hash, as with
tokens. Each session also holds the synchronizer token that its forms must send.
"""

import hashlib
import hmac
import secrets
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from librelibrary.authz.policy import Actor, Role, Scope
from librelibrary.db import utcnow
from librelibrary.errors import Unauthenticated
from librelibrary.models import User, WebSession
from librelibrary.services import audit
from librelibrary.settings import Settings


def _hash(cookie_value: str) -> str:
    return hashlib.sha256(cookie_value.encode()).hexdigest()


def start(session: Session, *, settings: Settings, user: User) -> str:
    """Open a session for a user who has signed in; return the cookie value."""
    now = utcnow()
    session.execute(delete(WebSession).where(WebSession.expires_at <= now))
    cookie_value = secrets.token_urlsafe(32)
    session.add(
        WebSession(
            user_id=user.id,
            session_hash=_hash(cookie_value),
            csrf_token=secrets.token_urlsafe(32),
            expires_at=now + timedelta(days=settings.session_lifetime_days),
        )
    )
    audit.record(session, user.id, "web_login", f"user:{user.id}")
    session.commit()
    return cookie_value


def actor_for_session(
    session: Session, cookie_value: str | None
) -> tuple[Actor, WebSession]:
    """Return who a cookie acts for, with its session, or raise Unauthenticated.

    A browser acts with the user's full rights, so the actor holds the read and
    write scopes, and the admin scope for an admin.
    """
    if not cookie_value:
        raise Unauthenticated
    row = session.execute(
        select(WebSession, User)
        .join(User, WebSession.user_id == User.id)
        .where(WebSession.session_hash == _hash(cookie_value))
    ).one_or_none()
    if row is None:
        raise Unauthenticated
    web_session, user = row
    if web_session.expires_at <= utcnow() or not user.is_active:
        raise Unauthenticated
    scopes = {Scope.LIBRARY_READ, Scope.LIBRARY_WRITE}
    if user.role == Role.ADMIN.value:
        scopes.add(Scope.ADMIN)
    return Actor(user.id, Role(user.role), frozenset(scopes)), web_session


def csrf_matches(web_session: WebSession, submitted: str) -> bool:
    """Compare a submitted synchronizer token with the session's, in constant time."""
    return hmac.compare_digest(web_session.csrf_token, submitted)


def end(session: Session, web_session: WebSession) -> None:
    """Close a session, so that its cookie stops working at once."""
    audit.record(session, web_session.user_id, "web_logout")
    session.delete(web_session)
    session.commit()
