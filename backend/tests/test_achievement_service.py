from datetime import date

from sqlalchemy.orm import Session

from app.models import Achievement, BarberPerformance, Barbershop, User
from app.services.achievement_service import AchievementService


def test_daily_achievement_does_not_combine_services_from_different_dates(test_db: Session):
    shop = Barbershop(
        name="Logros de prueba", slug="achievement-test", email="achievement@example.com",
        phone="8095551000", address_line1="Calle 10", city="Santo Domingo",
        state="DN", postal_code="10101", country="DO", timezone="America/Santo_Domingo",
        currency="DOP",
    )
    test_db.add(shop)
    test_db.flush()
    barber = User(
        email="achievement-barber@example.com", password_hash="unused", first_name="Luis",
        last_name="Prueba", role="barber", is_active=True, barbershop_id=shop.id,
    )
    achievement = Achievement(
        code="TEST_DAILY_TEN", name="Diez en un día", description="Completa 10 en un día",
        icon="★", category="productivity", requirement_type="daily_appointments",
        requirement_value=10, points=10, rarity="common", is_active=True,
    )
    test_db.add_all([barber, achievement])
    test_db.flush()
    target_day = date(2026, 11, 19)
    test_db.add_all([
        BarberPerformance(
            barbershop_id=shop.id, barber_id=barber.id, date=date(2026, 11, 18),
            appointments_completed=5,
        ),
        BarberPerformance(
            barbershop_id=shop.id, barber_id=barber.id, date=target_day,
            appointments_completed=5,
        ),
    ])
    test_db.flush()

    context = {"business_date": target_day.isoformat()}
    earned = AchievementService.check_and_award_achievements(
        test_db, barber.id, shop.id, "appointment_completed", context, commit=False,
    )
    assert earned == []

    current_day = test_db.query(BarberPerformance).filter_by(
        barbershop_id=shop.id, barber_id=barber.id, date=target_day,
    ).one()
    current_day.appointments_completed = 10
    earned = AchievementService.check_and_award_achievements(
        test_db, barber.id, shop.id, "appointment_completed", context, commit=False,
    )
    assert [item.achievement_id for item in earned] == [achievement.id]
