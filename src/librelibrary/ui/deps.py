"""What page routes share: the signed-in user and CSRF checking."""

from typing import Annotated

from fastapi import Depends, Form, Request

from librelibrary.api.deps import DbSession
from librelibrary.authz.policy import Actor, Denied
from librelibrary.errors import Unauthenticated
from librelibrary.models import WebSession
from librelibrary.services import websessions

SESSION_COOKIE = "librelibrary_session"
LOGIN_CSRF_COOKIE = "librelibrary_login_csrf"


class LoginRequired(Exception):  # noqa: N818
    """A page needs a signed-in user; the app redirects to the sign-in form."""


class SignedIn:
    """The user behind a page request."""

    def __init__(self, actor: Actor, web_session: WebSession) -> None:
        """Hold the actor and the session that identified them."""
        self.actor = actor
        self.web_session = web_session

    @property
    def csrf_token(self) -> str:
        """Return the token that this user's forms must send."""
        return self.web_session.csrf_token


def get_signed_in(request: Request, session: DbSession) -> SignedIn:
    """Identify the user from the session cookie."""
    try:
        actor, web_session = websessions.actor_for_session(
            session, request.cookies.get(SESSION_COOKIE)
        )
    except Unauthenticated:
        raise LoginRequired from None
    return SignedIn(actor, web_session)


CurrentUser = Annotated[SignedIn, Depends(get_signed_in)]


def verify_csrf(user: CurrentUser, csrf_token: Annotated[str, Form()] = "") -> None:
    """Refuse a state-changing request without the session's synchronizer token."""
    if not websessions.csrf_matches(user.web_session, csrf_token):
        raise Denied


CsrfChecked = Depends(verify_csrf)
