"""MySQL integration coverage for transparent tenant-scoped demand forecasting."""

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.ai.demand_forecast import DemandForecastService
from app.core.security import create_access_token
from app.models import Appointment, Barbershop, User


def _shop(slug: str) -> Barbershop:
    return Barbershop(
        name=slug, slug=slug, email=f"{slug}@example.com", phone="8095554000",
        address_line1="Calle 1", city="Santo Domingo", state="DN", postal_code="10101",
        country="DO", timezone="America/Santo_Domingo", currency="DOP",
        opening_time=time(9), closing_time=time(18),
    )


def _user(email: str, role: str, shop_id: int) -> User:
    return User(
        email=email, password_hash="unused", first_name="Forecast", last_name=role,
        role=role, is_active=True, barbershop_id=shop_id,
    )


def _local_appointment_utc(day, hour: int) -> datetime:
    return datetime.combine(day, time(hour), tzinfo=ZoneInfo("America/Santo_Domingo")).astimezone(
        timezone.utc
    ).replace(tzinfo=None)


def test_forecast_uses_local_weekday_history_and_only_own_tenant(test_db: Session):
    shop = _shop("forecast-main")
    other_shop = _shop("forecast-other")
    test_db.add_all([shop, other_shop])
    test_db.flush()
    barber = _user("forecast-barber@example.com", "barber", shop.id)
    client = _user("forecast-client@example.com", "client", shop.id)
    other_barber = _user("forecast-other-barber@example.com", "barber", other_shop.id)
    other_client = _user("forecast-other-client@example.com", "client", other_shop.id)
    test_db.add_all([barber, client, other_barber, other_client])
    test_db.flush()

    as_of = datetime(2026, 11, 19, 16, tzinfo=timezone.utc)
    today = as_of.astimezone(timezone(timedelta(hours=-4))).date()
    history_start = today - timedelta(days=DemandForecastService.HISTORY_DAYS)
    # Repeated Friday services at 15:00 create a deterministic historical baseline.
    first_friday = history_start + timedelta(days=(4 - history_start.weekday()) % 7)
    for week in range(12):
        service_date = first_friday + timedelta(days=week * 7)
        test_db.add(Appointment(
            barbershop_id=shop.id, client_id=client.id, barber_id=barber.id,
            scheduled_time=_local_appointment_utc(service_date, 15), estimated_duration=30,
            service_type="cut", service_price=2500, status="completed",
        ))
    # A different tenant's history must never influence this forecast.
    test_db.add(Appointment(
        barbershop_id=other_shop.id, client_id=other_client.id, barber_id=other_barber.id,
        scheduled_time=_local_appointment_utc(first_friday, 15), estimated_duration=30,
        service_type="cut", service_price=2500, status="completed",
    ))
    # Tomorrow is Friday; an existing reservation at 16:00 is included in the projection.
    tomorrow = today + timedelta(days=1)
    test_db.add(Appointment(
        barbershop_id=shop.id, client_id=client.id, barber_id=barber.id,
        scheduled_time=_local_appointment_utc(tomorrow, 16), estimated_duration=30,
        service_type="cut", service_price=2500, status="confirmed",
    ))
    test_db.flush()

    result = DemandForecastService.forecast(test_db, shop.id, as_of=as_of)
    friday = result["forecast"][0]
    hourly = {item["hour"]: item for item in friday["peak_hours"]}

    assert result["method"] == "weekday_hour_historical_average"
    assert result["completed_services_in_history"] == 12
    assert result["sufficient_history"] is True
    assert friday["date"] == tomorrow.isoformat()
    assert friday["known_bookings"] == 1
    assert hourly["15:00"]["historical_average"] == 1.0
    assert hourly["16:00"]["known_bookings"] == 1
    assert friday["expected_appointments"] == 2.0


def test_forecast_endpoint_is_owner_only_and_tenant_scoped(client: TestClient, test_db: Session):
    shop = _shop("forecast-api")
    other_shop = _shop("forecast-api-other")
    test_db.add_all([shop, other_shop])
    test_db.flush()
    owner = _user("forecast-owner@example.com", "barbershop_owner", shop.id)
    barber = _user("forecast-api-barber@example.com", "barber", shop.id)
    other_owner = _user("forecast-other-owner@example.com", "barbershop_owner", other_shop.id)
    test_db.add_all([owner, barber, other_owner])
    test_db.commit()

    def headers(user: User):
        token = create_access_token({"sub": str(user.id), "role": user.role})
        return {"Authorization": f"Bearer {token}"}

    allowed = client.get("/api/v1/analytics/demand-forecast", headers=headers(owner))
    assert allowed.status_code == 200
    assert allowed.json()["completed_services_in_history"] == 0
    assert len(allowed.json()["forecast"]) == 7

    forbidden = client.get("/api/v1/analytics/demand-forecast", headers=headers(barber))
    assert forbidden.status_code == 403

    other_tenant = client.get("/api/v1/analytics/demand-forecast", headers=headers(other_owner))
    assert other_tenant.status_code == 200
    assert other_tenant.json()["completed_services_in_history"] == 0
