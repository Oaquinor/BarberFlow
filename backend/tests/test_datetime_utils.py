"""Business-calendar time window helpers."""

from datetime import datetime
from zoneinfo import ZoneInfo

from app.utils.datetime import local_month_window_utc_naive


def test_local_month_window_respects_business_timezone_and_dst():
    start, end = local_month_window_utc_naive(
        datetime(2026, 3, 15, 12), ZoneInfo("America/New_York"),
    )

    assert start == datetime(2026, 3, 1, 5)
    assert end == datetime(2026, 4, 1, 4)


def test_local_month_window_uses_local_month_when_utc_date_has_changed():
    start, end = local_month_window_utc_naive(
        datetime(2026, 11, 1, 2), ZoneInfo("Pacific/Honolulu"),
    )

    assert start == datetime(2026, 10, 1, 10)
    assert end == datetime(2026, 11, 1, 10)
