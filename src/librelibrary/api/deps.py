"""What API routes share: the database session, the caller, and paging."""

import ipaddress
from collections.abc import Iterator
from typing import Annotated, cast

from fastapi import Depends, Path, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from librelibrary.authz.policy import Actor
from librelibrary.errors import Unauthenticated
from librelibrary.services.accounts import actor_for_token
from librelibrary.settings import Settings

_bearer = HTTPBearer(auto_error=False, description="A personal access token.")


def get_session(request: Request) -> Iterator[Session]:
    """Give a route one session, closed when the request ends."""
    with Session(request.app.state.engine, expire_on_commit=False) as session:
        yield session


DbSession = Annotated[Session, Depends(get_session)]


def get_actor(
    session: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Actor:
    """Identify the caller from a bearer token."""
    if credentials is None:
        raise Unauthenticated
    return actor_for_token(session, credentials.credentials)


CurrentActor = Annotated[Actor, Depends(get_actor)]
Limit = Annotated[int, Query(ge=1, le=200)]
Offset = Annotated[int, Query(ge=0, le=2_147_483_647)]
PathId = Annotated[int, Path(ge=1, le=2_147_483_647)]
QueryId = Annotated[int | None, Query(ge=1, le=2_147_483_647)]
SearchText = Annotated[str | None, Query(max_length=200, pattern=r"^[^\x00]*$")]


def get_settings(request: Request) -> Settings:
    """Return the application's settings."""
    return cast(Settings, request.app.state.settings)


def _is_trusted(address: str, proxies: list[str]) -> bool:
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError:
        return False
    for proxy in proxies:
        try:
            if parsed in ipaddress.ip_network(proxy, strict=False):
                return True
        except ValueError:
            continue
    return False


def client_ip(request: Request, settings: Settings) -> str:
    """Return the caller's address, believing forwarded headers only from proxies.

    The header is read from the right, because each proxy appends to it, so only
    the entries that trusted proxies added can be believed.
    """
    peer = request.client.host if request.client else "unknown"
    if not _is_trusted(peer, settings.trusted_proxies):
        return peer
    forwarded = request.headers.get("x-forwarded-for", "")
    hops = [hop.strip() for hop in forwarded.split(",") if hop.strip()]
    for hop in reversed(hops):
        if not _is_trusted(hop, settings.trusted_proxies):
            return hop
    return peer
