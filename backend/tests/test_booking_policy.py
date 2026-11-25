from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException

from app.models.barbershop import Barbershop
from app.schemas.onboarding import BusinessSettingsUpdate
from app.services.booking_policy import enforce_public_change_window


def test_tenant_booking_change_window_defaults_to_unrestricted():
    shop = Barbershop(cancellation_window_hours=0)
    enforce_public_change_window(shop, datetime(2030, 1, 1, 12), datetime(2030, 1, 1, 11, 59))


def test_booking_change_window_accepts_boundary_and_rejects_too_late_changes():
    shop = Barbershop(cancellation_window_hours=4)
    now = datetime(2030, 1, 1, 12)
    enforce_public_change_window(shop, now + timedelta(hours=4), now)

    with pytest.raises(HTTPException) as error:
        enforce_public_change_window(shop, now + timedelta(hours=3, minutes=59), now)

    assert error.value.status_code == 409
    assert "4 horas" in error.value.detail


def test_business_settings_accept_cancellation_window_from_zero_to_seven_days():
    base = {
        "name": "Barbería de prueba", "opening_time": "09:00", "closing_time": "18:00",
        "timezone": "America/Santo_Domingo", "primary_color": "#b98752", "secondary_color": "#5a4635",
    }
    assert BusinessSettingsUpdate(**base, cancellation_window_hours=0).cancellation_window_hours == 0
    assert BusinessSettingsUpdate(**base, cancellation_window_hours=168).cancellation_window_hours == 168
    with pytest.raises(ValueError):
        BusinessSettingsUpdate(**base, cancellation_window_hours=169)
    with pytest.raises(ValueError):
        BusinessSettingsUpdate(**base, cancellation_window_hours=-1)


def test_style_passport_retention_requires_an_explicit_supported_choice():
    base = {
        "name": "Barbería de prueba", "opening_time": "09:00", "closing_time": "18:00",
        "timezone": "America/Santo_Domingo", "primary_color": "#b98752", "secondary_color": "#5a4635",
    }
    assert BusinessSettingsUpdate(**base).style_passport_retention_days is None
    assert BusinessSettingsUpdate(**base, style_passport_retention_days=365).style_passport_retention_days == 365
    with pytest.raises(ValueError):
        BusinessSettingsUpdate(**base, style_passport_retention_days=100)
