"""Query helpers that keep rows an actor can't see out of every list."""

from sqlalchemy import ColumnElement, Select, and_, or_, select
from sqlalchemy.orm import Session

from librelibrary.authz.policy import Actor, LibraryRole, Privacy
from librelibrary.models import (
    Copy,
    GroupLibrary,
    GroupMember,
    Library,
    LibraryMember,
    Note,
    Rating,
    Review,
    User,
)


def member_library_ids(actor: Actor) -> Select[int]:
    """Select the libraries that the actor belongs to."""
    return select(LibraryMember.library_id).where(
        LibraryMember.user_id == actor.user_id
    )


def library_role(session: Session, actor: Actor, library_id: int) -> LibraryRole | None:
    """Return the actor's role in a library, or None for a non-member."""
    role = session.scalar(
        select(LibraryMember.role).where(
            LibraryMember.library_id == library_id,
            LibraryMember.user_id == actor.user_id,
        )
    )
    return LibraryRole(role) if role else None


def member_group_ids(actor: Actor) -> Select[int]:
    """Select the groups that the actor belongs to."""
    return select(GroupMember.group_id).where(GroupMember.user_id == actor.user_id)


def visible_copies(actor: Actor) -> ColumnElement[bool]:
    """Match the copies the actor can see.

    Each level adds to the one before it. Personal copies are for the library's
    owner, and for its editors if the library allows that. Library copies add its
    members, group copies add members of any group the library is in, and server
    copies are for everyone signed in.
    """
    owned = select(LibraryMember.library_id).where(
        LibraryMember.user_id == actor.user_id,
        LibraryMember.role == LibraryRole.OWNER.value,
    )
    edited = (
        select(LibraryMember.library_id)
        .join(Library, Library.id == LibraryMember.library_id)
        .where(
            LibraryMember.user_id == actor.user_id,
            LibraryMember.role == LibraryRole.EDITOR.value,
            Library.editors_see_personal.is_(True),
        )
    )
    group_libraries = select(GroupLibrary.library_id).where(
        GroupLibrary.group_id.in_(member_group_ids(actor))
    )
    return or_(
        Copy.privacy == Privacy.SERVER.value,
        and_(
            Copy.privacy.in_([Privacy.LIBRARY.value, Privacy.GROUP.value]),
            Copy.library_id.in_(member_library_ids(actor)),
        ),
        and_(Copy.privacy == Privacy.GROUP.value, Copy.library_id.in_(group_libraries)),
        Copy.library_id.in_(owned),
        Copy.library_id.in_(edited),
    )


def visible_responses(
    actor: Actor, model: type[Rating] | type[Review] | type[Note]
) -> ColumnElement[bool]:
    """Match the ratings, reviews, or notes the actor can see.

    Authors always see their own. Anyone else needs the record to be shared with
    them, and its author's account to be active.
    """
    active_users = select(User.id).where(User.is_active.is_(True))
    return or_(
        model.user_id == actor.user_id,
        and_(
            model.user_id.in_(active_users),
            or_(
                model.privacy == Privacy.SERVER.value,
                and_(
                    model.privacy == Privacy.LIBRARY.value,
                    model.audience_library_id.in_(member_library_ids(actor)),
                ),
                and_(
                    model.privacy == Privacy.GROUP.value,
                    model.audience_group_id.in_(member_group_ids(actor)),
                ),
            ),
        ),
    )
