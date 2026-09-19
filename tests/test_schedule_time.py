"""IANA-timezone-aware cron occurrence calculation (S5-02)."""

from datetime import datetime, timedelta, timezone

from app.core.schedule_time import due_occurrences_utc, next_occurrences_utc


def test_next_occurrences_are_wall_clock_in_configured_zone():
    # 9am New York on a fixed midwinter date (EST, UTC-5) -> 14:00 UTC.
    after = datetime(2026, 1, 1, tzinfo=timezone.utc)
    runs = next_occurrences_utc("0 9 * * *", "America/New_York", after, 1)
    assert runs[0].hour == 14
    assert runs[0].tzinfo is not None


def test_same_cron_in_different_zones_yields_different_utc_times():
    after = datetime(2026, 1, 1, tzinfo=timezone.utc)
    ny = next_occurrences_utc("0 9 * * *", "America/New_York", after, 1)[0]
    london = next_occurrences_utc("0 9 * * *", "Europe/London", after, 1)[0]
    assert ny != london


def test_utc_default_matches_naive_utc_interpretation():
    after = datetime(2026, 1, 1, tzinfo=timezone.utc)
    runs = next_occurrences_utc("0 9 * * *", "UTC", after, 1)
    assert runs[0].hour == 9


def test_spring_forward_gap_is_skipped_forward_not_dropped():
    # US spring-forward 2026-03-08: 02:00 -> 03:00 local. A 2:30am cron
    # has no valid instant that day; croniter rolls it forward to 3:00am.
    after = datetime(2026, 3, 7, 12, 0, tzinfo=timezone.utc)
    runs = next_occurrences_utc("30 2 * * *", "America/New_York", after, 1)
    local = runs[0].astimezone(__import__("zoneinfo").ZoneInfo("America/New_York"))
    assert local.date().isoformat() == "2026-03-08"
    assert (local.hour, local.minute) == (3, 0)


def test_fall_back_repeated_hour_fires_twice():
    # US fall-back 2026-11-01: 1:30am occurs twice (EDT then EST).
    after = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)
    runs = next_occurrences_utc("30 1 * * *", "America/New_York", after, 2)
    assert runs[0].date() == runs[1].date()
    assert runs[0] != runs[1]
    assert (runs[1] - runs[0]) == timedelta(hours=1)


def test_due_occurrences_bounded_and_timezone_aware():
    after = datetime(2026, 1, 1, tzinfo=timezone.utc)
    now = datetime(2026, 1, 1, 0, 10, tzinfo=timezone.utc)
    occurrences = due_occurrences_utc("* * * * *", "UTC", after, now, max_count=100)
    assert len(occurrences) == 10
    assert all(o <= now for o in occurrences)


def test_due_occurrences_respects_max_count():
    after = datetime(2026, 1, 1, tzinfo=timezone.utc)
    now = datetime(2026, 1, 2, tzinfo=timezone.utc)
    occurrences = due_occurrences_utc("* * * * *", "UTC", after, now, max_count=5)
    assert len(occurrences) == 5


def test_naive_after_datetime_is_treated_as_utc():
    after = datetime(2026, 1, 1)  # naive
    runs = next_occurrences_utc("0 9 * * *", "UTC", after, 1)
    assert runs[0].hour == 9
