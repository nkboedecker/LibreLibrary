"""Write the audit trail. Callers must pass no secrets in the details."""

from typing import Any

from sqlalchemy.orm import Session

from librelibrary.models import AuditEvent


def record(
    session: Session,
    actor_user_id: int | None,
    action: str,
    target: str | None = None,
    **detail: Any,
) -> None:
    """Add an event to the session; the caller commits it."""
    session.add(
        AuditEvent(
            actor_user_id=actor_user_id, action=action, target=target, detail=detail
        )
    )
