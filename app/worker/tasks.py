"""Celery periodic tasks."""

import asyncio
from datetime import datetime, timezone

from croniter import croniter
from sqlalchemy import select

from app.core.report_service import ReportGenerationError, generate_report
from app.db.models import Schedule
from app.db.session import AsyncSessionLocal, engine
from app.worker.celery_app import celery_app


def _is_due(schedule: Schedule, now: datetime) -> bool:
    base = schedule.last_run_at or schedule.created_at
    cron = croniter(schedule.cron_expression, base)
    return cron.get_next(datetime) <= now


async def _run_due_schedules() -> int:
    now = datetime.now(timezone.utc)
    ran = 0

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Schedule).where(Schedule.active.is_(True)))
        schedules = result.scalars().all()

        for schedule in schedules:
            if not _is_due(schedule, now):
                continue

            try:
                await generate_report(
                    db=db,
                    connector=schedule.connector,
                    board_id=schedule.board_id,
                    sprint_id=schedule.sprint_id,
                    output_format=schedule.output_format,
                    assigned_means_in_progress=schedule.assigned_means_in_progress,
                )
            except ReportGenerationError:
                pass
            finally:
                schedule.last_run_at = now
                db.add(schedule)
                await db.commit()
                ran += 1

    return ran


async def _run_due_schedules_and_dispose() -> int:
    # `engine` is a module-level singleton whose asyncpg pool binds to the
    # event loop it first opens connections under. Each task invocation
    # runs in a brand-new loop (asyncio.run below), so pooled connections
    # from the previous run belong to an already-closed loop and blow up
    # with "attached to a different loop". Disposing forces a fresh pool
    # next run, tied to that run's own loop.
    try:
        return await _run_due_schedules()
    finally:
        await engine.dispose()


@celery_app.task(name="app.worker.tasks.run_due_schedules")
def run_due_schedules() -> int:
    return asyncio.run(_run_due_schedules_and_dispose())
