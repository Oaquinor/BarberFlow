"""MySQL concurrency coverage for daily barber performance aggregation."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time
from threading import Barrier
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models import Appointment, Barbershop, BarberPerformance, User
from app.services.performance_service import PerformanceService
from app.utils.datetime import utc_now_naive


def test_concurrent_performance_recalculations_keep_one_complete_daily_row(mysql_test_engine):
    suffix = uuid4().hex
    target_date = utc_now_naive().date()
    with Session(mysql_test_engine) as db:
        shop = Barbershop(
            name="Performance concurrency",
            slug=f"performance-race-{suffix}",
            email=f"performance-race-shop-{suffix}@example.com",
            phone="8095555200",
            address_line1="Calle 52",
            city="Santo Domingo",
            state="DN",
            postal_code="10106",
            country="DO",
            timezone="America/Santo_Domingo",
            currency="DOP",
        )
        db.add(shop)
        db.flush()
        barber = User(
            email=f"performance-race-barber-{suffix}@example.com",
            password_hash="unused",
            first_name="Barbero",
            last_name="Concurrency",
            role="barber",
            is_active=True,
            barbershop_id=shop.id,
        )
        customer = User(
            email=f"performance-race-client-{suffix}@example.com",
            password_hash="unused",
            first_name="Cliente",
            last_name="Concurrency",
            role="client",
            is_active=True,
            barbershop_id=shop.id,
        )
        db.add_all([barber, customer])
        db.flush()
        appointments = [
            Appointment(
                barbershop_id=shop.id,
                client_id=customer.id,
                barber_id=barber.id,
                scheduled_time=datetime.combine(target_date, time(13 + index, 0)),
                estimated_duration=30,
                actual_start_time=datetime.combine(target_date, time(13 + index, 0)),
                actual_end_time=datetime.combine(target_date, time(13 + index, 30)),
                service_type="Corte",
                service_price=1800,
                status="completed",
            )
            for index in range(2)
        ]
        db.add_all(appointments)
        db.commit()
        shop_id, barber_id = shop.id, barber.id

    start = Barrier(2)

    def recalculate():
        with Session(mysql_test_engine) as db:
            start.wait(timeout=10)
            row = PerformanceService.calculate_daily_performance(
                db,
                shop_id,
                barber_id,
                target_date,
            )
            return row.id

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            row_ids = list(pool.map(lambda _index: recalculate(), range(2)))

        assert row_ids[0] == row_ids[1]
        with Session(mysql_test_engine) as db:
            rows = (
                db.query(BarberPerformance)
                .filter(
                    BarberPerformance.barbershop_id == shop_id,
                    BarberPerformance.barber_id == barber_id,
                    BarberPerformance.date == target_date,
                )
                .all()
            )
            assert len(rows) == 1
            assert rows[0].appointments_completed == 2
            assert rows[0].total_service_time_minutes == 60
    finally:
        with Session(mysql_test_engine) as db:
            db.query(BarberPerformance).filter(
                BarberPerformance.barbershop_id == shop_id,
                BarberPerformance.barber_id == barber_id,
            ).delete(synchronize_session=False)
            db.query(Appointment).filter(
                Appointment.barbershop_id == shop_id,
            ).delete(synchronize_session=False)
            db.query(User).filter(User.barbershop_id == shop_id).delete(synchronize_session=False)
            db.query(Barbershop).filter(Barbershop.id == shop_id).delete(synchronize_session=False)
            db.commit()
