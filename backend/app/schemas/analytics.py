"""Response contracts for business analytics and forecasts."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict


class HourlyDemandForecast(BaseModel):
    hour: str
    historical_average: float
    known_bookings: int
    expected_appointments: float
    sample_days: int
    active_weeks: int
    confidence: Literal["low", "medium", "high"]


class DemandDayForecast(BaseModel):
    date: date
    weekday: str
    expected_appointments: float
    known_bookings: int
    active_weeks: int
    confidence: Literal["low", "medium", "high"]
    peak_hours: list[HourlyDemandForecast]


class DemandForecastResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    method: str
    history_start: date
    history_end: date
    history_days: int
    completed_services_in_history: int
    hours_source: Literal["business_hours", "observed_history", "known_bookings", "unavailable"]
    sufficient_history: bool
    forecast: list[DemandDayForecast]
    insights: list[str]


class FinancialReportRow(BaseModel):
    key: str
    label: str
    payment_count: int
    service_revenue_cents: int
    retail_revenue_cents: int
    retail_sale_count: int
    tip_cents: int
    gross_cents: int


class FinancialReportResponse(BaseModel):
    start_date: date
    end_date: date
    timezone: str
    currency: str
    payment_count: int
    service_payment_count: int
    service_revenue_cents: int
    retail_revenue_cents: int
    retail_sale_count: int
    tip_cents: int
    gross_cents: int
    by_day: list[FinancialReportRow]
    by_method: list[FinancialReportRow]
    by_barber: list[FinancialReportRow]
