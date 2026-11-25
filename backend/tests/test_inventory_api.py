"""MySQL integration coverage for inventory ownership and immutable movements."""

from datetime import timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models import (
    Barbershop,
    InventoryMovement,
    InventoryProduct,
    RetailSale,
    Subscription,
    User,
)
from app.utils.datetime import utc_now_naive


def _tenant(db: Session, key: str, role: str = "barbershop_owner"):
    now = utc_now_naive()
    subscription = Subscription(
        plan="free",
        status="active",
        current_period_start=now - timedelta(days=1),
        current_period_end=now + timedelta(days=29),
        max_barbers=3,
        max_appointments_per_month=100,
        max_clients=200,
        auto_renew=False,
    )
    db.add(subscription)
    db.flush()
    shop = Barbershop(
        name=f"Inventory {key}",
        slug=f"inventory-{key}",
        email=f"{key}@example.com",
        phone="8095554100",
        address_line1="Calle 10",
        city="Santo Domingo",
        state="DN",
        postal_code="10110",
        country="DO",
        timezone="America/Santo_Domingo",
        currency="DOP",
        subscription_id=subscription.id,
    )
    db.add(shop)
    db.flush()
    user = User(
        email=f"owner-{key}@example.com",
        password_hash="unused",
        first_name="Owner",
        last_name=key,
        role=role,
        is_active=True,
        barbershop_id=shop.id,
    )
    db.add(user)
    db.commit()
    return shop, user


def _headers(user: User):
    token = create_access_token({"sub": str(user.id), "role": user.role})
    return {"Authorization": f"Bearer {token}"}


def _product(client: TestClient, headers: dict, name: str = "Pomada"):
    response = client.post(
        "/api/v1/owner/inventory/products",
        headers=headers,
        json={
            "name": name,
            "category": "Cabello",
            "barcode": "840000000001",
            "unit": "unidad",
            "unit_cost_cents": 50000,
            "unit_price_cents": 90000,
            "stock_minimum": 2,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_stock_movement_is_atomic_idempotent_and_auditable(client: TestClient, test_db: Session):
    shop, owner = _tenant(test_db, "ledger")
    headers = _headers(owner)
    product = _product(client, headers)
    key = str(uuid4())
    payload = {
        "idempotency_key": key,
        "quantity_delta": 5,
        "reason": "receipt",
        "unit_cost_cents": 47000,
        "note": "Factura 10",
    }

    created = client.post(
        f"/api/v1/owner/inventory/products/{product['id']}/movements", headers=headers, json=payload
    )
    retried = client.post(
        f"/api/v1/owner/inventory/products/{product['id']}/movements", headers=headers, json=payload
    )
    assert created.status_code == retried.status_code == 201
    assert created.json()["id"] == retried.json()["id"]
    changed_retry = client.post(
        f"/api/v1/owner/inventory/products/{product['id']}/movements",
        headers=headers,
        json={**payload, "quantity_delta": 6},
    )
    assert changed_retry.status_code == 409

    listing = client.get("/api/v1/owner/inventory/products", headers=headers)
    assert listing.json()["items"][0]["stock_quantity"] == 5
    assert listing.json()["items"][0]["unit_cost_cents"] == 47000
    assert test_db.query(InventoryMovement).filter_by(barbershop_id=shop.id).count() == 1


def test_inventory_prevents_negative_stock_and_cross_tenant_access(
    client: TestClient, test_db: Session
):
    shop, owner = _tenant(test_db, "local")
    foreign_shop, foreign_owner = _tenant(test_db, "foreign")
    product = _product(client, _headers(owner))
    headers = _headers(owner)
    negative = client.post(
        f"/api/v1/owner/inventory/products/{product['id']}/movements",
        headers=headers,
        json={
            "idempotency_key": str(uuid4()),
            "quantity_delta": -1,
            "reason": "consumption",
        },
    )
    assert negative.status_code == 409
    assert (
        client.get("/api/v1/owner/inventory/products", headers=_headers(foreign_owner)).json()[
            "items"
        ]
        == []
    )
    crossed = client.post(
        f"/api/v1/owner/inventory/products/{product['id']}/movements",
        headers=_headers(foreign_owner),
        json={
            "idempotency_key": str(uuid4()),
            "quantity_delta": 1,
            "reason": "receipt",
        },
    )
    assert crossed.status_code == 404
    assert (
        test_db.query(InventoryProduct).filter_by(barbershop_id=shop.id).one().stock_quantity == 0
    )
    assert test_db.query(InventoryProduct).filter_by(barbershop_id=foreign_shop.id).count() == 0


def test_inventory_owner_only_and_barcode_unique_per_tenant(client: TestClient, test_db: Session):
    _shop, owner = _tenant(test_db, "owner")
    _other_shop, other_owner = _tenant(test_db, "other")
    product = _product(client, _headers(owner))
    duplicate = client.post(
        "/api/v1/owner/inventory/products",
        headers=_headers(owner),
        json={
            "name": "Pomada 2",
            "barcode": product["barcode"],
        },
    )
    assert duplicate.status_code == 409
    other_tenant = client.post(
        "/api/v1/owner/inventory/products",
        headers=_headers(other_owner),
        json={
            "name": "Pomada en otro local",
            "barcode": product["barcode"],
        },
    )
    assert other_tenant.status_code == 201
    barber_shop, barber = _tenant(test_db, "barber", role="barber")
    denied = client.get("/api/v1/owner/inventory/products", headers=_headers(barber))
    assert denied.status_code == 403
    assert barber_shop.id
    assert client.get("/api/v1/owner/inventory/products").status_code == 401


def test_retail_sale_is_idempotent_and_flows_into_cash_close(client: TestClient, test_db: Session):
    shop, owner = _tenant(test_db, "pos")
    headers = _headers(owner)
    product = _product(client, headers)
    second_product_response = client.post(
        "/api/v1/owner/inventory/products",
        headers=headers,
        json={
            "name": "Champú",
            "category": "Cuidado",
            "barcode": "840000000002",
            "unit": "unidad",
            "unit_cost_cents": 40000,
            "unit_price_cents": 70000,
            "stock_minimum": 1,
        },
    )
    assert second_product_response.status_code == 201, second_product_response.text
    second_product = second_product_response.json()
    receipt = client.post(
        f"/api/v1/owner/inventory/products/{product['id']}/movements",
        headers=headers,
        json={"idempotency_key": str(uuid4()), "quantity_delta": 4, "reason": "receipt"},
    )
    assert receipt.status_code == 201, receipt.text
    second_receipt = client.post(
        f"/api/v1/owner/inventory/products/{second_product['id']}/movements",
        headers=headers,
        json={"idempotency_key": str(uuid4()), "quantity_delta": 4, "reason": "receipt"},
    )
    assert second_receipt.status_code == 201, second_receipt.text
    payload = {
        "idempotency_key": str(uuid4()),
        "method": "cash",
        "items": [
            {"product_id": product["id"], "quantity": 2},
            {"product_id": second_product["id"], "quantity": 1},
        ],
    }
    created = client.post("/api/v1/owner/inventory/sales", headers=headers, json=payload)
    retried = client.post("/api/v1/owner/inventory/sales", headers=headers, json=payload)
    assert created.status_code == retried.status_code == 201
    assert created.json()["id"] == retried.json()["id"]
    assert created.json()["total_cents"] == 250000
    assert {item["product_name"] for item in created.json()["items"]} == {"Pomada", "Champú"}
    assert test_db.query(RetailSale).filter_by(barbershop_id=shop.id).count() == 1
    assert (
        test_db.query(InventoryMovement).filter_by(barbershop_id=shop.id, reason="sale").count()
        == 2
    )

    inventory = client.get("/api/v1/owner/inventory/products", headers=headers).json()
    stock_by_product = {item["id"]: item["stock_quantity"] for item in inventory["items"]}
    assert stock_by_product == {product["id"]: 2, second_product["id"]: 3}
    summary = client.get("/api/v1/barber/cash/today", headers=headers)
    assert summary.status_code == 200
    assert summary.json()["by_method"]["cash"] == 250000
    assert summary.json()["retail_sale_count"] == 1

    close = client.post(
        "/api/v1/barber/cash/close",
        headers=headers,
        json={
            "business_date": summary.json()["business_date"],
            "declared_cash_cents": 250000,
        },
    )
    assert close.status_code == 201, close.text
    assert close.json()["expected_cash_cents"] == 250000
    assert close.json()["retail_sale_count"] == 1
