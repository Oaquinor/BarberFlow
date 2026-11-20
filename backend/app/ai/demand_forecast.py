"""Explainable demand forecast from a tenant's completed service history."""

from collections import Counter
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from app.models import Appointment, Barbershop
from app.utils.datetime import local_day_start_utc_naive


class DemandForecastService:
    """Project the next seven business days from 12 weeks of weekday/hour history."""

    HISTORY_DAYS = 84
    FORECAST_DAYS = 7

    @staticmethod
    def _utc_midnight(day: date, tz: ZoneInfo) -> datetime:
        return local_day_start_utc_naive(day, tz)

    @staticmethod
    def _confidence_from_weeks(active_weeks: int) -> str:
        if active_weeks >= 8:
            return "high"
        if active_weeks >= 4:
            return "medium"
        return "low"

    @classmethod
    def forecast(cls, db: Session, barbershop_id: int, as_of: datetime | None = None) -> dict:
        shop = db.query(Barbershop).filter(
            Barbershop.id == barbershop_id,
            Barbershop.is_deleted == False,
        ).first()
        if not shop:
            raise ValueError("Barbería no encontrada")
        try:
            business_tz = ZoneInfo(shop.timezone)
        except (ZoneInfoNotFoundError, TypeError) as exc:
            raise ValueError("Zona horaria de barbería inválida") from exc

        current_utc = as_of or datetime.now(timezone.utc)
        if current_utc.tzinfo is None:
            current_utc = current_utc.replace(tzinfo=timezone.utc)
        today = current_utc.astimezone(business_tz).date()
        history_start = today - timedelta(days=cls.HISTORY_DAYS)
        history_end = today
        history_start_utc = cls._utc_midnight(history_start, business_tz)
        history_end_utc = cls._utc_midnight(history_end, business_tz)

        historical_rows = db.query(Appointment.scheduled_time).filter(
            Appointment.barbershop_id == shop.id,
            Appointment.status == "completed",
            Appointment.scheduled_time >= history_start_utc,
            Appointment.scheduled_time < history_end_utc,
            Appointment.is_deleted == False,
        ).yield_per(1000)
        hourly_counts: Counter[tuple[date, int]] = Counter()
        for (scheduled_time,) in historical_rows:
            scheduled_utc = scheduled_time.replace(tzinfo=timezone.utc) if scheduled_time.tzinfo is None else scheduled_time.astimezone(timezone.utc)
            local_time = scheduled_utc.astimezone(business_tz)
            hourly_counts[(local_time.date(), local_time.hour)] += 1

        active_weeks_by_weekday: Counter[int] = Counter()
        active_week_keys: set[tuple[int, int]] = set()
        for day, _hour in hourly_counts:
            week_index = (day - history_start).days // 7
            active_week_keys.add((day.weekday(), week_index))
        for weekday, _week_index in active_week_keys:
            active_weeks_by_weekday[weekday] += 1

        known_rows = db.query(Appointment.scheduled_time).filter(
            Appointment.barbershop_id == shop.id,
            Appointment.status.in_(["pending", "confirmed", "in_progress"]),
            Appointment.scheduled_time >= cls._utc_midnight(today + timedelta(days=1), business_tz),
            Appointment.scheduled_time < cls._utc_midnight(today + timedelta(days=cls.FORECAST_DAYS + 1), business_tz),
            Appointment.is_deleted == False,
        ).yield_per(1000)
        known_counts: Counter[tuple[date, int]] = Counter()
        for (scheduled_time,) in known_rows:
            scheduled_utc = scheduled_time.replace(tzinfo=timezone.utc) if scheduled_time.tzinfo is None else scheduled_time.astimezone(timezone.utc)
            local_time = scheduled_utc.astimezone(business_tz)
            known_counts[(local_time.date(), local_time.hour)] += 1

        observed_hours = [hour for _, hour in hourly_counts]
        known_hours = [hour for _, hour in known_counts]
        if shop.opening_time and shop.closing_time and shop.opening_time < shop.closing_time:
            start_hour = shop.opening_time.hour
            end_hour = shop.closing_time.hour + (1 if shop.closing_time.minute else 0)
            hours = list(range(start_hour, min(24, end_hour)))
            hours_source = "business_hours"
        elif observed_hours:
            hours = list(range(min(observed_hours), max(observed_hours) + 1))
            hours_source = "observed_history"
        elif known_hours:
            hours = list(range(min(known_hours), max(known_hours) + 1))
            hours_source = "known_bookings"
        else:
            hours = []
            hours_source = "unavailable"

        sample_days_by_weekday = Counter(
            (history_start + timedelta(days=offset)).weekday()
            for offset in range((history_end - history_start).days)
        )
        weekday_hour_totals: Counter[tuple[int, int]] = Counter()
        for (day, hour), count in hourly_counts.items():
            weekday_hour_totals[(day.weekday(), hour)] += count

        forecast_days = []
        for offset in range(1, cls.FORECAST_DAYS + 1):
            forecast_date = today + timedelta(days=offset)
            same_weekday_samples = sample_days_by_weekday[forecast_date.weekday()]
            hourly = []
            for hour in hours:
                baseline = weekday_hour_totals[(forecast_date.weekday(), hour)] / same_weekday_samples if same_weekday_samples else 0.0
                known = known_counts[(forecast_date, hour)]
                hourly.append({
                    "hour": f"{hour:02d}:00",
                    "historical_average": round(baseline, 2),
                    "known_bookings": known,
                    "expected_appointments": round(max(baseline, float(known)), 2),
                    "sample_days": same_weekday_samples,
                    "active_weeks": active_weeks_by_weekday[forecast_date.weekday()],
                    "confidence": cls._confidence_from_weeks(active_weeks_by_weekday[forecast_date.weekday()]),
                })
            expected_total = round(sum(item["expected_appointments"] for item in hourly), 2)
            forecast_days.append({
                "date": forecast_date.isoformat(),
                "weekday": ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"][forecast_date.weekday()],
                "expected_appointments": expected_total,
                "known_bookings": sum(item["known_bookings"] for item in hourly),
                "active_weeks": active_weeks_by_weekday[forecast_date.weekday()],
                "confidence": cls._confidence_from_weeks(active_weeks_by_weekday[forecast_date.weekday()]),
                "peak_hours": [item for item in sorted(
                    hourly,
                    key=lambda item: (item["expected_appointments"], item["hour"]),
                    reverse=True,
                ) if item["expected_appointments"] > 0][:3],
            })

        history_count = sum(hourly_counts.values())
        active_history_weeks = len({week_index for _weekday, week_index in active_week_keys})
        sufficient_history = history_count >= 12 and active_history_weeks >= 4
        insights = []
        busiest = max(forecast_days, key=lambda item: item["expected_appointments"], default=None)
        if busiest and busiest["expected_appointments"] > 0 and sufficient_history:
            peak = busiest["peak_hours"][0] if busiest["peak_hours"] else None
            if peak:
                insights.append(
                    f"Mayor volumen estimado: {busiest['weekday']} {peak['hour']} "
                    f"({peak['expected_appointments']:.1f} citas por hora en promedio)."
                )
        if not sufficient_history:
            insights.append("Aún no hay suficiente historial de servicios completados para estimar patrones; se muestran las reservas ya confirmadas.")
        elif not insights:
            insights.append("El historial no muestra un periodo de demanda claramente más alto para los próximos siete días.")

        return {
            "method": "weekday_hour_historical_average",
            "history_start": history_start.isoformat(),
            "history_end": (history_end - timedelta(days=1)).isoformat(),
            "history_days": cls.HISTORY_DAYS,
            "completed_services_in_history": history_count,
            "hours_source": hours_source,
            "sufficient_history": sufficient_history,
            "forecast": forecast_days,
            "insights": insights,
        }
