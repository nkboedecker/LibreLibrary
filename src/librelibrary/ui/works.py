"""Page routes for works: list, detail, create, edit, and delete."""

from typing import Annotated

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import RedirectResponse, Response
from pydantic import ValidationError

from librelibrary.api.deps import DbSession, PathId
from librelibrary.schemas import EditionIn, EditionOut, Page, WorkIn, WorkOut, WorkPatch
from librelibrary.services import catalog
from librelibrary.ui import ui_route
from librelibrary.ui.deps import CsrfChecked, CurrentUser
from librelibrary.ui.forms import FormText, blank_to_none, problems
from librelibrary.ui.templating import templates

router = APIRouter()
PAGE_SIZE = 25
_SEE_OTHER = 303
_LABELS = {
    "title": "the title",
    "original_language": "the original language",
    "first_published": "the first published date",
    "description": "the description",
}


def _fields(
    title: str, original_language: str, first_published: str, description: str
) -> dict[str, str | None]:
    return {
        "title": blank_to_none(title),
        "original_language": blank_to_none(original_language),
        "first_published": blank_to_none(first_published),
        "description": blank_to_none(description),
    }


def _form(
    request: Request,
    user: CurrentUser,
    *,
    work: WorkOut | None,
    values: dict[str, str | None],
    errors: list[str],
    status_code: int = 200,
) -> Response:
    return templates.TemplateResponse(
        request,
        "work_form.html",
        {
            "user": user,
            "nav": "works",
            "work": work,
            "values": values,
            "errors": errors,
        },
        status_code=status_code,
    )


@ui_route(router, "GET", "/works", api="works_list")
def works(
    request: Request,
    session: DbSession,
    user: CurrentUser,
    q: Annotated[str | None, Query(max_length=200, pattern=r"^[^\x00]*$")] = None,
    page: Annotated[int, Query(ge=1, le=1_000_000)] = 1,
) -> Response:
    """List works, with a search box and paging."""
    listing = Page[WorkOut].model_validate(
        catalog.list_works(session, user.actor, q, PAGE_SIZE, (page - 1) * PAGE_SIZE)
    )
    last_page = max(1, -(-listing.total // PAGE_SIZE))
    return templates.TemplateResponse(
        request,
        "works.html",
        {
            "user": user,
            "nav": "works",
            "listing": listing,
            "q": q or "",
            "page": page,
            "last_page": last_page,
        },
    )


@ui_route(router, "GET", "/works/new", api=None)
def new_work_form(request: Request, user: CurrentUser) -> Response:
    """Show the form for a new work."""
    return _form(request, user, work=None, values={}, errors=[])


@ui_route(router, "POST", "/works/new", api="works_create")
def create_work(  # noqa: PLR0913
    request: Request,
    session: DbSession,
    user: CurrentUser,
    _csrf: None = CsrfChecked,
    title: FormText = "",
    original_language: FormText = "",
    first_published: FormText = "",
    description: FormText = "",
) -> Response:
    """Create a work from the form."""
    values = _fields(title, original_language, first_published, description)
    try:
        payload = WorkIn(**values)  # type: ignore[arg-type]
    except ValidationError as error:
        return _form(
            request,
            user,
            work=None,
            values=values,
            errors=problems(error, _LABELS),
            status_code=422,
        )
    work = catalog.create_work(session, user.actor, payload)
    return RedirectResponse(f"/works/{work.id}", status_code=_SEE_OTHER)


@ui_route(router, "GET", "/works/{work_id}", api="works_get")
def work_detail(
    request: Request, work_id: PathId, session: DbSession, user: CurrentUser
) -> Response:
    """Show a work with its contributors and editions."""
    work = WorkOut.model_validate(catalog.get_work(session, user.actor, work_id))
    editions = Page[EditionOut].model_validate(
        catalog.list_editions(session, user.actor, work_id, 100, 0)
    )
    names = {
        contribution.person_id: catalog.get_person(
            session, user.actor, contribution.person_id
        ).name
        for contribution in work.contributions
    }
    return templates.TemplateResponse(
        request,
        "work.html",
        {
            "user": user,
            "nav": "works",
            "work": work,
            "editions": editions,
            "names": names,
        },
    )


@ui_route(router, "GET", "/works/{work_id}/edit", api="works_get")
def edit_work_form(
    request: Request, work_id: PathId, session: DbSession, user: CurrentUser
) -> Response:
    """Show the form to change a work."""
    work = WorkOut.model_validate(catalog.get_work(session, user.actor, work_id))
    values = _fields(
        work.title,
        work.original_language or "",
        work.first_published or "",
        work.description or "",
    )
    return _form(request, user, work=work, values=values, errors=[])


@ui_route(router, "POST", "/works/{work_id}/edit", api="works_update")
def update_work(  # noqa: PLR0913
    request: Request,
    work_id: PathId,
    session: DbSession,
    user: CurrentUser,
    _csrf: None = CsrfChecked,
    title: FormText = "",
    original_language: FormText = "",
    first_published: FormText = "",
    description: FormText = "",
) -> Response:
    """Change a work from the form. A blank optional field clears it."""
    values = _fields(title, original_language, first_published, description)
    messages = ["Enter a title."] if values["title"] is None else []
    payload = None
    if not messages:
        try:
            payload = WorkPatch(**values)  # type: ignore[arg-type]
        except ValidationError as error:
            messages = problems(error, _LABELS)
    if payload is None:
        work = WorkOut.model_validate(catalog.get_work(session, user.actor, work_id))
        return _form(
            request, user, work=work, values=values, errors=messages, status_code=422
        )
    catalog.update_work(session, user.actor, work_id, payload)
    return RedirectResponse(f"/works/{work_id}", status_code=_SEE_OTHER)


@ui_route(router, "POST", "/works/{work_id}/delete", api="works_delete")
def delete_work(  # noqa: PLR0913
    request: Request,
    work_id: PathId,
    session: DbSession,
    user: CurrentUser,
    _csrf: None = CsrfChecked,
    confirm: Annotated[str, Form(max_length=10)] = "",
) -> Response:
    """Delete a work, once the box is ticked."""
    if confirm != "yes":
        work = WorkOut.model_validate(catalog.get_work(session, user.actor, work_id))
        values = _fields(
            work.title,
            work.original_language or "",
            work.first_published or "",
            work.description or "",
        )
        return _form(
            request,
            user,
            work=work,
            values=values,
            errors=["Tick the box to confirm the delete."],
            status_code=422,
        )
    catalog.delete_work(session, user.actor, work_id)
    return RedirectResponse("/works", status_code=_SEE_OTHER)


_EDITION_LABELS = {
    "title": "the title",
    "subtitle": "the subtitle",
    "publisher": "the publisher",
    "published": "the publication date",
    "language": "the language",
    "format": "the format",
    "pages": "the page count",
}


def _edition_fields(  # noqa: PLR0913
    title: str,
    subtitle: str,
    publisher: str,
    published: str,
    language: str,
    format_: str,
    pages: str,
) -> dict[str, str | None]:
    return {
        "title": blank_to_none(title),
        "subtitle": blank_to_none(subtitle),
        "publisher": blank_to_none(publisher),
        "published": blank_to_none(published),
        "language": blank_to_none(language),
        "format": blank_to_none(format_),
        "pages": blank_to_none(pages),
    }


def _edition_form(
    request: Request,
    user: CurrentUser,
    *,
    work: WorkOut,
    values: dict[str, str | None],
    errors: list[str],
    status_code: int = 200,
) -> Response:
    return templates.TemplateResponse(
        request,
        "edition_form.html",
        {
            "user": user,
            "nav": "works",
            "work": work,
            "values": values,
            "errors": errors,
        },
        status_code=status_code,
    )


@ui_route(router, "GET", "/works/{work_id}/editions/new", api=None)
def new_edition_form(
    request: Request, work_id: PathId, session: DbSession, user: CurrentUser
) -> Response:
    """Show the form to add an edition to a work."""
    work = WorkOut.model_validate(catalog.get_work(session, user.actor, work_id))
    return _edition_form(request, user, work=work, values={}, errors=[])


@ui_route(router, "POST", "/works/{work_id}/editions/new", api="editions_create")
def create_edition(  # noqa: PLR0913
    request: Request,
    work_id: PathId,
    session: DbSession,
    user: CurrentUser,
    _csrf: None = CsrfChecked,
    title: FormText = "",
    subtitle: FormText = "",
    publisher: FormText = "",
    published: FormText = "",
    language: FormText = "",
    format: FormText = "",  # noqa: A002
    pages: FormText = "",
) -> Response:
    """Add an edition to a work from the form."""
    values = _edition_fields(
        title, subtitle, publisher, published, language, format, pages
    )
    try:
        payload = EditionIn(**values)  # type: ignore[arg-type]
    except ValidationError as error:
        work = WorkOut.model_validate(catalog.get_work(session, user.actor, work_id))
        return _edition_form(
            request,
            user,
            work=work,
            values=values,
            errors=problems(error, _EDITION_LABELS),
            status_code=422,
        )
    catalog.create_edition(session, user.actor, work_id, payload)
    return RedirectResponse(f"/works/{work_id}", status_code=_SEE_OTHER)
