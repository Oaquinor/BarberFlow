"""Consent-controlled customer style records and private photos."""

from io import BytesIO
import logging
import re
import warnings
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from fastapi.responses import FileResponse
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser
from app.core.config import get_settings
from app.core.database import get_db
from app.models import (
    Appointment,
    Barbershop,
    ClientAccountShopLink,
    Service,
    StylePassportEntry,
    StylePassportPhoto,
    User,
)
from app.schemas.style_passport import (
    StylePassportCreate,
    StylePassportPhotoKind,
    StylePassportStaffUpdate,
    StylePassportUpdate,
)
from app.services.audit_service import record_audit
from app.utils.datetime import utc_now_naive

logger = logging.getLogger(__name__)

client_router = APIRouter(prefix="/client-account/style-passport", tags=["Style passport"])
staff_router = APIRouter(prefix="/owner/clients", tags=["Style passport"])
MAX_PHOTOS_PER_KIND = 2
MAX_PHOTO_SIZE = 5 * 1024 * 1024
MAX_PHOTO_PIXELS = 16_000_000
STORAGE_KEY_PATTERN = re.compile(r"^[0-9a-f]{32}\.jpg$")
PRIVATE_UPLOAD_ROOT = Path(get_settings().UPLOAD_DIR).resolve() / "private" / "style-passport"


def _entry_for_account(
    db: Session,
    account: User,
    entry_id: int,
    *,
    lock: bool = False,
) -> StylePassportEntry:
    if account.role != "client" or account.barbershop_id is not None or not account.is_verified:
        raise HTTPException(status_code=403, detail="Se requiere una cuenta de cliente verificada")
    query = db.query(StylePassportEntry).filter(
        StylePassportEntry.id == entry_id,
        StylePassportEntry.account_user_id == account.id,
        StylePassportEntry.is_deleted.is_(False),
    )
    if lock:
        query = query.with_for_update()
    entry = query.first()
    if not entry:
        raise HTTPException(status_code=404, detail="Registro de estilo no encontrado")
    return entry


def _serialize_entry(
    db: Session,
    entry: StylePassportEntry,
    appointment: Appointment | None = None,
) -> dict:
    if appointment is None:
        return _serialize_entries(db, [entry])[0]
    return _serialize_entries(db, [entry], {appointment.id: appointment})[0]


def _serialize_entries(
    db: Session,
    entries: list[StylePassportEntry],
    supplied_appointments: dict[int, Appointment] | None = None,
) -> list[dict]:
    if not entries:
        return []
    appointment_ids = {entry.appointment_id for entry in entries}
    appointment_by_id = dict(supplied_appointments or {})
    missing_ids = appointment_ids - set(appointment_by_id)
    if missing_ids:
        appointments = (
            db.query(Appointment)
            .filter(
                Appointment.id.in_(missing_ids),
                Appointment.is_deleted.is_(False),
            )
            .all()
        )
        appointment_by_id.update({item.id: item for item in appointments})
    shop_ids = {entry.barbershop_id for entry in entries}
    shops = (
        db.query(Barbershop)
        .filter(
            Barbershop.id.in_(shop_ids),
            Barbershop.is_deleted.is_(False),
        )
        .all()
    )
    shop_by_id = {item.id: item for item in shops}
    barber_ids = {item.barber_id for item in appointment_by_id.values()}
    barbers = (
        db.query(User)
        .filter(
            User.id.in_(barber_ids or {-1}),
            User.role == "barber",
            User.is_deleted.is_(False),
        )
        .all()
    )
    barber_by_id = {item.id: item for item in barbers}
    service_names = {appointment.service_type for appointment in appointment_by_id.values()}
    service_rows = (
        db.query(Service.id, Service.barbershop_id, Service.name)
        .filter(
            Service.barbershop_id.in_(shop_ids),
            Service.name.in_(service_names or {""}),
            Service.is_active.is_(True),
            Service.is_deleted.is_(False),
        )
        .all()
    )
    services_by_key: dict[tuple[int, str], list[int]] = {}
    for service_id, shop_id, service_name in service_rows:
        services_by_key.setdefault((shop_id, service_name), []).append(service_id)
    entry_ids = {entry.id for entry in entries}
    photos = (
        db.query(StylePassportPhoto)
        .filter(
            StylePassportPhoto.entry_id.in_(entry_ids),
            StylePassportPhoto.is_deleted.is_(False),
        )
        .order_by(StylePassportPhoto.id.asc())
        .all()
    )
    photos_by_entry: dict[int, list[StylePassportPhoto]] = {}
    for photo in photos:
        photos_by_entry.setdefault(photo.entry_id, []).append(photo)

    items = []
    for entry in entries:
        appointment = appointment_by_id.get(entry.appointment_id)
        shop = shop_by_id.get(entry.barbershop_id)
        barber = barber_by_id.get(appointment.barber_id) if appointment else None
        service_ids = (
            services_by_key.get((entry.barbershop_id, appointment.service_type), [])
            if appointment
            else []
        )
        service_id = service_ids[0] if len(service_ids) == 1 else None
        items.append(
            {
                "id": entry.id,
                "appointment_id": entry.appointment_id,
                "barbershop_name": shop.name if shop else "Barbería",
                "barbershop_slug": shop.slug if shop else None,
                "service": appointment.service_type if appointment else "Servicio",
                "service_id": service_id,
                "barber": barber.full_name if barber else "Equipo",
                "barber_id": appointment.barber_id if appointment else None,
                "service_date": (
                    (appointment.actual_end_time or appointment.scheduled_time).isoformat()
                    if appointment
                    else None
                ),
                "haircut_type": entry.haircut_type,
                "fade_style": entry.fade_style,
                "top_length": entry.top_length,
                "sides_length": entry.sides_length,
                "beard_style": entry.beard_style,
                "products_used": entry.products_used,
                "preferences": entry.preferences,
                "barber_notes": entry.barber_notes,
                "recommendations": entry.recommendations,
                "share_with_shop": entry.share_with_shop,
                "share_consent_updated_at": (
                    entry.share_consent_updated_at.isoformat()
                    if entry.share_consent_updated_at
                    else None
                ),
                "photos": [
                    {
                        "id": photo.id,
                        "kind": photo.photo_kind,
                        "content_type": photo.content_type,
                        "byte_size": photo.byte_size,
                    }
                    for photo in photos_by_entry.get(entry.id, [])
                ],
            }
        )
    return items


def _photo_path(account_user_id: int, storage_key: str) -> Path:
    if not STORAGE_KEY_PATTERN.fullmatch(storage_key):
        raise HTTPException(status_code=404, detail="Imagen no encontrada")
    account_dir = (PRIVATE_UPLOAD_ROOT / str(account_user_id)).resolve()
    path = (account_dir / storage_key).resolve()
    if path.parent != account_dir:
        raise HTTPException(status_code=404, detail="Imagen no encontrada")
    return path


def _photo_for_account(
    db: Session,
    account: User,
    entry_id: int,
    photo_id: int,
) -> tuple[StylePassportEntry, StylePassportPhoto, Path]:
    entry = _entry_for_account(db, account, entry_id)
    photo = (
        db.query(StylePassportPhoto)
        .filter(
            StylePassportPhoto.id == photo_id,
            StylePassportPhoto.entry_id == entry.id,
            StylePassportPhoto.is_deleted.is_(False),
        )
        .first()
    )
    if not photo:
        raise HTTPException(status_code=404, detail="Imagen no encontrada")
    return entry, photo, _photo_path(account.id, photo.storage_key)


def _private_photo_response(
    response: Response,
    photo: StylePassportPhoto,
    path: Path,
) -> FileResponse:
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Imagen no encontrada")
    response.headers["Cache-Control"] = "private, no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return FileResponse(
        path,
        media_type="image/jpeg",
        filename=f"style-passport-{photo.id}.jpg",
        content_disposition_type="inline",
        headers={
            "Cache-Control": "private, no-store, max-age=0",
            "Pragma": "no-cache",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )


def _sanitize_photo(contents: bytes) -> bytes:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(contents), formats=("JPEG", "PNG")) as source:
                width, height = source.size
                if width < 1 or height < 1 or width * height > MAX_PHOTO_PIXELS:
                    raise ValueError("Las dimensiones no son válidas")
                if getattr(source, "n_frames", 1) != 1:
                    raise ValueError("No se permiten imágenes animadas")
                source.verify()
            with Image.open(BytesIO(contents), formats=("JPEG", "PNG")) as source:
                image = ImageOps.exif_transpose(source).convert("RGB")
                output = BytesIO()
                image.save(output, format="JPEG", quality=88, optimize=True)
                sanitized = output.getvalue()
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        UnidentifiedImageError,
        OSError,
        ValueError,
    ) as exc:
        raise HTTPException(
            status_code=400,
            detail="Sube una fotografía JPG o PNG válida, no animada y dentro del límite permitido",
        ) from exc
    if len(sanitized) > MAX_PHOTO_SIZE:
        raise HTTPException(
            status_code=413,
            detail="La fotografía procesada debe pesar como máximo 5 MB",
        )
    return sanitized


@client_router.get("")
def list_style_passport(
    response: Response,
    user: CurrentUser,
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=100),
):
    if user.role != "client" or user.barbershop_id is not None or not user.is_verified:
        raise HTTPException(status_code=403, detail="Se requiere una cuenta de cliente verificada")
    response.headers["Cache-Control"] = "private, no-store, max-age=0"
    entries = (
        db.query(StylePassportEntry)
        .join(
            Appointment,
            Appointment.id == StylePassportEntry.appointment_id,
        )
        .filter(
            StylePassportEntry.account_user_id == user.id,
            StylePassportEntry.is_deleted.is_(False),
            Appointment.is_deleted.is_(False),
        )
        .order_by(
            Appointment.scheduled_time.desc(),
            StylePassportEntry.id.desc(),
        )
        .limit(limit)
        .all()
    )
    return {"items": _serialize_entries(db, entries), "limit": limit}


@client_router.post("", status_code=201)
def create_style_passport_entry(
    data: StylePassportCreate,
    response: Response,
    user: CurrentUser,
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "private, no-store, max-age=0"
    if user.role != "client" or user.barbershop_id is not None or not user.is_verified:
        raise HTTPException(status_code=403, detail="Se requiere una cuenta de cliente verificada")
    appointment = (
        db.query(Appointment)
        .join(
            ClientAccountShopLink,
            ClientAccountShopLink.crm_client_user_id == Appointment.client_id,
        )
        .filter(
            Appointment.id == data.appointment_id,
            Appointment.status == "completed",
            Appointment.is_deleted.is_(False),
            ClientAccountShopLink.account_user_id == user.id,
            ClientAccountShopLink.is_deleted.is_(False),
        )
        .with_for_update()
        .first()
    )
    if not appointment:
        raise HTTPException(
            status_code=404,
            detail="Solo puedes guardar el estilo de una cita completada de tu cuenta",
        )
    shop = (
        db.query(Barbershop)
        .filter(
            Barbershop.id == appointment.barbershop_id,
            Barbershop.is_active.is_(True),
            Barbershop.is_deleted.is_(False),
        )
        .first()
    )
    if not shop:
        raise HTTPException(status_code=404, detail="Barbería no disponible")
    existing = (
        db.query(StylePassportEntry)
        .filter(
            StylePassportEntry.appointment_id == appointment.id,
        )
        .with_for_update()
        .first()
    )
    if existing and existing.account_user_id != user.id:
        raise HTTPException(status_code=404, detail="Registro de estilo no encontrado")
    if existing and not existing.is_deleted:
        raise HTTPException(status_code=409, detail="Esta visita ya está en tu Style Passport")
    now = utc_now_naive()
    values = data.model_dump(exclude={"appointment_id", "share_with_shop"})
    if existing:
        for field, value in values.items():
            setattr(existing, field, value)
        existing.share_with_shop = data.share_with_shop
        existing.share_consent_updated_at = now if data.share_with_shop else None
        existing.is_deleted = False
        existing.deleted_at = None
        entry = existing
        action = "client_account.style_passport_restored"
    else:
        entry = StylePassportEntry(
            account_user_id=user.id,
            barbershop_id=shop.id,
            appointment_id=appointment.id,
            **values,
            share_with_shop=data.share_with_shop,
            share_consent_updated_at=now if data.share_with_shop else None,
        )
        db.add(entry)
        action = "client_account.style_passport_created"
    db.flush()
    record_audit(
        db,
        user,
        action,
        "style_passport_entry",
        entry.id,
        shop.id,
        {"appointment_id": appointment.id, "share_with_shop": data.share_with_shop},
    )
    return _serialize_entry(db, entry, appointment)


@client_router.patch("/{entry_id}")
def update_style_passport_entry(
    entry_id: int,
    data: StylePassportUpdate,
    response: Response,
    user: CurrentUser,
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "private, no-store, max-age=0"
    if user.role != "client" or user.barbershop_id is not None or not user.is_verified:
        raise HTTPException(status_code=403, detail="Se requiere una cuenta de cliente verificada")
    entry = _entry_for_account(db, user, entry_id, lock=True)
    changes = data.model_dump(exclude_unset=True)
    if not changes:
        return _serialize_entry(db, entry)
    changed_fields = []
    consent_changed = False
    for field, value in changes.items():
        if getattr(entry, field) != value:
            setattr(entry, field, value)
            changed_fields.append(field)
            if field == "share_with_shop":
                consent_changed = True
    if consent_changed:
        entry.share_consent_updated_at = utc_now_naive() if entry.share_with_shop else None
    if changed_fields:
        record_audit(
            db,
            user,
            "client_account.style_passport_updated",
            "style_passport_entry",
            entry.id,
            entry.barbershop_id,
            {
                "changed_fields": changed_fields,
                "share_with_shop": entry.share_with_shop,
            },
        )
    return _serialize_entry(db, entry)


@client_router.delete("/{entry_id}")
def delete_style_passport_entry(
    entry_id: int,
    response: Response,
    user: CurrentUser,
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "private, no-store, max-age=0"
    if user.role != "client" or user.barbershop_id is not None or not user.is_verified:
        raise HTTPException(status_code=403, detail="Se requiere una cuenta de cliente verificada")
    entry = _entry_for_account(db, user, entry_id, lock=True)
    photos = (
        db.query(StylePassportPhoto)
        .filter(
            StylePassportPhoto.entry_id == entry.id,
            StylePassportPhoto.is_deleted.is_(False),
        )
        .with_for_update()
        .all()
    )
    paths = [_photo_path(user.id, photo.storage_key) for photo in photos]
    for photo in photos:
        photo.soft_delete()
    entry.haircut_type = None
    entry.fade_style = None
    entry.top_length = None
    entry.sides_length = None
    entry.beard_style = None
    entry.products_used = None
    entry.preferences = None
    entry.barber_notes = None
    entry.recommendations = None
    entry.share_with_shop = False
    entry.share_consent_updated_at = None
    entry.soft_delete()
    record_audit(
        db,
        user,
        "client_account.style_passport_deleted",
        "style_passport_entry",
        entry.id,
        entry.barbershop_id,
        {"deleted_photo_count": len(photos)},
    )
    db.flush()
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.exception("Could not remove deleted style passport photo")
    return {"success": True}


@client_router.post("/{entry_id}/photos", status_code=201)
async def upload_style_passport_photo(
    entry_id: int,
    response: Response,
    user: CurrentUser,
    file: UploadFile = File(...),
    photo_kind: StylePassportPhotoKind = Query(...),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "private, no-store, max-age=0"
    if user.role != "client" or user.barbershop_id is not None or not user.is_verified:
        raise HTTPException(status_code=403, detail="Se requiere una cuenta de cliente verificada")
    entry = _entry_for_account(db, user, entry_id, lock=True)
    if file.content_type not in {"image/jpeg", "image/png"}:
        raise HTTPException(status_code=400, detail="Solo se permiten fotografías JPG o PNG")
    content = await file.read(MAX_PHOTO_SIZE + 1)
    if not content or len(content) > MAX_PHOTO_SIZE:
        raise HTTPException(status_code=413, detail="La fotografía debe pesar como máximo 5 MB")
    sanitized = _sanitize_photo(content)
    current_count = (
        db.query(StylePassportPhoto)
        .filter(
            StylePassportPhoto.entry_id == entry.id,
            StylePassportPhoto.photo_kind == photo_kind,
            StylePassportPhoto.is_deleted.is_(False),
        )
        .count()
    )
    if current_count >= MAX_PHOTOS_PER_KIND:
        raise HTTPException(
            status_code=409,
            detail="Ya guardaste el máximo de fotografías para esta categoría",
        )
    storage_key = f"{uuid4().hex}.jpg"
    account_dir = (PRIVATE_UPLOAD_ROOT / str(user.id)).resolve()
    photo_path = _photo_path(user.id, storage_key)
    account_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        account_dir.chmod(0o700)
    except OSError:
        logger.warning("Could not restrict style passport upload directory permissions")
    photo = StylePassportPhoto(
        entry_id=entry.id,
        photo_kind=photo_kind,
        storage_key=storage_key,
        content_type="image/jpeg",
        byte_size=len(sanitized),
    )
    db.add(photo)
    db.flush()
    try:
        photo_path.write_bytes(sanitized)
        try:
            photo_path.chmod(0o600)
        except OSError:
            logger.warning("Could not restrict style passport photo permissions")
        record_audit(
            db,
            user,
            "client_account.style_passport_photo_added",
            "style_passport_entry",
            entry.id,
            entry.barbershop_id,
            {"photo_kind": photo_kind, "photo_id": photo.id},
        )
        db.commit()
    except (OSError, SQLAlchemyError) as exc:
        db.rollback()
        photo_path.unlink(missing_ok=True)
        if isinstance(exc, OSError):
            raise HTTPException(status_code=503, detail="No se pudo guardar la fotografía") from exc
        raise
    return {
        "id": photo.id,
        "kind": photo.photo_kind,
        "content_type": photo.content_type,
        "byte_size": photo.byte_size,
    }


@client_router.delete("/{entry_id}/photos/{photo_id}")
def delete_style_passport_photo(
    entry_id: int,
    photo_id: int,
    response: Response,
    user: CurrentUser,
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "private, no-store, max-age=0"
    if user.role != "client" or user.barbershop_id is not None or not user.is_verified:
        raise HTTPException(status_code=403, detail="Se requiere una cuenta de cliente verificada")
    entry = _entry_for_account(db, user, entry_id, lock=True)
    photo = (
        db.query(StylePassportPhoto)
        .filter(
            StylePassportPhoto.id == photo_id,
            StylePassportPhoto.entry_id == entry.id,
            StylePassportPhoto.is_deleted.is_(False),
        )
        .with_for_update()
        .first()
    )
    if not photo:
        raise HTTPException(status_code=404, detail="Imagen no encontrada")
    photo_path = _photo_path(user.id, photo.storage_key)
    photo.soft_delete()
    record_audit(
        db,
        user,
        "client_account.style_passport_photo_deleted",
        "style_passport_entry",
        entry.id,
        entry.barbershop_id,
        {"photo_id": photo.id, "photo_kind": photo.photo_kind},
    )
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    try:
        photo_path.unlink(missing_ok=True)
    except OSError:
        logger.exception("Could not remove deleted style passport photo")
    return {"success": True}


@client_router.get("/{entry_id}/photos/{photo_id}")
def read_style_passport_photo(
    entry_id: int,
    photo_id: int,
    response: Response,
    user: CurrentUser,
    db: Session = Depends(get_db),
):
    _entry, photo, path = _photo_for_account(db, user, entry_id, photo_id)
    return _private_photo_response(response, photo, path)


def _staff_entry(
    db: Session,
    user: User,
    client_id: int,
    entry_id: int | None = None,
) -> StylePassportEntry | None:
    if user.role not in {"barbershop_owner", "barber"} or not user.barbershop_id:
        raise HTTPException(status_code=403, detail="Se requiere acceso del equipo de la barbería")
    if user.role == "barber" and not user.is_active:
        raise HTTPException(status_code=403, detail="El perfil profesional está inactivo")
    linked_account = (
        db.query(ClientAccountShopLink)
        .filter(
            ClientAccountShopLink.crm_client_user_id == client_id,
            ClientAccountShopLink.barbershop_id == user.barbershop_id,
            ClientAccountShopLink.is_deleted.is_(False),
        )
        .first()
    )
    if not linked_account:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    query = db.query(StylePassportEntry).filter(
        StylePassportEntry.account_user_id == linked_account.account_user_id,
        StylePassportEntry.barbershop_id == user.barbershop_id,
        StylePassportEntry.share_with_shop.is_(True),
        StylePassportEntry.is_deleted.is_(False),
    )
    if entry_id is not None:
        query = query.filter(StylePassportEntry.id == entry_id)
    return query.with_for_update().first() if entry_id is not None else query.first()


@staff_router.get("/{client_id}/style-passport")
def list_shared_style_passport(
    client_id: int,
    response: Response,
    user: CurrentUser,
    db: Session = Depends(get_db),
    limit: int = Query(default=25, ge=1, le=100),
):
    response.headers["Cache-Control"] = "private, no-store, max-age=0"
    sample = _staff_entry(db, user, client_id)
    if not sample:
        # The linked CRM client is still validated so a private passport is not
        # distinguishable from a client without a passport.
        _staff_entry(db, user, client_id, entry_id=-1)
        return {"items": [], "limit": limit}
    entries = (
        db.query(StylePassportEntry)
        .join(
            Appointment,
            Appointment.id == StylePassportEntry.appointment_id,
        )
        .filter(
            StylePassportEntry.account_user_id == sample.account_user_id,
            StylePassportEntry.barbershop_id == user.barbershop_id,
            StylePassportEntry.share_with_shop.is_(True),
            StylePassportEntry.is_deleted.is_(False),
            Appointment.is_deleted.is_(False),
        )
        .order_by(
            Appointment.scheduled_time.desc(),
            StylePassportEntry.id.desc(),
        )
        .limit(limit)
        .all()
    )
    return {"items": _serialize_entries(db, entries), "limit": limit}


@staff_router.patch("/{client_id}/style-passport/{entry_id}")
def update_shared_style_notes(
    client_id: int,
    entry_id: int,
    data: StylePassportStaffUpdate,
    response: Response,
    user: CurrentUser,
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "private, no-store, max-age=0"
    entry = _staff_entry(db, user, client_id, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Registro compartido no encontrado")
    changes = data.model_dump(exclude_unset=True)
    changed_fields = []
    for field, value in changes.items():
        if getattr(entry, field) != value:
            setattr(entry, field, value)
            changed_fields.append(field)
    if changed_fields:
        record_audit(
            db,
            user,
            "client_account.style_passport_staff_notes_updated",
            "style_passport_entry",
            entry.id,
            entry.barbershop_id,
            {"changed_fields": changed_fields},
        )
    return _serialize_entry(db, entry)


@staff_router.get("/{client_id}/style-passport/{entry_id}/photos/{photo_id}")
def read_shared_style_passport_photo(
    client_id: int,
    entry_id: int,
    photo_id: int,
    response: Response,
    user: CurrentUser,
    db: Session = Depends(get_db),
):
    entry = _staff_entry(db, user, client_id, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Registro compartido no encontrado")
    photo = (
        db.query(StylePassportPhoto)
        .filter(
            StylePassportPhoto.id == photo_id,
            StylePassportPhoto.entry_id == entry.id,
            StylePassportPhoto.is_deleted.is_(False),
        )
        .first()
    )
    if not photo:
        raise HTTPException(status_code=404, detail="Imagen no encontrada")
    path = _photo_path(entry.account_user_id, photo.storage_key)
    return _private_photo_response(response, photo, path)
