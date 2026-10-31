"""Query helpers that keep rows an actor can't see out of every list."""

from sqlalchemy import ColumnElement, Select, and_, or_, select
from sqlalchemy.orm import Session

from librelibrary.authz.policy import Actor, LibraryRole, Privacy
from librelibrary.models import Copy, Library, LibraryMember, Note, Rating, Review


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


def visible_copies(actor: Actor) -> ColumnElement[bool]:
    """Match the copies the actor can see.

    Private copies are for the library's owner, and for its editors if the
    library allows that. Household copies are for its members, and instance
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
            Library.editors_see_private.is_(True),
        )
    )
    return or_(
        Copy.privacy == Privacy.INSTANCE.value,
        and_(
            Copy.privacy == Privacy.HOUSEHOLD.value,
            Copy.library_id.in_(member_library_ids(actor)),
        ),
        Copy.library_id.in_(owned),
        Copy.library_id.in_(edited),
    )


def visible_responses(
    actor: Actor, model: type[Rating] | type[Review] | type[Note]
) -> ColumnElement[bool]:
    """Match the ratings, reviews, or notes the actor can see.

    Household means anyone who shares a library with the author.
    """
    housemates = select(LibraryMember.user_id).where(
        LibraryMember.library_id.in_(member_library_ids(actor))
    )
    return or_(
        model.user_id == actor.user_id,
        model.privacy == Privacy.INSTANCE.value,
        and_(model.privacy == Privacy.HOUSEHOLD.value, model.user_id.in_(housemates)),
    )
