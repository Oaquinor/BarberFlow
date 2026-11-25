"""MySQL integration coverage for owner staff and client operations."""

from datetime import time, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models import Appointment, AuditLog, Barbershop, Payment, Subscription, User
from app.utils.datetime import utc_now_naive


def test_owner_can_manage_only_plan_limited_staff(client: TestClient, test_db: Session):
    now = utc_now_naive()
    subscription = Subscription(
        plan="free", status="active", current_period_start=now - timedelta(days=1),
        current_period_end=now + timedelta(days=29), max_barbers=1,
        max_appointments_per_month=50, max_clients=100, auto_renew=False,
    )
    test_db.add(subscription)
    test_db.flush()
    shop = Barbershop(
        name="Owner Management", slug="owner-management-test", email="owner-shop@example.com",
        phone="8095553000", address_line1="Calle 20", city="Santo Domingo", state="DN",
        postal_code="10103", country="DO", timezone="America/Santo_Domingo", currency="DOP",
        subscription_id=subscription.id,
    )
    foreign_shop = Barbershop(
        name="Owner Management Other", slug="owner-management-other-test",
        email="owner-management-other@example.com", phone="8095553002",
        address_line1="Calle 21", city="Santo Domingo", state="DN", postal_code="10104",
        country="DO", timezone="America/Santo_Domingo", currency="DOP",
    )
    test_db.add_all([shop, foreign_shop])
    test_db.flush()
    owner = User(
        email="owner-management@example.com", password_hash="unused", first_name="Owner",
        last_name="Test", role="barbershop_owner", is_active=True, barbershop_id=shop.id,
    )
    foreign_barber = User(
        email="owner-management-foreign-barber@example.com", password_hash="unused",
        first_name="Foreign", last_name="Barber", role="barber", is_active=True,
        barbershop_id=foreign_shop.id,
    )
    test_db.add_all([owner, foreign_barber])
    test_db.commit()

    headers = {"Authorization": f"Bearer {create_access_token({'sub': str(owner.id), 'role': owner.role})}"}
    created = client.post("/api/v1/owner/barbers", headers=headers, json={
        "email": "owner-created-barber@example.com", "password": "SecureBarber2026",
        "first_name": "Barber", "last_name": "One", "phone": "8095553001",
    })
    assert created.status_code == 201
    barber_id = created.json()["id"]
    updated = client.put(
        f"/api/v1/owner/barbers/{barber_id}", headers=headers,
        json={"first_name": "Edited", "last_name": "Barber", "phone": "+1 (809) 555-3003"},
    )
    assert updated.status_code == 200
    assert updated.json() == {"id": barber_id, "full_name": "Edited Barber", "phone": "18095553003"}
    assert test_db.get(User, barber_id).first_name == "Edited"
    assert client.put(
        f"/api/v1/owner/barbers/{foreign_barber.id}", headers=headers,
        json={"first_name": "Changed", "last_name": "Elsewhere", "phone": None},
    ).status_code == 404
    barber_headers = {"Authorization": f"Bearer {create_access_token({'sub': str(barber_id)})}"}
    assert client.put(
        f"/api/v1/owner/barbers/{barber_id}", headers=barber_headers,
        json={"first_name": "Changed", "last_name": "By Barber", "phone": None},
    ).status_code == 403
    audit = test_db.query(AuditLog).filter_by(
        action="barber.profile_updated", entity_id=barber_id, barbershop_id=shop.id,
    ).one()
    assert audit.actor_user_id == owner.id
    assert audit.details["updated_fields"] == ["first_name", "last_name", "phone"]

    listed = client.get("/api/v1/owner/barbers", headers=headers)
    assert listed.status_code == 200
    assert [row["email"] for row in listed.json()["items"]] == ["owner-created-barber@example.com"]
    assert listed.json()["items"][0]["first_name"] == "Edited"

    deactivated = client.put(
        f"/api/v1/owner/barbers/{barber_id}/status",
        headers=headers, json={"is_active": False},
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False

    over_limit = client.post("/api/v1/owner/barbers", headers=headers, json={
        "email": "owner-created-barber2@example.com", "password": "SecureBarber2027",
        "first_name": "Barber", "last_name": "Two",
    })
    assert over_limit.status_code == 201
    assert client.put(
        f"/api/v1/owner/barbers/{barber_id}/status",
        headers=headers, json={"is_active": True},
    ).status_code == 402
    assert client.put(
        f"/api/v1/owner/barbers/{over_limit.json()['id']}/status",
        headers=headers, json={"is_active": False},
    ).status_code == 200
    reactivated = client.put(
        f"/api/v1/owner/barbers/{barber_id}/status",
        headers=headers, json={"is_active": True},
    )
    assert reactivated.status_code == 200
    assert reactivated.json()["is_active"] is True

    clients = client.get("/api/v1/owner/clients", headers=headers)
    assert clients.status_code == 200
    assert clients.json()["items"] == []


def test_owner_can_update_business_settings_with_tenant_audit(client: TestClient, test_db: Session):
    now = utc_now_naive()
    subscription = Subscription(
        plan="free", status="active", current_period_start=now - timedelta(days=1),
        current_period_end=now + timedelta(days=29), max_barbers=1,
        max_appointments_per_month=50, max_clients=100, auto_renew=False,
    )
    test_db.add(subscription)
    test_db.flush()
    shop = Barbershop(
        name="Ajustes Originales", slug="business-settings-test", email="settings@example.com",
        phone="8095553010", address_line1="Calle 10", city="Santo Domingo", state="DN",
        postal_code="10103", country="DO", timezone="America/Santo_Domingo",
        currency="DOP", subscription_id=subscription.id,
        opening_time=time(8), closing_time=time(18),
        primary_color="#112233", secondary_color="#445566",
    )
    foreign_shop = Barbershop(
        name="Otra barbería", slug="business-settings-other", email="other@example.com",
        phone="8095553011", address_line1="Calle 11", city="Santo Domingo", state="DN",
        postal_code="10103", country="DO", timezone="America/Santo_Domingo", currency="DOP",
    )
    test_db.add_all([shop, foreign_shop])
    test_db.flush()
    owner = User(
        email="settings-owner@example.com", password_hash="unused", first_name="Owner",
        last_name="Settings", role="barbershop_owner", is_active=True, barbershop_id=shop.id,
    )
    barber = User(
        email="settings-barber@example.com", password_hash="unused", first_name="Barber",
        last_name="Settings", role="barber", is_active=True, barbershop_id=shop.id,
    )
    test_db.add_all([owner, barber])
    test_db.commit()

    owner_headers = {"Authorization": f"Bearer {create_access_token({'sub': str(owner.id), 'role': owner.role})}"}
    barber_headers = {"Authorization": f"Bearer {create_access_token({'sub': str(barber.id), 'role': barber.role})}"}
    updated = {
        "name": "KingFlow Downtown", "opening_time": "09:30", "closing_time": "19:00",
        "timezone": "America/New_York", "primary_color": "#AABBCC", "secondary_color": "#DDEEFF",
        "cancellation_window_hours": 12,
    }

    profile = client.get("/api/v1/onboarding/profile", headers=owner_headers)
    assert profile.status_code == 200
    assert profile.json()["timezone"] == "America/Santo_Domingo"
    assert profile.json()["opening_time"].startswith("08:00")

    saved = client.put("/api/v1/onboarding/business-settings", headers=owner_headers, json=updated)
    assert saved.status_code == 200
    assert saved.json()["name"] == updated["name"]
    assert saved.json()["timezone"] == updated["timezone"]
    assert saved.json()["opening_time"].startswith("09:30")
    assert saved.json()["primary_color"] == updated["primary_color"]
    assert saved.json()["cancellation_window_hours"] == 12
    assert test_db.get(Barbershop, shop.id).cancellation_window_hours == 12
    public_profile = client.get(f"/api/v1/public/{shop.slug}")
    assert public_profile.status_code == 200
    assert public_profile.json()["name"] == updated["name"]
    assert public_profile.json()["timezone"] == updated["timezone"]
    assert public_profile.json()["primary_color"] == updated["primary_color"]
    assert public_profile.json()["cancellation_window_hours"] == 12

    audit = test_db.query(AuditLog).filter_by(
        barbershop_id=shop.id, action="business.settings_updated", entity_id=shop.id,
    ).one()
    assert audit.actor_user_id == owner.id
    assert audit.details["previous"]["timezone"] == "America/Santo_Domingo"
    assert audit.details["timezone"] == "America/New_York"

    assert client.put(
        "/api/v1/onboarding/business-settings", headers=barber_headers, json=updated,
    ).status_code == 403
    assert client.put(
        f"/api/v1/onboarding/business-settings?barbershop_id={foreign_shop.id}",
        headers=owner_headers, json=updated,
    ).status_code == 403
    invalid_hours = {**updated, "opening_time": "19:00", "closing_time": "09:30"}
    assert client.put(
        "/api/v1/onboarding/business-settings", headers=owner_headers, json=invalid_hours,
    ).status_code == 422
    invalid_timezone = {**updated, "timezone": "Not/A_Real_Zone"}
    assert client.put(
        "/api/v1/onboarding/business-settings", headers=owner_headers, json=invalid_timezone,
    ).status_code == 422

    colors = {"primary_color": "#112233", "secondary_color": "#445566"}
    color_response = client.put("/api/v1/onboarding/brand-colors", headers=owner_headers, json=colors)
    assert color_response.status_code == 200
    color_audit = test_db.query(AuditLog).filter_by(
        barbershop_id=shop.id, action="business.brand_colors_updated", entity_id=shop.id,
    ).one()
    assert color_audit.actor_user_id == owner.id
    assert color_audit.details == {
        "previous": {"primary_color": "#AABBCC", "secondary_color": "#DDEEFF"},
        "updated": colors,
    }

    step = client.post(
        "/api/v1/onboarding/step/1", headers=owner_headers,
        json={"barbershop_name": "Nombre del onboarding"},
    )
    assert step.status_code == 200
    step_audit = test_db.query(AuditLog).filter_by(
        barbershop_id=shop.id, action="onboarding.name_updated", entity_id=shop.id,
    ).one()
    assert step_audit.details == {"previous": updated["name"], "updated": "Nombre del onboarding"}

    complete_data = {
        "barbershop_name": "Onboarding Completo", "primary_color": "#223344",
        "secondary_color": "#556677", "style": "modern", "primary_goal": "organization",
        "team_size": 3, "avg_service_duration": 30, "opening_time": "09:00",
        "closing_time": "18:00", "personality": "professional", "logo_uploaded": False,
    }
    completed = client.post("/api/v1/onboarding/complete", headers=owner_headers, json=complete_data)
    assert completed.status_code == 200
    completion_audit = test_db.query(AuditLog).filter_by(
        barbershop_id=shop.id, action="onboarding.completed", entity_id=shop.id,
    ).one()
    assert completion_audit.actor_user_id == owner.id
    assert completion_audit.details["previous"]["name"] == "Nombre del onboarding"
    assert completion_audit.details["updated"]["name"] == complete_data["barbershop_name"]


def test_owner_can_edit_and_deactivate_client_without_losing_history(client: TestClient, test_db: Session):
    shop = Barbershop(
        name="Client Management", slug="client-management-test", email="client-management@example.com",
        phone="8095553020", address_line1="Calle 30", city="Santo Domingo", state="DN",
        postal_code="10103", country="DO", timezone="America/Santo_Domingo", currency="DOP",
    )
    foreign_shop = Barbershop(
        name="Client Management Other", slug="client-management-other", email="client-management-other@example.com",
        phone="8095553021", address_line1="Calle 31", city="Santo Domingo", state="DN",
        postal_code="10104", country="DO", timezone="America/Santo_Domingo", currency="DOP",
    )
    test_db.add_all([shop, foreign_shop])
    test_db.flush()
    owner = User(
        email="client-management-owner@example.com", password_hash="unused", first_name="Owner",
        last_name="Management", role="barbershop_owner", is_active=True, barbershop_id=shop.id,
    )
    barber = User(
        email="client-management-barber@example.com", password_hash="unused", first_name="Barber",
        last_name="Management", role="barber", is_active=True, barbershop_id=shop.id,
    )
    customer = User(
        email="client-management-customer@example.com", password_hash="unused", first_name="Old",
        last_name="Name", phone="8095553022", role="client", is_active=True, barbershop_id=shop.id,
    )
    duplicate_candidate = User(
        email="client-management-duplicate@example.com", password_hash="unused", first_name="Second",
        last_name="Client", phone="8095553034", role="client", is_active=True, barbershop_id=shop.id,
    )
    foreign_customer = User(
        email="client-management-foreign@example.com", password_hash="unused", first_name="Foreign",
        last_name="Client", role="client", is_active=True, barbershop_id=foreign_shop.id,
    )
    test_db.add_all([owner, barber, customer, duplicate_candidate, foreign_customer])
    test_db.flush()
    appointment = Appointment(
        barbershop_id=shop.id, client_id=customer.id, barber_id=barber.id,
        scheduled_time=utc_now_naive() - timedelta(days=1), estimated_duration=30,
        service_type="Corte", service_price=2500, status="completed",
    )
    test_db.add(appointment)
    test_db.flush()
    test_db.add(Payment(
        barbershop_id=shop.id, appointment_id=appointment.id, barber_id=barber.id,
        amount_cents=2500, tip_cents=500, method="cash", currency="DOP",
        received_at=utc_now_naive() - timedelta(days=1), recorded_by_user_id=barber.id,
    ))
    test_db.commit()

    owner_headers = {"Authorization": f"Bearer {create_access_token({'sub': str(owner.id), 'role': owner.role})}"}
    barber_headers = {"Authorization": f"Bearer {create_access_token({'sub': str(barber.id), 'role': barber.role})}"}
    update = client.put(
        f"/api/v1/owner/clients/{customer.id}", headers=owner_headers,
        json={"first_name": "New", "last_name": "Name", "phone": "809-555-3033"},
    )
    assert update.status_code == 200
    assert update.json()["full_name"] == "New Name"
    assert update.json()["phone"] == "8095553033"
    duplicate_phone = client.put(
        f"/api/v1/owner/clients/{duplicate_candidate.id}", headers=owner_headers,
        json={"first_name": "Second", "last_name": "Client", "phone": "(809) 555-3033"},
    )
    assert duplicate_phone.status_code == 409
    assert client.put(
        f"/api/v1/owner/clients/{foreign_customer.id}", headers=owner_headers,
        json={"first_name": "Changed", "last_name": "Elsewhere", "phone": None},
    ).status_code == 404
    assert client.put(
        f"/api/v1/owner/clients/{customer.id}", headers=barber_headers,
        json={"first_name": "Changed", "last_name": "Name", "phone": None},
    ).status_code == 403

    deactivated = client.put(
        f"/api/v1/owner/clients/{customer.id}/status", headers=owner_headers,
        json={"is_active": False},
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False
    listing = client.get("/api/v1/owner/clients", headers=owner_headers)
    assert listing.json()["total"] == 2
    row = next(item for item in listing.json()["items"] if item["id"] == customer.id)
    assert row["is_active"] is False
    assert row["appointment_count"] == row["completed_count"] == 1
    assert row["total_paid_cents"] == 3000
    name_search = client.get(
        "/api/v1/owner/clients?search=New%20Name", headers=owner_headers,
    )
    assert name_search.status_code == 200
    assert name_search.json()["total"] == 1
    assert name_search.json()["items"][0]["id"] == customer.id
    phone_search = client.get(
        "/api/v1/owner/clients?search=3033", headers=owner_headers,
    )
    assert phone_search.json()["total"] == 1
    foreign_search = client.get(
        "/api/v1/owner/clients?search=Foreign", headers=owner_headers,
    )
    assert foreign_search.json()["total"] == 0
    history = client.get(
        f"/api/v1/owner/clients/{customer.id}/appointments", headers=owner_headers,
    )
    assert history.status_code == 200
    assert history.json()["total"] == 1
    appointment_history = history.json()["items"][0]
    assert appointment_history["service_type"] == "Corte"
    assert appointment_history["barber_name"] == "Barber Management"
    assert appointment_history["scheduled_time"].endswith("Z")
    assert appointment_history["payment"]["amount_cents"] == 2500
    assert appointment_history["payment"]["tip_cents"] == 500
    assert appointment_history["payment"]["currency"] == "DOP"
    assert appointment_history["payment"]["method"] == "cash"
    assert appointment_history["payment"]["received_at"].endswith("Z")
    assert client.get(
        f"/api/v1/owner/clients/{customer.id}/appointments?limit=0", headers=owner_headers,
    ).status_code == 422
    assert client.get(
        f"/api/v1/owner/clients/{foreign_customer.id}/appointments", headers=owner_headers,
    ).status_code == 404
    assert client.get(
        f"/api/v1/owner/clients/{customer.id}/appointments", headers=barber_headers,
    ).status_code == 403
    assert test_db.query(AuditLog).filter(
        AuditLog.action.in_(["client.profile_updated", "client.status_changed"]),
        AuditLog.entity_id == customer.id, AuditLog.barbershop_id == shop.id,
    ).count() == 2


def test_owner_can_manually_register_clients_with_tenant_limits(client: TestClient, test_db: Session):
    now = utc_now_naive()
    subscription = Subscription(
        plan="free", status="active", current_period_start=now - timedelta(days=1),
        current_period_end=now + timedelta(days=29), max_barbers=1,
        max_appointments_per_month=50, max_clients=1, auto_renew=False,
    )
    foreign_subscription = Subscription(
        plan="free", status="active", current_period_start=now - timedelta(days=1),
        current_period_end=now + timedelta(days=29), max_barbers=1,
        max_appointments_per_month=50, max_clients=1, auto_renew=False,
    )
    test_db.add_all([subscription, foreign_subscription])
    test_db.flush()
    shop = Barbershop(
        name="Manual Clients", slug="manual-clients-test", email="manual-clients@example.com",
        phone="8095553040", address_line1="Calle 40", city="Santo Domingo", state="DN",
        postal_code="10105", country="DO", timezone="America/Santo_Domingo", currency="DOP",
        subscription_id=subscription.id,
    )
    foreign_shop = Barbershop(
        name="Manual Clients Other", slug="manual-clients-other-test",
        email="manual-clients-other@example.com", phone="8095553041", address_line1="Calle 41",
        city="Santo Domingo", state="DN", postal_code="10106", country="DO",
        timezone="America/Santo_Domingo", currency="DOP", subscription_id=foreign_subscription.id,
    )
    test_db.add_all([shop, foreign_shop])
    test_db.flush()
    owner = User(
        email="manual-clients-owner@example.com", password_hash="unused", first_name="Owner",
        last_name="Clients", role="barbershop_owner", is_active=True, barbershop_id=shop.id,
    )
    barber = User(
        email="manual-clients-barber@example.com", password_hash="unused", first_name="Barber",
        last_name="Clients", role="barber", is_active=True, barbershop_id=shop.id,
    )
    foreign_owner = User(
        email="manual-clients-foreign-owner@example.com", password_hash="unused",
        first_name="Foreign", last_name="Owner", role="barbershop_owner", is_active=True,
        barbershop_id=foreign_shop.id,
    )
    test_db.add_all([owner, barber, foreign_owner])
    test_db.commit()

    owner_headers = {"Authorization": f"Bearer {create_access_token({'sub': str(owner.id)})}"}
    barber_headers = {"Authorization": f"Bearer {create_access_token({'sub': str(barber.id)})}"}
    foreign_headers = {"Authorization": f"Bearer {create_access_token({'sub': str(foreign_owner.id)})}"}
    payload = {"first_name": "  Ana ", "last_name": "  García ", "phone": "+1 (809) 555-3042"}

    created = client.post("/api/v1/owner/clients", headers=owner_headers, json=payload)
    assert created.status_code == 201
    assert created.json()["full_name"] == "Ana García"
    assert created.json()["phone"] == "18095553042"
    record = test_db.get(User, created.json()["id"])
    assert record.role == "client"
    assert record.barbershop_id == shop.id
    assert record.email.endswith("@client.invalid")
    audit = test_db.query(AuditLog).filter_by(
        action="client.created", entity_id=record.id, barbershop_id=shop.id,
    ).one()
    assert audit.actor_user_id == owner.id
    assert audit.details == {"phone_last4": "3042", "source": "owner_manual"}

    assert client.post("/api/v1/owner/clients", headers=owner_headers, json=payload).status_code == 409
    over_limit = client.post("/api/v1/owner/clients", headers=owner_headers, json={
        "first_name": "Second", "last_name": "Client", "phone": "8095553043",
    })
    assert over_limit.status_code == 402
    assert client.post(
        "/api/v1/owner/clients", headers=barber_headers,
        json={"first_name": "Other", "last_name": "Client", "phone": "8095553044"},
    ).status_code == 403
    foreign_created = client.post(
        "/api/v1/owner/clients", headers=foreign_headers,
        json={"first_name": "Tenant", "last_name": "Client", "phone": "8095553044"},
    )
    assert foreign_created.status_code == 201
    assert test_db.get(User, foreign_created.json()["id"]).barbershop_id == foreign_shop.id
