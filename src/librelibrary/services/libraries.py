"""Libraries and their holdings: copies, tags, shelves, borrowers, and loans."""

from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from librelibrary.authz.policy import (
    Action,
    Actor,
    LibraryResource,
    LibraryRole,
    policy_action,
    require,
)
from librelibrary.authz.scoping import library_role, member_library_ids, visible_copies
from librelibrary.errors import Conflict, NotFound
from librelibrary.models import (
    Borrower,
    Copy,
    CopyTag,
    Edition,
    Library,
    LibraryMember,
    Loan,
    Shelf,
    ShelfItem,
    Tag,
    User,
)
from librelibrary.schemas import (
    BorrowerIn,
    BorrowerPatch,
    CopyIn,
    CopyPatch,
    LibraryIn,
    LibraryPatch,
    LoanIn,
    ShelfIn,
    ShelfPatch,
    TagIn,
)
from librelibrary.services import audit
from librelibrary.services.common import (
    Listing,
    apply_changes,
    get_or_404,
    paginate,
)


def _open_library(
    session: Session, actor: Actor, library_id: int, action: Action
) -> Library:
    """Return a library for an action.

    A non-member gets NotFound, so that a refusal doesn't confirm the library
    exists. A member without enough rights gets Denied.
    """
    library = get_or_404(session, Library, library_id)
    role = library_role(session, actor, library_id)
    if role is None:
        raise NotFound
    require(actor, action, LibraryResource(role))
    return library


def _visible_copy(session: Session, actor: Actor, copy_id: int) -> Copy:
    copy = session.scalar(select(Copy).where(Copy.id == copy_id, visible_copies(actor)))
    if copy is None:
        raise NotFound
    return copy


@policy_action(Action.COPY_READ)
def list_libraries(
    session: Session, actor: Actor, limit: int, offset: int
) -> Listing[Library]:
    """List the libraries that the actor belongs to."""
    statement = (
        select(Library)
        .where(Library.id.in_(member_library_ids(actor)))
        .order_by(Library.id)
    )
    return paginate(session, statement, limit, offset)


@policy_action(Action.LIBRARY_CREATE)
def create_library(session: Session, actor: Actor, payload: LibraryIn) -> Library:
    """Create a library owned by the actor."""
    library = Library(owner_id=actor.user_id, **payload.model_dump())
    session.add(library)
    session.flush()
    session.add(
        LibraryMember(
            library_id=library.id,
            user_id=actor.user_id,
            role=LibraryRole.OWNER.value,
        )
    )
    session.commit()
    return library


@policy_action(Action.LIBRARY_READ)
def get_library(session: Session, actor: Actor, library_id: int) -> Library:
    """Return a library the actor belongs to."""
    return _open_library(session, actor, library_id, Action.LIBRARY_READ)


@policy_action(Action.LIBRARY_MANAGE)
def update_library(
    session: Session, actor: Actor, library_id: int, payload: LibraryPatch
) -> Library:
    """Change a library."""
    library = _open_library(session, actor, library_id, Action.LIBRARY_MANAGE)
    apply_changes(library, payload.model_dump(exclude_unset=True))
    session.commit()
    return library


@policy_action(Action.LIBRARY_MANAGE)
def delete_library(session: Session, actor: Actor, library_id: int) -> None:
    """Delete a library and everything in it.

    Loans go first because the database cascades reach a borrower and a loan in no
    fixed order, and a borrower with a loan can't be deleted.
    """
    library = _open_library(session, actor, library_id, Action.LIBRARY_MANAGE)
    copies = select(Copy.id).where(Copy.library_id == library_id)
    session.execute(delete(Loan).where(Loan.copy_id.in_(copies)))
    session.delete(library)
    session.commit()


@policy_action(Action.LIBRARY_TRANSFER)
def transfer_library(
    session: Session, actor: Actor, library_id: int, owner_id: int
) -> Library:
    """Give a library a new owner, so that it can't be stranded by a departure.

    The old owner stays on as an editor.
    """
    library = get_or_404(session, Library, library_id)
    new_owner = get_or_404(session, User, owner_id)
    if not new_owner.is_active:
        raise Conflict
    old_member = session.get(LibraryMember, (library_id, library.owner_id))
    if old_member is not None and library.owner_id != owner_id:
        old_member.role = LibraryRole.EDITOR.value
    member = session.get(LibraryMember, (library_id, owner_id))
    if member is None:
        member = LibraryMember(library_id=library_id, user_id=owner_id, role="")
        session.add(member)
    member.role = LibraryRole.OWNER.value
    library.owner_id = owner_id
    audit.record(
        session,
        actor.user_id,
        "library_transferred",
        f"library:{library_id}",
        new_owner=owner_id,
    )
    session.commit()
    return library


@policy_action(Action.LIBRARY_READ)
def list_members(
    session: Session, actor: Actor, library_id: int, limit: int, offset: int
) -> Listing[LibraryMember]:
    """List a library's members."""
    _open_library(session, actor, library_id, Action.LIBRARY_READ)
    statement = (
        select(LibraryMember)
        .where(LibraryMember.library_id == library_id)
        .order_by(LibraryMember.user_id)
    )
    return paginate(session, statement, limit, offset)


@policy_action(Action.LIBRARY_MANAGE)
def set_member(
    session: Session, actor: Actor, library_id: int, user_id: int, role: str
) -> LibraryMember:
    """Add a member or change their role. A library keeps its one owner."""
    library = _open_library(session, actor, library_id, Action.LIBRARY_MANAGE)
    get_or_404(session, User, user_id)
    if user_id == library.owner_id or role == LibraryRole.OWNER.value:
        raise Conflict
    member = session.get(LibraryMember, (library_id, user_id))
    if member is None:
        member = LibraryMember(library_id=library_id, user_id=user_id, role=role)
        session.add(member)
    else:
        member.role = role
    session.commit()
    return member


@policy_action(Action.LIBRARY_MANAGE)
def remove_member(
    session: Session, actor: Actor, library_id: int, user_id: int
) -> None:
    """Remove a member. The owner can't be removed."""
    library = _open_library(session, actor, library_id, Action.LIBRARY_MANAGE)
    if user_id == library.owner_id:
        raise Conflict
    member = session.get(LibraryMember, (library_id, user_id))
    if member is None:
        raise NotFound
    session.delete(member)
    session.commit()


@policy_action(Action.COPY_READ)
def list_copies(
    session: Session,
    actor: Actor,
    library_id: int | None,
    edition_id: int | None,
    limit: int,
    offset: int,
) -> Listing[Copy]:
    """List the copies the actor can see, optionally narrowed."""
    statement = select(Copy).where(visible_copies(actor)).order_by(Copy.id)
    if library_id is not None:
        statement = statement.where(Copy.library_id == library_id)
    if edition_id is not None:
        statement = statement.where(Copy.edition_id == edition_id)
    return paginate(session, statement, limit, offset)


@policy_action(Action.LIBRARY_EDIT)
def create_copy(session: Session, actor: Actor, payload: CopyIn) -> Copy:
    """Add a copy to a library."""
    library = _open_library(session, actor, payload.library_id, Action.LIBRARY_EDIT)
    get_or_404(session, Edition, payload.edition_id)
    fields = payload.model_dump()
    fields["privacy"] = payload.privacy or library.default_privacy
    copy = Copy(**fields)
    session.add(copy)
    session.commit()
    return copy


@policy_action(Action.COPY_READ)
def get_copy(session: Session, actor: Actor, copy_id: int) -> Copy:
    """Return a copy the actor can see."""
    return _visible_copy(session, actor, copy_id)


def _editable_copy(session: Session, actor: Actor, copy_id: int) -> Copy:
    copy = _visible_copy(session, actor, copy_id)
    _open_library(session, actor, copy.library_id, Action.LIBRARY_EDIT)
    return copy


@policy_action(Action.LIBRARY_EDIT)
def update_copy(
    session: Session, actor: Actor, copy_id: int, payload: CopyPatch
) -> Copy:
    """Change a copy."""
    copy = _editable_copy(session, actor, copy_id)
    apply_changes(copy, payload.model_dump(exclude_unset=True))
    session.commit()
    return copy


@policy_action(Action.LIBRARY_EDIT)
def delete_copy(session: Session, actor: Actor, copy_id: int) -> None:
    """Delete a copy."""
    session.delete(_editable_copy(session, actor, copy_id))
    session.commit()


@policy_action(Action.COPY_READ)
def list_copy_tags(session: Session, actor: Actor, copy_id: int) -> list[Tag]:
    """List a visible copy's tags."""
    _visible_copy(session, actor, copy_id)
    statement = (
        select(Tag)
        .join(CopyTag, CopyTag.tag_id == Tag.id)
        .where(CopyTag.copy_id == copy_id)
        .order_by(Tag.name)
    )
    return list(session.scalars(statement))


@policy_action(Action.LIBRARY_EDIT)
def set_copy_tags(
    session: Session, actor: Actor, copy_id: int, names: list[str]
) -> list[Tag]:
    """Replace a copy's tags, creating any that are new in its library."""
    copy = _editable_copy(session, actor, copy_id)
    for link in session.scalars(select(CopyTag).where(CopyTag.copy_id == copy_id)):
        session.delete(link)
    session.flush()
    tags = []
    for name in sorted(set(names)):
        tag = session.scalar(
            select(Tag).where(Tag.library_id == copy.library_id, Tag.name == name)
        )
        if tag is None:
            tag = Tag(library_id=copy.library_id, name=name)
            session.add(tag)
            session.flush()
        session.add(CopyTag(copy_id=copy_id, tag_id=tag.id))
        tags.append(tag)
    session.commit()
    return tags


@policy_action(Action.LIBRARY_READ)
def list_tags(
    session: Session, actor: Actor, library_id: int, limit: int, offset: int
) -> Listing[Tag]:
    """List a library's tags."""
    _open_library(session, actor, library_id, Action.LIBRARY_READ)
    statement = select(Tag).where(Tag.library_id == library_id).order_by(Tag.name)
    return paginate(session, statement, limit, offset)


@policy_action(Action.LIBRARY_EDIT)
def create_tag(session: Session, actor: Actor, library_id: int, payload: TagIn) -> Tag:
    """Create a tag in a library."""
    _open_library(session, actor, library_id, Action.LIBRARY_EDIT)
    tag = Tag(library_id=library_id, name=payload.name)
    session.add(tag)
    session.commit()
    return tag


@policy_action(Action.LIBRARY_EDIT)
def delete_tag(session: Session, actor: Actor, tag_id: int) -> None:
    """Delete a tag from a library and its copies."""
    tag = get_or_404(session, Tag, tag_id)
    _open_library(session, actor, tag.library_id, Action.LIBRARY_EDIT)
    session.delete(tag)
    session.commit()


@policy_action(Action.LIBRARY_READ)
def list_shelves(
    session: Session, actor: Actor, library_id: int, limit: int, offset: int
) -> Listing[Shelf]:
    """List a library's shelves."""
    _open_library(session, actor, library_id, Action.LIBRARY_READ)
    statement = select(Shelf).where(Shelf.library_id == library_id).order_by(Shelf.id)
    return paginate(session, statement, limit, offset)


@policy_action(Action.LIBRARY_EDIT)
def create_shelf(
    session: Session, actor: Actor, library_id: int, payload: ShelfIn
) -> Shelf:
    """Create a shelf in a library."""
    _open_library(session, actor, library_id, Action.LIBRARY_EDIT)
    shelf = Shelf(library_id=library_id, **payload.model_dump())
    session.add(shelf)
    session.commit()
    return shelf


def _shelf(session: Session, actor: Actor, shelf_id: int, action: Action) -> Shelf:
    shelf = get_or_404(session, Shelf, shelf_id)
    _open_library(session, actor, shelf.library_id, action)
    return shelf


@policy_action(Action.LIBRARY_READ)
def get_shelf(session: Session, actor: Actor, shelf_id: int) -> Shelf:
    """Return a shelf in a library the actor belongs to."""
    return _shelf(session, actor, shelf_id, Action.LIBRARY_READ)


@policy_action(Action.LIBRARY_EDIT)
def update_shelf(
    session: Session, actor: Actor, shelf_id: int, payload: ShelfPatch
) -> Shelf:
    """Change a shelf."""
    shelf = _shelf(session, actor, shelf_id, Action.LIBRARY_EDIT)
    apply_changes(shelf, payload.model_dump(exclude_unset=True))
    session.commit()
    return shelf


@policy_action(Action.LIBRARY_EDIT)
def delete_shelf(session: Session, actor: Actor, shelf_id: int) -> None:
    """Delete a shelf, leaving its copies."""
    session.delete(_shelf(session, actor, shelf_id, Action.LIBRARY_EDIT))
    session.commit()


@policy_action(Action.LIBRARY_READ)
def list_shelf_copies(
    session: Session, actor: Actor, shelf_id: int, limit: int, offset: int
) -> Listing[Copy]:
    """List the copies on a shelf that the actor can see."""
    _shelf(session, actor, shelf_id, Action.LIBRARY_READ)
    statement = (
        select(Copy)
        .join(ShelfItem, ShelfItem.copy_id == Copy.id)
        .where(ShelfItem.shelf_id == shelf_id, visible_copies(actor))
        .order_by(Copy.id)
    )
    return paginate(session, statement, limit, offset)


@policy_action(Action.LIBRARY_EDIT)
def add_to_shelf(session: Session, actor: Actor, shelf_id: int, copy_id: int) -> None:
    """Put a copy on a shelf in the same library."""
    shelf = _shelf(session, actor, shelf_id, Action.LIBRARY_EDIT)
    copy = _visible_copy(session, actor, copy_id)
    if copy.library_id != shelf.library_id:
        raise Conflict
    if session.get(ShelfItem, (shelf_id, copy_id)) is None:
        session.add(ShelfItem(shelf_id=shelf_id, copy_id=copy_id))
        session.commit()


@policy_action(Action.LIBRARY_EDIT)
def remove_from_shelf(
    session: Session, actor: Actor, shelf_id: int, copy_id: int
) -> None:
    """Take a copy off a shelf."""
    _shelf(session, actor, shelf_id, Action.LIBRARY_EDIT)
    item = session.get(ShelfItem, (shelf_id, copy_id))
    if item is None:
        raise NotFound
    session.delete(item)
    session.commit()


@policy_action(Action.LOAN_READ)
def list_borrowers(
    session: Session, actor: Actor, library_id: int, limit: int, offset: int
) -> Listing[Borrower]:
    """List a library's borrowers. Viewers can't see these contact details."""
    _open_library(session, actor, library_id, Action.LOAN_READ)
    statement = (
        select(Borrower).where(Borrower.library_id == library_id).order_by(Borrower.id)
    )
    return paginate(session, statement, limit, offset)


@policy_action(Action.LIBRARY_EDIT)
def create_borrower(
    session: Session, actor: Actor, library_id: int, payload: BorrowerIn
) -> Borrower:
    """Add a borrower to a library."""
    _open_library(session, actor, library_id, Action.LIBRARY_EDIT)
    borrower = Borrower(library_id=library_id, **payload.model_dump())
    session.add(borrower)
    session.commit()
    return borrower


def _borrower(session: Session, actor: Actor, borrower_id: int) -> Borrower:
    borrower = get_or_404(session, Borrower, borrower_id)
    _open_library(session, actor, borrower.library_id, Action.LIBRARY_EDIT)
    return borrower


@policy_action(Action.LIBRARY_EDIT)
def update_borrower(
    session: Session, actor: Actor, borrower_id: int, payload: BorrowerPatch
) -> Borrower:
    """Change a borrower."""
    borrower = _borrower(session, actor, borrower_id)
    apply_changes(borrower, payload.model_dump(exclude_unset=True))
    session.commit()
    return borrower


@policy_action(Action.LIBRARY_EDIT)
def delete_borrower(session: Session, actor: Actor, borrower_id: int) -> None:
    """Delete a borrower; refused while they have loans."""
    session.delete(_borrower(session, actor, borrower_id))
    session.commit()


@policy_action(Action.LOAN_READ)
def list_loans(
    session: Session, actor: Actor, library_id: int, limit: int, offset: int
) -> Listing[Loan]:
    """List a library's loans."""
    _open_library(session, actor, library_id, Action.LOAN_READ)
    statement = (
        select(Loan)
        .join(Copy, Loan.copy_id == Copy.id)
        .where(Copy.library_id == library_id)
        .order_by(Loan.id)
    )
    return paginate(session, statement, limit, offset)


@policy_action(Action.LIBRARY_EDIT)
def create_loan(session: Session, actor: Actor, payload: LoanIn) -> Loan:
    """Lend a copy to a borrower of the same library."""
    copy = _editable_copy(session, actor, payload.copy_id)
    borrower = session.get(Borrower, payload.borrower_id)
    if borrower is None or borrower.library_id != copy.library_id:
        raise NotFound
    loan = Loan(**payload.model_dump())
    session.add(loan)
    session.commit()
    return loan


def _loan(session: Session, actor: Actor, loan_id: int) -> Loan:
    loan = get_or_404(session, Loan, loan_id)
    _editable_copy(session, actor, loan.copy_id)
    return loan


@policy_action(Action.LIBRARY_EDIT)
def return_loan(session: Session, actor: Actor, loan_id: int, returned: date) -> Loan:
    """Record that a copy came back."""
    loan = _loan(session, actor, loan_id)
    if loan.returned is not None:
        raise Conflict
    loan.returned = returned
    session.commit()
    return loan


@policy_action(Action.LIBRARY_EDIT)
def delete_loan(session: Session, actor: Actor, loan_id: int) -> None:
    """Delete a loan record."""
    session.delete(_loan(session, actor, loan_id))
    session.commit()
