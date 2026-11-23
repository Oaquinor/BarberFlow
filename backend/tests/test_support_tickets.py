"""MySQL integration coverage for the persistent platform support inbox."""

from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models import AuditLog, Barbershop, SupportTicket, Subscription, User
from app.utils.datetime import utc_now_naive


def test_support_request_is_saved_when_email_delivery_fails_and_admin_can_manage_it(
    client: TestClient, test_db: Session, monkeypatch
):
    import app.api.v1.endpoints.platform as platform

    monkeypatch.setattr(platform, "_send_email", lambda *_args, **_kwargs: False)
    now = utc_now_naive()
    subscription = Subscription(
        plan="free", status="active", current_period_start=now - timedelta(days=1),
        current_period_end=now + timedelta(days=29), max_barbers=1,
        max_appointments_per_month=50, max_clients=100, auto_renew=False,
    )
    test_db.add(subscription)
    test_db.flush()
    shop = Barbershop(
        name="Support Shop", slug="support-shop-test", email="support-shop@example.com",
        phone="8095553050", address_line1="Calle 50", city="Santo Domingo", state="DN",
        postal_code="10107", country="DO", timezone="America/Santo_Domingo",
        currency="DOP", subscription_id=subscription.id,
    )
    test_db.add(shop)
    test_db.flush()
    admin = User(
        email="support-platform-admin@example.com", password_hash="unused", first_name="Platform",
        last_name="Admin", role="super_admin", is_active=True, support_contact_enabled=True,
    )
    owner = User(
        email="support-shop-owner@example.com", password_hash="unused", first_name="Shop",
        last_name="Owner", role="barbershop_owner", is_active=True, barbershop_id=shop.id,
        support_contact_enabled=True,
    )
    test_db.add_all([admin, owner])
    test_db.commit()

    admin_headers = {"Authorization": f"Bearer {create_access_token({'sub': str(admin.id)})}"}
    owner_headers = {"Authorization": f"Bearer {create_access_token({'sub': str(owner.id)})}"}
    response = client.post("/api/v1/support/contact", json={
        "name": "  Ana Cliente ", "email": "ANA@example.com", "phone": "8095553051",
        "message": "  Necesito ayuda con una reserva.  ", "barbershop_slug": shop.slug,
    })
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["notification_sent"] is False
    assert payload["sent_to"] == 0

    ticket = test_db.get(SupportTicket, payload["ticket_id"])
    assert ticket.barbershop_id == shop.id
    assert ticket.sender_name == "Ana Cliente"
    assert ticket.sender_email == "ana@example.com"
    assert ticket.message == "Necesito ayuda con una reserva."

    listed = client.get("/api/v1/admin/support/tickets?status=open", headers=admin_headers)
    assert listed.status_code == 200
    assert listed.json()["items"] == [{
        "id": ticket.id,
        "barbershop_id": shop.id,
        "barbershop_name": shop.name,
        "name": "Ana Cliente",
        "email": "ana@example.com",
        "phone": "8095553051",
        "message": "Necesito ayuda con una reserva.",
        "status": "open",
        "notification_sent": False,
        "created_at": ticket.created_at.isoformat(),
    }]
    assert client.get("/api/v1/admin/support/tickets", headers=owner_headers).status_code == 403
    assert client.put(
        f"/api/v1/admin/support/tickets/{ticket.id}/status", headers=owner_headers,
        json={"status": "resolved"},
    ).status_code == 403

    updated = client.put(
        f"/api/v1/admin/support/tickets/{ticket.id}/status", headers=admin_headers,
        json={"status": "in_progress"},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "in_progress"
    assert client.get(
        "/api/v1/admin/support/tickets?status=open", headers=admin_headers,
    ).json()["items"] == []
    assert client.get(
        "/api/v1/admin/support/tickets?status=in_progress", headers=admin_headers,
    ).json()["items"][0]["id"] == ticket.id
    audit = test_db.query(AuditLog).filter_by(
        action="support.ticket_status_changed", entity_id=ticket.id,
    ).one()
    assert audit.actor_user_id == admin.id
    assert audit.details == {"previous": "open", "status": "in_progress"}
