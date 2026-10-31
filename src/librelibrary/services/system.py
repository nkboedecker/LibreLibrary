"""Administration: the audit trail and run-time settings."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from librelibrary.authz.policy import Action, Actor, policy_action
from librelibrary.db import utcnow
from librelibrary.models import AuditEvent, Setting
from librelibrary.services import audit
from librelibrary.services.common import Listing, paginate


@policy_action(Action.AUDIT_READ)
def list_audit_events(
    session: Session, actor: Actor, limit: int, offset: int
) -> Listing[AuditEvent]:
    """List the audit trail, newest first."""
    statement = select(AuditEvent).order_by(AuditEvent.id.desc())
    return paginate(session, statement, limit, offset)


@policy_action(Action.SETTINGS_ADMIN)
def list_settings(
    session: Session, actor: Actor, limit: int, offset: int
) -> Listing[Setting]:
    """List run-time settings."""
    return paginate(session, select(Setting).order_by(Setting.key), limit, offset)


@policy_action(Action.SETTINGS_ADMIN)
def set_setting(session: Session, actor: Actor, key: str, value: Any) -> Setting:
    """Create or change a run-time setting."""
    setting = session.get(Setting, key)
    if setting is None:
        setting = Setting(key=key, value=value, updated_at=utcnow())
        session.add(setting)
    else:
        setting.value = value
        setting.updated_at = utcnow()
    audit.record(session, actor.user_id, "setting_changed", f"setting:{key}")
    session.commit()
    return setting
