"""IANA-timezone-aware cron occurrence calculation.

Shared by the dispatch loop (app.worker.tasks) and the future-run preview
endpoint, so "what will this schedule do next" and "what did dispatch just
do" are always computed the same way.

DST/missed-run policy (see docs/scheduling.md for the full writeup):
- Cron fields are wall-clock time in the schedule's configured zone, not a
  fixed UTC offset — "09:00" means 9am local on every occurrence, across
  DST transitions, not 9am-then-8am-then-9am in UTC.
- A time that doesn't exist during a "spring forward" gap (e.g. 2:30am on
  the day clocks skip 2:00-3:00) is skipped forward to the next valid
  instant that day, matching croniter's own gap-skipping behavior.
- A time that occurs twice during a "fall back" repeat (e.g. 1:30am
  happening twice) fires once for each of those two distinct instants —
  they are different moments in UTC even though they share a local
  clock reading.
- Missed occurrences (worker downtime, a paused schedule) are backfilled
  only up to MAX_BACKFILL_OCCURRENCES; older misses are never
  reconstructed after that bound is exceeded.
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from croniter import croniter


def _as_aware_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def next_occurrences_utc(
    cron_expression: str, tz_name: str, after: datetime, count: int
) -> list[datetime]:
    """The next `count` cron occurrences strictly after `after`, evaluated
    as wall-clock time in `tz_name`, returned as UTC-aware datetimes."""
    tz = ZoneInfo(tz_name)
    base = _as_aware_utc(after).astimezone(tz)
    cron = croniter(cron_expression, base)
    return [cron.get_next(datetime).astimezone(timezone.utc) for _ in range(count)]


def due_occurrences_utc(
    cron_expression: str, tz_name: str, after: datetime, now: datetime, max_count: int
) -> list[datetime]:
    """Return at most the most recent `max_count` due occurrences.

    Looking backward from `now` is deliberate: when downtime produced more
    missed runs than the catch-up policy permits, older occurrences are
    skipped permanently and the returned final occurrence advances the
    schedule cursor to the present backlog boundary.
    """
    tz = ZoneInfo(tz_name)
    after_utc = _as_aware_utc(after)
    now_utc = _as_aware_utc(now)
    # croniter.get_prev() is strict. Moving one microsecond beyond now makes
    # an occurrence exactly at `now` eligible, matching the <= now contract.
    base = now_utc.astimezone(tz) + timedelta(microseconds=1)
    cron = croniter(cron_expression, base)
    occurrences: list[datetime] = []
    while len(occurrences) < max_count:
        previous_utc = cron.get_prev(datetime).astimezone(timezone.utc)
        if previous_utc <= after_utc:
            break
        occurrences.append(previous_utc)
    occurrences.reverse()
    return occurrences
