"""Real Postgres concurrency/recovery tests for the durable job pipeline (S3-06).

These exercise the guarantees that only hold with a real database: the
unique-constraint-backed atomic occurrence claim under concurrent dispatch,
transaction isolation between jobs, idempotency-key races, and stuck-job
recovery after a simulated worker crash.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.job_service import (
    MAX_JOB_ATTEMPTS,
    claim_schedule_occurrences,
    create_report_job,
    recover_stuck_jobs,
    run_job,
)
from app.core.report_service import ReportGenerationError
from app.db.models import (
    JOB_STATUS_FAILED,
    JOB_STATUS_QUEUED,
    JOB_STATUS_SUCCEEDED,
    ReportJob,
    Schedule,
)
from app.db.session import AsyncSessionLocal

pytestmark = pytest.mark.integration


async def _make_schedule(db) -> Schedule:
    schedule = Schedule(
        connector="jira",
        board_id="PROJ",
        cron_expression="* * * * *",
        active=True,
    )
    db.add(schedule)
    await db.commit()
    await db.refresh(schedule)
    return schedule


@pytest.mark.asyncio
async def test_concurrent_claims_on_same_occurrence_produce_one_job():
    """Two overlapping dispatch passes racing for the same occurrence must
    not both win — the DB unique constraint is the only thing enforcing
    this, not application-level locking, so it has to be tested for real."""
    scheduled_for = datetime.now(timezone.utc).replace(microsecond=0)

    async with AsyncSessionLocal() as setup_db:
        schedule = await _make_schedule(setup_db)

    async def attempt_claim():
        async with AsyncSessionLocal() as db:
            sched = await db.get(Schedule, schedule.id)
            return await claim_schedule_occurrences(db, sched, [scheduled_for])

    results = await asyncio.gather(*(attempt_claim() for _ in range(10)))
    total_claimed = sum(len(r) for r in results)
    assert total_claimed == 1

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ReportJob).where(
                ReportJob.schedule_id == schedule.id, ReportJob.scheduled_for == scheduled_for
            )
        )
        rows = result.scalars().all()
        assert len(rows) == 1


@pytest.mark.asyncio
async def test_idempotency_key_race_produces_one_job():
    """Two concurrent manual-generate requests with the same idempotency key
    must resolve to the same job, not two."""
    key = f"race-{uuid4()}"

    async def attempt_create():
        async with AsyncSessionLocal() as db:
            job, created = await create_report_job(
                db, connector="jira", board_id="PROJ", sprint_id=None, idempotency_key=key
            )
            return job.id, created

    results = await asyncio.gather(*(attempt_create() for _ in range(10)))
    job_ids = {r[0] for r in results}
    assert len(job_ids) == 1
    assert sum(1 for _, created in results if created) == 1

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(ReportJob).where(ReportJob.idempotency_key == key))
        assert len(result.scalars().all()) == 1


@pytest.mark.asyncio
async def test_failed_job_transaction_does_not_affect_next_job():
    """A job whose generate_report call fails mid-transaction must not
    poison a subsequent job's session/transaction — each job execution
    uses its own session (this test exercises two in sequence on
    independent sessions, matching how the worker actually runs them)."""
    async with AsyncSessionLocal() as db:
        failing_job = ReportJob(
            status=JOB_STATUS_QUEUED, connector="jira", board_id="PROJ", sprint_id=None
        )
        db.add(failing_job)
        await db.commit()
        await db.refresh(failing_job)

    with patch(
        "app.core.job_service.generate_report",
        AsyncMock(side_effect=ReportGenerationError(502, "upstream down")),
    ):
        async with AsyncSessionLocal() as db:
            job = await db.get(ReportJob, failing_job.id)
            result = await run_job(db, job)
    assert result.status == JOB_STATUS_QUEUED
    assert result.error_reason == "upstream down"

    # A completely independent session/job must work normally afterward.
    async with AsyncSessionLocal() as db:
        healthy_job = ReportJob(
            status=JOB_STATUS_QUEUED, connector="jira", board_id="PROJ", sprint_id=None
        )
        db.add(healthy_job)
        await db.commit()
        await db.refresh(healthy_job)

    from app.db.models import Report

    fake_report = Report(
        connector="jira",
        status="complete",
        model_used="openai",
        tokens_used=10,
        narrative="ok",
        output_format="text",
    )
    with patch(
        "app.core.job_service.generate_report",
        AsyncMock(return_value=(fake_report, 1)),
    ):
        async with AsyncSessionLocal() as db:
            db.add(fake_report)
            await db.commit()
            job = await db.get(ReportJob, healthy_job.id)
            result = await run_job(db, job)
    assert result.status == JOB_STATUS_SUCCEEDED


@pytest.mark.asyncio
async def test_job_marked_failed_after_max_attempts():
    async with AsyncSessionLocal() as db:
        job = ReportJob(
            status=JOB_STATUS_QUEUED,
            connector="jira",
            board_id="PROJ",
            sprint_id=None,
            attempts=MAX_JOB_ATTEMPTS - 1,
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)

    with patch(
        "app.core.job_service.generate_report",
        AsyncMock(side_effect=ReportGenerationError(502, "still down")),
    ):
        async with AsyncSessionLocal() as db:
            job = await db.get(ReportJob, job.id)
            result = await run_job(db, job)

    assert result.attempts == MAX_JOB_ATTEMPTS
    assert result.status == JOB_STATUS_FAILED


@pytest.mark.asyncio
async def test_stuck_running_job_is_recovered():
    """Simulates a worker crash: a job left `running` past the staleness
    window must be found and requeued by the recovery sweep."""
    async with AsyncSessionLocal() as db:
        stuck = ReportJob(
            status="running",
            connector="jira",
            board_id="PROJ",
            sprint_id=None,
            started_at=datetime.now(timezone.utc) - timedelta(minutes=30),
            attempts=1,
        )
        fresh = ReportJob(
            status="running",
            connector="jira",
            board_id="PROJ",
            sprint_id=None,
            started_at=datetime.now(timezone.utc),
            attempts=1,
        )
        db.add_all([stuck, fresh])
        await db.commit()
        await db.refresh(stuck)
        await db.refresh(fresh)

    async with AsyncSessionLocal() as db:
        recovered = await recover_stuck_jobs(db)

    recovered_ids = {job.id for job in recovered}
    assert stuck.id in recovered_ids
    assert fresh.id not in recovered_ids

    async with AsyncSessionLocal() as db:
        refreshed_stuck = await db.get(ReportJob, stuck.id)
        refreshed_fresh = await db.get(ReportJob, fresh.id)
        assert refreshed_stuck.status == JOB_STATUS_QUEUED
        assert refreshed_fresh.status == "running"


@pytest.mark.asyncio
async def test_dispatch_backfills_bounded_occurrences_after_downtime():
    """A schedule whose worker was down for a long time must backfill only
    up to the bounded catch-up limit, not every missed minute."""
    from app.core.job_service import MAX_BACKFILL_OCCURRENCES
    from app.worker.tasks import _due_occurrences

    async with AsyncSessionLocal() as db:
        schedule = Schedule(
            connector="jira",
            board_id="PROJ",
            cron_expression="* * * * *",
            active=True,
            created_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        db.add(schedule)
        await db.commit()
        await db.refresh(schedule)

    now = datetime.now(timezone.utc)
    occurrences = _due_occurrences(schedule, now, MAX_BACKFILL_OCCURRENCES)
    assert len(occurrences) == MAX_BACKFILL_OCCURRENCES

    async with AsyncSessionLocal() as db:
        sched = await db.get(Schedule, schedule.id)
        claimed = await claim_schedule_occurrences(db, sched, occurrences)
    assert len(claimed) == MAX_BACKFILL_OCCURRENCES


@pytest.mark.asyncio
async def test_lost_claim_race_does_not_break_subsequent_session_use():
    """Regression test: a lost occurrence-claim race used to roll back the
    whole session, expiring every already-loaded object (including
    `schedule` itself and any other schedule mid-iteration in the same
    dispatch pass) and crashing the next plain attribute read with
    MissingGreenlet. claim_schedule_occurrences must survive a lost race
    without poisoning the caller's session."""
    scheduled_for = datetime.now(timezone.utc).replace(microsecond=0)

    async with AsyncSessionLocal() as db:
        schedule_a = await _make_schedule(db)
        schedule_b = await _make_schedule(db)

    # Pre-claim the occurrence for schedule_a from a separate session, so
    # the claim attempt inside the real dispatch-shaped flow below loses
    # the race and must recover cleanly.
    async with AsyncSessionLocal() as db:
        sched_a = await db.get(Schedule, schedule_a.id)
        pre_claimed = await claim_schedule_occurrences(db, sched_a, [scheduled_for])
    assert len(pre_claimed) == 1

    async with AsyncSessionLocal() as db:
        sched_a = await db.get(Schedule, schedule_a.id)
        sched_b = await db.get(Schedule, schedule_b.id)

        # This call loses the race for schedule_a's occurrence (already
        # claimed above) and must not expire the session.
        lost = await claim_schedule_occurrences(db, sched_a, [scheduled_for])
        assert lost == []

        # Reading schedule_a's own attributes and dispatching a second,
        # unrelated schedule in the same session/loop — exactly what
        # app.worker.tasks._dispatch_due_schedules does — must still work.
        assert sched_a.connector == "jira"
        won = await claim_schedule_occurrences(db, sched_b, [scheduled_for])
        assert len(won) == 1
        assert won[0].schedule_id == schedule_b.id


@pytest.mark.asyncio
async def test_successful_job_enqueues_webhook_deliveries():
    """run_job's success path must create the webhook outbox rows in the
    same transaction it commits the job/report success in (S5-01)."""
    from app.db.models import Report, WebhookDelivery, WebhookDestination

    async with AsyncSessionLocal() as db:
        destination = WebhookDestination(
            name="hook", url="https://hooks.example.com/x", secret="s", active=True
        )
        db.add(destination)
        job = ReportJob(status=JOB_STATUS_QUEUED, connector="jira", board_id="PROJ", sprint_id=None)
        db.add(job)
        await db.commit()
        await db.refresh(destination)
        await db.refresh(job)

    fake_report = Report(
        connector="jira",
        board_id="PROJ",
        status="complete",
        model_used="openai",
        tokens_used=10,
        ticket_count=1,
        narrative="ok",
        output_format="text",
    )
    with patch(
        "app.core.job_service.generate_report",
        AsyncMock(return_value=(fake_report, 1)),
    ):
        async with AsyncSessionLocal() as db:
            db.add(fake_report)
            await db.commit()
            job = await db.get(ReportJob, job.id)
            await run_job(db, job)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(WebhookDelivery).where(WebhookDelivery.destination_id == destination.id)
        )
        deliveries = result.scalars().all()
        assert len(deliveries) == 1
        assert deliveries[0].status == "pending"
