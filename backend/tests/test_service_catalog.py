"""Tenant and role checks for the connected MySQL service catalog API."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.models import AuditLog, Barbershop, RefreshSession, Service, User


def test_owner_can_manage_only_own_service_catalog(client: TestClient, test_db: Session):
    shops = [
        Barbershop(
            name=f"Catálogo {index}", slug=f"catalog-{index}", email=f"shop{index}@example.com",
            phone="8095550000", address_line1="Calle 1", city="Santo Domingo", state="DN",
            postal_code="10101", country="DO", timezone="America/Santo_Domingo",
        )
        for index in (1, 2)
    ]
    test_db.add_all(shops)
    test_db.flush()
    owner = User(
        email="catalog-owner@example.com", password_hash="unused", first_name="Dueño",
        last_name="Prueba", role="barbershop_owner", is_active=True, barbershop_id=shops[0].id,
    )
    barber = User(
        email="catalog-barber@example.com", password_hash="unused", first_name="Barbero",
        last_name="Prueba", role="barber", is_active=True, barbershop_id=shops[0].id,
    )
    foreign = Service(
        barbershop_id=shops[1].id, name="Ajeno", duration_minutes=30, price=1000,
        category="haircut", is_active=True,
    )
    test_db.add_all([owner, barber, foreign])
    test_db.commit()

    owner_headers = {"Authorization": f"Bearer {create_access_token({'sub': str(owner.id), 'role': owner.role})}"}
    barber_headers = {"Authorization": f"Bearer {create_access_token({'sub': str(barber.id), 'role': barber.role})}"}
    created = client.post(
        "/api/v1/services/",
        headers=owner_headers,
        json={"name": "Corte clásico", "duration_minutes": 45, "price": 25000, "category": "haircut"},
    )
    assert created.status_code == 201
    service_id = created.json()["id"]
    assert created.json()["price_cents"] == 25000
    assert test_db.query(AuditLog).filter(
        AuditLog.action == "service.created", AuditLog.entity_id == service_id,
    ).count() == 1

    invalid_update = client.put(
        f"/api/v1/services/{service_id}", headers=owner_headers, json={"price": None},
    )
    assert invalid_update.status_code == 422

    forbidden_create = client.post(
        "/api/v1/services/",
        headers=barber_headers,
        json={"name": "Servicio no autorizado", "duration_minutes": 30, "price": 1000, "category": "haircut"},
    )
    assert forbidden_create.status_code == 403

    foreign_id = foreign.id
    forbidden_read = client.get(f"/api/v1/services/{foreign_id}", headers=owner_headers)
    assert forbidden_read.status_code == 404

    deactivated = client.delete(f"/api/v1/services/{service_id}", headers=owner_headers)
    assert deactivated.status_code == 204
    assert test_db.query(AuditLog).filter(
        AuditLog.action == "service.deleted", AuditLog.entity_id == service_id,
    ).count() == 1
    hidden = client.get("/api/v1/services/", headers=owner_headers)
    assert all(item["id"] != service_id for item in hidden.json()["services"])


def test_superadmin_can_suspend_tenant_and_cannot_disable_self(client: TestClient, test_db: Session):
    shop = Barbershop(
        name="Suspendida", slug="suspend-test", email="suspend@example.com", phone="8095550200",
        address_line1="Calle 2", city="Santo Domingo", state="DN", postal_code="10101",
        country="DO", timezone="America/Santo_Domingo",
    )
    test_db.add(shop)
    test_db.flush()
    owner = User(
        email="suspend-owner@example.com", password_hash=hash_password("StrongPassword123"), first_name="Dueño",
        last_name="Suspendido", role="barbershop_owner", is_active=True, barbershop_id=shop.id,
    )
    admin = User(
        email="super-admin@example.com", password_hash="unused", first_name="Super",
        last_name="Admin", role="super_admin", is_active=True,
    )
    test_db.add_all([owner, admin])
    test_db.commit()

    admin_headers = {"Authorization": f"Bearer {create_access_token({'sub': str(admin.id), 'role': admin.role})}"}
    owner_headers = {"Authorization": f"Bearer {create_access_token({'sub': str(owner.id), 'role': owner.role})}"}
    login = client.post("/api/v1/auth/login", json={
        "email": owner.email, "password": "StrongPassword123",
    })
    assert login.status_code == 200
    session_tokens = login.json()
    disabled = client.put(
        f"/api/v1/admin/tenants/{shop.id}/status", headers=admin_headers, json={"is_active": False}
    )
    assert disabled.status_code == 200
    test_db.refresh(owner)
    assert owner.auth_version == 1
    assert test_db.query(RefreshSession).filter(
        RefreshSession.user_id == owner.id,
        RefreshSession.revoked_at.is_(None),
    ).count() == 0
    assert client.get("/api/v1/services/", headers=owner_headers).status_code == 401
    assert client.post("/api/v1/auth/refresh", json={
        "refresh_token": session_tokens["refresh_token"],
    }).status_code == 401
    assert client.get("/api/v1/owner/barbers", headers=owner_headers).status_code == 401
    enabled = client.put(
        f"/api/v1/admin/tenants/{shop.id}/status", headers=admin_headers, json={"is_active": True}
    )
    assert enabled.status_code == 200
    test_db.refresh(owner)
    assert owner.auth_version == 2
    assert client.get("/api/v1/services/", headers=owner_headers).status_code == 401
    assert client.post("/api/v1/auth/login", json={
        "email": owner.email, "password": "StrongPassword123",
    }).status_code == 200
    self_disable = client.put(
        f"/api/v1/admin/users/{admin.id}/status", headers=admin_headers, json={"is_active": False}
    )
    assert self_disable.status_code == 409
