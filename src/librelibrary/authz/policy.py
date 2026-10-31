"""Decide what an actor may do. Every service function comes through here."""

from collections.abc import Callable
from dataclasses import dataclass
from enum import IntEnum, StrEnum
from functools import wraps
from typing import Concatenate, NamedTuple


class Scope(StrEnum):
    """What a token may be used for."""

    LIBRARY_READ = "library:read"
    LIBRARY_WRITE = "library:write"
    ADMIN = "admin"
    OPDS = "opds"


class Role(StrEnum):
    """A user's role on the instance."""

    ADMIN = "admin"
    MEMBER = "member"
    GUEST = "guest"


class LibraryRole(StrEnum):
    """A user's role in one library."""

    VIEWER = "viewer"
    EDITOR = "editor"
    OWNER = "owner"


class Privacy(StrEnum):
    """Who can see a copy, rating, review, or note."""

    PRIVATE = "private"  # noqa: S105
    HOUSEHOLD = "household"
    INSTANCE = "instance"


class _Rank(IntEnum):
    VIEWER = 1
    EDITOR = 2
    OWNER = 3


_RANKS = {
    LibraryRole.VIEWER: _Rank.VIEWER,
    LibraryRole.EDITOR: _Rank.EDITOR,
    LibraryRole.OWNER: _Rank.OWNER,
}


class Action(StrEnum):
    """Everything that a service can do."""

    ACCOUNT_READ = "account:read"
    ACCOUNT_WRITE = "account:write"
    TOKEN_READ = "token:read"  # noqa: S105
    TOKEN_WRITE = "token:write"  # noqa: S105
    USER_ADMIN = "user:admin"
    AUDIT_READ = "audit:read"
    SETTINGS_ADMIN = "settings:admin"
    CATALOG_READ = "catalog:read"
    CATALOG_WRITE = "catalog:write"
    CATALOG_DELETE = "catalog:delete"
    LIBRARY_CREATE = "library:create"
    LIBRARY_READ = "library:read"
    LIBRARY_EDIT = "library:edit"
    LIBRARY_MANAGE = "library:manage"
    COPY_READ = "copy:read"
    LOAN_READ = "loan:read"
    PERSONAL_READ = "personal:read"
    PERSONAL_WRITE = "personal:write"


class _Rule(NamedTuple):
    scope: Scope
    blocks_guests: bool = False
    needs_admin: bool = False
    library_role: LibraryRole | None = None


_READ = Scope.LIBRARY_READ
_WRITE = Scope.LIBRARY_WRITE

_RULES = {
    Action.ACCOUNT_READ: _Rule(_READ),
    Action.ACCOUNT_WRITE: _Rule(_WRITE),
    Action.TOKEN_READ: _Rule(_READ),
    Action.TOKEN_WRITE: _Rule(_WRITE),
    Action.USER_ADMIN: _Rule(Scope.ADMIN, needs_admin=True),
    Action.AUDIT_READ: _Rule(Scope.ADMIN, needs_admin=True),
    Action.SETTINGS_ADMIN: _Rule(Scope.ADMIN, needs_admin=True),
    Action.CATALOG_READ: _Rule(_READ),
    Action.CATALOG_WRITE: _Rule(_WRITE, blocks_guests=True),
    Action.CATALOG_DELETE: _Rule(Scope.ADMIN, needs_admin=True),
    Action.LIBRARY_CREATE: _Rule(_WRITE, blocks_guests=True),
    Action.LIBRARY_READ: _Rule(_READ, library_role=LibraryRole.VIEWER),
    Action.LIBRARY_EDIT: _Rule(
        _WRITE, blocks_guests=True, library_role=LibraryRole.EDITOR
    ),
    Action.LIBRARY_MANAGE: _Rule(
        _WRITE, blocks_guests=True, library_role=LibraryRole.OWNER
    ),
    Action.COPY_READ: _Rule(_READ),
    Action.LOAN_READ: _Rule(_READ, library_role=LibraryRole.EDITOR),
    Action.PERSONAL_READ: _Rule(_READ),
    Action.PERSONAL_WRITE: _Rule(_WRITE, blocks_guests=True),
}


@dataclass(frozen=True)
class Actor:
    """Who is acting: a user, their role, and their token's scopes."""

    user_id: int
    role: Role
    scopes: frozenset[Scope]
    token_id: int | None = None


@dataclass(frozen=True)
class LibraryResource:
    """A library, as seen by the actor; the role is None for a non-member."""

    role: LibraryRole | None


@dataclass(frozen=True)
class OwnedResource:
    """A record that belongs to one user."""

    owner_id: int


Resource = LibraryResource | OwnedResource


class Denied(Exception):  # noqa: N818
    """The actor may not do this."""


def require(actor: Actor, action: Action, resource: Resource | None = None) -> None:
    """Raise Denied unless the actor may take the action on the resource."""
    rule = _RULES[action]
    if rule.scope not in actor.scopes:
        raise Denied
    if rule.needs_admin and actor.role != Role.ADMIN:
        raise Denied
    if rule.blocks_guests and actor.role == Role.GUEST:
        raise Denied
    if isinstance(resource, LibraryResource):
        needed = rule.library_role
        if needed is None or resource.role is None:
            raise Denied
        if _RANKS[resource.role] < _RANKS[needed]:
            raise Denied
    if isinstance(resource, OwnedResource) and resource.owner_id != actor.user_id:
        raise Denied


def policy_action[S, **P, R](
    action: Action,
) -> Callable[
    [Callable[Concatenate[S, Actor, P], R]], Callable[Concatenate[S, Actor, P], R]
]:
    """Declare a service function's action, and check it before the function runs.

    Checking first means that a token without the scope is refused before any
    record is read, so a refusal says nothing about what exists.
    """

    def decorate(
        function: Callable[Concatenate[S, Actor, P], R],
    ) -> Callable[Concatenate[S, Actor, P], R]:
        @wraps(function)
        def checked(session: S, actor: Actor, *args: P.args, **kwargs: P.kwargs) -> R:
            require(actor, action)
            return function(session, actor, *args, **kwargs)

        checked.__policy_action__ = action  # type: ignore[attr-defined]
        return checked  # type: ignore[return-value]

    return decorate
