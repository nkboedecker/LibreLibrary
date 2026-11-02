"""Sign-in, your own account, tokens, and user administration."""

from typing import cast

from fastapi import APIRouter, Depends, Request, status
from limits.strategies import RateLimiter

from librelibrary.api.deps import (
    CurrentActor,
    DbSession,
    Limit,
    Offset,
    PathId,
    client_ip,
    get_settings,
)
from librelibrary.models import ApiToken, User
from librelibrary.schemas import (
    LoginIn,
    Page,
    PasswordChangeIn,
    TokenCreatedOut,
    TokenIn,
    TokenOut,
    UserIn,
    UserOut,
    UserPatch,
)
from librelibrary.services import accounts
from librelibrary.services.common import Listing
from librelibrary.settings import Settings

router = APIRouter()


def _created(issued: accounts.IssuedToken) -> TokenCreatedOut:
    """Combine a token's record with the secret shown this once."""
    fields = TokenOut.model_validate(issued.record).model_dump()
    return TokenCreatedOut(**fields, token=issued.plaintext)


@router.post(
    "/auth/login",
    operation_id="auth_login",
    tags=["auth"],
    status_code=status.HTTP_201_CREATED,
)
def login(
    payload: LoginIn,
    request: Request,
    session: DbSession,
    settings: Settings = Depends(get_settings),  # noqa: B008
) -> TokenCreatedOut:
    """Check a username and password, and issue a bearer token."""
    limiter = cast(RateLimiter, request.app.state.login_limiter)
    user = accounts.sign_in(
        session,
        limiter=limiter,
        settings=settings,
        ip=client_ip(request, settings),
        username=payload.username,
        password=payload.password,
    )
    issued = accounts.issue_login_token(
        session,
        settings=settings,
        user=user,
        token_name=payload.token_name,
        scopes=[str(scope) for scope in payload.scopes],
    )
    return _created(issued)


@router.get("/users/me", operation_id="users_me_get", tags=["account"])
def get_me(session: DbSession, actor: CurrentActor) -> UserOut:
    """Return your account."""
    return UserOut.model_validate(accounts.get_me(session, actor))


@router.post(
    "/users/me/password",
    operation_id="users_me_password_change",
    tags=["account"],
    status_code=status.HTTP_204_NO_CONTENT,
)
def change_password(
    payload: PasswordChangeIn,
    request: Request,
    session: DbSession,
    actor: CurrentActor,
    settings: Settings = Depends(get_settings),  # noqa: B008
) -> None:
    """Change your password. This ends your other tokens."""
    limiter = cast(RateLimiter, request.app.state.login_limiter)
    accounts.change_own_password(
        session, actor, payload, limiter=limiter, settings=settings
    )


@router.get("/tokens", operation_id="tokens_list", tags=["account"])
def list_tokens(
    session: DbSession, actor: CurrentActor, limit: Limit = 50, offset: Offset = 0
) -> Page[TokenOut]:
    """List your tokens. Their secrets aren't shown."""
    listing: Listing[ApiToken] = accounts.list_tokens(session, actor, limit, offset)
    return Page[TokenOut].model_validate(listing)


@router.post(
    "/tokens",
    operation_id="tokens_create",
    tags=["account"],
    status_code=status.HTTP_201_CREATED,
)
def create_token(
    payload: TokenIn, session: DbSession, actor: CurrentActor
) -> TokenCreatedOut:
    """Create a token. Copy its secret now: it is shown only once."""
    return _created(accounts.create_token(session, actor, payload))


@router.delete(
    "/tokens/{token_id}",
    operation_id="tokens_delete",
    tags=["account"],
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_token(token_id: PathId, session: DbSession, actor: CurrentActor) -> None:
    """Revoke one of your tokens."""
    accounts.revoke_token(session, actor, token_id)


@router.get("/users", operation_id="users_list", tags=["admin"])
def list_users(
    session: DbSession, actor: CurrentActor, limit: Limit = 50, offset: Offset = 0
) -> Page[UserOut]:
    """List users."""
    listing: Listing[User] = accounts.list_users(session, actor, limit, offset)
    return Page[UserOut].model_validate(listing)


@router.post(
    "/users",
    operation_id="users_create",
    tags=["admin"],
    status_code=status.HTTP_201_CREATED,
)
def create_user(payload: UserIn, session: DbSession, actor: CurrentActor) -> UserOut:
    """Create a user."""
    return UserOut.model_validate(accounts.create_user(session, actor, payload))


@router.get("/users/{user_id}", operation_id="users_get", tags=["admin"])
def get_user(user_id: PathId, session: DbSession, actor: CurrentActor) -> UserOut:
    """Return a user."""
    return UserOut.model_validate(accounts.get_user(session, actor, user_id))


@router.patch("/users/{user_id}", operation_id="users_update", tags=["admin"])
def update_user(
    user_id: PathId, payload: UserPatch, session: DbSession, actor: CurrentActor
) -> UserOut:
    """Change a user. Setting a password ends their tokens."""
    return UserOut.model_validate(
        accounts.update_user(session, actor, user_id, payload)
    )
