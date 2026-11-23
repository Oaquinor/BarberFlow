"""MySQL integration coverage for appointment status and performance consistency."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models import Appointment, AuditLog, Barbershop, BarberPerformance, User
from app.services.performance_service import PerformanceService
from app.utils.datetime import utc_now_naive


@pytest.mark.parametrize(
    ("new_status", "initial_status", "scheduled_offset"),
    [
        ("cancelled", "pending", timedelta(hours=2)),
        ("no_show", "confirmed", -timedelta(hours=2)),
    ],
)
def test_status_rolls_back_when_performance_cannot_be_updated(
    client: TestClient,
    test_db: Session,
    monkeypatch,
    new_status: str,
    initial_status: str,
    scheduled_offset: timedelta,
):
    shop = Barbershop(
        name="Estado atómico", slug=f"status-atomic-{new_status}",
        email=f"status-atomic-{new_status}@example.com", phone="8095550701",
        address_line1="Calle 7", city="Santo Domingo", state="DN",
        postal_code="10107", country="DO", timezone="America/Santo_Domingo",
    )
    test_db.add(shop)
    test_db.flush()
    barber = User(
        email=f"status-atomic-{new_status}-barber@example.com", password_hash="unused",
        first_name="Barbero", last_name="Prueba", role="barber", is_active=True,
        barbershop_id=shop.id,
    )
    customer = User(
        email=f"status-atomic-{new_status}-client@example.com", password_hash="unused",
        first_name="Cliente", last_name="Prueba", role="client", is_active=True,
        barbershop_id=shop.id,
    )
    test_db.add_all([barber, customer])
    test_db.flush()
    appointment = Appointment(
        barbershop_id=shop.id, client_id=customer.id, barber_id=barber.id,
        scheduled_time=utc_now_naive() + scheduled_offset, estimated_duration=30,
        service_type="Corte", service_price=18000, status=initial_status,
    )
    test_db.add(appointment)
    test_db.commit()

    def fail_performance_update(**_kwargs):
        raise RuntimeError("performance storage unavailable")

    monkeypatch.setattr(PerformanceService, "calculate_daily_performance", fail_performance_update)
    token = create_access_token({"sub": str(barber.id), "role": barber.role})
    response = client.put(
        f"/api/v1/barber/appointments/{appointment.id}/status",
        headers={"Authorization": f"Bearer {token}"},
        json={"status": new_status},
    )

    assert response.status_code == 503
    test_db.expire_all()
    assert test_db.get(Appointment, appointment.id).status == initial_status
    assert test_db.query(AuditLog).filter(
        AuditLog.action == f"appointment.{new_status}",
        AuditLog.entity_id == appointment.id,
        AuditLog.barbershop_id == shop.id,
    ).count() == 0
    assert test_db.query(BarberPerformance).filter(
        BarberPerformance.barbershop_id == shop.id,
        BarberPerformance.barber_id == barber.id,
    ).count() == 0
