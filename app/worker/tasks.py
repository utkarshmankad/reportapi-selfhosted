"""Celery tasks: schedule dispatch, job execution, and crash recovery.

Each task opens its own AsyncSessionLocal — one session per job/dispatch
pass — so one job's failed transaction can never affect another's. Each
`asyncio.run` invocation gets a brand-new event loop; the module-level
`engine`'s pooled asyncpg connections are bound to whichever loop first
opened them, so every entry point disposes the engine in a `finally` to
force a fresh pool tied to that run's own loop.
"""

import asyncio
from datetime import datetime, timezone
from uuid import UUID

from croniter import croniter
from redis.asyncio import Redis
from sqlalchemy import select

from app.api.routes.health import SCHEDULER_HEARTBEAT_KEY
from app.config import settings
from app.core.job_service import (
    MAX_BACKFILL_OCCURRENCES,
    claim_schedule_occurrences,
    recover_stuck_jobs,
    run_job,
)
from app.core.logging_config import get_logger
from app.db.models import ReportJob, Schedule
from app.db.session import AsyncSessionLocal, engine
from app.worker.celery_app import celery_app

logger = get_logger(__name__)

# Retry delay for a job that failed but has attempts remaining. Short
# enough that a transient upstream blip resolves quickly, long enough not
# to hammer a genuinely-down connector/provider.
RETRY_COUNTDOWN_SECONDS = 30


def _due_occurrences(schedule: Schedule, now: datetime, max_count: int) -> list[datetime]:
    """
    Cron occurrences for `schedule` that are due (<= now) and haven't been
    claimed yet, starting just after the last occurrence this schedule
    attempted. Bounded by max_count so a schedule that was paused or a
    worker that was down for a long time doesn't burst-create an unbounded
    backlog of catch-up jobs in one pass.
    """
    base = schedule.last_attempted_at or schedule.created_at
    cron = croniter(schedule.cron_expression, base)
    occurrences: list[datetime] = []
    while len(occurrences) < max_count:
        next_occurrence = cron.get_next(datetime)
        if next_occurrence.tzinfo is None:
            next_occurrence = next_occurrence.replace(tzinfo=timezone.utc)
        if next_occurrence > now:
            break
        occurrences.append(next_occurrence)
    return occurrences


async def _dispatch_due_schedules() -> int:
    now = datetime.now(timezone.utc)
    dispatched = 0

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Schedule).where(Schedule.active.is_(True)))
        schedules = result.scalars().all()

        for schedule in schedules:
            occurrences = _due_occurrences(schedule, now, MAX_BACKFILL_OCCURRENCES)
            if not occurrences:
                continue

            claimed = await claim_schedule_occurrences(db, schedule, occurrences)
            # Advance the cursor past every occurrence considered this pass
            # (claimed or lost to a concurrent claimant) so the next tick
            # doesn't re-examine them.
            schedule.last_attempted_at = occurrences[-1]
            db.add(schedule)
            await db.commit()

            for job in claimed:
                execute_report_job.delay(str(job.id))
                dispatched += 1

    await _record_scheduler_heartbeat()
    logger.info("dispatched due schedules", extra={"dispatched": dispatched})
    return dispatched


async def _record_scheduler_heartbeat() -> None:
    """Written on every successful dispatch pass so /health/ready can tell
    a beat process that's actually down from one that's simply mid-cycle."""
    client = Redis.from_url(settings.redis_url)
    try:
        await client.set(SCHEDULER_HEARTBEAT_KEY, datetime.now(timezone.utc).timestamp())
    finally:
        await client.aclose()


async def _dispatch_due_schedules_and_dispose() -> int:
    try:
        return await _dispatch_due_schedules()
    finally:
        await engine.dispose()


@celery_app.task(name="app.worker.tasks.dispatch_due_schedules")
def dispatch_due_schedules() -> int:
    return asyncio.run(_dispatch_due_schedules_and_dispose())


async def _execute_report_job(job_id: str) -> str:
    async with AsyncSessionLocal() as db:
        job = await db.get(ReportJob, UUID(job_id))
        if job is None:
            return "missing"
        result = await run_job(db, job)
        return result.status


async def _execute_report_job_and_dispose(job_id: str) -> str:
    try:
        return await _execute_report_job(job_id)
    finally:
        await engine.dispose()


@celery_app.task(name="app.worker.tasks.execute_report_job")
def execute_report_job(job_id: str) -> str:
    status = asyncio.run(_execute_report_job_and_dispose(job_id))
    if status == "queued":
        # run_job left the job queued for a bounded retry after a failed
        # attempt — re-enqueue this same job rather than losing it, with a
        # short delay so a transient failure isn't hammered immediately.
        execute_report_job.apply_async(args=[job_id], countdown=RETRY_COUNTDOWN_SECONDS)
    return status


async def _recover_stuck_report_jobs() -> int:
    async with AsyncSessionLocal() as db:
        recovered = await recover_stuck_jobs(db)
        for job in recovered:
            if job.status == "queued":
                execute_report_job.delay(str(job.id))
        return len(recovered)


async def _recover_stuck_report_jobs_and_dispose() -> int:
    try:
        return await _recover_stuck_report_jobs()
    finally:
        await engine.dispose()


@celery_app.task(name="app.worker.tasks.recover_stuck_report_jobs")
def recover_stuck_report_jobs() -> int:
    count = asyncio.run(_recover_stuck_report_jobs_and_dispose())
    if count:
        logger.warning("recovered stuck report jobs", extra={"count": count})
    return count
