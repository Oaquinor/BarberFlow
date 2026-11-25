"""Fast validation tests for public waitlist requests."""

import pytest
from pydantic import ValidationError
from uuid import uuid4

from app.schemas.booking_waitlist import PublicWaitlistRequest, WaitlistStatusUpdate


def test_waitlist_normalizes_public_contact_details():
    request = PublicWaitlistRequest(
        client_name="  Ana Cliente  ",
        phone=" 809 555 1234 ",
        service_id=8,
        idempotency_key=uuid4(),
        notes="  Tarde, si es posible  ",
    )
    assert request.client_name == "Ana Cliente"
    assert request.phone == "809 555 1234"
    assert request.notes == "Tarde, si es posible"


def test_waitlist_rejects_reversed_dates_and_short_phone():
    with pytest.raises(ValidationError):
        PublicWaitlistRequest(
            client_name="Ana Cliente",
            phone="8095551234",
            service_id=8,
            idempotency_key=uuid4(),
            preferred_date_start="2026-12-10",
            preferred_date_end="2026-12-09",
        )
    with pytest.raises(ValidationError):
        PublicWaitlistRequest(
            client_name="Ana Cliente", phone="123", service_id=8, idempotency_key=uuid4()
        )


def test_waitlist_status_has_only_supported_values():
    assert WaitlistStatusUpdate(status="contacted").status == "contacted"
    with pytest.raises(ValidationError):
        WaitlistStatusUpdate(status="booked")
