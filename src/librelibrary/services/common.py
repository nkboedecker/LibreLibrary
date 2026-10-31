"""Helpers that services share."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from librelibrary.errors import NotFound


@dataclass
class Listing[T]:
    """One page of results, with the total across all pages."""

    items: Sequence[T]
    total: int
    limit: int
    offset: int


def paginate[T](
    session: Session, statement: Select[T], limit: int, offset: int
) -> Listing[T]:
    """Run a statement for one page, and count its full result."""
    total = session.scalar(
        select(func.count()).select_from(statement.order_by(None).subquery())
    )
    items = session.scalars(statement.limit(limit).offset(offset)).all()
    return Listing(items, total or 0, limit, offset)


def get_or_404[T](session: Session, model: type[T], record_id: Any) -> T:
    """Return a record by primary key, or raise NotFound."""
    record = session.get(model, record_id)
    if record is None:
        raise NotFound
    return record


def apply_changes(record: object, changes: dict[str, Any]) -> None:
    """Copy changed fields onto a record."""
    for name, value in changes.items():
        setattr(record, name, value)
