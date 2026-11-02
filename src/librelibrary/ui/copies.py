"""Page routes for copies: detail, add, edit, and delete."""

from typing import Annotated, Any

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import RedirectResponse, Response
from pydantic import ValidationError

from librelibrary.api.deps import DbSession, PathId
from librelibrary.authz.policy import Action, LibraryResource, require
from librelibrary.schemas import CopyIn, CopyOut, CopyPatch, LibraryOut, Page
from librelibrary.services import libraries
from librelibrary.ui import ui_route
from librelibrary.ui.deps import CsrfChecked, CurrentUser
from librelibrary.ui.forms import FormText, blank_to_none, problems
from librelibrary.ui.support import allowed, edition_labels, money
from librelibrary.ui.templating import templates

router = APIRouter()
ALL = 200
_SEE_OTHER = 303
_ID = Annotated[int, Form(ge=1, le=2_147_483_647)]
_LABELS = {
    "condition": "the condition",
    "location": "the location",
    "acquired": "the date acquired",
    "source": "the source",
    "price": "the price",
    "currency": "the currency",
    "privacy": "the sharing",
    "library_id": "the library",
    "edition_id": "the edition",
}


def _fields(  # noqa: PLR0913
    condition: str,
    location: str,
    acquired: str,
    source: str,
    price: str,
    currency: str,
    privacy: str,
) -> dict[str, str | None]:
    code = blank_to_none(currency)
    return {
        "condition": blank_to_none(condition),
        "location": blank_to_none(location),
        "acquired": blank_to_none(acquired),
        "source": blank_to_none(source),
        "price": blank_to_none(price),
        "currency": code.upper() if code else None,
        "privacy": blank_to_none(privacy),
    }


def _values_of(copy: CopyOut) -> dict[str, Any]:
    return {
        "condition": copy.condition,
        "location": copy.location,
        "acquired": copy.acquired.isoformat() if copy.acquired else None,
        "source": copy.source,
        "price": money(copy.price) if copy.price is not None else None,
        "currency": copy.currency,
        "privacy": copy.privacy,
    }


def _writable_libraries(session: DbSession, user: CurrentUser) -> list[LibraryOut]:
    """List the libraries where I may add copies."""
    roles = libraries.my_roles(session, user.actor)
    listing = Page[LibraryOut].model_validate(
        libraries.list_libraries(session, user.actor, ALL, 0)
    )
    return [
        library
        for library in listing.items
        if allowed(
            user.actor, Action.LIBRARY_EDIT, LibraryResource(roles.get(library.id))
        )
    ]


def _new_form(  # noqa: PLR0913
    request: Request,
    session: DbSession,
    user: CurrentUser,
    *,
    edition_id: int,
    values: dict[str, Any],
    errors: list[str],
    status_code: int = 200,
) -> Response:
    label = edition_labels(session, user.actor, [edition_id])[edition_id]
    return templates.TemplateResponse(
        request,
        "copy_form.html",
        {
            "user": user,
            "nav": "libraries",
            "copy": None,
            "edition_id": edition_id,
            "label": label,
            "choices": _writable_libraries(session, user),
            "values": values,
            "errors": errors,
        },
        status_code=status_code,
    )


def _edit_form(  # noqa: PLR0913
    request: Request,
    session: DbSession,
    user: CurrentUser,
    *,
    copy: CopyOut,
    values: dict[str, Any],
    errors: list[str],
    status_code: int = 200,
) -> Response:
    label = edition_labels(session, user.actor, [copy.edition_id])[copy.edition_id]
    return templates.TemplateResponse(
        request,
        "copy_form.html",
        {
            "user": user,
            "nav": "libraries",
            "copy": copy,
            "edition_id": copy.edition_id,
            "label": label,
            "choices": [],
            "values": values,
            "errors": errors,
        },
        status_code=status_code,
    )


@ui_route(router, "GET", "/copies/new", api=None)
def new_copy_form(
    request: Request,
    session: DbSession,
    user: CurrentUser,
    edition_id: Annotated[int, Query(ge=1, le=2_147_483_647)],
) -> Response:
    """Show the form to add a copy of an edition."""
    return _new_form(
        request, session, user, edition_id=edition_id, values={}, errors=[]
    )


@ui_route(router, "POST", "/copies/new", api="copies_create")
def create_copy(  # noqa: PLR0913
    request: Request,
    session: DbSession,
    user: CurrentUser,
    library_id: _ID,
    edition_id: _ID,
    _csrf: None = CsrfChecked,
    condition: FormText = "",
    location: FormText = "",
    acquired: FormText = "",
    source: FormText = "",
    price: FormText = "",
    currency: FormText = "",
    privacy: FormText = "",
) -> Response:
    """Add a copy to a library from the form."""
    values: dict[str, Any] = {
        "library_id": library_id,
        "edition_id": edition_id,
        **_fields(condition, location, acquired, source, price, currency, privacy),
    }
    try:
        payload = CopyIn(**values)
    except ValidationError as error:
        return _new_form(
            request,
            session,
            user,
            edition_id=edition_id,
            values=values,
            errors=problems(error, _LABELS),
            status_code=422,
        )
    copy = libraries.create_copy(session, user.actor, payload)
    return RedirectResponse(f"/copies/{copy.id}", status_code=_SEE_OTHER)


@ui_route(router, "GET", "/copies/{copy_id}", api="copies_get")
def copy_detail(
    request: Request, copy_id: PathId, session: DbSession, user: CurrentUser
) -> Response:
    """Show a copy I can see."""
    copy = CopyOut.model_validate(libraries.get_copy(session, user.actor, copy_id))
    label = edition_labels(session, user.actor, [copy.edition_id])[copy.edition_id]
    role = libraries.my_roles(session, user.actor).get(copy.library_id)
    library = None
    if role is not None:
        library = LibraryOut.model_validate(
            libraries.get_library(session, user.actor, copy.library_id)
        )
    return templates.TemplateResponse(
        request,
        "copy.html",
        {
            "user": user,
            "nav": "libraries",
            "copy": copy,
            "label": label,
            "library": library,
            "can_edit": allowed(user.actor, Action.LIBRARY_EDIT, LibraryResource(role)),
        },
    )


@ui_route(router, "GET", "/copies/{copy_id}/edit", api="copies_get")
def edit_copy_form(
    request: Request, copy_id: PathId, session: DbSession, user: CurrentUser
) -> Response:
    """Show the form to change a copy; only editors and owners may."""
    copy = CopyOut.model_validate(libraries.get_copy(session, user.actor, copy_id))
    role = libraries.my_roles(session, user.actor).get(copy.library_id)
    require(user.actor, Action.LIBRARY_EDIT, LibraryResource(role))
    return _edit_form(
        request, session, user, copy=copy, values=_values_of(copy), errors=[]
    )


@ui_route(router, "POST", "/copies/{copy_id}/edit", api="copies_update")
def update_copy(  # noqa: PLR0913
    request: Request,
    copy_id: PathId,
    session: DbSession,
    user: CurrentUser,
    _csrf: None = CsrfChecked,
    condition: FormText = "",
    location: FormText = "",
    acquired: FormText = "",
    source: FormText = "",
    price: FormText = "",
    currency: FormText = "",
    privacy: FormText = "",
) -> Response:
    """Change a copy from the form. A blank optional field clears it."""
    values = _fields(condition, location, acquired, source, price, currency, privacy)
    # Sharing can't be cleared, so a blank choice means "leave it as it is".
    changes: dict[str, Any] = {
        k: v for k, v in values.items() if not (k == "privacy" and v is None)
    }
    try:
        payload = CopyPatch(**changes)
    except ValidationError as error:
        copy = CopyOut.model_validate(libraries.get_copy(session, user.actor, copy_id))
        return _edit_form(
            request,
            session,
            user,
            copy=copy,
            values=values,
            errors=problems(error, _LABELS),
            status_code=422,
        )
    libraries.update_copy(session, user.actor, copy_id, payload)
    return RedirectResponse(f"/copies/{copy_id}", status_code=_SEE_OTHER)


@ui_route(router, "POST", "/copies/{copy_id}/delete", api="copies_delete")
def delete_copy(  # noqa: PLR0913
    request: Request,
    copy_id: PathId,
    session: DbSession,
    user: CurrentUser,
    _csrf: None = CsrfChecked,
    confirm: Annotated[str, Form(max_length=10)] = "",
) -> Response:
    """Delete a copy, once the box is ticked."""
    copy = CopyOut.model_validate(libraries.get_copy(session, user.actor, copy_id))
    if confirm != "yes":
        return _edit_form(
            request,
            session,
            user,
            copy=copy,
            values=_values_of(copy),
            errors=["Tick the box to confirm the delete."],
            status_code=422,
        )
    libraries.delete_copy(session, user.actor, copy_id)
    return RedirectResponse(f"/libraries/{copy.library_id}", status_code=_SEE_OTHER)
