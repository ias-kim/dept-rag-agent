from datetime import UTC, date, datetime

from app.core.clock import seoul_today


def test_seoul_date_rolls_over_at_15_utc():
    assert seoul_today(datetime(2026, 9, 30, 14, 59, tzinfo=UTC)) == date(2026, 9, 30)
    assert seoul_today(datetime(2026, 9, 30, 15, 0, tzinfo=UTC)) == date(2026, 10, 1)
