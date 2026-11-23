"""Owner subscription status is derived from MySQL plan and tenant usage."""

from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models import AuditLog, Appointment, Barbershop, Service, Subscription, SupportTicket, User
from app.utils.datetime import local_month_window_utc_naive, utc_now_naive
from zoneinfo import ZoneInfo


def _headers(user: User) -> dict[str, str]:
    token = create_access_token({"sub": str(user.id), "role": user.role})
    return {"Authorization": f"Bearer {token}"}


def test_expired_subscription_blocks_public_booking_but_owner_can_review_billing(
    client: TestClient, test_db: Session,
):
    now = utc_now_naive()
    subscription = Subscription(
        plan="basic", status="active", current_period_start=now - timedelta(days=31),
        current_period_end=now - timedelta(seconds=1), max_barbers=3,
        max_appointments_per_month=100, max_clients=200, auto_renew=True,
    )
    test_db.add(subscription)
    test_db.flush()
    shop = Barbershop(
        name="Expired Billing", slug="expired-billing-test", email="expired-billing@example.com",
        phone="8095555011", address_line1="Calle 51", city="Santo Domingo", state="DN",
        postal_code="10106", country="DO", timezone="America/Santo_Domingo",
        currency="DOP", subscription_id=subscription.id, is_active=True,
    )
    test_db.add(shop)
    test_db.flush()
    owner = User(
        email="expired-billing-owner@example.com", password_hash="unused", first_name="Owner",
        last_name="Expired", role="barbershop_owner", is_active=True, barbershop_id=shop.id,
    )
    barber = User(
        email="expired-billing-barber@example.com", password_hash="unused", first_name="Barber",
        last_name="Expired", role="barber", is_active=True, barbershop_id=shop.id,
    )
    service = Service(
        barbershop_id=shop.id, name="Corte expirado", duration_minutes=30,
        price=2000, category="haircut", is_active=True,
    )
    test_db.add_all([owner, barber, service])
    test_db.commit()

    public_profile = client.get(f"/api/v1/public/{shop.slug}")
    public_services = client.get(f"/api/v1/public/{shop.slug}/services")
    assert public_profile.status_code == 402
    assert public_services.status_code == 402
    public_booking = client.post(f"/api/v1/public/{shop.slug}/appointments", json={
        "client_name": "Cliente vencido", "phone": "8095555012", "service_id": service.id,
        "scheduled_time": (now + timedelta(days=1)).isoformat(),
    })
    assert public_booking.status_code == 402

    barber_headers = _headers(barber)
    target_date = (datetime.now(ZoneInfo(shop.timezone)).date() + timedelta(days=1)).isoformat()
    new_slot = client.post("/api/v1/barber/slots", headers=barber_headers, json={
        "date": target_date, "start_time": "09:00", "end_time": "12:00", "slot_minutes": 30,
    })
    absence = client.post("/api/v1/barber/absences", headers=barber_headers, json={
        "date": target_date, "start_time": "09:00", "end_time": "10:00",
    })
    walk_in = client.post("/api/v1/barber/appointments/walk-in", headers=barber_headers, json={
        "client_name": "Cliente local", "phone": "8095555013", "service_id": service.id,
    })
    assert new_slot.status_code == 402
    assert absence.status_code == 402
    assert walk_in.status_code == 402

    billing = client.get("/api/v1/billing/subscription", headers=_headers(owner))
    assert billing.status_code == 200
    assert billing.json()["status"] == "expired"
    assert billing.json()["days_remaining"] == 0

    renewal = client.post("/api/v1/billing/renewal-request", headers=_headers(owner))
    assert renewal.status_code == 201
    assert renewal.json()["created"] is True
    ticket_id = renewal.json()["ticket_id"]
    assert test_db.query(SupportTicket).filter(
        SupportTicket.id == ticket_id, SupportTicket.barbershop_id == shop.id,
    ).count() == 1
    assert test_db.query(AuditLog).filter(
        AuditLog.action == "subscription.renewal_requested",
        AuditLog.entity_id == ticket_id,
        AuditLog.barbershop_id == shop.id,
    ).count() == 1

    duplicate = client.post("/api/v1/billing/renewal-request", headers=_headers(owner))
    assert duplicate.status_code == 200
    assert duplicate.json() == {"success": True, "created": False, "ticket_id": ticket_id}
    assert test_db.query(SupportTicket).filter(
        SupportTicket.barbershop_id == shop.id,
        SupportTicket.message.startswith("[Solicitud de renovación]"),
    ).count() == 1
    assert client.post(
        "/api/v1/billing/renewal-request", headers=_headers(barber),
    ).status_code == 403

    admin = User(
        email="expired-billing-admin@example.com", password_hash="unused", first_name="Platform",
        last_name="Admin", role="super_admin", is_active=True,
    )
    test_db.add(admin)
    test_db.commit()
    support = client.get(
        f"/api/v1/admin/support/tickets?barbershop_id={shop.id}", headers=_headers(admin),
    )
    assert support.status_code == 200
    assert [item["id"] for item in support.json()["items"]] == [ticket_id]


def test_owner_reads_subscription_period_and_real_limits(client: TestClient, test_db: Session):
    now = utc_now_naive()
    subscription = Subscription(
        plan="basic", status="active", current_period_start=now - timedelta(days=2),
        current_period_end=now + timedelta(days=20), max_barbers=3,
        max_appointments_per_month=100, max_clients=200, auto_renew=True,
    )
    test_db.add(subscription)
    test_db.flush()
    shop = Barbershop(
        name="Billing Status", slug="billing-status-test", email="billing-status@example.com",
        phone="8095555010", address_line1="Calle 50", city="Santo Domingo", state="DN",
        postal_code="10105", country="DO", timezone="America/Santo_Domingo",
        currency="DOP", subscription_id=subscription.id,
    )
    test_db.add(shop)
    test_db.flush()
    owner = User(
        email="billing-status-owner@example.com", password_hash="unused", first_name="Owner",
        last_name="Billing", role="barbershop_owner", is_active=True, barbershop_id=shop.id,
    )
    barber = User(
        email="billing-status-barber@example.com", password_hash="unused", first_name="Barber",
        last_name="Active", role="barber", is_active=True, barbershop_id=shop.id,
    )
    inactive_barber = User(
        email="billing-status-inactive@example.com", password_hash="unused", first_name="Barber",
        last_name="Inactive", role="barber", is_active=False, barbershop_id=shop.id,
    )
    customers = [User(
        email=f"billing-status-client-{i}@example.com", password_hash="unused",
        first_name="Client", last_name=str(i), role="client", is_active=True, barbershop_id=shop.id,
    ) for i in range(2)]
    test_db.add_all([owner, barber, inactive_barber, *customers])
    test_db.flush()
    appointment = Appointment(
        barbershop_id=shop.id, client_id=customers[0].id, barber_id=barber.id,
        scheduled_time=now + timedelta(days=1), estimated_duration=30, service_type="Corte",
        service_price=1500, status="confirmed", created_at=now,
    )
    month_start, _ = local_month_window_utc_naive(now, ZoneInfo(shop.timezone))
    previous_month_appointment = Appointment(
        barbershop_id=shop.id, client_id=customers[1].id, barber_id=barber.id,
        scheduled_time=now - timedelta(days=2), estimated_duration=30, service_type="Corte",
        service_price=1500, status="completed", created_at=month_start - timedelta(seconds=1),
    )
    test_db.add_all([appointment, previous_month_appointment])
    test_db.commit()

    result = client.get("/api/v1/billing/subscription", headers=_headers(owner))
    assert result.status_code == 200
    data = result.json()
    assert data["plan"] == "basic"
    assert data["status"] == "active"
    assert data["currency"] == "DOP"
    assert data["days_remaining"] in range(19, 22)
    assert data["auto_renew"] is True
    assert data["usage"] == {
        "barbers": {"used": 1, "limit": 3},
        "appointments": {"used": 1, "limit": 100},
        "clients": {"used": 2, "limit": 200},
    }
    assert client.get("/api/v1/billing/subscription", headers=_headers(barber)).status_code == 403

    subscription.current_period_end = now - timedelta(seconds=1)
    test_db.commit()
    expired = client.get("/api/v1/billing/subscription", headers=_headers(owner))
    assert expired.status_code == 200
    assert expired.json()["status"] == "expired"
    assert expired.json()["days_remaining"] == 0
