from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.db import session_scope
from app.models import AuditLog

log = logging.getLogger('ottv2.audit')


def jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    if isinstance(value, uuid.UUID):
        return str(value)
    if hasattr(value, 'isoformat'):
        from app.timeutil import iso
        return iso(value)
    return value


def audit(db: Session, actor_id: uuid.UUID | None, action: str, target_type: str, target_id: uuid.UUID | None,
          payload: dict[str, Any] | None = None) -> AuditLog:
    entry = AuditLog(actor_user_id=actor_id, action=action, target_type=target_type, target_id=target_id,
                     payload=jsonable(payload or {}))
    db.add(entry)
    return entry


def audit_separately(actor_id: uuid.UUID | None, action: str, target_type: str, target_id: uuid.UUID | None,
                     payload: dict[str, Any] | None = None) -> None:
    """Audit outside the (rolled back) business transaction, e.g. a rejected admin mutation."""
    try:
        with session_scope() as db:
            audit(db, actor_id, action, target_type, target_id, payload)
    except Exception:  # noqa: BLE001 - never turn an audit failure into a different API error
        log.exception('Could not write audit entry action=%s', action)
