"""Shared rules for client-initiated appointment changes."""

from datetime import datetime, timedelta

from fastapi import HTTPException


def enforce_public_change_window(shop, scheduled_time: datetime, now: datetime) -> None:
    """Apply the tenant's cancellation/reschedule lead time; zero keeps changes unrestricted."""
    hours = max(0, int(getattr(shop, "cancellation_window_hours", 0) or 0))
    if hours and scheduled_time - now < timedelta(hours=hours):
        raise HTTPException(
            status_code=409,
            detail=(
                "Solo puedes cancelar o reprogramar esta cita con al menos "
                f"{hours} horas de anticipación. Contacta a la barbería si necesitas ayuda."
            ),
        )
