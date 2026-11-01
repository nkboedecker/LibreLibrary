"""Test the policy layer: a matrix of roles, scopes, and library roles."""

import pytest

from librelibrary.authz.policy import (
    Action,
    Actor,
    Denied,
    LibraryResource,
    LibraryRole,
    OwnedResource,
    Role,
    Scope,
    require,
)

READ = frozenset({Scope.LIBRARY_READ})
WRITE = frozenset({Scope.LIBRARY_READ, Scope.LIBRARY_WRITE})
ADMIN = frozenset({Scope.ADMIN})


def actor(role: Role = Role.MEMBER, scopes: frozenset[Scope] = WRITE) -> Actor:
    """Build an actor with user ID 1."""
    return Actor(user_id=1, role=role, scopes=scopes)


@pytest.mark.parametrize("action", list(Action))
def test_a_token_with_no_scopes_can_do_nothing(action: Action) -> None:
    """Every action needs a scope, even for an admin."""
    with pytest.raises(Denied):
        require(actor(Role.ADMIN, frozenset()), action)


@pytest.mark.parametrize(
    "action",
    [
        Action.CATALOG_WRITE,
        Action.LIBRARY_CREATE,
        Action.LIBRARY_EDIT,
        Action.LIBRARY_MANAGE,
        Action.PERSONAL_WRITE,
    ],
)
def test_guests_are_read_only(action: Action) -> None:
    """A guest's write scope gives no write access to the library."""
    with pytest.raises(Denied):
        require(actor(Role.GUEST), action)


@pytest.mark.parametrize("action", [Action.TOKEN_WRITE, Action.ACCOUNT_WRITE])
def test_guests_can_look_after_their_own_account(action: Action) -> None:
    """Read-only applies to library data, not to a guest's own credentials."""
    require(actor(Role.GUEST), action)


def test_a_read_token_cannot_write() -> None:
    """A token never gets more than its scopes, whatever its user's role."""
    with pytest.raises(Denied):
        require(actor(Role.ADMIN, READ), Action.CATALOG_WRITE)


@pytest.mark.parametrize(
    "action",
    [
        Action.USER_ADMIN,
        Action.AUDIT_READ,
        Action.SETTINGS_ADMIN,
        Action.CATALOG_DELETE,
        Action.GROUP_ADMIN,
    ],
)
class TestAdminActions:
    """Administration needs both the role and the scope."""

    def test_admin_with_scope_is_allowed(self, action: Action) -> None:
        """An admin's admin-scoped token may administer."""
        require(actor(Role.ADMIN, ADMIN), action)

    def test_member_with_scope_is_denied(self, action: Action) -> None:
        """An admin-scoped token never exceeds its user's permissions."""
        with pytest.raises(Denied):
            require(actor(Role.MEMBER, ADMIN), action)

    def test_admin_without_scope_is_denied(self, action: Action) -> None:
        """An admin's everyday token can't administer."""
        with pytest.raises(Denied):
            require(actor(Role.ADMIN, WRITE), action)


@pytest.mark.parametrize(
    ("action", "library_role", "allowed"),
    [
        (Action.LIBRARY_READ, None, False),
        (Action.LIBRARY_READ, LibraryRole.VIEWER, True),
        (Action.LIBRARY_EDIT, LibraryRole.VIEWER, False),
        (Action.LIBRARY_EDIT, LibraryRole.EDITOR, True),
        (Action.LIBRARY_MANAGE, LibraryRole.EDITOR, False),
        (Action.LIBRARY_MANAGE, LibraryRole.OWNER, True),
        (Action.LOAN_READ, LibraryRole.VIEWER, False),
        (Action.LOAN_READ, LibraryRole.EDITOR, True),
    ],
)
def test_library_roles(
    action: Action, library_role: LibraryRole | None, allowed: bool
) -> None:
    """Each library action has a minimum library role."""
    resource = LibraryResource(library_role)
    if allowed:
        require(actor(), action, resource)
    else:
        with pytest.raises(Denied):
            require(actor(), action, resource)


def test_global_admins_get_no_library_rights() -> None:
    """Being an admin doesn't open other people's libraries."""
    with pytest.raises(Denied):
        require(actor(Role.ADMIN), Action.LIBRARY_READ, LibraryResource(None))


def test_owned_resources_belong_to_their_owner() -> None:
    """Only the owner may change a personal record."""
    require(actor(), Action.PERSONAL_WRITE, OwnedResource(owner_id=1))
    with pytest.raises(Denied):
        require(actor(Role.ADMIN), Action.PERSONAL_WRITE, OwnedResource(owner_id=2))
