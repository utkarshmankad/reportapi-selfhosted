"""Durable report jobs: creation, atomic schedule-occurrence claiming, and
attempt-bounded execution with crash recovery.

A ReportJob row is the unit of durability. It exists the moment work is
accepted (queued), independent of whether any worker process survives to
finish it — a crash mid-run leaves a `running` row that recover_stuck_jobs
can find and requeue, instead of silently losing the request.
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging_config import get_logger
from app.core.report_service import ReportGenerationError, generate_report
from app.core.webhook_service import enqueue_deliveries_for_report
from app.db.models import (
    JOB_STATUS_FAILED,
    JOB_STATUS_QUEUED,
    JOB_STATUS_RUNNING,
    JOB_STATUS_SUCCEEDED,
    ReportJob,
    Schedule,
)

logger = get_logger(__name__)

# A job that fails outright (not a crash-recovery requeue) gets this many
# total attempts before it's terminal. Bounded so a permanently broken
# connector/provider config can't retry forever.
MAX_JOB_ATTEMPTS = 3

# A job stuck in `running` longer than this is assumed to belong to a dead
# worker (process crash, OOM kill, host restart) rather than one still
# legitimately in progress, and is eligible for recovery.
STALE_RUNNING_AFTER = timedelta(minutes=10)

# Bounds how many missed cron occurrences a schedule backfills after being
# paused or the worker being down for a long stretch — never claim more
# than this many occurrences in one dispatch pass.
MAX_BACKFILL_OCCURRENCES = 5


async def create_report_job(
    db: AsyncSession,
    *,
    connector: str,
    board_id: str | None,
    sprint_id: str | None,
    output_format: str = "text",
    assigned_means_in_progress: bool = True,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
    template_id: UUID | None = None,
    idempotency_key: str | None = None,
) -> tuple[ReportJob, bool]:
    """
    Create a queued job for a manual (non-schedule) report request.
    Returns (job, created) — created is False when idempotency_key matched
    an existing job, in which case that existing job is returned unchanged.
    """
    if idempotency_key:
        existing = await db.execute(
            select(ReportJob).where(ReportJob.idempotency_key == idempotency_key)
        )
        found = existing.scalar_one_or_none()
        if found:
            return found, False

    job = ReportJob(
        idempotency_key=idempotency_key,
        status=JOB_STATUS_QUEUED,
        connector=connector,
        board_id=board_id,
        sprint_id=sprint_id,
        output_format=output_format,
        assigned_means_in_progress=assigned_means_in_progress,
        period_start=period_start,
        period_end=period_end,
        template_id=template_id,
    )
    db.add(job)
    try:
        await db.commit()
    except IntegrityError:
        # Concurrent request with the same idempotency_key won the race —
        # fetch and return the row it created instead of erroring.
        await db.rollback()
        existing = await db.execute(
            select(ReportJob).where(ReportJob.idempotency_key == idempotency_key)
        )
        return existing.scalar_one(), False
    await db.refresh(job)
    return job, True


async def claim_schedule_occurrences(
    db: AsyncSession, schedule: Schedule, occurrences: list[datetime]
) -> list[ReportJob]:
    """
    Atomically claim each due occurrence as a queued job. The database's
    unique (schedule_id, scheduled_for) constraint — not application locking
    — is what makes this safe under concurrent/overlapping dispatch: only
    one INSERT for a given occurrence can ever succeed.
    """
    # Read every field up front: db.rollback() after a lost race below
    # expires the *entire* session's identity map (not just the failed
    # insert), so re-reading `schedule.<attr>` on a later iteration — or
    # back in the caller right after this returns — would try to lazily
    # reload an expired attribute outside the async greenlet context and
    # raise MissingGreenlet. Snapshotting values once sidesteps that.
    connector = schedule.connector
    board_id = schedule.board_id
    sprint_id = schedule.sprint_id
    output_format = schedule.output_format
    assigned_means_in_progress = schedule.assigned_means_in_progress
    period_start = schedule.period_start
    period_end = schedule.period_end
    schedule_id = schedule.id

    claimed: list[ReportJob] = []
    for scheduled_for in occurrences:
        job = ReportJob(
            status=JOB_STATUS_QUEUED,
            connector=connector,
            board_id=board_id,
            sprint_id=sprint_id,
            output_format=output_format,
            assigned_means_in_progress=assigned_means_in_progress,
            period_start=period_start,
            period_end=period_end,
            schedule_id=schedule_id,
            scheduled_for=scheduled_for,
        )
        try:
            # A SAVEPOINT, not a full commit/rollback: a lost race only
            # undoes this one insert. A full session-level rollback (the
            # previous approach) expires every already-loaded object in
            # the session — including `schedule` itself and any other
            # schedules the caller is mid-iterating — which then raises
            # MissingGreenlet the next time a plain attribute is read,
            # since an expired attribute can't be lazily reloaded outside
            # an explicit await.
            async with db.begin_nested():
                db.add(job)
                await db.flush()
        except IntegrityError:
            # Another dispatch pass (overlapping beat tick, second worker)
            # already claimed this exact occurrence — not an error, just
            # lost the race for a row we didn't need to create anyway.
            continue
        claimed.append(job)

    if claimed:
        await db.commit()
        for job in claimed:
            await db.refresh(job)
    return claimed


async def run_job(db: AsyncSession, job: ReportJob) -> ReportJob:
    """
    Execute one attempt of a job in the caller's session/transaction scope.
    Transitions queued -> running -> succeeded, or queued -> running ->
    queued (retry) / failed (attempts exhausted) on error. The caller is
    responsible for using a session scoped to just this job — see
    app.worker.tasks.execute_report_job — so one job's failure can never
    poison another job's transaction.
    """
    job.status = JOB_STATUS_RUNNING
    job.started_at = datetime.now(timezone.utc)
    job.attempts += 1
    db.add(job)
    await db.commit()
    logger.info(
        "report job started",
        extra={
            "job_id": str(job.id),
            "connector": job.connector,
            "attempt": job.attempts,
            "schedule_id": str(job.schedule_id) if job.schedule_id else None,
        },
    )

    try:
        report, _ = await generate_report(
            db=db,
            connector=job.connector,
            board_id=job.board_id,
            sprint_id=job.sprint_id,
            output_format=job.output_format,
            assigned_means_in_progress=job.assigned_means_in_progress,
            period_start=job.period_start,
            period_end=job.period_end,
            template_id=job.template_id,
        )
    except ReportGenerationError as e:
        job.finished_at = datetime.now(timezone.utc)
        job.error_reason = e.detail
        job.status = JOB_STATUS_QUEUED if job.attempts < MAX_JOB_ATTEMPTS else JOB_STATUS_FAILED
        db.add(job)
        await db.commit()
        await db.refresh(job)
        logger.warning(
            "report job attempt failed",
            extra={
                "job_id": str(job.id),
                "connector": job.connector,
                "attempt": job.attempts,
                "status": job.status,
                "error_reason": job.error_reason,
            },
        )

        if job.schedule_id and job.status == JOB_STATUS_FAILED:
            schedule = await db.get(Schedule, job.schedule_id)
            if schedule:
                schedule.last_attempted_at = job.scheduled_for
                db.add(schedule)
                await db.commit()
        return job

    job.status = JOB_STATUS_SUCCEEDED
    job.report_id = report.id
    job.finished_at = datetime.now(timezone.utc)
    db.add(job)

    if job.schedule_id:
        schedule = await db.get(Schedule, job.schedule_id)
        if schedule:
            schedule.last_run_at = job.finished_at
            schedule.last_attempted_at = job.scheduled_for
            db.add(schedule)

    # Outbox insert in the same transaction as the success — a delivery
    # row only exists if the report/job state it's notifying about was
    # actually committed, and vice versa: nothing is silently skipped. A
    # periodic sweep (app.worker.tasks.dispatch_pending_webhook_deliveries)
    # picks up pending rows rather than dispatching inline here, so a
    # worker crash between this commit and dispatch still leaves the
    # delivery discoverable.
    await enqueue_deliveries_for_report(db, report)

    await db.commit()
    await db.refresh(job)
    logger.info(
        "report job succeeded",
        extra={"job_id": str(job.id), "connector": job.connector, "report_id": str(job.report_id)},
    )
    return job


async def recover_stuck_jobs(db: AsyncSession) -> list[ReportJob]:
    """
    Find jobs stuck in `running` past STALE_RUNNING_AFTER — evidence of a
    worker that died mid-attempt rather than one still working — and put
    them back in `queued` (or `failed` once attempts are exhausted) so a
    live worker picks them up instead of the request being lost forever.
    """
    cutoff = datetime.now(timezone.utc) - STALE_RUNNING_AFTER
    result = await db.execute(
        select(ReportJob).where(
            ReportJob.status == JOB_STATUS_RUNNING, ReportJob.started_at < cutoff
        )
    )
    stuck = list(result.scalars().all())

    recovered: list[ReportJob] = []
    for job in stuck:
        job.error_reason = "Worker did not report completion in time; recovered"
        job.finished_at = datetime.now(timezone.utc)
        job.status = JOB_STATUS_QUEUED if job.attempts < MAX_JOB_ATTEMPTS else JOB_STATUS_FAILED
        db.add(job)
        recovered.append(job)

    if recovered:
        await db.commit()
        for job in recovered:
            await db.refresh(job)
            logger.warning(
                "report job recovered from stale running state",
                extra={"job_id": str(job.id), "connector": job.connector, "status": job.status},
            )
    return recovered
