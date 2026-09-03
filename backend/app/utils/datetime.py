"""
Utility helpers.

Common utility functions used across the application.
"""

from datetime import datetime, date
from typing import Optional


def format_datetime(dt: datetime, format: str = "%Y-%m-%d %H:%M:%S") -> str:
    """
    Format datetime to string.

    Args:
        dt: Datetime object
        format: Format string

    Returns:
        Formatted datetime string
    """
    return dt.strftime(format)


def parse_datetime(dt_string: str, format: str = "%Y-%m-%d %H:%M:%S") -> Optional[datetime]:
    """
    Parse string to datetime.

    Args:
        dt_string: Datetime string
        format: Format string

    Returns:
        Datetime object or None if parsing fails
    """
    try:
        return datetime.strptime(dt_string, format)
    except ValueError:
        return None


def get_date_range(start_date: date, end_date: date) -> list[date]:
    """
    Get list of dates between start and end.

    Args:
        start_date: Start date
        end_date: End date

    Returns:
        List of dates
    """
    dates = []
    current_date = start_date

    while current_date <= end_date:
        dates.append(current_date)
        current_date += timedelta(days=1)

    return dates


def is_business_hours(dt: datetime, opening: str = "09:00", closing: str = "18:00") -> bool:
    """
    Check if datetime is within business hours.

    Args:
        dt: Datetime to check
        opening: Opening time (HH:MM)
        closing: Closing time (HH:MM)

    Returns:
        True if within business hours
    """
    time_str = dt.strftime("%H:%M")
    return opening <= time_str <= closing


def calculate_duration_minutes(start: datetime, end: datetime) -> int:
    """
    Calculate duration between two datetimes in minutes.

    Args:
        start: Start datetime
        end: End datetime

    Returns:
        Duration in minutes
    """
    delta = end - start
    return int(delta.total_seconds() / 60)


from datetime import timedelta
