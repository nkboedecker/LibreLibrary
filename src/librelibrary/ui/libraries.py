"""Page routes for libraries: list, detail, create, edit, and delete."""

from typing import Annotated, Any

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import RedirectResponse, Response
from pydantic import ValidationError

from librelibrary.api.deps import DbSession, PathId
from librelibrary.authz.policy import Action, LibraryResource, require
from librelibrary.schemas import (
    CopyOut,
    LibraryIn,
    LibraryOut,
    LibraryPatch,
    MemberOut,
    Page,
)
from librelibrary.services import libraries
from librelibrary.ui import ui_route
from librelibrary.ui.deps import CsrfChecked, CurrentUser
from librelibrary.ui.forms import FormText, blank_to_none, problems
from librelibrary.ui.support import allowed, edition_labels
from librelibrary.ui.templating import templates

router = APIRouter()
PAGE_SIZE = 25
ALL = 200
_SEE_OTHER = 303
_LABELS = {"name": "the name", "default_privacy": "the default sharing"}


def _fields(
    name: str, default_privacy: str, editors_see_personal: str
) -> dict[str, Any]:
    return {
        "name": blank_to_none(name),
        "default_privacy": default_privacy.strip() or "personal",
        "editors_see_personal": editors_see_personal == "yes",
    }


def _form(
    request: Request,
    user: CurrentUser,
    *,
    library: LibraryOut | None,
    values: dict[str, Any],
    errors: list[str],
    status_code: int = 200,
) -> Response:
    return templates.TemplateResponse(
        request,
        "library_form.html",
        {
            "user": user,
            "nav": "libraries",
            "library": library,
            "values": values,
            "errors": errors,
        },
        status_code=status_code,
    )


def _values_of(library: LibraryOut) -> dict[str, Any]:
    return {
        "name": library.name,
        "default_privacy": library.default_privacy,
        "editors_see_personal": library.editors_see_personal,
    }


@ui_route(router, "GET", "/libraries", api="libraries_list")
def library_list(request: Request, session: DbSession, user: CurrentUser) -> Response:
    """List the libraries I belong to, with my role in each."""
    listing = Page[LibraryOut].model_validate(
        libraries.list_libraries(session, user.actor, ALL, 0)
    )
    roles = libraries.my_roles(session, user.actor)
    return templates.TemplateResponse(
        request,
        "libraries.html",
        {"user": user, "nav": "libraries", "listing": listing, "roles": roles},
    )


@ui_route(router, "GET", "/libraries/new", api=None)
def new_library_form(request: Request, user: CurrentUser) -> Response:
    """Show the form for a new library."""
    values = {"default_privacy": "personal", "editors_see_personal": True}
    return _form(request, user, library=None, values=values, errors=[])


@ui_route(router, "POST", "/libraries/new", api="libraries_create")
def create_library(  # noqa: PLR0913
    request: Request,
    session: DbSession,
    user: CurrentUser,
    _csrf: None = CsrfChecked,
    name: FormText = "",
    default_privacy: FormText = "",
    editors_see_personal: FormText = "",
) -> Response:
    """Create a library that I own."""
    values = _fields(name, default_privacy, editors_see_personal)
    try:
        payload = LibraryIn(**values)
    except ValidationError as error:
        return _form(
            request,
            user,
            library=None,
            values=values,
            errors=problems(error, _LABELS),
            status_code=422,
        )
    library = libraries.create_library(session, user.actor, payload)
    return RedirectResponse(f"/libraries/{library.id}", status_code=_SEE_OTHER)


@ui_route(router, "GET", "/libraries/{library_id}", api="libraries_get")
def library_detail(
    request: Request,
    library_id: PathId,
    session: DbSession,
    user: CurrentUser,
    page: Annotated[int, Query(ge=1, le=1_000_000)] = 1,
) -> Response:
    """Show a library with its members and the copies I can see in it."""
    library = LibraryOut.model_validate(
        libraries.get_library(session, user.actor, library_id)
    )
    role = libraries.my_roles(session, user.actor).get(library_id)
    resource = LibraryResource(role)
    members = Page[MemberOut].model_validate(
        libraries.list_members(session, user.actor, library_id, ALL, 0)
    )
    copies = Page[CopyOut].model_validate(
        libraries.list_copies(
            session, user.actor, library_id, None, PAGE_SIZE, (page - 1) * PAGE_SIZE
        )
    )
    labels = edition_labels(session, user.actor, [c.edition_id for c in copies.items])
    return templates.TemplateResponse(
        request,
        "library.html",
        {
            "user": user,
            "nav": "libraries",
            "library": library,
            "role": role,
            "can_manage": allowed(user.actor, Action.LIBRARY_MANAGE, resource),
            "can_edit": allowed(user.actor, Action.LIBRARY_EDIT, resource),
            "members": members,
            "copies": copies,
            "labels": labels,
            "page": page,
            "last_page": max(1, -(-copies.total // PAGE_SIZE)),
        },
    )


@ui_route(router, "GET", "/libraries/{library_id}/edit", api="libraries_get")
def edit_library_form(
    request: Request, library_id: PathId, session: DbSession, user: CurrentUser
) -> Response:
    """Show the form to change a library; only its owner may."""
    library = LibraryOut.model_validate(
        libraries.get_library(session, user.actor, library_id)
    )
    role = libraries.my_roles(session, user.actor).get(library_id)
    require(user.actor, Action.LIBRARY_MANAGE, LibraryResource(role))
    return _form(request, user, library=library, values=_values_of(library), errors=[])


@ui_route(router, "POST", "/libraries/{library_id}/edit", api="libraries_update")
def update_library(  # noqa: PLR0913
    request: Request,
    library_id: PathId,
    session: DbSession,
    user: CurrentUser,
    _csrf: None = CsrfChecked,
    name: FormText = "",
    default_privacy: FormText = "",
    editors_see_personal: FormText = "",
) -> Response:
    """Change a library from the form."""
    values = _fields(name, default_privacy, editors_see_personal)
    try:
        checked = LibraryIn(**values)
    except ValidationError as error:
        library = LibraryOut.model_validate(
            libraries.get_library(session, user.actor, library_id)
        )
        return _form(
            request,
            user,
            library=library,
            values=values,
            errors=problems(error, _LABELS),
            status_code=422,
        )
    libraries.update_library(
        session, user.actor, library_id, LibraryPatch(**checked.model_dump())
    )
    return RedirectResponse(f"/libraries/{library_id}", status_code=_SEE_OTHER)


@ui_route(router, "POST", "/libraries/{library_id}/delete", api="libraries_delete")
def delete_library(  # noqa: PLR0913
    request: Request,
    library_id: PathId,
    session: DbSession,
    user: CurrentUser,
    _csrf: None = CsrfChecked,
    confirm: Annotated[str, Form(max_length=10)] = "",
) -> Response:
    """Delete a library with its copies, once the box is ticked."""
    if confirm != "yes":
        library = LibraryOut.model_validate(
            libraries.get_library(session, user.actor, library_id)
        )
        return _form(
            request,
            user,
            library=library,
            values=_values_of(library),
            errors=["Tick the box to confirm the delete."],
            status_code=422,
        )
    libraries.delete_library(session, user.actor, library_id)
    return RedirectResponse("/libraries", status_code=_SEE_OTHER)
