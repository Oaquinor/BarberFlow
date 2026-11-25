"""Authenticated, tenant-scoped onboarding endpoints."""

import warnings
from datetime import datetime, time
from io import BytesIO
from pathlib import Path
from typing import Optional
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from PIL import Image, UnidentifiedImageError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser
from app.core import get_db
from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.barbershop import Barbershop
from app.models.service import Service
from app.schemas.onboarding import (
    BarbershopProfile,
    BusinessSettingsUpdate,
    ContextualMessage,
    DashboardLayoutResponse,
    OnboardingComplete,
    OnboardingStep1,
    OnboardingStep3,
    OnboardingStep4,
    OnboardingStep5,
    OnboardingStep6,
    OnboardingStep7,
    OnboardingStep8,
    OnboardingStep9,
)
from app.services.audit_service import record_audit
from app.services.onboarding_service import OnboardingService

router = APIRouter(prefix="/onboarding", tags=["onboarding"])
MAX_LOGO_SIZE = get_settings().MAX_UPLOAD_SIZE
ALLOWED_LOGO_TYPES = {"image/png": ".png", "image/jpeg": ".jpg"}
LOGO_IMAGE_FORMATS = {"image/png": "PNG", "image/jpeg": "JPEG"}
MAX_LOGO_PIXELS = 16_000_000
UPLOAD_ROOT = Path(get_settings().UPLOAD_DIR) / "barbershops"
logger = get_logger(__name__)


def _remove_logo_file(path: Path, *, tenant_id: int, purpose: str) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.warning(
            "Could not remove logo file after %s",
            purpose,
            extra={"tenant_id": tenant_id, "path": str(path)},
            exc_info=True,
        )


def _sanitize_logo(contents: bytes, expected_format: str) -> bytes:
    """Decode and re-encode a bounded, single-frame PNG/JPEG without metadata."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(contents), formats=(expected_format,)) as source:
                if source.format != expected_format:
                    raise ValueError("El formato no coincide")
                width, height = source.size
                if width < 1 or height < 1 or width * height > MAX_LOGO_PIXELS:
                    raise ValueError("Las dimensiones del logo no son válidas")
                if getattr(source, "n_frames", 1) != 1:
                    raise ValueError("No se permiten imágenes animadas")
                source.verify()

            with Image.open(BytesIO(contents), formats=(expected_format,)) as source:
                source.load()
                image = source.convert("RGBA" if expected_format == "PNG" else "RGB")
                output = BytesIO()
                image.save(output, format=expected_format, optimize=True)
                sanitized = output.getvalue()
    except (Image.DecompressionBombError, Image.DecompressionBombWarning,
            UnidentifiedImageError, OSError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail="El archivo debe ser una imagen PNG o JPG válida y de dimensiones permitidas",
        ) from exc

    if len(sanitized) > MAX_LOGO_SIZE:
        raise HTTPException(status_code=413, detail="El logo procesado debe pesar como máximo 5 MB")
    return sanitized


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
        "public_theme": shop.public_theme,
        "booking_questions": shop.booking_questions or [],
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
    contents = _sanitize_logo(contents, LOGO_IMAGE_FORMATS[file.content_type])

    shop = _lock_barbershop(db, tenant_id)
    directory = UPLOAD_ROOT / str(tenant_id)
    filename = f"{uuid4().hex}{extension}"
    destination = directory / filename
    previous_logo_url = shop.logo_url
    try:
        directory.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(contents)
    except OSError as exc:
        _remove_logo_file(destination, tenant_id=tenant_id, purpose="write failure")
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
        _remove_logo_file(destination, tenant_id=tenant_id, purpose="database rollback")
        raise HTTPException(status_code=503, detail="No se pudo actualizar el logo") from exc

    # Remove only an older file managed under this tenant's upload directory.
    tenant_prefix = f"/uploads/barbershops/{tenant_id}/"
    if previous_logo_url and previous_logo_url.startswith(tenant_prefix):
        previous_name = previous_logo_url[len(tenant_prefix):]
        previous_path = (directory / previous_name).resolve()
        if previous_path.parent == directory.resolve() and previous_path != destination.resolve():
            _remove_logo_file(previous_path, tenant_id=tenant_id, purpose="logo replacement")
    return {"success": True, "logo_url": logo_url, "message": "Logo subido correctamente"}


@router.post("/upload-gallery-image")
async def upload_gallery_image(
    current_user: CurrentUser,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    barbershop_id: Optional[int] = Query(default=None),
):
    """Add a sanitized portfolio photo to this owner's public barber shop page."""
    _require_owner(current_user)
    tenant_id = _get_tenant_id(current_user, barbershop_id)
    extension = ALLOWED_LOGO_TYPES.get(file.content_type or "")
    if not extension:
        raise HTTPException(status_code=400, detail="Solo se permiten imágenes PNG o JPG")
    contents = await file.read(MAX_LOGO_SIZE + 1)
    if not contents or len(contents) > MAX_LOGO_SIZE:
        raise HTTPException(status_code=413, detail="La imagen debe pesar como máximo 5 MB")
    contents = _sanitize_logo(contents, LOGO_IMAGE_FORMATS[file.content_type])
    shop = _lock_barbershop(db, tenant_id)
    gallery = list(shop.gallery_images or [])
    if len(gallery) >= 8:
        raise HTTPException(status_code=400, detail="La galería admite hasta 8 imágenes")
    directory = UPLOAD_ROOT / str(tenant_id)
    filename = f"gallery-{uuid4().hex}{extension}"
    destination = directory / filename
    try:
        directory.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(contents)
    except OSError as exc:
        _remove_logo_file(destination, tenant_id=tenant_id, purpose="gallery write failure")
        raise HTTPException(status_code=500, detail="No se pudo guardar la imagen") from exc
    image_url = f"/uploads/barbershops/{tenant_id}/{filename}"
    shop.gallery_images = [*gallery, image_url]
    record_audit(db, current_user, "barbershop.gallery_image_added", "barbershop",
                 shop.id, shop.id, {"image_url": image_url})
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        _remove_logo_file(destination, tenant_id=tenant_id, purpose="gallery rollback")
        raise HTTPException(status_code=503, detail="No se pudo actualizar la galería") from exc
    return {"success": True, "gallery_images": shop.gallery_images}


@router.post("/upload-cover")
async def upload_cover(
    current_user: CurrentUser,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    barbershop_id: Optional[int] = Query(default=None),
):
    """Set the owner's sanitized photo as the hero cover on its public page."""
    _require_owner(current_user)
    tenant_id = _get_tenant_id(current_user, barbershop_id)
    extension = ALLOWED_LOGO_TYPES.get(file.content_type or "")
    if not extension:
        raise HTTPException(status_code=400, detail="Solo se permiten imágenes PNG o JPG")
    contents = await file.read(MAX_LOGO_SIZE + 1)
    if not contents or len(contents) > MAX_LOGO_SIZE:
        raise HTTPException(status_code=413, detail="La portada debe pesar como máximo 5 MB")
    contents = _sanitize_logo(contents, LOGO_IMAGE_FORMATS[file.content_type])
    shop = _lock_barbershop(db, tenant_id)
    directory = UPLOAD_ROOT / str(tenant_id)
    filename = f"cover-{uuid4().hex}{extension}"
    destination = directory / filename
    previous_url = shop.cover_image_url
    try:
        directory.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(contents)
    except OSError as exc:
        _remove_logo_file(destination, tenant_id=tenant_id, purpose="cover write failure")
        raise HTTPException(status_code=500, detail="No se pudo guardar la portada") from exc

    cover_url = f"/uploads/barbershops/{tenant_id}/{filename}"
    shop.cover_image_url = cover_url
    record_audit(db, current_user, "barbershop.cover_updated", "barbershop",
                 shop.id, shop.id, {"previous_cover_url": previous_url, "cover_image_url": cover_url})
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        _remove_logo_file(destination, tenant_id=tenant_id, purpose="cover rollback")
        raise HTTPException(status_code=503, detail="No se pudo actualizar la portada") from exc
    tenant_prefix = f"/uploads/barbershops/{tenant_id}/"
    if previous_url and previous_url.startswith(tenant_prefix):
        previous_path = (directory / previous_url[len(tenant_prefix):]).resolve()
        if previous_path.parent == directory.resolve() and previous_path != destination.resolve():
            _remove_logo_file(previous_path, tenant_id=tenant_id, purpose="cover replacement")
    return {"success": True, "cover_image_url": cover_url}


@router.delete("/cover-image")
def delete_cover_image(
    current_user: CurrentUser,
    db: Session = Depends(get_db),
    barbershop_id: Optional[int] = Query(default=None),
):
    """Restore the default hero image and remove only a tenant-owned uploaded cover."""
    _require_owner(current_user)
    tenant_id = _get_tenant_id(current_user, barbershop_id)
    shop = _lock_barbershop(db, tenant_id)
    previous_url = shop.cover_image_url
    if not previous_url:
        return {"success": True, "cover_image_url": None}
    shop.cover_image_url = None
    record_audit(db, current_user, "barbershop.cover_removed", "barbershop",
                 shop.id, shop.id, {"previous_cover_url": previous_url})
    db.commit()
    tenant_prefix = f"/uploads/barbershops/{tenant_id}/"
    if previous_url.startswith(tenant_prefix):
        directory = (UPLOAD_ROOT / str(tenant_id)).resolve()
        image_path = (directory / previous_url[len(tenant_prefix):]).resolve()
        if image_path.parent == directory and image_path.name.startswith("cover-"):
            _remove_logo_file(image_path, tenant_id=tenant_id, purpose="cover removal")
    return {"success": True, "cover_image_url": None}


@router.delete("/gallery-image")
def delete_gallery_image(
    current_user: CurrentUser,
    image_url: str = Query(..., min_length=1, max_length=500),
    db: Session = Depends(get_db),
    barbershop_id: Optional[int] = Query(default=None),
):
    """Remove only a gallery image owned by the authenticated barber shop."""
    _require_owner(current_user)
    tenant_id = _get_tenant_id(current_user, barbershop_id)
    shop = _lock_barbershop(db, tenant_id)
    gallery = list(shop.gallery_images or [])
    if image_url not in gallery:
        raise HTTPException(status_code=404, detail="La imagen no pertenece a esta galería")
    shop.gallery_images = [item for item in gallery if item != image_url]
    db.query(Service).filter(
        Service.barbershop_id == tenant_id,
        Service.image_url == image_url,
    ).update({Service.image_url: None}, synchronize_session=False)
    record_audit(db, current_user, "barbershop.gallery_image_removed", "barbershop",
                 shop.id, shop.id, {"image_url": image_url})
    db.commit()
    prefix = f"/uploads/barbershops/{tenant_id}/gallery-"
    if image_url.startswith(prefix):
        image_name = image_url.removeprefix(f"/uploads/barbershops/{tenant_id}/")
        directory = (UPLOAD_ROOT / str(tenant_id)).resolve()
        image_path = (directory / image_name).resolve()
        if image_path.parent == directory and image_path.name.startswith("gallery-"):
            _remove_logo_file(image_path, tenant_id=tenant_id, purpose="gallery removal")
    return {"success": True, "gallery_images": shop.gallery_images}


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
        "description": shop.description,
        "opening_time": shop.opening_time.isoformat() if shop.opening_time else None,
        "closing_time": shop.closing_time.isoformat() if shop.closing_time else None,
        "timezone": shop.timezone,
        "primary_color": shop.primary_color,
        "secondary_color": shop.secondary_color,
        "cancellation_window_hours": shop.cancellation_window_hours or 0,
        "booking_questions": shop.booking_questions or [],
    }
    shop.name = data.name
    shop.description = data.description
    shop.opening_time = data.opening_time
    shop.closing_time = data.closing_time
    shop.timezone = data.timezone
    shop.primary_color = data.primary_color
    shop.secondary_color = data.secondary_color
    shop.public_theme = data.public_theme
    if data.cancellation_window_hours is not None:
        shop.cancellation_window_hours = data.cancellation_window_hours
    if data.booking_questions is not None:
        shop.booking_questions = data.booking_questions
    record_audit(db, current_user, "business.settings_updated", "barbershop", shop.id,
                 shop.id, {"previous": previous, "name": data.name,
                           "description": data.description,
                           "timezone": data.timezone,
                           "opening_time": data.opening_time.isoformat(),
                           "closing_time": data.closing_time.isoformat(),
                           "primary_color": data.primary_color,
                           "secondary_color": data.secondary_color,
                           "public_theme": data.public_theme,
                           "cancellation_window_hours": shop.cancellation_window_hours,
                           "booking_questions": shop.booking_questions or []})
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
