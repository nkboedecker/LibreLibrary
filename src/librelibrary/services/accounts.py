"""Sign-in, tokens, and user accounts."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from limits import RateLimitItem, parse
from limits.strategies import RateLimiter
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from librelibrary.auth.passwords import (
    hash_password,
    needs_rehash,
    verify_password,
    waste_time_verifying,
)
from librelibrary.auth.tokens import TOKEN_PREFIX, hash_token, new_token
from librelibrary.authz.policy import Action, Actor, Denied, Role, Scope, policy_action
from librelibrary.db import utcnow
from librelibrary.errors import Conflict, NotFound, RateLimited, Unauthenticated
from librelibrary.models import ApiToken, User
from librelibrary.schemas import (
    PasswordChangeIn,
    TokenIn,
    UserIn,
    UserPatch,
)
from librelibrary.services import audit
from librelibrary.services.common import (
    Listing,
    apply_changes,
    get_or_404,
    paginate,
)
from librelibrary.settings import Settings

_LAST_USED_RESOLUTION = timedelta(hours=1)


@dataclass
class IssuedToken:
    """A new token, with the secret that is shown only once."""

    record: ApiToken
    plaintext: str


def _issue_token(
    session: Session,
    user_id: int,
    name: str,
    scopes: list[str],
    expires_at: datetime | None,
) -> IssuedToken:
    plaintext, token_hash, prefix = new_token()
    token = ApiToken(
        user_id=user_id,
        name=name,
        token_hash=token_hash,
        display_prefix=prefix,
        scopes=scopes,
        expires_at=expires_at,
        created_at=utcnow(),
    )
    session.add(token)
    session.flush()
    return IssuedToken(token, plaintext)


def actor_for_token(session: Session, plaintext: str) -> Actor:
    """Return who a bearer token acts for, or raise Unauthenticated."""
    if not plaintext.startswith(TOKEN_PREFIX):
        raise Unauthenticated
    row = session.execute(
        select(ApiToken, User)
        .join(User, ApiToken.user_id == User.id)
        .where(ApiToken.token_hash == hash_token(plaintext))
    ).one_or_none()
    if row is None:
        raise Unauthenticated
    token, user = row
    now = utcnow()
    expired = token.expires_at is not None and token.expires_at <= now
    if token.revoked_at is not None or expired or not user.is_active:
        raise Unauthenticated
    stale = (
        token.last_used_at is None or now - token.last_used_at > _LAST_USED_RESOLUTION
    )
    if stale:
        token.last_used_at = now
        session.commit()
    return Actor(
        user_id=user.id,
        role=Role(user.role),
        scopes=frozenset(Scope(scope) for scope in token.scopes),
        token_id=token.id,
    )


def _hit_username_limit(
    limiter: RateLimiter, settings: Settings, username: str
) -> bool:
    """Count a password guess against an account; return False past the limit."""
    limit: RateLimitItem = parse(settings.login_rate_limit_per_username)
    return limiter.hit(limit, "login-username", username)


def _hit_login_limits(
    limiter: RateLimiter, settings: Settings, ip: str, username: str
) -> None:
    """Count this attempt against both limits; raise if either is exceeded."""
    per_ip: RateLimitItem = parse(settings.login_rate_limit_per_ip)
    within_ip = limiter.hit(per_ip, "login-ip", ip)
    within_username = _hit_username_limit(limiter, settings, username)
    if not (within_ip and within_username):
        raise RateLimited


def sign_in(  # noqa: PLR0913
    session: Session,
    *,
    limiter: RateLimiter,
    settings: Settings,
    ip: str,
    username: str,
    password: str,
) -> User:
    """Check a password and return the user. The caller has no identity yet."""
    if not settings.local_auth_enabled:
        raise Denied
    _hit_login_limits(limiter, settings, ip, username)
    user = session.scalar(select(User).where(User.username == username))
    if user is None or user.password_hash is None:
        waste_time_verifying(password)
        audit.record(session, None, "login_failed")
        session.commit()
        raise Unauthenticated
    valid = verify_password(user.password_hash, password)
    if not valid or not user.is_active:
        audit.record(session, user.id, "login_failed", f"user:{user.id}")
        session.commit()
        raise Unauthenticated
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    return user


def issue_login_token(
    session: Session,
    *,
    settings: Settings,
    user: User,
    token_name: str,
    scopes: list[str],
) -> IssuedToken:
    """Issue the bearer token that a successful sign-in earns."""
    if Scope.ADMIN.value in scopes and user.role != Role.ADMIN.value:
        raise Denied
    expires = utcnow() + timedelta(days=settings.login_token_lifetime_days)
    issued = _issue_token(session, user.id, token_name, scopes, expires)
    audit.record(session, user.id, "login", f"user:{user.id}")
    session.commit()
    return issued


@policy_action(Action.ACCOUNT_READ)
def get_me(session: Session, actor: Actor) -> User:
    """Return the actor's account."""
    return get_or_404(session, User, actor.user_id)


@policy_action(Action.ACCOUNT_WRITE)
def change_own_password(
    session: Session,
    actor: Actor,
    payload: PasswordChangeIn,
    *,
    limiter: RateLimiter,
    settings: Settings,
) -> None:
    """Change the actor's password, and end their other tokens.

    Guesses share the account's sign-in limit, so that a stolen token can't be
    used to find the password by trying it here instead.
    """
    user = get_or_404(session, User, actor.user_id)
    if not _hit_username_limit(limiter, settings, user.username):
        raise RateLimited
    if user.password_hash is None or not verify_password(
        user.password_hash, payload.current_password
    ):
        audit.record(session, user.id, "password_change_denied", f"user:{user.id}")
        session.commit()
        raise Denied
    user.password_hash = hash_password(payload.new_password)
    session.execute(
        update(ApiToken)
        .where(
            ApiToken.user_id == user.id,
            ApiToken.id != actor.token_id,
            ApiToken.revoked_at.is_(None),
        )
        .values(revoked_at=utcnow())
    )
    audit.record(session, user.id, "password_changed", f"user:{user.id}")
    session.commit()


@policy_action(Action.TOKEN_READ)
def list_tokens(
    session: Session, actor: Actor, limit: int, offset: int
) -> Listing[ApiToken]:
    """List the actor's tokens that haven't been revoked."""
    statement = (
        select(ApiToken)
        .where(ApiToken.user_id == actor.user_id, ApiToken.revoked_at.is_(None))
        .order_by(ApiToken.id)
    )
    return paginate(session, statement, limit, offset)


@policy_action(Action.TOKEN_WRITE)
def create_token(session: Session, actor: Actor, payload: TokenIn) -> IssuedToken:
    """Create a token with no scope that the creating token lacks."""
    wanted = {Scope(scope) for scope in payload.scopes}
    if not wanted <= actor.scopes:
        raise Denied
    if Scope.ADMIN in wanted and actor.role != Role.ADMIN:
        raise Denied
    scopes = sorted(scope.value for scope in wanted)
    issued = _issue_token(
        session, actor.user_id, payload.name, scopes, payload.expires_at
    )
    audit.record(session, actor.user_id, "token_created", f"token:{issued.record.id}")
    session.commit()
    return issued


@policy_action(Action.TOKEN_WRITE)
def revoke_token(session: Session, actor: Actor, token_id: int) -> None:
    """Revoke one of the actor's tokens."""
    token = session.scalar(
        select(ApiToken).where(
            ApiToken.id == token_id,
            ApiToken.user_id == actor.user_id,
            ApiToken.revoked_at.is_(None),
        )
    )
    if token is None:
        raise NotFound
    token.revoked_at = utcnow()
    audit.record(session, actor.user_id, "token_revoked", f"token:{token.id}")
    session.commit()


@policy_action(Action.USER_ADMIN)
def list_users(
    session: Session, actor: Actor, limit: int, offset: int
) -> Listing[User]:
    """List every user."""
    return paginate(session, select(User).order_by(User.id), limit, offset)


@policy_action(Action.USER_ADMIN)
def create_user(session: Session, actor: Actor, payload: UserIn) -> User:
    """Create a user."""
    user = User(
        username=payload.username,
        email=payload.email,
        display_name=payload.display_name,
        role=payload.role,
        password_hash=hash_password(payload.password),
        created_at=utcnow(),
    )
    session.add(user)
    session.flush()
    audit.record(session, actor.user_id, "user_created", f"user:{user.id}")
    session.commit()
    return user


@policy_action(Action.USER_ADMIN)
def get_user(session: Session, actor: Actor, user_id: int) -> User:
    """Return a user."""
    return get_or_404(session, User, user_id)


def _would_remove_last_admin(
    session: Session, user: User, changes: dict[str, object]
) -> bool:
    if user.role != Role.ADMIN.value or not user.is_active:
        return False
    if changes.get("role", user.role) == Role.ADMIN.value and changes.get(
        "is_active", True
    ):
        return False
    admins = session.scalar(
        select(func.count())
        .select_from(User)
        .where(User.role == Role.ADMIN.value, User.is_active.is_(True))
    )
    return admins == 1


@policy_action(Action.USER_ADMIN)
def update_user(
    session: Session, actor: Actor, user_id: int, payload: UserPatch
) -> User:
    """Change a user, keeping at least one active admin."""
    user = get_or_404(session, User, user_id)
    changes = payload.model_dump(exclude_unset=True)
    if _would_remove_last_admin(session, user, changes):
        raise Conflict
    password = changes.pop("password", None)
    if password is not None:
        user.password_hash = hash_password(password)
        session.execute(
            update(ApiToken)
            .where(ApiToken.user_id == user.id, ApiToken.revoked_at.is_(None))
            .values(revoked_at=utcnow())
        )
    apply_changes(user, changes)
    audit.record(
        session,
        actor.user_id,
        "user_updated",
        f"user:{user.id}",
        fields=sorted(payload.model_dump(exclude_unset=True)),
    )
    session.commit()
    return user


def create_first_admin(
    session: Session, username: str, display_name: str, password: str
) -> User:
    """Create an admin from the command line, before any account exists."""
    if session.scalar(select(User.id).where(User.username == username)) is not None:
        raise Conflict
    user = User(
        username=username,
        display_name=display_name,
        role=Role.ADMIN.value,
        password_hash=hash_password(password),
        created_at=utcnow(),
    )
    session.add(user)
    session.flush()
    audit.record(session, None, "admin_created_from_cli", f"user:{user.id}")
    session.commit()
    return user
