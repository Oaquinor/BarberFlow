"""Exercise account registration through the first real public reservation."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def test_saas_registration_onboarding_setup_and_public_booking(
    client: TestClient, test_db: Session,
):
    registration = client.post(
        "/api/v1/saas/register",
        json={
            "owner_email": "lifecycle-owner@example.com",
            "owner_password": "SecureLifecycle2026",
            "owner_first_name": "Owner",
            "owner_last_name": "Lifecycle",
            "owner_phone": "8095554101",
            "barbershop_name": "Lifecycle Barbería",
            "barbershop_email": "lifecycle-shop@example.com",
            "barbershop_phone": "8095554102",
            "address_line1": "Calle Lifecycle 1",
            "city": "Santo Domingo",
            "state": "DN",
            "postal_code": "10110",
            "country": "DO",
            "timezone": "America/Santo_Domingo",
            "currency": "DOP",
            "affiliate_code": "",
        },
    )
    assert registration.status_code == 201
    access_token = registration.json()["access_token"]
    owner_headers = {"Authorization": f"Bearer {access_token}"}

    onboarding = client.post(
        "/api/v1/onboarding/complete",
        headers=owner_headers,
        json={
            "barbershop_name": "Lifecycle Barbería",
            "primary_color": "#223344",
            "secondary_color": "#556677",
            "style": "modern",
            "primary_goal": "organization",
            "team_size": 1,
            "avg_service_duration": 30,
            "opening_time": "09:00",
            "closing_time": "18:00",
            "personality": "professional",
        },
    )
    assert onboarding.status_code == 200
    assert onboarding.json()["onboarding_completed"] is True

    barber_created = client.post(
        "/api/v1/owner/barbers",
        headers=owner_headers,
        json={
            "email": "lifecycle-barber@example.com",
            "password": "SecureBarber2026",
            "first_name": "Barber",
            "last_name": "Lifecycle",
            "phone": "8095554103",
        },
    )
    assert barber_created.status_code == 201
    barber_login = client.post(
        "/api/v1/auth/login",
        json={"email": "lifecycle-barber@example.com", "password": "SecureBarber2026"},
    )
    assert barber_login.status_code == 200
    barber_headers = {"Authorization": f"Bearer {barber_login.json()['access_token']}"}

    service_created = client.post(
        "/api/v1/services/",
        headers=owner_headers,
        json={
            "name": "Corte Lifecycle",
            "description": "Servicio de prueba de flujo completo",
            "duration_minutes": 30,
            "price": 25000,
            "category": "haircut",
        },
    )
    assert service_created.status_code == 201

    shop_id = registration.json()["user"]["barbershop_id"]
    from app.models import Barbershop

    shop = test_db.get(Barbershop, shop_id)
    local_date = datetime.now(ZoneInfo(shop.timezone)).date() + timedelta(days=1)
    availability = client.post(
        "/api/v1/barber/slots",
        headers=barber_headers,
        json={
            "date": local_date.isoformat(),
            "start_time": "10:00",
            "end_time": "11:00",
            "slot_minutes": 30,
        },
    )
    assert availability.status_code == 200

    public_shop = client.get(f"/api/v1/public/{shop.slug}")
    public_services = client.get(f"/api/v1/public/{shop.slug}/services")
    public_slots = client.get(
        f"/api/v1/public/{shop.slug}/slots",
        params={"duration_minutes": 30},
    )
    assert public_shop.status_code == 200
    assert public_services.status_code == 200
    assert [service["id"] for service in public_services.json()] == [service_created.json()["id"]]
    assert public_slots.status_code == 200
    selected_slot = next(slot for slot in public_slots.json() if slot["barber_id"] == barber_created.json()["id"])
    slot_start = datetime.fromisoformat(selected_slot["slot_start"].replace("Z", "+00:00"))
    if slot_start.tzinfo is None:
        slot_start = slot_start.replace(tzinfo=timezone.utc)

    reservation = client.post(
        f"/api/v1/public/{shop.slug}/appointments",
        json={
            "client_name": "Cliente Lifecycle",
            "phone": "8095554104",
            "service_id": service_created.json()["id"],
            "barber_id": selected_slot["barber_id"],
            "scheduled_time": slot_start.astimezone(timezone.utc).isoformat(),
        },
    )
    assert reservation.status_code == 200
    assert reservation.json()["status"] == "pending"
