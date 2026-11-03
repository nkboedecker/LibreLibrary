"""Page routes for shelves: create, view, edit, delete, and remove a copy."""

from typing import Annotated, Any

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import RedirectResponse, Response
from pydantic import ValidationError

from librelibrary.api.deps import DbSession, PathId
from librelibrary.authz.policy import Action, LibraryResource, require
from librelibrary.schemas import (
    CopyOut,
    LibraryOut,
    Page,
    ShelfIn,
    ShelfOut,
    ShelfPatch,
)
from librelibrary.services import libraries
from librelibrary.ui import ui_route
from librelibrary.ui.deps import CsrfChecked, CurrentUser
from librelibrary.ui.forms import FormText, blank_to_none, problems
from librelibrary.ui.support import KIND_LABELS, allowed, edition_labels
from librelibrary.ui.templating import templates

router = APIRouter()
PAGE_SIZE = 25
_SEE_OTHER = 303
_LABELS = {"name": "the name", "kind": "the kind"}


def _fields(name: str, kind: str) -> dict[str, str | None]:
    return {"name": blank_to_none(name), "kind": kind.strip() or "shelf"}


def _check(values: dict[str, str | None]) -> tuple[ShelfIn | None, list[str]]:
    """Validate the form, and refuse a kind the page doesn't offer."""
    errors: list[str] = []
    payload = None
    try:
        payload = ShelfIn(**values)  # type: ignore[arg-type]
    except ValidationError as error:
        errors = problems(error, _LABELS)
    if values["kind"] not in KIND_LABELS and "Check the kind." not in errors:
        errors = [*errors, "Check the kind."]
    return (None if errors else payload), errors


def _form(  # noqa: PLR0913
    request: Request,
    user: CurrentUser,
    *,
    library: LibraryOut,
    shelf: ShelfOut | None,
    values: dict[str, Any],
    errors: list[str],
    status_code: int = 200,
) -> Response:
    return templates.TemplateResponse(
        request,
        "shelf_form.html",
        {
            "user": user,
            "nav": "libraries",
            "library": library,
            "shelf": shelf,
            "values": values,
            "errors": errors,
        },
        status_code=status_code,
    )


def _library(session: DbSession, user: CurrentUser, library_id: int) -> LibraryOut:
    return LibraryOut.model_validate(
        libraries.get_library(session, user.actor, library_id)
    )


def _require_edit(session: DbSession, user: CurrentUser, library_id: int) -> None:
    role = libraries.my_roles(session, user.actor).get(library_id)
    require(user.actor, Action.LIBRARY_EDIT, LibraryResource(role))


@ui_route(router, "GET", "/libraries/{library_id}/shelves/new", api=None)
def new_shelf_form(
    request: Request, library_id: PathId, session: DbSession, user: CurrentUser
) -> Response:
    """Show the form for a new shelf; editors and owners only."""
    library = _library(session, user, library_id)
    _require_edit(session, user, library_id)
    return _form(
        request, user, library=library, shelf=None, values={"kind": "shelf"}, errors=[]
    )


@ui_route(router, "POST", "/libraries/{library_id}/shelves/new", api="shelves_create")
def create_shelf(  # noqa: PLR0913
    request: Request,
    library_id: PathId,
    session: DbSession,
    user: CurrentUser,
    _csrf: None = CsrfChecked,
    name: FormText = "",
    kind: FormText = "",
) -> Response:
    """Create a shelf from the form."""
    values = _fields(name, kind)
    payload, errors = _check(values)
    if payload is None:
        return _form(
            request,
            user,
            library=_library(session, user, library_id),
            shelf=None,
            values=values,
            errors=errors,
            status_code=422,
        )
    shelf = libraries.create_shelf(session, user.actor, library_id, payload)
    return RedirectResponse(f"/shelves/{shelf.id}", status_code=_SEE_OTHER)


@ui_route(router, "GET", "/shelves/{shelf_id}", api="shelves_get")
def shelf_detail(
    request: Request,
    shelf_id: PathId,
    session: DbSession,
    user: CurrentUser,
    page: Annotated[int, Query(ge=1, le=1_000_000)] = 1,
) -> Response:
    """Show a shelf with the copies on it that I can see."""
    shelf = ShelfOut.model_validate(libraries.get_shelf(session, user.actor, shelf_id))
    library = _library(session, user, shelf.library_id)
    role = libraries.my_roles(session, user.actor).get(shelf.library_id)
    copies = Page[CopyOut].model_validate(
        libraries.list_shelf_copies(
            session, user.actor, shelf_id, PAGE_SIZE, (page - 1) * PAGE_SIZE
        )
    )
    labels = edition_labels(session, user.actor, [c.edition_id for c in copies.items])
    return templates.TemplateResponse(
        request,
        "shelf.html",
        {
            "user": user,
            "nav": "libraries",
            "shelf": shelf,
            "library": library,
            "can_edit": allowed(user.actor, Action.LIBRARY_EDIT, LibraryResource(role)),
            "copies": copies,
            "labels": labels,
            "page": page,
            "last_page": max(1, -(-copies.total // PAGE_SIZE)),
        },
    )


@ui_route(router, "GET", "/shelves/{shelf_id}/edit", api="shelves_get")
def edit_shelf_form(
    request: Request, shelf_id: PathId, session: DbSession, user: CurrentUser
) -> Response:
    """Show the form to change a shelf; editors and owners only."""
    shelf = ShelfOut.model_validate(libraries.get_shelf(session, user.actor, shelf_id))
    _require_edit(session, user, shelf.library_id)
    return _form(
        request,
        user,
        library=_library(session, user, shelf.library_id),
        shelf=shelf,
        values={"name": shelf.name, "kind": shelf.kind},
        errors=[],
    )


@ui_route(router, "POST", "/shelves/{shelf_id}/edit", api="shelves_update")
def update_shelf(  # noqa: PLR0913
    request: Request,
    shelf_id: PathId,
    session: DbSession,
    user: CurrentUser,
    _csrf: None = CsrfChecked,
    name: FormText = "",
    kind: FormText = "",
) -> Response:
    """Change a shelf from the form."""
    values = _fields(name, kind)
    payload, errors = _check(values)
    if payload is None:
        shelf = ShelfOut.model_validate(
            libraries.get_shelf(session, user.actor, shelf_id)
        )
        return _form(
            request,
            user,
            library=_library(session, user, shelf.library_id),
            shelf=shelf,
            values=values,
            errors=errors,
            status_code=422,
        )
    libraries.update_shelf(
        session, user.actor, shelf_id, ShelfPatch(**payload.model_dump())
    )
    return RedirectResponse(f"/shelves/{shelf_id}", status_code=_SEE_OTHER)


@ui_route(router, "POST", "/shelves/{shelf_id}/delete", api="shelves_delete")
def delete_shelf(  # noqa: PLR0913
    request: Request,
    shelf_id: PathId,
    session: DbSession,
    user: CurrentUser,
    _csrf: None = CsrfChecked,
    confirm: Annotated[str, Form(max_length=10)] = "",
) -> Response:
    """Delete a shelf, once the box is ticked. Its copies stay in the library."""
    shelf = ShelfOut.model_validate(libraries.get_shelf(session, user.actor, shelf_id))
    if confirm != "yes":
        return _form(
            request,
            user,
            library=_library(session, user, shelf.library_id),
            shelf=shelf,
            values={"name": shelf.name, "kind": shelf.kind},
            errors=["Tick the box to confirm the delete."],
            status_code=422,
        )
    libraries.delete_shelf(session, user.actor, shelf_id)
    return RedirectResponse(f"/libraries/{shelf.library_id}", status_code=_SEE_OTHER)


@ui_route(
    router,
    "POST",
    "/shelves/{shelf_id}/copies/{copy_id}/remove",
    api="shelf_copies_remove",
)
def remove_copy_from_shelf(
    shelf_id: PathId,
    copy_id: PathId,
    session: DbSession,
    user: CurrentUser,
    _csrf: None = CsrfChecked,
) -> Response:
    """Take a copy off a shelf. The copy stays in the library."""
    libraries.remove_from_shelf(session, user.actor, shelf_id, copy_id)
    return RedirectResponse(f"/shelves/{shelf_id}", status_code=_SEE_OTHER)
