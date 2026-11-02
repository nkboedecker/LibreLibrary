"""Libraries, members, copies, tags, shelves, borrowers, and loans."""

from fastapi import APIRouter, status

from librelibrary.api.deps import (
    CurrentActor,
    DbSession,
    Limit,
    Offset,
    PathId,
    QueryId,
)
from librelibrary.schemas import (
    BorrowerIn,
    BorrowerOut,
    BorrowerPatch,
    CopyIn,
    CopyOut,
    CopyPatch,
    LibraryIn,
    LibraryOut,
    LibraryPatch,
    LibraryTransferIn,
    LoanIn,
    LoanOut,
    LoanReturnIn,
    MemberIn,
    MemberOut,
    Page,
    ShelfIn,
    ShelfOut,
    ShelfPatch,
    TagIn,
    TagNamesIn,
    TagOut,
)
from librelibrary.services import libraries

router = APIRouter(tags=["libraries"])
_NO_CONTENT = status.HTTP_204_NO_CONTENT
_CREATED = status.HTTP_201_CREATED


@router.get("/libraries", operation_id="libraries_list")
def list_libraries(
    session: DbSession, actor: CurrentActor, limit: Limit = 50, offset: Offset = 0
) -> Page[LibraryOut]:
    """List the libraries you belong to."""
    return Page[LibraryOut].model_validate(
        libraries.list_libraries(session, actor, limit, offset)
    )


@router.post("/libraries", operation_id="libraries_create", status_code=_CREATED)
def create_library(
    payload: LibraryIn, session: DbSession, actor: CurrentActor
) -> LibraryOut:
    """Create a library that you own."""
    return LibraryOut.model_validate(libraries.create_library(session, actor, payload))


@router.get("/libraries/{library_id}", operation_id="libraries_get")
def get_library(
    library_id: PathId, session: DbSession, actor: CurrentActor
) -> LibraryOut:
    """Return a library you belong to."""
    return LibraryOut.model_validate(libraries.get_library(session, actor, library_id))


@router.patch("/libraries/{library_id}", operation_id="libraries_update")
def update_library(
    library_id: PathId,
    payload: LibraryPatch,
    session: DbSession,
    actor: CurrentActor,
) -> LibraryOut:
    """Change a library you own."""
    return LibraryOut.model_validate(
        libraries.update_library(session, actor, library_id, payload)
    )


@router.delete(
    "/libraries/{library_id}", operation_id="libraries_delete", status_code=_NO_CONTENT
)
def delete_library(library_id: PathId, session: DbSession, actor: CurrentActor) -> None:
    """Delete a library you own, with everything in it."""
    libraries.delete_library(session, actor, library_id)


@router.post("/libraries/{library_id}/transfer", operation_id="libraries_transfer")
def transfer_library(
    library_id: PathId,
    payload: LibraryTransferIn,
    session: DbSession,
    actor: CurrentActor,
) -> LibraryOut:
    """Give a library a new owner. Needs the admin scope."""
    return LibraryOut.model_validate(
        libraries.transfer_library(session, actor, library_id, payload.owner_id)
    )


@router.get("/libraries/{library_id}/members", operation_id="library_members_list")
def list_members(
    library_id: PathId,
    session: DbSession,
    actor: CurrentActor,
    limit: Limit = 50,
    offset: Offset = 0,
) -> Page[MemberOut]:
    """List a library's members."""
    return Page[MemberOut].model_validate(
        libraries.list_members(session, actor, library_id, limit, offset)
    )


@router.put(
    "/libraries/{library_id}/members/{user_id}", operation_id="library_members_set"
)
def set_member(
    library_id: PathId,
    user_id: PathId,
    payload: MemberIn,
    session: DbSession,
    actor: CurrentActor,
) -> MemberOut:
    """Add a member, or change their role."""
    return MemberOut.model_validate(
        libraries.set_member(session, actor, library_id, user_id, payload.role)
    )


@router.delete(
    "/libraries/{library_id}/members/{user_id}",
    operation_id="library_members_remove",
    status_code=_NO_CONTENT,
)
def remove_member(
    library_id: PathId, user_id: PathId, session: DbSession, actor: CurrentActor
) -> None:
    """Remove a member."""
    libraries.remove_member(session, actor, library_id, user_id)


@router.get("/copies", operation_id="copies_list")
def list_copies(  # noqa: PLR0913
    session: DbSession,
    actor: CurrentActor,
    library_id: QueryId = None,
    edition_id: QueryId = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> Page[CopyOut]:
    """List the copies you can see, optionally in one library or of one edition."""
    return Page[CopyOut].model_validate(
        libraries.list_copies(session, actor, library_id, edition_id, limit, offset)
    )


@router.post("/copies", operation_id="copies_create", status_code=_CREATED)
def create_copy(payload: CopyIn, session: DbSession, actor: CurrentActor) -> CopyOut:
    """Add a copy to a library."""
    return CopyOut.model_validate(libraries.create_copy(session, actor, payload))


@router.get("/copies/{copy_id}", operation_id="copies_get")
def get_copy(copy_id: PathId, session: DbSession, actor: CurrentActor) -> CopyOut:
    """Return a copy you can see."""
    return CopyOut.model_validate(libraries.get_copy(session, actor, copy_id))


@router.patch("/copies/{copy_id}", operation_id="copies_update")
def update_copy(
    copy_id: PathId, payload: CopyPatch, session: DbSession, actor: CurrentActor
) -> CopyOut:
    """Change a copy."""
    return CopyOut.model_validate(
        libraries.update_copy(session, actor, copy_id, payload)
    )


@router.delete(
    "/copies/{copy_id}", operation_id="copies_delete", status_code=_NO_CONTENT
)
def delete_copy(copy_id: PathId, session: DbSession, actor: CurrentActor) -> None:
    """Delete a copy."""
    libraries.delete_copy(session, actor, copy_id)


@router.get("/copies/{copy_id}/tags", operation_id="copy_tags_list")
def list_copy_tags(
    copy_id: PathId, session: DbSession, actor: CurrentActor
) -> list[TagOut]:
    """List a copy's tags."""
    tags = libraries.list_copy_tags(session, actor, copy_id)
    return [TagOut.model_validate(tag) for tag in tags]


@router.put("/copies/{copy_id}/tags", operation_id="copy_tags_set")
def set_copy_tags(
    copy_id: PathId, payload: TagNamesIn, session: DbSession, actor: CurrentActor
) -> list[TagOut]:
    """Replace a copy's tags, creating any that are new."""
    tags = libraries.set_copy_tags(session, actor, copy_id, payload.names)
    return [TagOut.model_validate(tag) for tag in tags]


@router.get("/copies/{copy_id}/shelves", operation_id="copy_shelves_list")
def list_copy_shelves(
    copy_id: PathId, session: DbSession, actor: CurrentActor
) -> list[ShelfOut]:
    """List the shelves that hold a copy. Only members of its library see them."""
    shelves = libraries.list_copy_shelves(session, actor, copy_id)
    return [ShelfOut.model_validate(shelf) for shelf in shelves]


@router.get("/libraries/{library_id}/tags", operation_id="tags_list")
def list_tags(
    library_id: PathId,
    session: DbSession,
    actor: CurrentActor,
    limit: Limit = 50,
    offset: Offset = 0,
) -> Page[TagOut]:
    """List a library's tags."""
    return Page[TagOut].model_validate(
        libraries.list_tags(session, actor, library_id, limit, offset)
    )


@router.post(
    "/libraries/{library_id}/tags", operation_id="tags_create", status_code=_CREATED
)
def create_tag(
    library_id: PathId, payload: TagIn, session: DbSession, actor: CurrentActor
) -> TagOut:
    """Create a tag."""
    return TagOut.model_validate(
        libraries.create_tag(session, actor, library_id, payload)
    )


@router.delete("/tags/{tag_id}", operation_id="tags_delete", status_code=_NO_CONTENT)
def delete_tag(tag_id: PathId, session: DbSession, actor: CurrentActor) -> None:
    """Delete a tag."""
    libraries.delete_tag(session, actor, tag_id)


@router.get("/libraries/{library_id}/shelves", operation_id="shelves_list")
def list_shelves(
    library_id: PathId,
    session: DbSession,
    actor: CurrentActor,
    limit: Limit = 50,
    offset: Offset = 0,
) -> Page[ShelfOut]:
    """List a library's shelves."""
    return Page[ShelfOut].model_validate(
        libraries.list_shelves(session, actor, library_id, limit, offset)
    )


@router.post(
    "/libraries/{library_id}/shelves",
    operation_id="shelves_create",
    status_code=_CREATED,
)
def create_shelf(
    library_id: PathId, payload: ShelfIn, session: DbSession, actor: CurrentActor
) -> ShelfOut:
    """Create a shelf."""
    return ShelfOut.model_validate(
        libraries.create_shelf(session, actor, library_id, payload)
    )


@router.get("/shelves/{shelf_id}", operation_id="shelves_get")
def get_shelf(shelf_id: PathId, session: DbSession, actor: CurrentActor) -> ShelfOut:
    """Return a shelf."""
    return ShelfOut.model_validate(libraries.get_shelf(session, actor, shelf_id))


@router.patch("/shelves/{shelf_id}", operation_id="shelves_update")
def update_shelf(
    shelf_id: PathId, payload: ShelfPatch, session: DbSession, actor: CurrentActor
) -> ShelfOut:
    """Change a shelf."""
    return ShelfOut.model_validate(
        libraries.update_shelf(session, actor, shelf_id, payload)
    )


@router.delete(
    "/shelves/{shelf_id}", operation_id="shelves_delete", status_code=_NO_CONTENT
)
def delete_shelf(shelf_id: PathId, session: DbSession, actor: CurrentActor) -> None:
    """Delete a shelf, leaving its copies."""
    libraries.delete_shelf(session, actor, shelf_id)


@router.get("/shelves/{shelf_id}/copies", operation_id="shelf_copies_list")
def list_shelf_copies(
    shelf_id: PathId,
    session: DbSession,
    actor: CurrentActor,
    limit: Limit = 50,
    offset: Offset = 0,
) -> Page[CopyOut]:
    """List the copies on a shelf that you can see."""
    return Page[CopyOut].model_validate(
        libraries.list_shelf_copies(session, actor, shelf_id, limit, offset)
    )


@router.put(
    "/shelves/{shelf_id}/copies/{copy_id}",
    operation_id="shelf_copies_add",
    status_code=_NO_CONTENT,
)
def add_to_shelf(
    shelf_id: PathId, copy_id: PathId, session: DbSession, actor: CurrentActor
) -> None:
    """Put a copy on a shelf."""
    libraries.add_to_shelf(session, actor, shelf_id, copy_id)


@router.delete(
    "/shelves/{shelf_id}/copies/{copy_id}",
    operation_id="shelf_copies_remove",
    status_code=_NO_CONTENT,
)
def remove_from_shelf(
    shelf_id: PathId, copy_id: PathId, session: DbSession, actor: CurrentActor
) -> None:
    """Take a copy off a shelf."""
    libraries.remove_from_shelf(session, actor, shelf_id, copy_id)


@router.get("/libraries/{library_id}/borrowers", operation_id="borrowers_list")
def list_borrowers(
    library_id: PathId,
    session: DbSession,
    actor: CurrentActor,
    limit: Limit = 50,
    offset: Offset = 0,
) -> Page[BorrowerOut]:
    """List a library's borrowers. Needs the editor role."""
    return Page[BorrowerOut].model_validate(
        libraries.list_borrowers(session, actor, library_id, limit, offset)
    )


@router.post(
    "/libraries/{library_id}/borrowers",
    operation_id="borrowers_create",
    status_code=_CREATED,
)
def create_borrower(
    library_id: PathId, payload: BorrowerIn, session: DbSession, actor: CurrentActor
) -> BorrowerOut:
    """Add a borrower."""
    return BorrowerOut.model_validate(
        libraries.create_borrower(session, actor, library_id, payload)
    )


@router.patch("/borrowers/{borrower_id}", operation_id="borrowers_update")
def update_borrower(
    borrower_id: PathId,
    payload: BorrowerPatch,
    session: DbSession,
    actor: CurrentActor,
) -> BorrowerOut:
    """Change a borrower."""
    return BorrowerOut.model_validate(
        libraries.update_borrower(session, actor, borrower_id, payload)
    )


@router.delete(
    "/borrowers/{borrower_id}",
    operation_id="borrowers_delete",
    status_code=_NO_CONTENT,
)
def delete_borrower(
    borrower_id: PathId, session: DbSession, actor: CurrentActor
) -> None:
    """Delete a borrower with no loans."""
    libraries.delete_borrower(session, actor, borrower_id)


@router.get("/libraries/{library_id}/loans", operation_id="loans_list")
def list_loans(
    library_id: PathId,
    session: DbSession,
    actor: CurrentActor,
    limit: Limit = 50,
    offset: Offset = 0,
) -> Page[LoanOut]:
    """List a library's loans. Needs the editor role."""
    return Page[LoanOut].model_validate(
        libraries.list_loans(session, actor, library_id, limit, offset)
    )


@router.post("/loans", operation_id="loans_create", status_code=_CREATED)
def create_loan(payload: LoanIn, session: DbSession, actor: CurrentActor) -> LoanOut:
    """Lend a copy to one of its library's borrowers."""
    return LoanOut.model_validate(libraries.create_loan(session, actor, payload))


@router.post("/loans/{loan_id}/return", operation_id="loans_return")
def return_loan(
    loan_id: PathId, payload: LoanReturnIn, session: DbSession, actor: CurrentActor
) -> LoanOut:
    """Record that a copy came back."""
    return LoanOut.model_validate(
        libraries.return_loan(session, actor, loan_id, payload.returned)
    )


@router.delete("/loans/{loan_id}", operation_id="loans_delete", status_code=_NO_CONTENT)
def delete_loan(loan_id: PathId, session: DbSession, actor: CurrentActor) -> None:
    """Delete a loan record."""
    libraries.delete_loan(session, actor, loan_id)
