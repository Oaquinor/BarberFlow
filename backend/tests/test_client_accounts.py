"""Customer account verification and tracking-token CRM claims (MySQL integration)."""

from datetime import timedelta, timezone
from hashlib import sha256
from urllib.parse import urlparse, parse_qs

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.v1 import client_accounts as accounts_api
from app.core.security import create_access_token
from app.models import (
    Appointment, BarberAvailability, Barbershop, ClientAccountShopLink, Service, Subscription, User,
)
from app.utils.datetime import utc_now_naive


def test_client_registration_requires_email_verification_before_login(
    client: TestClient, test_db: Session, monkeypatch,
):
    monkeypatch.setattr(accounts_api, "_smtp_ready", lambda: True)
    sent = {}
    monkeypatch.setattr(
        accounts_api, "_deliver_verification_email",
        lambda recipient, first_name, url: sent.update(recipient=recipient, url=url),
    )
    payload = {
        "email": "new-client@example.com", "password": "CustomerPass123",
        "first_name": "Ana", "last_name": "Cliente", "phone": "+1 (809) 555-1212",
    }
    registered = client.post("/api/v1/client-account/register", json=payload)
    assert registered.status_code == 202
    assert sent["recipient"] == payload["email"]
    user = test_db.query(User).filter_by(email=payload["email"]).one()
    assert user.role == "client" and user.barbershop_id is None
    assert user.is_active is False and user.is_verified is False
    assert client.post("/api/v1/auth/login", json={"email": payload["email"], "password": payload["password"]}).status_code == 401

    token = parse_qs(urlparse(sent["url"]).query)["verify"][0]
    verified = client.post("/api/v1/client-account/verify", json={"token": token})
    assert verified.status_code == 200
    assert client.post("/api/v1/client-account/verify", json={"token": token}).status_code == 400
    login = client.post("/api/v1/auth/login", json={"email": payload["email"], "password": payload["password"]})
    assert login.status_code == 200
    assert login.json()["user"]["role"] == "client"


def test_client_claims_only_a_private_token_and_sees_only_linked_shop_history(
    client: TestClient, test_db: Session,
):
    now = utc_now_naive()
    subscription = Subscription(
        plan="free", status="active", current_period_start=now - timedelta(days=1),
        current_period_end=now + timedelta(days=29), max_barbers=2,
        max_appointments_per_month=100, max_clients=100, auto_renew=False,
    )
    test_db.add(subscription)
    test_db.flush()
    shop = Barbershop(
        name="Cliente Seguro", slug="client-account-claim", email="account-shop@example.com",
        phone="8095550401", address_line1="Calle 8", city="Santo Domingo",
        state="DN", postal_code="10101", country="DO", timezone="America/Santo_Domingo",
        currency="DOP", subscription_id=subscription.id,
    )
    barber = User(email="account-barber@example.com", password_hash="unused", first_name="Luis",
                  last_name="Barbero", role="barber", is_active=True, barbershop=shop)
    old_client = User(email="old-guest@client.invalid", password_hash="unused", first_name="Ana",
                      last_name="Invitada", phone="18095551212", role="client", is_active=True,
                      is_verified=False, barbershop=shop)
    service = Service(barbershop=shop, name="Corte", duration_minutes=30, price=25000,
                      category="haircut", is_active=True)
    test_db.add_all([shop, barber, old_client, service])
    test_db.flush()
    private_token = "private-tracking-token-" + "x" * 20
    appointment = Appointment(
        barbershop_id=shop.id, client_id=old_client.id, barber_id=barber.id,
        scheduled_time=now + timedelta(days=2), estimated_duration=30,
        service_type="Corte", service_price=25000, status="confirmed",
        tracking_token_hash=sha256(private_token.encode()).hexdigest(),
    )
    account = User(email="verified-client@example.com", password_hash="unused", first_name="Ana",
                   last_name="Cuenta", phone="18095551212", role="client", is_active=True,
                   is_verified=True, barbershop_id=None)
    test_db.add_all([appointment, account])
    test_db.commit()
    headers = {"Authorization": f"Bearer {create_access_token({'sub': str(account.id), 'role': account.role})}"}

    assert client.get("/api/v1/client-account/appointments", headers=headers).json() == {"items": []}
    invalid = client.post("/api/v1/client-account/appointments/claim", headers=headers,
                          json={"tracking_token": "z" * 40})
    assert invalid.status_code == 404
    assert test_db.get(Appointment, appointment.id).client_id == old_client.id

    claimed = client.post("/api/v1/client-account/appointments/claim", headers=headers,
                          json={"tracking_token": private_token})
    assert claimed.status_code == 200
    test_db.refresh(appointment)
    assert appointment.client_id != old_client.id
    link = test_db.query(ClientAccountShopLink).filter_by(account_user_id=account.id).one()
    assert link.crm_client_user_id == appointment.client_id
    history = client.get("/api/v1/client-account/appointments", headers=headers)
    assert history.status_code == 200
    assert [item["appointment_id"] for item in history.json()["items"]] == [appointment.id]


def test_verified_customer_booking_needs_no_repeated_identity_and_appears_in_account(
    client: TestClient, test_db: Session, monkeypatch,
):
    import app.api.v1.endpoints.booking as booking_api
    import app.api.v1.endpoints.common as common_api

    now = utc_now_naive().replace(second=0, microsecond=0)
    monkeypatch.setattr(booking_api, "utc_now_naive", lambda: now)
    monkeypatch.setattr(common_api, "utc_now_naive", lambda: now)
    subscription = Subscription(
        plan="free", status="active", current_period_start=now - timedelta(days=1),
        current_period_end=now + timedelta(days=29), max_barbers=2,
        max_appointments_per_month=100, max_clients=100, auto_renew=False,
    )
    shop = Barbershop(
        name="Reserva de Cuenta", slug="verified-account-booking",
        email="verified-booking-shop@example.com", phone="8095550402",
        address_line1="Calle 9", city="Santo Domingo", state="DN", postal_code="10102",
        country="DO", timezone="America/Santo_Domingo", subscription=subscription,
    )
    barber = User(
        email="verified-booking-barber@example.com", password_hash="unused",
        first_name="Luis", last_name="Barbero", role="barber", is_active=True,
        barbershop=shop,
    )
    account = User(
        email="verified-booking-customer@example.com", password_hash="unused",
        first_name="Ana", last_name="Cliente", phone="18095551213", role="client",
        is_active=True, is_verified=True, barbershop_id=None,
    )
    service = Service(
        barbershop=shop, name="Corte clásico", duration_minutes=30, price=25000,
        category="haircut", is_active=True,
    )
    test_db.add_all([shop, barber, account, service])
    test_db.flush()
    slot_start = now + timedelta(days=2)
    slot = BarberAvailability(
        barbershop_id=shop.id, barber_id=barber.id, slot_start=slot_start,
        slot_end=slot_start + timedelta(minutes=30), is_active=True, is_booked=False,
    )
    test_db.add(slot)
    test_db.commit()

    monkeypatch.setattr(booking_api, "_notify_appointment_staff", lambda *args, **kwargs: None)
    monkeypatch.setattr(booking_api, "_queue_appointment_email", lambda *args, **kwargs: None)
    monkeypatch.setattr(booking_api, "_queue_appointment_whatsapp", lambda *args, **kwargs: None)
    payload = {
        "service_id": service.id,
        "barber_id": barber.id,
        "scheduled_time": slot_start.replace(tzinfo=timezone.utc).isoformat(),
    }
    guest_without_identity = client.post(
        f"/api/v1/public/{shop.slug}/appointments", json=payload,
    )
    assert guest_without_identity.status_code == 422
    headers = {
        "Authorization": f"Bearer {create_access_token({'sub': str(account.id), 'role': 'client'})}",
    }
    response = client.post(
        f"/api/v1/public/{shop.slug}/appointments", headers=headers, json=payload,
    )

    assert response.status_code == 200, response.text
    assert response.json()["saved_to_account"] is True
    appointment = test_db.get(Appointment, response.json()["appointment_id"])
    link = test_db.query(ClientAccountShopLink).filter_by(account_user_id=account.id).one()
    assert appointment.client_id == link.crm_client_user_id
    assert appointment.client_id != account.id
    history = client.get("/api/v1/client-account/appointments", headers=headers)
    assert [item["appointment_id"] for item in history.json()["items"]] == [appointment.id]

