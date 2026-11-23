"""Tenant-scoped in-app notification endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core import get_db
from app.models.in_app_notification import InAppNotification
from app.utils.datetime import utc_now_naive
from app.api.v1.endpoints.common import _get_current_user

router = APIRouter(tags=["platform"])


@router.get("/notifications")
def list_in_app_notifications(
    limit: int = 50,
    unread_only: bool = False,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    user = _get_current_user(db, authorization)
    if not user.barbershop_id:
        raise HTTPException(status_code=403, detail="El usuario no tiene una barbería asignada")
    if not 1 <= limit <= 100:
        raise HTTPException(status_code=422, detail="El límite debe estar entre 1 y 100")
    query = db.query(InAppNotification).filter(
        InAppNotification.barbershop_id == user.barbershop_id,
        InAppNotification.recipient_user_id == user.id,
        InAppNotification.is_deleted == False,
    )
    unread_count = query.filter(InAppNotification.read_at.is_(None)).count()
    if unread_only:
        query = query.filter(InAppNotification.read_at.is_(None))
    rows = query.order_by(InAppNotification.created_at.desc(), InAppNotification.id.desc()).limit(limit).all()
    return {
        "unread_count": unread_count,
        "items": [{
            "id": row.id,
            "event_type": row.event_type,
            "title": row.title,
            "message": row.message,
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
            "created_at": row.created_at.isoformat(),
            "read_at": row.read_at.isoformat() if row.read_at else None,
        } for row in rows],
    }


@router.get("/notifications/unread-count")
def get_in_app_notification_unread_count(
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    """Return only the authenticated user's tenant-scoped unread count."""
    user = _get_current_user(db, authorization)
    if not user.barbershop_id:
        raise HTTPException(status_code=403, detail="El usuario no tiene una barbería asignada")
    unread_count = db.query(func.count(InAppNotification.id)).filter(
        InAppNotification.barbershop_id == user.barbershop_id,
        InAppNotification.recipient_user_id == user.id,
        InAppNotification.read_at.is_(None),
        InAppNotification.is_deleted == False,
    ).scalar() or 0
    return {"unread_count": int(unread_count)}


@router.post("/notifications/{notification_id}/read")
def mark_in_app_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    user = _get_current_user(db, authorization)
    if not user.barbershop_id:
        raise HTTPException(status_code=403, detail="El usuario no tiene una barbería asignada")
    row = db.query(InAppNotification).filter(
        InAppNotification.id == notification_id,
        InAppNotification.barbershop_id == user.barbershop_id,
        InAppNotification.recipient_user_id == user.id,
        InAppNotification.is_deleted == False,
    ).with_for_update().first()
    if not row:
        raise HTTPException(status_code=404, detail="Notificación no encontrada")
    if row.read_at is None:
        row.read_at = utc_now_naive()
        db.commit()
    return {"success": True, "notification_id": row.id,
            "read_at": row.read_at.isoformat()}
