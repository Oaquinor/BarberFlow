"""Unit tests that do not require a running database."""

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.v1.endpoints.onboarding import _get_tenant_id
from app.api.deps import get_current_user as get_api_current_user
from app.api.v1.endpoints.platform import (
    _business_date_for_appointment,
    _email_html_lines,
    _local_day_bounds,
    _to_utc_naive,
    _utc_aware,
)
from app.api.v1.endpoints import platform as platform_module
from app.core.exceptions import InvalidTokenError
from app.core.security import (
    create_access_token, create_refresh_token, get_user_id_from_token,
    hash_password, verify_token,
)
from app.services.affiliate_service import AffiliateService
from app.services.notification_service import NotificationService
from app.services.onboarding_service import OnboardingService
from app.services.performance_service import PerformanceService
from app.main import app
from app.schemas.onboarding import OnboardingComplete
from app.schemas.auth import PasswordChangeRequest, PasswordResetConfirm, RegisterRequest
from app.schemas.platform import BarberCreateSlotsRequest, PublicCreateAppointmentRequest, TenantRegistrationRequest


def test_onboarding_requires_authentication():
    response = TestClient(app).get("/api/v1/onboarding/profile")
    assert response.status_code == 401


def test_password_hash_uses_explicit_twelve_round_bcrypt_cost():
    assert hash_password("StrongPassword123").split("$")[2] == "12"


def test_smtp_senders_skip_delivery_when_verified_from_address_is_missing(monkeypatch):
    import app.services.notification_service as notification_module

    for settings in (platform_module.settings, notification_module.settings):
        monkeypatch.setattr(settings, "SMTP_HOST", "smtp.example.test")
        monkeypatch.setattr(settings, "SMTP_USER", "user")
        monkeypatch.setattr(settings, "SMTP_PASSWORD", "secret")
        monkeypatch.setattr(settings, "EMAIL_FROM", " ")

    assert platform_module._send_email("client@example.test", "Subject", "Body") is False
    assert NotificationService(None)._send_email("client@example.test", "Subject", "Body") is False


def test_transactional_email_lines_escape_untrusted_content():
    body = _email_html_lines(["<script>alert(1)</script>", "Cliente & servicio"])
    assert "<script>" not in body
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in body
    assert "Cliente &amp; servicio" in body


def test_performance_and_achievement_apis_are_mounted():
    paths = app.openapi()["paths"]
    assert "/api/v1/performance/daily/{barber_id}" in paths
    assert "/api/v1/performance/weekly/{barber_id}" in paths
    assert "/api/v1/performance/monthly/{barber_id}" in paths
    assert "/api/v1/achievements/" in paths


def test_tenant_is_derived_from_user_and_rejects_override():
    owner = SimpleNamespace(role="barbershop_owner", barbershop_id=12)
    assert _get_tenant_id(owner) == 12
    with pytest.raises(HTTPException) as error:
        _get_tenant_id(owner, requested_id=13)
    assert error.value.status_code == 403


def test_super_admin_must_select_tenant_explicitly():
    admin = SimpleNamespace(role="super_admin", barbershop_id=None)
    with pytest.raises(HTTPException) as error:
        _get_tenant_id(admin)
    assert error.value.status_code == 400
    assert _get_tenant_id(admin, requested_id=12) == 12


def test_new_passwords_use_the_same_twelve_character_policy():
    strong_password = "StrongPassword123"
    assert RegisterRequest(
        email="owner@example.com", password=strong_password,
        first_name="Owner", last_name="Test", phone="8095551234",
    ).password == strong_password
    assert PasswordChangeRequest(
        current_password="CurrentPassword123", new_password=strong_password,
    ).new_password == strong_password
    assert PasswordResetConfirm(
        token="x" * 43, new_password=strong_password,
    ).new_password == strong_password

    for schema, data in (
        (RegisterRequest, {
            "email": "owner@example.com", "password": "Strong123",
            "first_name": "Owner", "last_name": "Test", "phone": "8095551234",
        }),
        (PasswordChangeRequest, {
            "current_password": "CurrentPassword123", "new_password": "Strong123",
        }),
        (PasswordResetConfirm, {"token": "x" * 43, "new_password": "Strong123"}),
    ):
        with pytest.raises(ValueError):
            schema(**data)


def test_api_and_security_packages_share_the_same_auth_dependency():
    from app.core.security.dependencies import get_current_user as shared_current_user

    assert get_api_current_user is shared_current_user


def test_jwt_subject_must_be_a_decimal_user_id():
    token = create_access_token({"sub": "42"})
    assert get_user_id_from_token(token) == 42
    invalid_token = create_access_token({"sub": "not-an-id"})
    with pytest.raises(InvalidTokenError):
        get_user_id_from_token(invalid_token)


def test_refresh_tokens_have_a_unique_session_identifier():
    first = verify_token(create_refresh_token({"sub": "42"}), token_type="refresh")
    second = verify_token(create_refresh_token({"sub": "42"}), token_type="refresh")
    assert first["jti"]
    assert first["jti"] != second["jti"]


def test_complete_onboarding_validates_business_hours_and_fields():
    values = {
        "barbershop_name": "Barbería Centro",
        "primary_color": "#112233",
        "secondary_color": "#445566",
        "style": "classic",
        "primary_goal": "organization",
        "team_size": 4,
        "avg_service_duration": 30,
        "opening_time": "09:00",
        "closing_time": "18:00",
        "personality": "friendly",
    }
    OnboardingComplete(**values)
    with pytest.raises(ValueError):
        OnboardingComplete(**{**values, "closing_time": "08:00"})
    with pytest.raises(ValueError):
        OnboardingComplete(**{**values, "team_size": 0})


def test_tenant_registration_validates_password_timezone_and_currency():
    values = {
        "owner_email": "owner@example.com",
        "owner_password": "SecurePassword123",
        "owner_first_name": "Ana",
        "owner_last_name": "García",
        "owner_phone": "8095551234",
        "barbershop_name": "KingFlow Centro",
        "barbershop_email": "info@example.com",
        "barbershop_phone": "8095551234",
        "address_line1": "Calle Principal 12",
        "city": "Santo Domingo",
        "state": "Distrito Nacional",
        "postal_code": "10101",
        "country": "República Dominicana",
        "timezone": "America/Santo_Domingo",
        "currency": "DOP",
    }
    assert TenantRegistrationRequest(**values).currency == "DOP"
    with pytest.raises(ValueError):
        TenantRegistrationRequest(**{**values, "timezone": "Mars/Olympus"})
    with pytest.raises(ValueError):
        TenantRegistrationRequest(**{**values, "currency": "peso"})
    with pytest.raises(ValueError):
        TenantRegistrationRequest(**{**values, "owner_password": "password123456"})


def test_booking_requests_reject_invalid_dates_and_oversized_notes():
    with pytest.raises(ValueError):
        BarberCreateSlotsRequest(date="2026-02-30", start_time="09:00", end_time="10:00")
    with pytest.raises(ValueError):
        BarberCreateSlotsRequest(date="2026-02-28", start_time="24:00", end_time="25:00")
    with pytest.raises(ValueError):
        PublicCreateAppointmentRequest(
            client_name="Ana Prueba", phone="8095551234", service_id=1,
            scheduled_time=datetime(2026, 11, 20, 13, 0), notes="x" * 1001,
        )
    with pytest.raises(ValueError):
        PublicCreateAppointmentRequest(
            client_name="Ana Prueba", phone="8095551234", service_id=1,
            scheduled_time=datetime(2026, 11, 20, 13, 0),
            booking_answers={"x" * 121: "Respuesta"},
        )


def test_business_timezone_converts_local_slots_to_utc():
    shop = SimpleNamespace(timezone="America/Santo_Domingo")
    local = datetime(2026, 11, 19, 9, 0)
    assert _to_utc_naive(local, shop) == datetime(2026, 11, 19, 13, 0)
    assert _utc_aware(local).isoformat() == "2026-11-19T09:00:00+00:00"


def test_dashboard_business_day_uses_shop_timezone():
    shop = SimpleNamespace(timezone="America/Santo_Domingo")
    now = datetime(2026, 11, 19, 2, 0)
    day_start, day_end, yesterday_start, week_start = _local_day_bounds(now, shop)
    assert day_start == datetime(2026, 11, 18, 4, 0)
    assert day_end - day_start == timedelta(days=1)
    assert day_start - yesterday_start == timedelta(days=1)
    assert day_start - week_start == timedelta(days=6)


def test_appointment_metrics_use_the_business_calendar_date():
    shop = SimpleNamespace(timezone="America/Santo_Domingo")
    appointment = SimpleNamespace(scheduled_time=datetime(2026, 11, 19, 2, 0))
    assert _business_date_for_appointment(appointment, shop).isoformat() == "2026-11-18"


def test_time_efficiency_uses_only_completed_services_with_real_timings():
    appointments = [
        SimpleNamespace(estimated_duration=30, actual_duration=20),
        SimpleNamespace(estimated_duration=60, actual_duration=None),
        SimpleNamespace(estimated_duration=45, actual_duration=0),
    ]
    assert PerformanceService.time_efficiency(appointments) == 150
    assert PerformanceService.time_efficiency(appointments[1:]) == 0


def test_onboarding_insights_are_based_on_real_appointment_counts():
    no_appointments = OnboardingService._message_for_appointment_counts({})
    assert "Aún no hay citas" in no_appointments.message
    assert "100%" not in no_appointments.message

    cancellation_insight = OnboardingService._message_for_appointment_counts(
        {"cancelled": 3, "completed": 7}
    )
    assert cancellation_insight.type == "warning"
    assert "3 de 10" in cancellation_insight.message

    completed_insight = OnboardingService._message_for_appointment_counts(
        {"completed": 4, "pending": 2}
    )
    assert "4 de 6" in completed_insight.message
    assert "+8%" not in completed_insight.message


def test_affiliate_commission_refuses_placeholder_or_invalid_payment_amount():
    with pytest.raises(ValueError):
        AffiliateService.calculate_commission(
            None, 1, 1, datetime(2026, 1, 1), datetime(2026, 2, 1), 0
        )
    with pytest.raises(ValueError):
        AffiliateService.create_affiliate(
            None, "A", "B", "affiliate@example.com", commission_rate=1.5
        )


def test_sms_never_reports_fake_delivery_without_a_provider():
    notifications = NotificationService(None)
    assert notifications._send_sms("8095551234", "test") is False


def test_email_templates_escape_user_controlled_html():
    notifications = NotificationService(None)
    html = notifications._get_confirmation_email_template(
        '<img src=x onerror="alert(1)">', "Barbero", "Tienda", datetime(2026, 1, 1),
        "<script>alert(1)</script>", 30, "<b>Dirección</b>", "8095551234",
    )
    assert "<img src=x" not in html
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_whatsapp_never_sends_without_a_configured_service_token(monkeypatch):
    import app.services.notification_service as notification_module

    monkeypatch.setattr(notification_module.settings, "WHATSAPP_API_TOKEN", "")
    monkeypatch.setattr(
        notification_module.urlrequest,
        "urlopen",
        lambda *args, **kwargs: pytest.fail("Unauthenticated WhatsApp request was attempted"),
    )
    assert NotificationService(None)._send_whatsapp("8095551234", "test") is False


def test_whatsapp_delivery_uses_the_configured_bearer_token(monkeypatch):
    import app.services.notification_service as notification_module

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return b'{"success": true}'

    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr(notification_module.settings, "WHATSAPP_API_TOKEN", "unit-test-secret")
    monkeypatch.setattr(notification_module.urlrequest, "urlopen", fake_urlopen)
    assert NotificationService(None)._send_whatsapp("8095551234", "test") is True
    assert captured["request"].get_header("Authorization") == "Bearer unit-test-secret"
