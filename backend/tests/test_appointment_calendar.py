"""Tenant-safe day navigation for the barber appointment calendar."""

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models import Appointment, Barbershop, Subscription, User
from app.utils.datetime import utc_now_naive


def test_barber_calendar_filters_selected_local_day_and_tenant(
    client: TestClient, test_db: Session
):
    now = utc_now_naive()
    subscription = Subscription(
        plan="free", status="active", current_period_start=now - timedelta(days=1),
        current_period_end=now + timedelta(days=30), auto_renew=False,
    )
    test_db.add(subscription)
    test_db.flush()
    shop = Barbershop(
        name="Agenda Uno", slug="calendar-shop-one", email="calendar-one@example.com",
        phone="8095550401", address_line1="Calle 1", city="Santo Domingo",
        state="DN", postal_code="10101", country="DO",
        timezone="America/Santo_Domingo", subscription_id=subscription.id,
    )
    other_shop = Barbershop(
        name="Agenda Dos", slug="calendar-shop-two", email="calendar-two@example.com",
        phone="8095550402", address_line1="Calle 2", city="Santiago",
        state="STI", postal_code="51000", country="DO",
        timezone="America/Santo_Domingo", subscription_id=subscription.id,
    )
    test_db.add_all([shop, other_shop])
    test_db.flush()

    barber = User(
        email="calendar-barber@example.com", password_hash="unused", first_name="Barbero",
        last_name="Uno", role="barber", is_active=True, barbershop_id=shop.id,
    )
    coworker = User(
        email="calendar-coworker@example.com", password_hash="unused", first_name="Barbero",
        last_name="Dos", role="barber", is_active=True, barbershop_id=shop.id,
    )
    client_one = User(
        email="calendar-client-one@example.com", password_hash="unused", first_name="Cliente",
        last_name="Uno", role="client", is_active=True, barbershop_id=shop.id,
    )
    other_barber = User(
        email="calendar-other-barber@example.com", password_hash="unused", first_name="Barbero",
        last_name="Otro", role="barber", is_active=True, barbershop_id=other_shop.id,
    )
    other_client = User(
        email="calendar-client-two@example.com", password_hash="unused", first_name="Cliente",
        last_name="Dos", role="client", is_active=True, barbershop_id=other_shop.id,
    )
    test_db.add_all([barber, coworker, client_one, other_barber, other_client])
    test_db.flush()

    target_date = datetime.now(ZoneInfo(shop.timezone)).date() + timedelta(days=2)
    target_time = datetime.combine(target_date, time(10), tzinfo=ZoneInfo(shop.timezone))
    appointment_time = target_time.astimezone(timezone.utc).replace(tzinfo=None)
    test_db.add_all([
        Appointment(
            barbershop_id=shop.id, client_id=client_one.id, barber_id=barber.id,
            scheduled_time=appointment_time, estimated_duration=30, service_type="Corte",
            service_price=2000, status="confirmed",
        ),
        Appointment(
            barbershop_id=shop.id, client_id=client_one.id, barber_id=coworker.id,
            scheduled_time=appointment_time + timedelta(hours=1), estimated_duration=30,
            service_type="Barba", service_price=1000, status="pending",
        ),
        Appointment(
            barbershop_id=other_shop.id, client_id=other_client.id, barber_id=other_barber.id,
            scheduled_time=appointment_time, estimated_duration=30, service_type="Privado",
            service_price=5000, status="confirmed",
        ),
        Appointment(
            barbershop_id=shop.id, client_id=client_one.id, barber_id=barber.id,
            scheduled_time=appointment_time + timedelta(days=5), estimated_duration=30,
            service_type="Corte futuro", service_price=2000, status="pending",
        ),
    ])
    test_db.commit()

    token = create_access_token({"sub": str(barber.id), "role": "barber"})
    response = client.get(
        f"/api/v1/barber/appointments?target_date={target_date.isoformat()}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["business_date"] == target_date.isoformat()
    assert payload["summary"]["total"] == 1
    assert [item["service_type"] for item in payload["appointments"]] == ["Corte"]
    assert payload["appointments"][0]["client_name"] == "Cliente Uno"
    assert payload["appointments"][0]["client_id"] == client_one.id

    weekly = client.get(
        f"/api/v1/barber/appointments/calendar?view=week&anchor_date={target_date.isoformat()}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert weekly.status_code == 200
    week_payload = weekly.json()
    week_start = target_date - timedelta(days=target_date.weekday())
    second_date = target_date + timedelta(days=5)
    expected_week_count = 2 if week_start <= second_date < week_start + timedelta(days=7) else 1
    assert week_payload["summary"]["total"] == expected_week_count
    assert len(week_payload["days"]) == 7
    assert week_payload["days"][0]["date"] == week_start.isoformat()
    weekly_items = [item for day in week_payload["days"] for item in day["appointments"]]
    assert next(item for item in weekly_items if item["service_type"] == "Corte")["client_id"] == client_one.id

    monthly = client.get(
        f"/api/v1/barber/appointments/calendar?view=month&anchor_date={target_date.isoformat()}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert monthly.status_code == 200
    month_payload = monthly.json()
    expected_month_count = 2 if second_date.month == target_date.month else 1
    assert month_payload["summary"]["total"] == expected_month_count
    assert len(month_payload["days"]) in {28, 29, 30, 31}
    assert all(item["service_type"] != "Privado" for day in month_payload["days"] for item in day["appointments"])
