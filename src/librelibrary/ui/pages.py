"""Page routes: sign-in, sign-out, and the catalog."""

import secrets
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse, Response
from limits.strategies import RateLimiter

from librelibrary.api.deps import DbSession, client_ip, get_settings
from librelibrary.authz.policy import Denied
from librelibrary.errors import RateLimited, Unauthenticated
from librelibrary.services import accounts, websessions
from librelibrary.settings import Settings
from librelibrary.ui import ui_route
from librelibrary.ui.deps import (
    LOGIN_CSRF_COOKIE,
    SESSION_COOKIE,
    CsrfChecked,
    CurrentUser,
)
from librelibrary.ui.templating import templates

router = APIRouter()
_SEE_OTHER = 303
_COOKIE_FLAGS = {"httponly": True, "secure": True, "samesite": "lax", "path": "/"}
_LOGIN_FAILED = {
    Unauthenticated: (401, "The username or password is wrong."),
    RateLimited: (429, "Too many attempts. Wait a minute and try again."),
    Denied: (403, "Password sign-in is turned off on this server."),
}


@ui_route(router, "GET", "/", api=None)
def home() -> Response:
    """Send visitors to the catalog, which asks them to sign in if needed."""
    return RedirectResponse("/works", status_code=_SEE_OTHER)


def _login_page(
    request: Request, csrf_token: str, status_code: int = 200, error: str = ""
) -> Response:
    response = templates.TemplateResponse(
        request,
        "login.html",
        {"csrf_token": csrf_token, "error": error},
        status_code=status_code,
    )
    response.set_cookie(
        LOGIN_CSRF_COOKIE,
        csrf_token,
        max_age=600,
        **_COOKIE_FLAGS,  # type: ignore[arg-type]
    )
    return response


@ui_route(router, "GET", "/login", api=None)
def login_form(request: Request) -> Response:
    """Show the sign-in form, with a fresh token that the cookie repeats."""
    return _login_page(request, secrets.token_urlsafe(32))


@ui_route(router, "POST", "/login", api="auth_login")
def login(  # noqa: PLR0913
    request: Request,
    session: DbSession,
    username: Annotated[str, Form(max_length=64)],
    password: Annotated[str, Form(max_length=1024)],
    csrf_token: Annotated[str, Form()] = "",
    settings: Settings = Depends(get_settings),  # noqa: B008
) -> Response:
    """Check a password, and open a browser session."""
    cookie_token = request.cookies.get(LOGIN_CSRF_COOKIE, "")
    if not (cookie_token and secrets.compare_digest(cookie_token, csrf_token)):
        raise Denied
    limiter = cast(RateLimiter, request.app.state.login_limiter)
    try:
        user = accounts.sign_in(
            session,
            limiter=limiter,
            settings=settings,
            ip=client_ip(request, settings),
            username=username,
            password=password,
        )
    except (Unauthenticated, RateLimited, Denied) as error:
        code, message = _LOGIN_FAILED[type(error)]
        return _login_page(request, secrets.token_urlsafe(32), code, message)
    cookie_value = websessions.start(session, settings=settings, user=user)
    response = RedirectResponse("/works", status_code=_SEE_OTHER)
    response.set_cookie(
        SESSION_COOKIE,
        cookie_value,
        max_age=settings.session_lifetime_days * 86400,
        **_COOKIE_FLAGS,  # type: ignore[arg-type]
    )
    response.delete_cookie(LOGIN_CSRF_COOKIE, path="/")
    return response


@ui_route(router, "POST", "/logout", api=None)
def logout(
    session: DbSession, user: CurrentUser, _csrf: None = CsrfChecked
) -> Response:
    """Close the browser session."""
    websessions.end(session, user.web_session)
    response = RedirectResponse("/login", status_code=_SEE_OTHER)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response
