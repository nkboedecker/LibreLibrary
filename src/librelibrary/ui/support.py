"""Helpers that page routes and templates share."""

from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from librelibrary.authz.policy import Action, Actor, Denied, Resource, require
from librelibrary.services import catalog

PRIVACY_CHOICES = [
    (
        "personal",
        "Personal",
        "Only the library's owner, and its editors if the library allows it.",
    ),
    ("library", "Library", "Everyone in this library."),
    (
        "group",
        "Group",
        "Everyone in this library, and in groups that include it.",
    ),
    ("server", "Server", "Everyone signed in to this server."),
]
PRIVACY_LABELS = {value: label for value, label, _hint in PRIVACY_CHOICES}


def allowed(actor: Actor, action: Action, resource: Resource | None = None) -> bool:
    """Say whether the policy layer would allow an action, to offer or hide a link.

    This only shapes a page. The service layer checks again on every request.
    """
    try:
        require(actor, action, resource)
    except Denied:
        return False
    return True


def privacy_label(value: str) -> str:
    """Return the name of a sharing level."""
    return PRIVACY_LABELS.get(value, value)


def money(value: object) -> str:
    """Show a price with two decimal places."""
    return "" if value is None else f"{value:.2f}"


@dataclass(frozen=True)
class EditionLabel:
    """What a page needs to name an edition and its work."""

    work_id: int
    work_title: str
    edition_title: str | None
    publisher: str | None
    format: str | None


def edition_labels(
    session: Session, actor: Actor, edition_ids: Iterable[int]
) -> dict[int, EditionLabel]:
    """Look up the titles for some editions, one read per edition and work."""
    labels: dict[int, EditionLabel] = {}
    titles: dict[int, str] = {}
    for edition_id in sorted(set(edition_ids)):
        edition = catalog.get_edition(session, actor, edition_id)
        if edition.work_id not in titles:
            titles[edition.work_id] = catalog.get_work(
                session, actor, edition.work_id
            ).title
        labels[edition_id] = EditionLabel(
            edition.work_id,
            titles[edition.work_id],
            edition.title,
            edition.publisher,
            edition.format,
        )
    return labels
