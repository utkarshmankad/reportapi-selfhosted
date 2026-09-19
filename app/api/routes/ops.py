"""Operational status: queue depths, scheduler freshness, recent failures.

A single read-only endpoint an operator (or a dashboard/alerting rule)
can poll instead of querying the database directly — the numbers here
are exactly what the runbook (docs/runbook.md) tells an operator to
check first when something looks wrong.
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter
from sqlalchemy import func, select

from app.api.routes.health import _scheduler_freshness
from app.config import settings
from app.core.job_service import STALE_RUNNING_AFTER
from app.db.models import (
    DELIVERY_STATUS_FAILED,
    DELIVERY_STATUS_PENDING,
    JOB_STATUS_FAILED,
    JOB_STATUS_QUEUED,
    JOB_STATUS_RUNNING,
    Report,
    ReportJob,
    WebhookDelivery,
)
from app.db.session import AsyncSessionLocal

router = APIRouter(prefix="/api/ops", tags=["ops"])


@router.get("/status")
async def ops_status() -> dict:
    async with AsyncSessionLocal() as db:
        job_counts = dict(
            (
                await db.execute(select(ReportJob.status, func.count()).group_by(ReportJob.status))
            ).all()
        )

        stuck_cutoff = datetime.now(timezone.utc) - STALE_RUNNING_AFTER
        stuck_jobs = (
            await db.execute(
                select(func.count()).where(
                    ReportJob.status == JOB_STATUS_RUNNING,
                    ReportJob.started_at < stuck_cutoff,
                )
            )
        ).scalar_one()

        delivery_counts = dict(
            (
                await db.execute(
                    select(WebhookDelivery.status, func.count()).group_by(WebhookDelivery.status)
                )
            ).all()
        )

        retention_days = settings.report_retention_days
        reports_eligible_for_cleanup = 0
        if retention_days > 0:
            cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
            reports_eligible_for_cleanup = (
                await db.execute(select(func.count()).where(Report.created_at < cutoff))
            ).scalar_one()

    return {
        "scheduler": await _scheduler_freshness(),
        "jobs": {
            "queued": job_counts.get(JOB_STATUS_QUEUED, 0),
            "running": job_counts.get(JOB_STATUS_RUNNING, 0),
            "failed": job_counts.get(JOB_STATUS_FAILED, 0),
            "stuck": stuck_jobs,
        },
        "webhook_deliveries": {
            "pending": delivery_counts.get(DELIVERY_STATUS_PENDING, 0),
            "failed": delivery_counts.get(DELIVERY_STATUS_FAILED, 0),
        },
        "retention": {
            "retention_days": retention_days,
            "reports_eligible_for_cleanup": reports_eligible_for_cleanup,
        },
    }
