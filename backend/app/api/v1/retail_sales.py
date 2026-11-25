"""Owner checkout for retail products, atomically coupled to inventory and cash."""

import hashlib
import json
from datetime import datetime, time

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user
from app.api.v1.endpoints.common import (
    _audit,
    _cash_register_closed_for_user,
    _get_timezone,
    _utc_aware,
)
from app.core.database import get_db
from app.models import (
    Barbershop,
    InventoryMovement,
    InventoryProduct,
    RetailSale,
    RetailSaleLine,
    User,
)
from app.schemas.inventory import InventorySaleCreate
from app.utils.datetime import utc_now_naive

router = APIRouter(prefix="/owner/inventory", tags=["Inventory sales"])


def _owner_shop_id(user: User) -> int:
    if user.role != "barbershop_owner" or not user.barbershop_id:
        raise HTTPException(
            status_code=403, detail="Solo el propietario puede cobrar ventas de productos"
        )
    return user.barbershop_id


def _serialize_sale(sale: RetailSale) -> dict:
    return {
        "id": sale.id,
        "payment_method": sale.payment_method,
        "currency": sale.currency,
        "subtotal_cents": sale.subtotal_cents,
        "total_cents": sale.total_cents,
        "cost_total_cents": sale.cost_total_cents,
        "sold_at": sale.sold_at,
        "sold_by_user_id": sale.sold_by_user_id,
        "items": [
            {
                "product_id": line.product_id,
                "product_name": line.product_name_snapshot,
                "barcode": line.barcode_snapshot,
                "quantity": line.quantity,
                "unit_price_cents": line.unit_price_cents,
                "line_total_cents": line.line_total_cents,
            }
            for line in sale.lines
            if not line.is_deleted
        ],
    }


def _sale_by_key(db: Session, shop_id: int, key_hash: str):
    return (
        db.query(RetailSale)
        .options(selectinload(RetailSale.lines))
        .filter(
            RetailSale.barbershop_id == shop_id,
            RetailSale.request_key_hash == key_hash,
            RetailSale.is_deleted == False,
        )
        .first()
    )


@router.post("/sales", status_code=status.HTTP_201_CREATED)
def create_retail_sale(
    data: InventorySaleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Sell without an appointment; persist payment and stock changes together."""
    shop_id = _owner_shop_id(current_user)
    item_payload = sorted(
        [{"product_id": item.product_id, "quantity": item.quantity} for item in data.items],
        key=lambda item: item["product_id"],
    )
    key_hash = hashlib.sha256(str(data.idempotency_key).encode("ascii")).hexdigest()
    payload_hash = hashlib.sha256(
        json.dumps(
            {"method": data.method, "items": item_payload, "sold_by_user_id": current_user.id},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    # The tenant row is the shared mutex used by service checkout and daily cash
    # closure; all inventory sale paths follow the same lock order.
    shop = (
        db.query(Barbershop)
        .filter(
            Barbershop.id == shop_id, Barbershop.is_active == True, Barbershop.is_deleted == False
        )
        .with_for_update()
        .first()
    )
    if not shop:
        raise HTTPException(status_code=404, detail="Barbería no encontrada o inactiva")

    existing = _sale_by_key(db, shop_id, key_hash)
    if existing:
        if existing.request_payload_hash != payload_hash:
            raise HTTPException(
                status_code=409, detail="La clave de venta ya se usó con otros datos"
            )
        return _serialize_sale(existing)
    if not shop.currency:
        raise HTTPException(
            status_code=409, detail="Configura la moneda de la barbería antes de vender"
        )
    business_day = _utc_aware(utc_now_naive()).astimezone(_get_timezone(shop)).date()
    close_key = datetime.combine(business_day, time.min)
    if _cash_register_closed_for_user(db, current_user, shop.id, close_key):
        raise HTTPException(
            status_code=409,
            detail="La caja de hoy ya fue cerrada; no se pueden registrar más ventas",
        )

    product_ids = [item["product_id"] for item in item_payload]
    products = (
        db.query(InventoryProduct)
        .filter(
            InventoryProduct.barbershop_id == shop.id,
            InventoryProduct.id.in_(product_ids),
            InventoryProduct.is_deleted == False,
            InventoryProduct.is_active == True,
        )
        .order_by(InventoryProduct.id.asc())
        .with_for_update()
        .all()
    )
    product_by_id = {product.id: product for product in products}
    if len(product_by_id) != len(product_ids):
        raise HTTPException(
            status_code=404, detail="Uno o más productos no están disponibles en esta barbería"
        )

    total_cents = cost_total_cents = 0
    sale_lines: list[RetailSaleLine] = []
    movement_data: list[tuple[InventoryProduct, int, int]] = []
    for item in item_payload:
        product = product_by_id[item["product_id"]]
        quantity = item["quantity"]
        if product.unit_price_cents <= 0:
            raise HTTPException(
                status_code=409, detail=f"Configura un precio de venta para {product.name}"
            )
        if product.stock_quantity < quantity:
            raise HTTPException(
                status_code=409, detail=f"Existencias insuficientes para {product.name}"
            )
        line_total = product.unit_price_cents * quantity
        total_cents += line_total
        cost_total_cents += product.unit_cost_cents * quantity
        sale_lines.append(
            RetailSaleLine(
                product_id=product.id,
                product_name_snapshot=product.name,
                barcode_snapshot=product.barcode,
                quantity=quantity,
                unit_price_cents=product.unit_price_cents,
                unit_cost_cents=product.unit_cost_cents,
                line_total_cents=line_total,
            )
        )
        movement_data.append((product, quantity, product.unit_cost_cents))
    if total_cents <= 0 or total_cents > 2_000_000_000 or cost_total_cents > 2_000_000_000:
        raise HTTPException(
            status_code=422, detail="El total de la venta está fuera del límite permitido"
        )

    sold_at = utc_now_naive()
    sale = RetailSale(
        barbershop_id=shop.id,
        sold_by_user_id=current_user.id,
        payment_method=data.method,
        currency=shop.currency,
        subtotal_cents=total_cents,
        total_cents=total_cents,
        cost_total_cents=cost_total_cents,
        sold_at=sold_at,
        request_key_hash=key_hash,
        request_payload_hash=payload_hash,
    )
    db.add(sale)
    db.flush()
    for line in sale_lines:
        line.sale_id = sale.id
        db.add(line)
    db.flush()

    for product, quantity, cost in movement_data:
        product.stock_quantity -= quantity
        movement_key = hashlib.sha256(
            f"retail-sale:{data.idempotency_key}:{product.id}".encode("ascii")
        ).hexdigest()
        movement_payload_hash = hashlib.sha256(
            f"sale:{sale.id}:{product.id}:{quantity}:{cost}".encode("ascii")
        ).hexdigest()
        db.add(
            InventoryMovement(
                barbershop_id=shop.id,
                product_id=product.id,
                retail_sale_id=sale.id,
                created_by_user_id=current_user.id,
                quantity_delta=-quantity,
                unit_cost_cents=cost,
                reason="sale",
                note=f"Venta #{sale.id}",
                request_key_hash=movement_key,
                request_payload_hash=movement_payload_hash,
            )
        )

    _audit(
        db,
        current_user,
        "inventory.retail_sale_completed",
        "retail_sale",
        sale.id,
        shop.id,
        {"line_count": len(sale_lines), "total_cents": total_cents, "currency": shop.currency},
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        existing = _sale_by_key(db, shop_id, key_hash)
        if existing and existing.request_payload_hash == payload_hash:
            return _serialize_sale(existing)
        raise HTTPException(
            status_code=409, detail="No se pudo guardar la venta; vuelve a revisar la caja"
        ) from exc
    db.refresh(sale)
    return _serialize_sale(sale)


@router.get("/sales")
def list_retail_sales(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100_000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    shop_id = _owner_shop_id(current_user)
    query = db.query(RetailSale).filter(
        RetailSale.barbershop_id == shop_id,
        RetailSale.is_deleted == False,
    )
    total = query.count()
    sales = (
        query.options(selectinload(RetailSale.lines))
        .order_by(RetailSale.sold_at.desc(), RetailSale.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {
        "items": [_serialize_sale(sale) for sale in sales],
        "total": total,
        "limit": limit,
        "offset": offset,
    }
