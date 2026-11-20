"""Small transactional helper for sensitive-operation audit records."""

from typing import Optional

from sqlalchemy.orm import Session

from app.models import AuditLog, User
from app.utils.datetime import utc_now_naive


def record_audit(
    db: Session,
    actor: Optional[User],
    action: str,
    entity_type: str,
    entity_id: Optional[int],
    barbershop_id: Optional[int] = None,
    details: Optional[dict] = None,
) -> None:
    """Add an audit record to the caller's transaction; the caller commits it."""
    db.add(AuditLog(
        actor_user_id=actor.id if actor else None,
        barbershop_id=barbershop_id or (actor.barbershop_id if actor else None),
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        occurred_at=utc_now_naive(),
        details=details,
    ))
