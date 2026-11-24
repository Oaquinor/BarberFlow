"""Tenant-scoped service catalog endpoints for the active synchronous SQLAlchemy app."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.constants.enums import MAX_SERVICE_DURATION_MINUTES
from app.api.deps import get_current_user
from app.services.audit_service import record_audit
from app.models import Barbershop, Service, User


router = APIRouter(prefix="/services", tags=["Services"])


class ServiceCreateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=2, max_length=100)
    description: Optional[str] = Field(None, max_length=2000)
    duration_minutes: int = Field(..., ge=10, le=MAX_SERVICE_DURATION_MINUTES)
    price: int = Field(..., gt=0, le=2_000_000_000, description="Precio en centavos")
    category: str = Field(..., min_length=2, max_length=50)
    icon: Optional[str] = Field(None, max_length=50)
    image_url: Optional[str] = Field(None, max_length=500)


class ServiceUpdateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: Optional[str] = Field(None, min_length=2, max_length=100)
    description: Optional[str] = Field(None, max_length=2000)
    duration_minutes: Optional[int] = Field(None, ge=10, le=MAX_SERVICE_DURATION_MINUTES)
    price: Optional[int] = Field(None, gt=0, le=2_000_000_000)
    category: Optional[str] = Field(None, min_length=2, max_length=50)
    icon: Optional[str] = Field(None, max_length=50)
    image_url: Optional[str] = Field(None, max_length=500)
    is_active: Optional[bool] = None
    display_order: Optional[int] = Field(None, ge=0, le=100_000)


def _tenant_user(user: User) -> int:
    if user.role not in {"barbershop_owner", "barber"} or not user.barbershop_id:
        raise HTTPException(status_code=403, detail="No autorizado para acceder al catálogo")
    return user.barbershop_id


def _owner(user: User) -> int:
    if user.role != "barbershop_owner" or not user.barbershop_id:
        raise HTTPException(status_code=403, detail="Solo el propietario puede administrar servicios")
    return user.barbershop_id


def _validate_gallery_image(db: Session, shop_id: int, image_url: Optional[str]) -> None:
    if image_url is None:
        return
    shop = db.query(Barbershop).filter(
        Barbershop.id == shop_id,
        Barbershop.is_deleted == False,
    ).first()
    if not shop or image_url not in (shop.gallery_images or []):
        raise HTTPException(status_code=422, detail="Selecciona una foto de la galería de esta barbería")


def _serialize(service: Service) -> dict:
    return {
        "id": service.id,
        "name": service.name,
        "description": service.description,
        "duration_minutes": service.duration_minutes,
        "price": service.price,
        "price_cents": service.price,
        "price_formatted": service.price_formatted,
        "category": service.category,
        "icon": service.icon,
        "is_active": service.is_active,
        "display_order": service.display_order,
        "image_url": service.image_url,
    }


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_service(
    data: ServiceCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    shop_id = _owner(current_user)
    _validate_gallery_image(db, shop_id, data.image_url)
    service = Service(barbershop_id=shop_id, **data.model_dump())
    db.add(service)
    db.flush()
    record_audit(db, current_user, "service.created", "service", service.id, shop_id,
                 {"name": service.name, "price_cents": service.price})
    db.commit()
    db.refresh(service)
    return _serialize(service)


@router.get("/")
def list_services(
    category: Optional[str] = None,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    shop_id = _tenant_user(current_user)
    query = db.query(Service).filter(Service.barbershop_id == shop_id, Service.is_deleted == False)
    if not (include_inactive and current_user.role == "barbershop_owner"):
        query = query.filter(Service.is_active == True)
    if category:
        query = query.filter(Service.category == category.strip())
    items = query.order_by(Service.display_order.asc(), Service.name.asc()).all()
    return {"total": len(items), "services": [_serialize(item) for item in items]}


@router.get("/{service_id}")
def get_service(
    service_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    shop_id = _tenant_user(current_user)
    service = db.query(Service).filter(
        Service.id == service_id,
        Service.barbershop_id == shop_id,
        Service.is_deleted == False,
    ).first()
    if not service:
        raise HTTPException(status_code=404, detail="Servicio no encontrado")
    return _serialize(service)


@router.put("/{service_id}")
def update_service(
    service_id: int,
    data: ServiceUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    shop_id = _owner(current_user)
    service = db.query(Service).filter(
        Service.id == service_id,
        Service.barbershop_id == shop_id,
        Service.is_deleted == False,
    ).first()
    if not service:
        raise HTTPException(status_code=404, detail="Servicio no encontrado")
    changes = data.model_dump(exclude_unset=True)
    if "image_url" in changes:
        _validate_gallery_image(db, shop_id, changes["image_url"])
    for field in {"name", "duration_minutes", "price", "category"}:
        if changes.get(field) is None and field in changes:
            raise HTTPException(status_code=422, detail=f"{field} no puede ser nulo")
    previous_price = service.price
    for field, value in changes.items():
        setattr(service, field, value)
    if changes:
        record_audit(
            db, current_user, "service.updated", "service", service.id, shop_id,
            {"changed_fields": sorted(changes),
             "previous_price_cents": previous_price,
             "price_cents": service.price},
        )
    db.commit()
    db.refresh(service)
    return _serialize(service)


@router.delete("/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_service(
    service_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    shop_id = _owner(current_user)
    service = db.query(Service).filter(
        Service.id == service_id,
        Service.barbershop_id == shop_id,
        Service.is_deleted == False,
    ).first()
    if not service:
        raise HTTPException(status_code=404, detail="Servicio no encontrado")
    service.soft_delete()
    service.is_active = False
    record_audit(db, current_user, "service.deleted", "service", service.id, shop_id,
                 {"name": service.name, "price_cents": service.price})
    db.commit()
    return None
