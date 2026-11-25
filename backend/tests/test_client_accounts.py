"""Customer account verification and tracking-token CRM claims (MySQL integration)."""

from datetime import timedelta
from hashlib import sha256
from urllib.parse import urlparse, parse_qs

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.v1 import client_accounts as accounts_api
from app.core.security import create_access_token
from app.models import (
    Appointment, Barbershop, ClientAccountShopLink, Service, Subscription, User,
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

