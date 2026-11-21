"""Super-admin controls for non-secret platform behavior settings."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import PlatformSettings, User
from app.schemas.platform import PlatformSettingsResponse, PlatformSettingsUpdateRequest
from app.services.audit_service import record_audit

router = APIRouter(tags=["Platform settings"])


def _require_super_admin(user: User) -> None:
    if user.role != "super_admin":
        raise HTTPException(status_code=403, detail="Solo el superadministrador puede gestionar estos ajustes")


@router.get("/admin/settings", response_model=PlatformSettingsResponse)
def get_platform_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_super_admin(current_user)
    settings = db.get(PlatformSettings, 1)
    return PlatformSettingsResponse(
        registrations_enabled=settings.registrations_enabled if settings else True,
        free_period_days=settings.free_period_days if settings else 30,
    )


@router.put("/admin/settings", response_model=PlatformSettingsResponse)
def update_platform_settings(
    data: PlatformSettingsUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_super_admin(current_user)
    settings = db.query(PlatformSettings).filter(PlatformSettings.id == 1).with_for_update().first()
    previous = {
        "registrations_enabled": settings.registrations_enabled if settings else True,
        "free_period_days": settings.free_period_days if settings else 30,
    }
    if settings is None:
        settings = PlatformSettings(id=1)
        db.add(settings)
    settings.registrations_enabled = data.registrations_enabled
    settings.free_period_days = data.free_period_days
    settings.updated_by_user_id = current_user.id
    record_audit(
        db, current_user, "platform.settings_updated", "platform_settings", 1,
        details={"previous": previous, "updated": data.model_dump()},
    )
    db.commit()
    return PlatformSettingsResponse(**data.model_dump())


@router.get("/saas/registration-status", response_model=PlatformSettingsResponse)
def get_registration_status(db: Session = Depends(get_db)):
    settings = db.get(PlatformSettings, 1)
    return PlatformSettingsResponse(
        registrations_enabled=settings.registrations_enabled if settings else True,
        free_period_days=settings.free_period_days if settings else 30,
    )
