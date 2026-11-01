"""Groups: users and libraries that share with each other."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from librelibrary.authz.policy import (
    Action,
    Actor,
    Denied,
    LibraryResource,
    Role,
    Scope,
    policy_action,
    require,
)
from librelibrary.authz.scoping import library_role, member_group_ids
from librelibrary.errors import NotFound
from librelibrary.models import Group, GroupLibrary, GroupMember, Library, User
from librelibrary.schemas import GroupIn
from librelibrary.services import audit
from librelibrary.services.common import Listing, get_or_404, paginate


def _can_administer(actor: Actor) -> bool:
    return actor.role == Role.ADMIN and Scope.ADMIN in actor.scopes


def _readable_group(session: Session, actor: Actor, group_id: int) -> Group:
    """Return a group its member or an admin may see; others get NotFound."""
    group = get_or_404(session, Group, group_id)
    is_member = session.get(GroupMember, (group_id, actor.user_id)) is not None
    if not is_member and not _can_administer(actor):
        raise NotFound
    return group


@policy_action(Action.GROUP_READ)
def list_groups(
    session: Session, actor: Actor, limit: int, offset: int
) -> Listing[Group]:
    """List the groups that the actor belongs to."""
    statement = (
        select(Group).where(Group.id.in_(member_group_ids(actor))).order_by(Group.id)
    )
    return paginate(session, statement, limit, offset)


@policy_action(Action.GROUP_ADMIN)
def list_all_groups(
    session: Session, actor: Actor, limit: int, offset: int
) -> Listing[Group]:
    """List every group."""
    return paginate(session, select(Group).order_by(Group.id), limit, offset)


@policy_action(Action.GROUP_ADMIN)
def create_group(session: Session, actor: Actor, payload: GroupIn) -> Group:
    """Create a group."""
    group = Group(name=payload.name)
    session.add(group)
    session.flush()
    audit.record(session, actor.user_id, "group_created", f"group:{group.id}")
    session.commit()
    return group


@policy_action(Action.GROUP_READ)
def get_group(session: Session, actor: Actor, group_id: int) -> Group:
    """Return a group."""
    return _readable_group(session, actor, group_id)


@policy_action(Action.GROUP_ADMIN)
def update_group(
    session: Session, actor: Actor, group_id: int, payload: GroupIn
) -> Group:
    """Rename a group."""
    group = get_or_404(session, Group, group_id)
    group.name = payload.name
    session.commit()
    return group


@policy_action(Action.GROUP_ADMIN)
def delete_group(session: Session, actor: Actor, group_id: int) -> None:
    """Delete a group. Records shared with it stay visible to their authors."""
    session.delete(get_or_404(session, Group, group_id))
    audit.record(session, actor.user_id, "group_deleted", f"group:{group_id}")
    session.commit()


@policy_action(Action.GROUP_READ)
def list_members(
    session: Session, actor: Actor, group_id: int, limit: int, offset: int
) -> Listing[GroupMember]:
    """List a group's members."""
    _readable_group(session, actor, group_id)
    statement = (
        select(GroupMember)
        .where(GroupMember.group_id == group_id)
        .order_by(GroupMember.user_id)
    )
    return paginate(session, statement, limit, offset)


@policy_action(Action.GROUP_ADMIN)
def add_member(session: Session, actor: Actor, group_id: int, user_id: int) -> None:
    """Add a user to a group."""
    get_or_404(session, Group, group_id)
    get_or_404(session, User, user_id)
    if session.get(GroupMember, (group_id, user_id)) is None:
        session.add(GroupMember(group_id=group_id, user_id=user_id))
        audit.record(
            session,
            actor.user_id,
            "group_member_added",
            f"group:{group_id}",
            user=user_id,
        )
        session.commit()


@policy_action(Action.GROUP_ADMIN)
def remove_member(session: Session, actor: Actor, group_id: int, user_id: int) -> None:
    """Remove a user from a group. Their access through it ends at once."""
    member = session.get(GroupMember, (group_id, user_id))
    if member is None:
        raise NotFound
    session.delete(member)
    audit.record(
        session,
        actor.user_id,
        "group_member_removed",
        f"group:{group_id}",
        user=user_id,
    )
    session.commit()


@policy_action(Action.GROUP_READ)
def list_libraries(
    session: Session, actor: Actor, group_id: int, limit: int, offset: int
) -> Listing[GroupLibrary]:
    """List the libraries in a group."""
    _readable_group(session, actor, group_id)
    statement = (
        select(GroupLibrary)
        .where(GroupLibrary.group_id == group_id)
        .order_by(GroupLibrary.library_id)
    )
    return paginate(session, statement, limit, offset)


@policy_action(Action.GROUP_LIBRARY_EDIT)
def add_library(session: Session, actor: Actor, group_id: int, library_id: int) -> None:
    """Add a library to a group; its owner must belong to the group."""
    get_or_404(session, Library, library_id)
    role = library_role(session, actor, library_id)
    if role is None:
        raise NotFound
    require(actor, Action.LIBRARY_MANAGE, LibraryResource(role))
    get_or_404(session, Group, group_id)
    if session.get(GroupMember, (group_id, actor.user_id)) is None:
        raise NotFound
    if session.get(GroupLibrary, (group_id, library_id)) is None:
        session.add(GroupLibrary(group_id=group_id, library_id=library_id))
        audit.record(
            session,
            actor.user_id,
            "group_library_added",
            f"group:{group_id}",
            library=library_id,
        )
        session.commit()


@policy_action(Action.GROUP_LIBRARY_EDIT)
def remove_library(
    session: Session, actor: Actor, group_id: int, library_id: int
) -> None:
    """Take a library out of a group; its owner or an admin may do this."""
    if not _can_administer(actor):
        role = library_role(session, actor, library_id)
        if role is None:
            # A group member who isn't in the library knows it's there, so a
            # refusal reveals nothing; a stranger gets the same answer.
            raise Denied
        require(actor, Action.LIBRARY_MANAGE, LibraryResource(role))
    link = session.get(GroupLibrary, (group_id, library_id))
    if link is None:
        raise NotFound
    session.delete(link)
    audit.record(
        session,
        actor.user_id,
        "group_library_removed",
        f"group:{group_id}",
        library=library_id,
    )
    session.commit()
