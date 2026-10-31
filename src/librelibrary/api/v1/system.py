"""The health check, the audit trail, and run-time settings."""

from typing import Annotated

from fastapi import APIRouter, Path

from librelibrary import __version__
from librelibrary.api.deps import CurrentActor, DbSession, Limit, Offset
from librelibrary.schemas import (
    AuditEventOut,
    Health,
    Page,
    SettingIn,
    SettingOut,
)
from librelibrary.services import system

public_router = APIRouter()
router = APIRouter(tags=["admin"])
SettingKey = Annotated[str, Path(max_length=100, pattern=r"^[a-z0-9_.-]+$")]


@public_router.get("/health", operation_id="health_get", tags=["system"])
def health() -> Health:
    """Report that the server is running.

    This route is public so that container healthchecks can call it. It
    returns no user data.
    """
    return Health(status="ok", version=__version__)


@router.get("/audit-events", operation_id="audit_events_list")
def list_audit_events(
    session: DbSession, actor: CurrentActor, limit: Limit = 50, offset: Offset = 0
) -> Page[AuditEventOut]:
    """List the audit trail, newest first."""
    return Page[AuditEventOut].model_validate(
        system.list_audit_events(session, actor, limit, offset)
    )


@router.get("/settings", operation_id="settings_list")
def list_settings(
    session: DbSession, actor: CurrentActor, limit: Limit = 50, offset: Offset = 0
) -> Page[SettingOut]:
    """List run-time settings."""
    return Page[SettingOut].model_validate(
        system.list_settings(session, actor, limit, offset)
    )


@router.put("/settings/{key}", operation_id="settings_set")
def set_setting(
    key: SettingKey, payload: SettingIn, session: DbSession, actor: CurrentActor
) -> SettingOut:
    """Create or change a run-time setting."""
    return SettingOut.model_validate(
        system.set_setting(session, actor, key, payload.value)
    )
