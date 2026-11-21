"""Tenant and role integration coverage for performance endpoints (MySQL only)."""

from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models import Appointment, Barbershop, User
from app.utils.datetime import utc_now_naive


def _make_user(email, role, shop_id):
    return User(email=email, password_hash="unused", first_name="Test", last_name=role,
                role=role, is_active=True, barbershop_id=shop_id)


def test_performance_api_enforces_barber_and_tenant_access(client: TestClient, test_db: Session):
    shop_a = Barbershop(name="Rendimiento A", slug="performance-a", email="performance-a@example.com",
                        phone="8095552000", address_line1="A", city="Santo Domingo", state="DN",
                        postal_code="10101", country="DO", timezone="America/Santo_Domingo", currency="DOP")
    shop_b = Barbershop(name="Rendimiento B", slug="performance-b", email="performance-b@example.com",
                        phone="8095552001", address_line1="B", city="Santo Domingo", state="DN",
                        postal_code="10102", country="DO", timezone="America/Santo_Domingo", currency="DOP")
    test_db.add_all([shop_a, shop_b])
    test_db.flush()
    barber_a = _make_user("performance-barber-a@example.com", "barber", shop_a.id)
    barber_b = _make_user("performance-barber-b@example.com", "barber", shop_a.id)
    barber_other_tenant = _make_user("performance-barber-other@example.com", "barber", shop_b.id)
    owner_a = _make_user("performance-owner-a@example.com", "barbershop_owner", shop_a.id)
    test_db.add_all([barber_a, barber_b, barber_other_tenant, owner_a])
    test_db.commit()

    def auth(user):
        return {"Authorization": f"Bearer {create_access_token({'sub': str(user.id), 'role': user.role})}"}

    forbidden_same_tenant = client.get(
        f"/api/v1/performance/daily/{barber_b.id}?target_date={date.today().isoformat()}",
        headers=auth(barber_a),
    )
    assert forbidden_same_tenant.status_code == 403

    owner_cross_tenant = client.get(
        f"/api/v1/performance/daily/{barber_other_tenant.id}", headers=auth(owner_a)
    )
    assert owner_cross_tenant.status_code == 404

    owner_same_tenant = client.get(
        f"/api/v1/performance/daily/{barber_a.id}", headers=auth(owner_a)
    )
    assert owner_same_tenant.status_code == 200


def test_dashboard_time_metrics_use_measured_service_durations(client: TestClient, test_db: Session):
    shop = Barbershop(
        name="Panel Métricas", slug="dashboard-metrics", email="dashboard-metrics@example.com",
        phone="8095552002", address_line1="A", city="Santo Domingo", state="DN",
        postal_code="10103", country="DO", timezone="America/Santo_Domingo", currency="DOP",
    )
    test_db.add(shop)
    test_db.flush()
    barber = _make_user("dashboard-metrics-barber@example.com", "barber", shop.id)
    customer = _make_user("dashboard-metrics-client@example.com", "client", shop.id)
    test_db.add_all([barber, customer])
    test_db.flush()
    now = utc_now_naive()
    completed = Appointment(
        barbershop_id=shop.id, client_id=customer.id, barber_id=barber.id,
        scheduled_time=now, estimated_duration=30, actual_start_time=now - timedelta(minutes=20),
        actual_end_time=now, service_type="cut", service_price=2500, status="completed",
    )
    active = Appointment(
        barbershop_id=shop.id, client_id=customer.id, barber_id=barber.id,
        scheduled_time=now, estimated_duration=30, actual_start_time=now - timedelta(minutes=10),
        service_type="beard", service_price=1500, status="in_progress",
    )
    test_db.add_all([completed, active])
    test_db.commit()

    token = create_access_token({"sub": str(barber.id), "role": barber.role})
    response = client.get(
        "/api/v1/barber/dashboard",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["summary"]["efficiency_percent"] == 150
    assert sum(item["count"] for item in response.json()["weekly_counts"]) == 1
    active_item = next(item for item in response.json()["appointments"] if item["id"] == active.id)
    assert 30 <= active_item["progress_percent"] <= 36
