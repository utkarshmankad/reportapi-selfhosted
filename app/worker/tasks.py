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
from app.core.retention_service import enforce_report_retention
from app.core.retry_policy import RETRY_BACKOFF_SECONDS
from app.core.schedule_time import due_occurrences_utc
from app.core.webhook_service import send_delivery
from app.db.models import DELIVERY_STATUS_PENDING, ReportJob, Schedule, WebhookDelivery
from app.db.session import AsyncSessionLocal, engine
from app.worker.celery_app import celery_app

logger = get_logger(__name__)

# Retry delay for a job that failed but has attempts remaining — shared
# with WebhookDelivery's retry backoff via app.core.retry_policy (S5-05).
RETRY_COUNTDOWN_SECONDS = RETRY_BACKOFF_SECONDS


def _due_occurrences(schedule: Schedule, now: datetime, max_count: int) -> list[datetime]:
    """
    Cron occurrences for `schedule` that are due (<= now) and haven't been
    claimed yet, starting just after the last occurrence this schedule
    attempted, evaluated as wall-clock time in the schedule's configured
    IANA timezone (see app.core.schedule_time for the DST/missed-run
    policy this implies). Bounded by max_count so a schedule that was
    paused or a worker that was down for a long time doesn't burst-create
    an unbounded backlog of catch-up jobs in one pass.
    """
    base = schedule.last_attempted_at or schedule.created_at
    return due_occurrences_utc(schedule.cron_expression, schedule.timezone, base, now, max_count)


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


async def _dispatch_queued_report_jobs() -> int:
    """Republish durable queued jobs, including rows stranded by a broker
    outage or a process crash between the database commit and `.delay()`."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ReportJob.id).where(ReportJob.status == "queued").order_by(ReportJob.queued_at)
        )
        job_ids = list(result.scalars().all())

    published = 0
    for job_id in job_ids:
        try:
            execute_report_job.delay(str(job_id))
            published += 1
        except Exception:
            logger.warning(
                "queued report job dispatch failed",
                extra={"job_id": str(job_id)},
            )
    return published


async def _dispatch_queued_report_jobs_and_dispose() -> int:
    try:
        return await _dispatch_queued_report_jobs()
    finally:
        await engine.dispose()


@celery_app.task(name="app.worker.tasks.dispatch_queued_report_jobs")
def dispatch_queued_report_jobs() -> int:
    return asyncio.run(_dispatch_queued_report_jobs_and_dispose())


async def _dispatch_pending_webhook_deliveries() -> int:
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(WebhookDelivery).where(
                WebhookDelivery.status == DELIVERY_STATUS_PENDING,
                (WebhookDelivery.next_attempt_at.is_(None))
                | (WebhookDelivery.next_attempt_at <= now),
            )
        )
        pending = list(result.scalars().all())
        for delivery in pending:
            deliver_webhook.delay(str(delivery.id))
        return len(pending)


async def _dispatch_pending_webhook_deliveries_and_dispose() -> int:
    try:
        return await _dispatch_pending_webhook_deliveries()
    finally:
        await engine.dispose()


@celery_app.task(name="app.worker.tasks.dispatch_pending_webhook_deliveries")
def dispatch_pending_webhook_deliveries() -> int:
    return asyncio.run(_dispatch_pending_webhook_deliveries_and_dispose())


async def _deliver_webhook(delivery_id: str) -> str:
    async with AsyncSessionLocal() as db:
        delivery = await db.get(WebhookDelivery, UUID(delivery_id))
        if delivery is None:
            return "missing"
        result = await send_delivery(db, delivery)
        return result.status


async def _deliver_webhook_and_dispose(delivery_id: str) -> str:
    try:
        return await _deliver_webhook(delivery_id)
    finally:
        await engine.dispose()


@celery_app.task(name="app.worker.tasks.deliver_webhook")
def deliver_webhook(delivery_id: str) -> str:
    # No self-requeue here (unlike execute_report_job): a retryable
    # failure sets next_attempt_at and waits for the next
    # dispatch_pending_webhook_deliveries sweep to pick it back up. A
    # single dispatch path — never two racing schedulers for the same
    # delivery — is the whole point of the next_attempt_at column.
    return asyncio.run(_deliver_webhook_and_dispose(delivery_id))


async def _enforce_report_retention() -> int:
    async with AsyncSessionLocal() as db:
        return await enforce_report_retention(db, settings.report_retention_days)


async def _enforce_report_retention_and_dispose() -> int:
    try:
        return await _enforce_report_retention()
    finally:
        await engine.dispose()


@celery_app.task(name="app.worker.tasks.enforce_report_retention")
def enforce_report_retention_task() -> int:
    count = asyncio.run(_enforce_report_retention_and_dispose())
    if count:
        logger.info("retention sweep deleted reports", extra={"count": count})
    return count
