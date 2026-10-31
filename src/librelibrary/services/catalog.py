"""Works, editions, people, and series: records shared across the instance."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from librelibrary.authz.policy import Action, Actor, policy_action
from librelibrary.models import (
    Classification,
    Contribution,
    Edition,
    Identifier,
    Person,
    Series,
    SeriesEntry,
    Subject,
    Work,
)
from librelibrary.schemas import (
    ClassificationIn,
    ContributionIn,
    EditionIn,
    EditionPatch,
    IdentifierIn,
    PersonIn,
    PersonPatch,
    SeriesEntryIn,
    SeriesIn,
    SubjectIn,
    WorkIn,
    WorkPatch,
)
from librelibrary.services.common import (
    Listing,
    apply_changes,
    get_or_404,
    paginate,
)


def _like(text: str) -> str:
    """Escape a search term for a case-insensitive LIKE."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _contributions(items: Sequence[ContributionIn]) -> list[Contribution]:
    return [Contribution(**item.model_dump()) for item in items]


def _subjects(session: Session, items: Sequence[SubjectIn]) -> list[Subject]:
    subjects: dict[tuple[str, str], Subject] = {}
    for item in items:
        key = (item.scheme, item.label)
        if key in subjects:
            continue
        found = session.scalar(
            select(Subject).where(
                Subject.scheme == item.scheme, Subject.label == item.label
            )
        )
        subjects[key] = found or Subject(scheme=item.scheme, label=item.label)
    return list(subjects.values())


def _classifications(items: Sequence[ClassificationIn]) -> list[Classification]:
    return [Classification(**item.model_dump()) for item in items]


def _series_entries(items: Sequence[SeriesEntryIn]) -> list[SeriesEntry]:
    return [SeriesEntry(**item.model_dump()) for item in items]


def _identifiers(items: Sequence[IdentifierIn]) -> list[Identifier]:
    return [Identifier(**item.model_dump()) for item in items]


@policy_action(Action.CATALOG_READ)
def list_works(
    session: Session, actor: Actor, query: str | None, limit: int, offset: int
) -> Listing[Work]:
    """List works, optionally those whose title contains the query."""
    statement = select(Work).order_by(Work.id)
    if query:
        statement = statement.where(Work.title.ilike(_like(query), escape="\\"))
    return paginate(session, statement, limit, offset)


@policy_action(Action.CATALOG_WRITE)
def create_work(session: Session, actor: Actor, payload: WorkIn) -> Work:
    """Create a work with its contributors, subjects, and series."""
    fields = payload.model_dump(
        exclude={"contributions", "subjects", "classifications", "series_entries"}
    )
    work = Work(
        **fields,
        contributions=_contributions(payload.contributions),
        subjects=_subjects(session, payload.subjects),
        classifications=_classifications(payload.classifications),
        series_entries=_series_entries(payload.series_entries),
    )
    session.add(work)
    session.commit()
    return work


@policy_action(Action.CATALOG_READ)
def get_work(session: Session, actor: Actor, work_id: int) -> Work:
    """Return a work."""
    return get_or_404(session, Work, work_id)


@policy_action(Action.CATALOG_WRITE)
def update_work(
    session: Session, actor: Actor, work_id: int, payload: WorkPatch
) -> Work:
    """Change a work."""
    work = get_or_404(session, Work, work_id)
    lists = {"contributions", "subjects", "classifications", "series_entries"}
    apply_changes(work, payload.model_dump(exclude_unset=True, exclude=lists))
    sent = payload.model_fields_set
    # Unique rows are removed first, because a flush inserts before it deletes.
    if "classifications" in sent:
        work.classifications = []
    if "series_entries" in sent:
        work.series_entries = []
    if "contributions" in sent:
        work.contributions = []
    session.flush()
    if "contributions" in sent:
        work.contributions = _contributions(payload.contributions or [])
    if "subjects" in sent:
        work.subjects = _subjects(session, payload.subjects or [])
    if "classifications" in sent:
        work.classifications = _classifications(payload.classifications or [])
    if "series_entries" in sent:
        work.series_entries = _series_entries(payload.series_entries or [])
    session.commit()
    return work


@policy_action(Action.CATALOG_DELETE)
def delete_work(session: Session, actor: Actor, work_id: int) -> None:
    """Delete a work; refused while a copy of an edition exists."""
    session.delete(get_or_404(session, Work, work_id))
    session.commit()


@policy_action(Action.CATALOG_READ)
def list_editions(
    session: Session, actor: Actor, work_id: int, limit: int, offset: int
) -> Listing[Edition]:
    """List a work's editions."""
    get_or_404(session, Work, work_id)
    statement = select(Edition).where(Edition.work_id == work_id).order_by(Edition.id)
    return paginate(session, statement, limit, offset)


@policy_action(Action.CATALOG_WRITE)
def create_edition(
    session: Session, actor: Actor, work_id: int, payload: EditionIn
) -> Edition:
    """Add an edition to a work."""
    get_or_404(session, Work, work_id)
    fields = payload.model_dump(exclude={"contributions", "identifiers"})
    edition = Edition(
        **fields,
        work_id=work_id,
        contributions=_contributions(payload.contributions),
        identifiers=_identifiers(payload.identifiers),
    )
    session.add(edition)
    session.commit()
    return edition


@policy_action(Action.CATALOG_READ)
def get_edition(session: Session, actor: Actor, edition_id: int) -> Edition:
    """Return an edition."""
    return get_or_404(session, Edition, edition_id)


@policy_action(Action.CATALOG_WRITE)
def update_edition(
    session: Session, actor: Actor, edition_id: int, payload: EditionPatch
) -> Edition:
    """Change an edition."""
    edition = get_or_404(session, Edition, edition_id)
    lists = {"contributions", "identifiers"}
    apply_changes(edition, payload.model_dump(exclude_unset=True, exclude=lists))
    sent = payload.model_fields_set
    if "contributions" in sent:
        edition.contributions = []
    if "identifiers" in sent:
        edition.identifiers = []
    session.flush()
    if "contributions" in sent:
        edition.contributions = _contributions(payload.contributions or [])
    if "identifiers" in sent:
        edition.identifiers = _identifiers(payload.identifiers or [])
    session.commit()
    return edition


@policy_action(Action.CATALOG_DELETE)
def delete_edition(session: Session, actor: Actor, edition_id: int) -> None:
    """Delete an edition; refused while a copy of it exists."""
    session.delete(get_or_404(session, Edition, edition_id))
    session.commit()


@policy_action(Action.CATALOG_READ)
def list_people(
    session: Session, actor: Actor, query: str | None, limit: int, offset: int
) -> Listing[Person]:
    """List people, optionally those whose name contains the query."""
    statement = select(Person).order_by(Person.id)
    if query:
        statement = statement.where(Person.name.ilike(_like(query), escape="\\"))
    return paginate(session, statement, limit, offset)


@policy_action(Action.CATALOG_WRITE)
def create_person(session: Session, actor: Actor, payload: PersonIn) -> Person:
    """Create a person."""
    person = Person(**payload.model_dump())
    session.add(person)
    session.commit()
    return person


@policy_action(Action.CATALOG_READ)
def get_person(session: Session, actor: Actor, person_id: int) -> Person:
    """Return a person."""
    return get_or_404(session, Person, person_id)


@policy_action(Action.CATALOG_WRITE)
def update_person(
    session: Session, actor: Actor, person_id: int, payload: PersonPatch
) -> Person:
    """Change a person."""
    person = get_or_404(session, Person, person_id)
    apply_changes(person, payload.model_dump(exclude_unset=True))
    session.commit()
    return person


@policy_action(Action.CATALOG_DELETE)
def delete_person(session: Session, actor: Actor, person_id: int) -> None:
    """Delete a person; refused while they are credited on anything."""
    session.delete(get_or_404(session, Person, person_id))
    session.commit()


@policy_action(Action.CATALOG_READ)
def list_series(
    session: Session, actor: Actor, limit: int, offset: int
) -> Listing[Series]:
    """List series."""
    return paginate(session, select(Series).order_by(Series.id), limit, offset)


@policy_action(Action.CATALOG_WRITE)
def create_series(session: Session, actor: Actor, payload: SeriesIn) -> Series:
    """Create a series."""
    series = Series(name=payload.name)
    session.add(series)
    session.commit()
    return series


@policy_action(Action.CATALOG_READ)
def get_series(session: Session, actor: Actor, series_id: int) -> Series:
    """Return a series."""
    return get_or_404(session, Series, series_id)


@policy_action(Action.CATALOG_WRITE)
def update_series(
    session: Session, actor: Actor, series_id: int, payload: SeriesIn
) -> Series:
    """Rename a series."""
    series = get_or_404(session, Series, series_id)
    series.name = payload.name
    session.commit()
    return series


@policy_action(Action.CATALOG_DELETE)
def delete_series(session: Session, actor: Actor, series_id: int) -> None:
    """Delete a series and its entries, leaving the works."""
    session.delete(get_or_404(session, Series, series_id))
    session.commit()
