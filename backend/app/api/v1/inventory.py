"""Tenant-isolated product catalog and immutable stock movements."""

import hashlib
import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import InventoryMovement, InventoryProduct, User
from app.schemas.inventory import (
    InventoryMovementCreate,
    InventoryProductCreate,
    InventoryProductUpdate,
)
from app.services.audit_service import record_audit

router = APIRouter(prefix="/owner/inventory", tags=["Inventory"])


def _owner_shop_id(user: User) -> int:
    if user.role != "barbershop_owner" or not user.barbershop_id:
        raise HTTPException(
            status_code=403, detail="Solo el propietario puede administrar inventario"
        )
    return user.barbershop_id


def _product_or_404(db: Session, shop_id: int, product_id: int, lock: bool = False):
    query = db.query(InventoryProduct).filter(
        InventoryProduct.id == product_id,
        InventoryProduct.barbershop_id == shop_id,
        InventoryProduct.is_deleted == False,
    )
    if lock:
        query = query.with_for_update()
    product = query.first()
    if not product:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return product


def _serialize_product(product: InventoryProduct) -> dict:
    return {
        "id": product.id,
        "name": product.name,
        "description": product.description,
        "category": product.category,
        "barcode": product.barcode,
        "unit": product.unit,
        "unit_cost_cents": product.unit_cost_cents,
        "unit_price_cents": product.unit_price_cents,
        "stock_quantity": product.stock_quantity,
        "stock_minimum": product.stock_minimum,
        "low_stock": product.stock_minimum > 0 and product.stock_quantity <= product.stock_minimum,
        "is_active": product.is_active,
        "created_at": product.created_at,
        "updated_at": product.updated_at,
    }


def _serialize_movement(movement: InventoryMovement) -> dict:
    return {
        "id": movement.id,
        "product_id": movement.product_id,
        "quantity_delta": movement.quantity_delta,
        "unit_cost_cents": movement.unit_cost_cents,
        "reason": movement.reason,
        "note": movement.note,
        "created_by_user_id": movement.created_by_user_id,
        "created_at": movement.created_at,
    }


@router.get("/products")
def list_products(
    q: str | None = Query(default=None, max_length=100),
    low_stock: bool = False,
    include_inactive: bool = False,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100_000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    shop_id = _owner_shop_id(current_user)
    query = db.query(InventoryProduct).filter(
        InventoryProduct.barbershop_id == shop_id,
        InventoryProduct.is_deleted == False,
    )
    if not include_inactive:
        query = query.filter(InventoryProduct.is_active == True)
    if q and q.strip():
        term = f"%{q.strip()}%"
        query = query.filter(
            InventoryProduct.name.ilike(term) | InventoryProduct.barcode.ilike(term)
        )
    if low_stock:
        query = query.filter(
            InventoryProduct.stock_minimum > 0,
            InventoryProduct.stock_quantity <= InventoryProduct.stock_minimum,
        )
    total = query.count()
    rows = (
        query.order_by(InventoryProduct.name.asc(), InventoryProduct.id.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {
        "items": [_serialize_product(item) for item in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/products", status_code=status.HTTP_201_CREATED)
def create_product(
    data: InventoryProductCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    shop_id = _owner_shop_id(current_user)
    if (
        data.barcode
        and db.query(InventoryProduct.id)
        .filter(
            InventoryProduct.barbershop_id == shop_id,
            InventoryProduct.barcode == data.barcode,
            InventoryProduct.is_deleted == False,
        )
        .first()
    ):
        raise HTTPException(
            status_code=409, detail="Ya existe un producto con ese código de barras"
        )
    product = InventoryProduct(barbershop_id=shop_id, **data.model_dump())
    db.add(product)
    try:
        db.flush()
        record_audit(
            db,
            current_user,
            "inventory.product_created",
            "inventory_product",
            product.id,
            shop_id,
            {"category": product.category, "has_barcode": bool(product.barcode)},
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="Ya existe un producto con ese código de barras"
        ) from exc
    db.refresh(product)
    return _serialize_product(product)


@router.patch("/products/{product_id}")
def update_product(
    product_id: int,
    data: InventoryProductUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    shop_id = _owner_shop_id(current_user)
    product = _product_or_404(db, shop_id, product_id, lock=True)
    changes = data.model_dump(exclude_unset=True)
    if any(
        value is None for key, value in changes.items() if key not in {"description", "barcode"}
    ):
        raise HTTPException(status_code=422, detail="Los campos enviados no pueden ser nulos")
    barcode = changes.get("barcode", product.barcode)
    if (
        barcode
        and db.query(InventoryProduct.id)
        .filter(
            InventoryProduct.barbershop_id == shop_id,
            InventoryProduct.barcode == barcode,
            InventoryProduct.id != product.id,
            InventoryProduct.is_deleted == False,
        )
        .first()
    ):
        raise HTTPException(
            status_code=409, detail="Ya existe un producto con ese código de barras"
        )
    for key, value in changes.items():
        setattr(product, key, value)
    if changes:
        record_audit(
            db,
            current_user,
            "inventory.product_updated",
            "inventory_product",
            product.id,
            shop_id,
            {"changed_fields": sorted(changes)},
        )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="Ya existe un producto con ese código de barras"
        ) from exc
    db.refresh(product)
    return _serialize_product(product)


@router.post("/products/{product_id}/movements", status_code=status.HTTP_201_CREATED)
def create_stock_movement(
    product_id: int,
    data: InventoryMovementCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    shop_id = _owner_shop_id(current_user)
    if data.quantity_delta == 0:
        raise HTTPException(status_code=422, detail="La cantidad del movimiento no puede ser cero")
    if data.reason in {"receipt", "return"} and data.quantity_delta < 0:
        raise HTTPException(
            status_code=422, detail="Una recepción o devolución debe aumentar existencias"
        )
    if data.reason == "consumption" and data.quantity_delta > 0:
        raise HTTPException(status_code=422, detail="El consumo debe disminuir existencias")
    key_hash = hashlib.sha256(str(data.idempotency_key).encode("ascii")).hexdigest()
    request_payload = {
        "product_id": product_id,
        **data.model_dump(mode="json", exclude={"idempotency_key"}),
    }
    payload_hash = hashlib.sha256(
        json.dumps(request_payload, sort_keys=True).encode("utf-8")
    ).hexdigest()
    existing = (
        db.query(InventoryMovement)
        .filter(
            InventoryMovement.barbershop_id == shop_id,
            InventoryMovement.request_key_hash == key_hash,
        )
        .first()
    )
    if existing:
        if existing.request_payload_hash != payload_hash:
            raise HTTPException(
                status_code=409, detail="La clave de idempotencia ya se usó con otros datos"
            )
        return _serialize_movement(existing)
    product = _product_or_404(db, shop_id, product_id, lock=True)
    if not product.is_active:
        raise HTTPException(
            status_code=409, detail="Activa el producto antes de mover sus existencias"
        )
    new_stock = product.stock_quantity + data.quantity_delta
    if new_stock < 0:
        raise HTTPException(status_code=409, detail="El movimiento dejaría existencias negativas")
    movement = InventoryMovement(
        barbershop_id=shop_id,
        product_id=product.id,
        created_by_user_id=current_user.id,
        quantity_delta=data.quantity_delta,
        unit_cost_cents=(
            data.unit_cost_cents if data.unit_cost_cents is not None else product.unit_cost_cents
        ),
        reason=data.reason,
        note=data.note,
        request_key_hash=key_hash,
        request_payload_hash=payload_hash,
    )
    product.stock_quantity = new_stock
    if data.reason == "receipt" and data.unit_cost_cents is not None:
        product.unit_cost_cents = data.unit_cost_cents
    db.add(movement)
    db.flush()
    record_audit(
        db,
        current_user,
        "inventory.stock_moved",
        "inventory_movement",
        movement.id,
        shop_id,
        {"product_id": product.id, "quantity_delta": data.quantity_delta, "reason": data.reason},
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        existing = (
            db.query(InventoryMovement)
            .filter(
                InventoryMovement.barbershop_id == shop_id,
                InventoryMovement.request_key_hash == key_hash,
            )
            .first()
        )
        if existing and existing.request_payload_hash == payload_hash:
            return _serialize_movement(existing)
        raise HTTPException(status_code=409, detail="No se pudo registrar el movimiento") from exc
    db.refresh(movement)
    return _serialize_movement(movement)


@router.get("/movements")
def list_movements(
    product_id: int | None = Query(default=None, gt=0),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100_000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    shop_id = _owner_shop_id(current_user)
    query = db.query(InventoryMovement).filter(InventoryMovement.barbershop_id == shop_id)
    if product_id:
        query = query.filter(InventoryMovement.product_id == product_id)
    total = query.count()
    rows = (
        query.order_by(InventoryMovement.created_at.desc(), InventoryMovement.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {
        "items": [_serialize_movement(item) for item in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }
