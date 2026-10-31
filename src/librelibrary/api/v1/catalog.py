"""Works, editions, people, and series."""

from fastapi import APIRouter, status

from librelibrary.api.deps import (
    CurrentActor,
    DbSession,
    Limit,
    Offset,
    PathId,
    SearchText,
)
from librelibrary.schemas import (
    EditionIn,
    EditionOut,
    EditionPatch,
    Page,
    PersonIn,
    PersonOut,
    PersonPatch,
    SeriesIn,
    SeriesOut,
    WorkIn,
    WorkOut,
    WorkPatch,
)
from librelibrary.services import catalog

router = APIRouter(tags=["catalog"])
_NO_CONTENT = status.HTTP_204_NO_CONTENT
_CREATED = status.HTTP_201_CREATED


@router.get("/works", operation_id="works_list")
def list_works(
    session: DbSession,
    actor: CurrentActor,
    q: SearchText = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> Page[WorkOut]:
    """List works; `q` matches part of the title."""
    return Page[WorkOut].model_validate(
        catalog.list_works(session, actor, q, limit, offset)
    )


@router.post("/works", operation_id="works_create", status_code=_CREATED)
def create_work(payload: WorkIn, session: DbSession, actor: CurrentActor) -> WorkOut:
    """Create a work."""
    return WorkOut.model_validate(catalog.create_work(session, actor, payload))


@router.get("/works/{work_id}", operation_id="works_get")
def get_work(work_id: PathId, session: DbSession, actor: CurrentActor) -> WorkOut:
    """Return a work."""
    return WorkOut.model_validate(catalog.get_work(session, actor, work_id))


@router.patch("/works/{work_id}", operation_id="works_update")
def update_work(
    work_id: PathId, payload: WorkPatch, session: DbSession, actor: CurrentActor
) -> WorkOut:
    """Change a work."""
    return WorkOut.model_validate(catalog.update_work(session, actor, work_id, payload))


@router.delete("/works/{work_id}", operation_id="works_delete", status_code=_NO_CONTENT)
def delete_work(work_id: PathId, session: DbSession, actor: CurrentActor) -> None:
    """Delete a work. Needs the admin scope."""
    catalog.delete_work(session, actor, work_id)


@router.get("/works/{work_id}/editions", operation_id="editions_list")
def list_editions(
    work_id: PathId,
    session: DbSession,
    actor: CurrentActor,
    limit: Limit = 50,
    offset: Offset = 0,
) -> Page[EditionOut]:
    """List a work's editions."""
    return Page[EditionOut].model_validate(
        catalog.list_editions(session, actor, work_id, limit, offset)
    )


@router.post(
    "/works/{work_id}/editions", operation_id="editions_create", status_code=_CREATED
)
def create_edition(
    work_id: PathId, payload: EditionIn, session: DbSession, actor: CurrentActor
) -> EditionOut:
    """Add an edition to a work."""
    return EditionOut.model_validate(
        catalog.create_edition(session, actor, work_id, payload)
    )


@router.get("/editions/{edition_id}", operation_id="editions_get")
def get_edition(
    edition_id: PathId, session: DbSession, actor: CurrentActor
) -> EditionOut:
    """Return an edition."""
    return EditionOut.model_validate(catalog.get_edition(session, actor, edition_id))


@router.patch("/editions/{edition_id}", operation_id="editions_update")
def update_edition(
    edition_id: PathId,
    payload: EditionPatch,
    session: DbSession,
    actor: CurrentActor,
) -> EditionOut:
    """Change an edition."""
    return EditionOut.model_validate(
        catalog.update_edition(session, actor, edition_id, payload)
    )


@router.delete(
    "/editions/{edition_id}", operation_id="editions_delete", status_code=_NO_CONTENT
)
def delete_edition(edition_id: PathId, session: DbSession, actor: CurrentActor) -> None:
    """Delete an edition. Needs the admin scope."""
    catalog.delete_edition(session, actor, edition_id)


@router.get("/people", operation_id="people_list")
def list_people(
    session: DbSession,
    actor: CurrentActor,
    q: SearchText = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> Page[PersonOut]:
    """List people; `q` matches part of the name."""
    return Page[PersonOut].model_validate(
        catalog.list_people(session, actor, q, limit, offset)
    )


@router.post("/people", operation_id="people_create", status_code=_CREATED)
def create_person(
    payload: PersonIn, session: DbSession, actor: CurrentActor
) -> PersonOut:
    """Create a person."""
    return PersonOut.model_validate(catalog.create_person(session, actor, payload))


@router.get("/people/{person_id}", operation_id="people_get")
def get_person(person_id: PathId, session: DbSession, actor: CurrentActor) -> PersonOut:
    """Return a person."""
    return PersonOut.model_validate(catalog.get_person(session, actor, person_id))


@router.patch("/people/{person_id}", operation_id="people_update")
def update_person(
    person_id: PathId, payload: PersonPatch, session: DbSession, actor: CurrentActor
) -> PersonOut:
    """Change a person."""
    return PersonOut.model_validate(
        catalog.update_person(session, actor, person_id, payload)
    )


@router.delete(
    "/people/{person_id}", operation_id="people_delete", status_code=_NO_CONTENT
)
def delete_person(person_id: PathId, session: DbSession, actor: CurrentActor) -> None:
    """Delete a person. Needs the admin scope."""
    catalog.delete_person(session, actor, person_id)


@router.get("/series", operation_id="series_list")
def list_series(
    session: DbSession, actor: CurrentActor, limit: Limit = 50, offset: Offset = 0
) -> Page[SeriesOut]:
    """List series."""
    return Page[SeriesOut].model_validate(
        catalog.list_series(session, actor, limit, offset)
    )


@router.post("/series", operation_id="series_create", status_code=_CREATED)
def create_series(
    payload: SeriesIn, session: DbSession, actor: CurrentActor
) -> SeriesOut:
    """Create a series."""
    return SeriesOut.model_validate(catalog.create_series(session, actor, payload))


@router.get("/series/{series_id}", operation_id="series_get")
def get_series(series_id: PathId, session: DbSession, actor: CurrentActor) -> SeriesOut:
    """Return a series."""
    return SeriesOut.model_validate(catalog.get_series(session, actor, series_id))


@router.patch("/series/{series_id}", operation_id="series_update")
def update_series(
    series_id: PathId, payload: SeriesIn, session: DbSession, actor: CurrentActor
) -> SeriesOut:
    """Rename a series."""
    return SeriesOut.model_validate(
        catalog.update_series(session, actor, series_id, payload)
    )


@router.delete(
    "/series/{series_id}", operation_id="series_delete", status_code=_NO_CONTENT
)
def delete_series(series_id: PathId, session: DbSession, actor: CurrentActor) -> None:
    """Delete a series. Needs the admin scope."""
    catalog.delete_series(session, actor, series_id)
