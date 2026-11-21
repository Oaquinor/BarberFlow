"""Calendar-day boundary conversion across MySQL UTC-naive storage and IANA time zones."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.utils.datetime import local_day_start_utc_naive


def test_regular_local_midnight_maps_to_utc():
    assert local_day_start_utc_naive(
        date(2026, 6, 1), ZoneInfo("America/Santo_Domingo")
    ) == datetime(2026, 6, 1, 4)


def test_day_that_skips_midnight_starts_at_first_valid_local_instant():
    assert local_day_start_utc_naive(
        date(2018, 11, 4), ZoneInfo("America/Sao_Paulo")
    ) == datetime(2018, 11, 4, 3)


def test_ambiguous_midnight_uses_its_first_occurrence():
    assert local_day_start_utc_naive(
        date(2020, 11, 1), ZoneInfo("America/Havana")
    ) == datetime(2020, 11, 1, 4)
