# Schedule timing: timezones, DST, and missed runs

## Timezone

Every schedule has a `timezone` field — an IANA zone name such as `UTC`,
`America/New_York`, or `Europe/London` (default: `UTC`). The
`cron_expression` fields are evaluated as **wall-clock time in that zone**,
not as a fixed UTC offset. A schedule set to `0 9 * * 1` in
`America/New_York` means "9am New York time every Monday" year-round, not
"9am-then-8am-then-9am UTC" as the offset shifts across DST.

Existing schedules created before this field existed default to `UTC`,
preserving their exact prior behavior.

## Daylight Saving Time

Because cron fields are wall-clock time in the configured zone, DST
transitions are handled as follows:

- **Spring forward (a local time is skipped).** If a schedule's time falls
  in the gap that a "spring forward" transition skips (e.g. 2:30am on a day
  when clocks jump from 2:00am to 3:00am), that occurrence is moved forward
  to the next valid instant on the same day — it is not skipped entirely
  and not moved to the next day.
- **Fall back (a local time repeats).** If a schedule's time falls in an
  hour that "fall back" repeats (e.g. 1:30am occurring twice), the
  schedule fires **once for each of the two distinct instants** — they are
  different moments in UTC even though they share the same local clock
  reading. A schedule in an affected zone will therefore run twice on that
  calendar day for that occurrence.

This is a deliberate, literal interpretation of "wall-clock time in this
zone," not an attempt to guess which of the two instants was "really"
meant. If your workflow needs exactly-once-per-day semantics through a
fall-back transition, account for the possibility of a duplicate run near
that boundary.

## Missed runs

The scheduler (`app.worker.tasks.dispatch_due_schedules`, on a one-minute
beat tick) claims and dispatches every cron occurrence that is due and
hasn't yet been claimed, starting from the schedule's last-attempted
occurrence. If the worker/beat process was down, or a schedule was paused
and reactivated, multiple occurrences may be due at once.

**Backfill is bounded** (`MAX_BACKFILL_OCCURRENCES`, currently 5): a single
dispatch pass claims at most that many missed occurrences per schedule.
Older misses beyond that bound are **not** reconstructed — the schedule's
cursor (`last_attempted_at`) simply advances to the most recent occurrence
considered in that pass, and any occurrences further in the past are
permanently skipped. This bound exists so that a schedule left paused for
weeks doesn't suddenly burst-create weeks of catch-up jobs; it does mean
this system does not claim to guarantee eventual delivery of every missed
occurrence after an arbitrarily long outage.

## Previewing future runs

`GET /api/schedule/{id}/next-runs?count=N` (default 5, max 20) returns the
next N occurrences as explicit UTC timestamps, computed with the same
timezone-aware logic the dispatcher uses (`app.core.schedule_time`) — so
what you see in a preview is exactly what will actually be claimed and
dispatched, not an approximation.
