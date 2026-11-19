"""Authenticated, tenant-scoped onboarding endpoints."""

from datetime import datetime, time
from pathlib import Path
from typing import Optional
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser
from app.core import get_db
from app.core.config import get_settings
from app.models.barbershop import Barbershop
from app.schemas.onboarding import (
    BarbershopProfile,
    ContextualMessage,
    DashboardLayoutResponse,
    OnboardingComplete,
    BusinessSettingsUpdate,
    OnboardingStep1,
    OnboardingStep3,
    OnboardingStep4,
    OnboardingStep5,
    OnboardingStep6,
    OnboardingStep7,
    OnboardingStep8,
    OnboardingStep9,
)
from app.services.onboarding_service import OnboardingService
from app.services.audit_service import record_audit

router = APIRouter(prefix="/onboarding", tags=["onboarding"])
MAX_LOGO_SIZE = get_settings().MAX_UPLOAD_SIZE
ALLOWED_LOGO_TYPES = {"image/png": ".png", "image/jpeg": ".jpg"}
UPLOAD_ROOT = Path(get_settings().UPLOAD_DIR) / "barbershops"


def _get_tenant_id(user, requested_id: Optional[int] = None) -> int:
    """Resolve tenant from the authenticated identity; only platform admins may select one."""
    if user.role == "super_admin":
        if requested_id is None:
            raise HTTPException(status_code=400, detail="barbershop_id is required for platform administrators")
        return requested_id
    if requested_id is not None and requested_id != user.barbershop_id:
        raise HTTPException(status_code=403, detail="No tienes acceso a esta barbería")
    if user.role not in {"barbershop_owner", "barber"} or user.barbershop_id is None:
        raise HTTPException(status_code=403, detail="Tu cuenta no pertenece a una barbería")
    return user.barbershop_id


def _require_owner(user) -> None:
    if user.role not in {"barbershop_owner", "super_admin"}:
        raise HTTPException(status_code=403, detail="Se requiere el rol de propietario")


def _get_barbershop(db: Session, tenant_id: int) -> Barbershop:
    shop = db.query(Barbershop).filter(
        Barbershop.id == tenant_id, Barbershop.is_deleted == False
    ).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Barbería no encontrada")
    return shop


def _lock_barbershop(db: Session, tenant_id: int) -> Barbershop:
    shop = db.query(Barbershop).filter(
        Barbershop.id == tenant_id, Barbershop.is_deleted == False
    ).with_for_update().first()
    if not shop:
        raise HTTPException(status_code=404, detail="Barbería no encontrada")
    return shop


@router.post("/complete", response_model=BarbershopProfile)
def complete_onboarding(
    data: OnboardingComplete,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
    barbershop_id: Optional[int] = Query(default=None),
):
    _require_owner(current_user)
    tenant_id = _get_tenant_id(current_user, barbershop_id)
    shop = _lock_barbershop(db, tenant_id)
    previous = {
        "name": shop.name,
        "primary_color": shop.primary_color,
        "secondary_color": shop.secondary_color,
        "style": shop.style,
        "primary_goal": shop.primary_goal,
        "team_size": shop.team_size,
        "avg_service_duration": shop.avg_service_duration,
        "opening_time": shop.opening_time.isoformat() if shop.opening_time else None,
        "closing_time": shop.closing_time.isoformat() if shop.closing_time else None,
        "personality": shop.personality,
    }
    try:
        shop = OnboardingService.complete_onboarding(db, tenant_id, data, commit=False)
        record_audit(
            db, current_user, "onboarding.completed", "barbershop", shop.id, shop.id,
            {"previous": previous, "updated": {
                "name": data.barbershop_name,
                "primary_color": data.primary_color,
                "secondary_color": data.secondary_color,
                "style": data.style,
                "primary_goal": data.primary_goal,
                "team_size": data.team_size,
                "avg_service_duration": data.avg_service_duration,
                "opening_time": data.opening_time,
                "closing_time": data.closing_time,
                "personality": data.personality,
            }},
        )
        db.commit()
        db.refresh(shop)
        return BarbershopProfile.model_validate(shop)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/profile", response_model=BarbershopProfile)
def get_barbershop_profile(
    current_user: CurrentUser,
    db: Session = Depends(get_db),
    barbershop_id: Optional[int] = Query(default=None),
):
    tenant_id = _get_tenant_id(current_user, barbershop_id)
    profile = OnboardingService.get_barbershop_profile(db, tenant_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Barbería no encontrada")
    return profile


@router.get("/dashboard-layout", response_model=DashboardLayoutResponse)
def get_dashboard_layout(
    current_user: CurrentUser,
    db: Session = Depends(get_db),
    barbershop_id: Optional[int] = Query(default=None),
):
    return OnboardingService.get_dashboard_layout(db, _get_tenant_id(current_user, barbershop_id))


@router.get("/greeting", response_model=ContextualMessage)
def get_contextual_greeting(
    current_user: CurrentUser,
    db: Session = Depends(get_db),
    barbershop_id: Optional[int] = Query(default=None),
):
    tenant_id = _get_tenant_id(current_user, barbershop_id)
    shop = _get_barbershop(db, tenant_id)
    try:
        local_hour = datetime.now(ZoneInfo(shop.timezone)).hour
    except (ZoneInfoNotFoundError, TypeError) as exc:
        raise HTTPException(status_code=500, detail="La zona horaria de la barbería no es válida") from exc
    return OnboardingService.get_contextual_greeting(
        db, tenant_id, local_hour
    )


@router.post("/motivational-message", response_model=Optional[ContextualMessage])
def get_motivational_message(
    context: dict,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
    barbershop_id: Optional[int] = Query(default=None),
):
    return OnboardingService.get_motivational_message(
        db, _get_tenant_id(current_user, barbershop_id), context
    )


@router.post("/upload-logo")
async def upload_logo(
    current_user: CurrentUser,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    barbershop_id: Optional[int] = Query(default=None),
):
    _require_owner(current_user)
    tenant_id = _get_tenant_id(current_user, barbershop_id)
    extension = ALLOWED_LOGO_TYPES.get(file.content_type or "")
    if not extension:
        raise HTTPException(status_code=400, detail="Solo se permiten imágenes PNG o JPG")
    contents = await file.read(MAX_LOGO_SIZE + 1)
    if not contents or len(contents) > MAX_LOGO_SIZE:
        raise HTTPException(status_code=413, detail="El logo debe pesar como máximo 5 MB")
    if (extension == ".png" and not contents.startswith(b"\x89PNG\r\n\x1a\n")) or (
        extension == ".jpg" and not contents.startswith(b"\xff\xd8\xff")
    ):
        raise HTTPException(status_code=400, detail="El contenido no coincide con el tipo de imagen")

    shop = _lock_barbershop(db, tenant_id)
    directory = UPLOAD_ROOT / str(tenant_id)
    filename = f"{uuid4().hex}{extension}"
    destination = directory / filename
    previous_logo_url = shop.logo_url
    try:
        directory.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(contents)
    except OSError as exc:
        try:
            destination.unlink(missing_ok=True)
        except OSError:
            pass
        raise HTTPException(status_code=500, detail="No se pudo guardar el logo") from exc

    logo_url = f"/uploads/barbershops/{tenant_id}/{filename}"
    shop.logo_url = logo_url
    record_audit(
        db,
        current_user,
        "barbershop.logo_updated",
        "barbershop",
        shop.id,
        shop.id,
        {"previous_logo_url": previous_logo_url, "logo_url": logo_url},
    )
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=503, detail="No se pudo actualizar el logo") from exc

    # Remove only an older file managed under this tenant's upload directory.
    tenant_prefix = f"/uploads/barbershops/{tenant_id}/"
    if previous_logo_url and previous_logo_url.startswith(tenant_prefix):
        previous_name = previous_logo_url[len(tenant_prefix):]
        previous_path = (directory / previous_name).resolve()
        if previous_path.parent == directory.resolve() and previous_path != destination.resolve():
            previous_path.unlink(missing_ok=True)
    return {"success": True, "logo_url": logo_url, "message": "Logo subido correctamente"}


@router.put("/brand-colors")
def update_brand_colors(
    data: OnboardingStep3,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
    barbershop_id: Optional[int] = Query(default=None),
):
    _require_owner(current_user)
    tenant_id = _get_tenant_id(current_user, barbershop_id)
    shop = _lock_barbershop(db, tenant_id)
    previous = {"primary_color": shop.primary_color, "secondary_color": shop.secondary_color}
    try:
        shop = OnboardingService.update_brand_colors(
            db, tenant_id, data.primary_color, data.secondary_color, commit=False
        )
        updated = {"primary_color": shop.primary_color, "secondary_color": shop.secondary_color}
        if previous != updated:
            record_audit(
                db, current_user, "business.brand_colors_updated", "barbershop", shop.id,
                shop.id, {"previous": previous, "updated": updated},
            )
        db.commit()
        return {"success": True, "primary_color": shop.primary_color,
                "secondary_color": shop.secondary_color, "message": "Colores actualizados"}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/business-settings", response_model=BarbershopProfile)
def update_business_settings(
    data: BusinessSettingsUpdate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
    barbershop_id: Optional[int] = Query(default=None),
):
    """Update owner-editable business identity, hours, timezone and public branding atomically."""
    _require_owner(current_user)
    tenant_id = _get_tenant_id(current_user, barbershop_id)
    shop = db.query(Barbershop).filter(
        Barbershop.id == tenant_id,
        Barbershop.is_deleted == False,
    ).with_for_update().first()
    if not shop:
        raise HTTPException(status_code=404, detail="Barbería no encontrada")

    previous = {
        "name": shop.name,
        "opening_time": shop.opening_time.isoformat() if shop.opening_time else None,
        "closing_time": shop.closing_time.isoformat() if shop.closing_time else None,
        "timezone": shop.timezone,
        "primary_color": shop.primary_color,
        "secondary_color": shop.secondary_color,
    }
    shop.name = data.name
    shop.opening_time = data.opening_time
    shop.closing_time = data.closing_time
    shop.timezone = data.timezone
    shop.primary_color = data.primary_color
    shop.secondary_color = data.secondary_color
    record_audit(db, current_user, "business.settings_updated", "barbershop", shop.id,
                 shop.id, {"previous": previous, "name": data.name,
                           "timezone": data.timezone,
                           "opening_time": data.opening_time.isoformat(),
                           "closing_time": data.closing_time.isoformat(),
                           "primary_color": data.primary_color,
                           "secondary_color": data.secondary_color})
    db.commit()
    db.refresh(shop)
    return BarbershopProfile.model_validate(shop)


def _save_step(db: Session, current_user, tenant_id: int, field: str, value) -> dict:
    shop = _lock_barbershop(db, tenant_id)
    previous = getattr(shop, field)
    setattr(shop, field, value)
    if previous != value:
        record_audit(
            db, current_user, f"onboarding.{field}_updated", "barbershop", shop.id,
            shop.id, {"previous": previous.isoformat() if hasattr(previous, "isoformat") else previous,
                      "updated": value.isoformat() if hasattr(value, "isoformat") else value},
        )
    db.commit()
    return {"success": True, "message": "Paso guardado"}


def _step_context(current_user, db, barbershop_id):
    _require_owner(current_user)
    return _get_tenant_id(current_user, barbershop_id)


@router.post("/step/1")
def onboarding_step_1(data: OnboardingStep1, current_user: CurrentUser,
                      db: Session = Depends(get_db), barbershop_id: Optional[int] = Query(default=None)):
    return _save_step(db, current_user, _step_context(current_user, db, barbershop_id), "name", data.barbershop_name)


@router.post("/step/3")
def onboarding_step_3(data: OnboardingStep3, current_user: CurrentUser,
                      db: Session = Depends(get_db), barbershop_id: Optional[int] = Query(default=None)):
    _require_owner(current_user)
    tenant_id = _get_tenant_id(current_user, barbershop_id)
    return update_brand_colors(data, current_user, db, tenant_id)


@router.post("/step/4")
def onboarding_step_4(data: OnboardingStep4, current_user: CurrentUser,
                      db: Session = Depends(get_db), barbershop_id: Optional[int] = Query(default=None)):
    return _save_step(db, current_user, _step_context(current_user, db, barbershop_id), "style", data.style)


@router.post("/step/5")
def onboarding_step_5(data: OnboardingStep5, current_user: CurrentUser,
                      db: Session = Depends(get_db), barbershop_id: Optional[int] = Query(default=None)):
    return _save_step(db, current_user, _step_context(current_user, db, barbershop_id), "primary_goal", data.primary_goal)


@router.post("/step/6")
def onboarding_step_6(data: OnboardingStep6, current_user: CurrentUser,
                      db: Session = Depends(get_db), barbershop_id: Optional[int] = Query(default=None)):
    return _save_step(db, current_user, _step_context(current_user, db, barbershop_id), "team_size", data.team_size)


@router.post("/step/7")
def onboarding_step_7(data: OnboardingStep7, current_user: CurrentUser,
                      db: Session = Depends(get_db), barbershop_id: Optional[int] = Query(default=None)):
    return _save_step(db, current_user, _step_context(current_user, db, barbershop_id), "avg_service_duration", data.avg_service_duration)


@router.post("/step/8")
def onboarding_step_8(data: OnboardingStep8, current_user: CurrentUser,
                      db: Session = Depends(get_db), barbershop_id: Optional[int] = Query(default=None)):
    tenant_id = _step_context(current_user, db, barbershop_id)
    shop = _lock_barbershop(db, tenant_id)
    previous_hours = {
        "opening_time": shop.opening_time.isoformat() if shop.opening_time else None,
        "closing_time": shop.closing_time.isoformat() if shop.closing_time else None,
    }
    try:
        shop.opening_time = time.fromisoformat(data.opening_time)
        shop.closing_time = time.fromisoformat(data.closing_time)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Formato de horario inválido") from exc
    if shop.opening_time >= shop.closing_time:
        raise HTTPException(status_code=422, detail="La hora de apertura debe preceder al cierre")
    record_audit(
        db, current_user, "onboarding.business_hours_updated", "barbershop", shop.id,
        shop.id, {"previous": previous_hours,
                  "updated": {"opening_time": shop.opening_time.isoformat(),
                              "closing_time": shop.closing_time.isoformat()}},
    )
    db.commit()
    return {"success": True, "message": "Paso guardado"}


@router.post("/step/9")
def onboarding_step_9(data: OnboardingStep9, current_user: CurrentUser,
                      db: Session = Depends(get_db), barbershop_id: Optional[int] = Query(default=None)):
    return _save_step(db, current_user, _step_context(current_user, db, barbershop_id), "personality", data.personality)
