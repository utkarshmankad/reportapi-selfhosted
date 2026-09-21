"""Durable report job routes: enqueue and poll status/result."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.job_service import create_report_job
from app.core.logging_config import get_logger
from app.db.models import ReportJob
from app.db.session import get_db
from app.models.job import CreateReportJobRequest, ReportJobResponse

router = APIRouter(prefix="/api/report/jobs", tags=["report-jobs"])
logger = get_logger(__name__)


@router.post("", response_model=ReportJobResponse)
async def create_job(request: CreateReportJobRequest, db: AsyncSession = Depends(get_db)):
    job, created = await create_report_job(
        db,
        connector=request.connector,
        board_id=request.board_id,
        sprint_id=request.sprint_id,
        output_format=request.output_format,
        assigned_means_in_progress=request.assigned_means_in_progress,
        period_start=request.period_start,
        period_end=request.period_end,
        template_id=request.template_id,
        idempotency_key=request.idempotency_key,
    )

    if created:
        from app.worker.tasks import execute_report_job

        try:
            execute_report_job.delay(str(job.id))
        except Exception:
            # The queued database row is the durable work record. A periodic
            # dispatcher will retry broker publication, so a transient broker
            # outage after the commit must not turn an accepted request into
            # an HTTP failure or lose it forever.
            logger.warning(
                "initial report job dispatch failed; queued sweep will retry",
                extra={"job_id": str(job.id)},
            )

    return job


@router.get("/{job_id}", response_model=ReportJobResponse)
async def get_job(job_id: UUID, db: AsyncSession = Depends(get_db)):
    job = await db.get(ReportJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("", response_model=list[ReportJobResponse])
async def list_jobs(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ReportJob)
        .order_by(ReportJob.created_at.desc(), ReportJob.id)
        .offset(offset)
        .limit(limit)
    )
    return result.scalars().all()
