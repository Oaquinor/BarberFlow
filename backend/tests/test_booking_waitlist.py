"""MySQL integration tests for public waitlist intake and owner follow-up."""

from datetime import date, datetime, time, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models import (
    AuditLog, BarberAvailability, BarberAvailabilityBlock, Barbershop,
    BookingWaitlistEntry, Service, Subscription, User,
)
from app.utils.datetime import utc_now_naive


def _create_shop(test_db: Session, suffix: str):
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
    test_db.add(subscription)
    test_db.flush()
    shop = Barbershop(
        name=f"Waitlist {suffix}",
        slug=f"waitlist-{suffix}",
        email=f"shop-{suffix}@example.com",
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
    test_db.add(shop)
    test_db.flush()
    owner = User(
        email=f"owner-{suffix}@example.com",
        password_hash="unused",
        first_name="Owner",
        last_name=suffix,
        role="barbershop_owner",
        is_active=True,
        barbershop_id=shop.id,
    )
    barber = User(
        email=f"barber-{suffix}@example.com",
        password_hash="unused",
        first_name="Barber",
        last_name=suffix,
        role="barber",
        is_active=True,
        barbershop_id=shop.id,
    )
    service = Service(
        barbershop_id=shop.id,
        name="Corte clásico",
        duration_minutes=30,
        price=1800,
        category="haircut",
        is_active=True,
    )
    test_db.add_all([owner, barber, service])
    test_db.commit()
    return shop, owner, barber, service


def _headers(user: User):
    token = create_access_token({"sub": str(user.id), "role": user.role})
    return {"Authorization": f"Bearer {token}"}


def test_public_request_persists_and_owner_can_contact_and_close(
    client: TestClient,
    test_db: Session,
):
    shop, owner, barber, service = _create_shop(test_db, "one")
    preferred_start = date.today() + timedelta(days=6)
    preferred_end = date.today() + timedelta(days=10)
    payload = {
        "client_name": " Ana Cliente ",
        "phone": "+1 (809) 555-4141",
        "service_id": service.id,
        "idempotency_key": str(uuid4()),
        "barber_id": barber.id,
        "preferred_date_start": preferred_start.isoformat(),
        "preferred_date_end": preferred_end.isoformat(),
        "notes": "  Después de las cinco  ",
    }

    submitted = client.post(f"/api/v1/public/{shop.slug}/waitlist", json=payload)
    assert submitted.status_code == 202
    assert submitted.json()["accepted"] is True
    assert "no garantiza una cita" in submitted.json()["message"].lower()
    retry = client.post(f"/api/v1/public/{shop.slug}/waitlist", json=payload)
    assert retry.status_code == 202
    assert test_db.query(BookingWaitlistEntry).filter_by(barbershop_id=shop.id).count() == 1

    entry = test_db.query(BookingWaitlistEntry).filter_by(barbershop_id=shop.id).one()
    assert entry.client_name == "Ana Cliente"
    assert entry.phone == "18095554141"
    assert entry.status == "new"
    assert entry.notes == "Después de las cinco"
    assert (
        test_db.query(AuditLog)
        .filter_by(
            action="booking.waitlist_requested",
            entity_id=entry.id,
            barbershop_id=shop.id,
        )
        .count()
        == 1
    )

    headers = _headers(owner)
    listed = client.get("/api/v1/owner/waitlist", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["barber_name"] == barber.full_name
    assert listed.json()["items"][0]["service_name"] == service.name

    good_start = datetime.combine(preferred_start, time(17))
    blocked_start = datetime.combine(preferred_start, time(18))
    short_start = datetime.combine(preferred_start, time(19))
    good_slot = BarberAvailability(
        barbershop_id=shop.id, barber_id=barber.id,
        slot_start=good_start, slot_end=good_start + timedelta(minutes=45),
        is_active=True, is_booked=False,
    )
    blocked_slot = BarberAvailability(
        barbershop_id=shop.id, barber_id=barber.id,
        slot_start=blocked_start, slot_end=blocked_start + timedelta(minutes=45),
        is_active=True, is_booked=False,
    )
    short_slot = BarberAvailability(
        barbershop_id=shop.id, barber_id=barber.id,
        slot_start=short_start, slot_end=short_start + timedelta(minutes=20),
        is_active=True, is_booked=False,
    )
    test_db.add_all([good_slot, blocked_slot, short_slot])
    test_db.add(BarberAvailabilityBlock(
        barbershop_id=shop.id, barber_id=barber.id,
        starts_at=blocked_start, ends_at=blocked_start + timedelta(minutes=45),
        reason="Pausa",
    ))
    test_db.commit()
    matches = client.get(
        f"/api/v1/owner/waitlist/{entry.id}/matches", headers=headers,
    )
    assert matches.status_code == 200
    assert matches.json()["service_name"] == service.name
    assert [item["availability_id"] for item in matches.json()["items"]] == [good_slot.id]
    assert matches.json()["items"][0]["barber_name"] == barber.full_name
    assert f"service_id={service.id}&barber_id={barber.id}" in matches.json()["items"][0]["booking_url"]

    contacted = client.put(
        f"/api/v1/owner/waitlist/{entry.id}/status",
        headers=headers,
        json={"status": "contacted"},
    )
    assert contacted.status_code == 200
    assert contacted.json()["contacted_at"]
    assert test_db.get(BookingWaitlistEntry, entry.id).status == "contacted"

    closed = client.put(
        f"/api/v1/owner/waitlist/{entry.id}/status",
        headers=headers,
        json={"status": "closed"},
    )
    assert closed.status_code == 200
    filtered = client.get("/api/v1/owner/waitlist?status=new", headers=headers)
    assert filtered.status_code == 200
    assert filtered.json()["items"] == []


def test_waitlist_rejects_foreign_resources_and_isolates_tenant_management(
    client: TestClient,
    test_db: Session,
):
    shop, owner, _barber, _service = _create_shop(test_db, "local")
    other_shop, other_owner, other_barber, other_service = _create_shop(test_db, "foreign")
    payload = {
        "client_name": "Cliente Prueba",
        "phone": "8095554222",
        "service_id": other_service.id,
        "idempotency_key": str(uuid4()),
    }
    rejected_service = client.post(f"/api/v1/public/{shop.slug}/waitlist", json=payload)
    assert rejected_service.status_code == 422
    payload["service_id"] = _service.id
    payload["barber_id"] = other_barber.id
    rejected_barber = client.post(f"/api/v1/public/{shop.slug}/waitlist", json=payload)
    assert rejected_barber.status_code == 422

    created = client.post(
        f"/api/v1/public/{shop.slug}/waitlist",
        json={
            "client_name": "Cliente Prueba",
            "phone": "8095554222",
            "service_id": _service.id,
            "idempotency_key": str(uuid4()),
        },
    )
    assert created.status_code == 202
    entry = test_db.query(BookingWaitlistEntry).filter_by(barbershop_id=shop.id).one()

    assert client.get("/api/v1/owner/waitlist").status_code == 401
    assert client.get("/api/v1/owner/waitlist", headers=_headers(other_owner)).json()["items"] == []
    assert client.get(
        f"/api/v1/owner/waitlist/{entry.id}/matches", headers=_headers(other_owner),
    ).status_code == 404
    cross_tenant_update = client.put(
        f"/api/v1/owner/waitlist/{entry.id}/status",
        headers=_headers(other_owner),
        json={"status": "closed"},
    )
    assert cross_tenant_update.status_code == 404
    assert test_db.get(BookingWaitlistEntry, entry.id).status == "new"
    assert client.get("/api/v1/owner/waitlist", headers=_headers(other_barber)).status_code == 403


def test_waitlist_validates_date_range_and_status(client: TestClient, test_db: Session):
    shop, owner, _barber, service = _create_shop(test_db, "validation")
    today = date.today()
    invalid_range = client.post(
        f"/api/v1/public/{shop.slug}/waitlist",
        json={
            "client_name": "Cliente Prueba",
            "phone": "8095554333",
            "service_id": service.id,
            "idempotency_key": str(uuid4()),
            "preferred_date_start": (today + timedelta(days=10)).isoformat(),
            "preferred_date_end": (today + timedelta(days=1)).isoformat(),
        },
    )
    assert invalid_range.status_code == 422
    invalid_status = client.put(
        "/api/v1/owner/waitlist/1/status",
        headers=_headers(owner),
        json={"status": "booked"},
    )
    assert invalid_status.status_code == 422

