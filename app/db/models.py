"""SQLAlchemy ORM models."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


# ReportJob.status values. A job's lifecycle is strictly forward-moving:
# queued -> running -> (succeeded | failed), with failed -> queued allowed
# only as an explicit, attempt-bounded retry (see MAX_JOB_ATTEMPTS).
JOB_STATUS_QUEUED = "queued"
JOB_STATUS_RUNNING = "running"
JOB_STATUS_SUCCEEDED = "succeeded"
JOB_STATUS_FAILED = "failed"


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connector: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="complete")
    model_used: Mapped[str] = mapped_column(String(100), nullable=False)
    tokens_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    narrative: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_format: Mapped[str] = mapped_column(String(20), nullable=False, default="text")
    error_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_truncated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    truncation_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Fixed for now: describes how period_start/period_end were interpreted
    # when this report was generated ("tickets updated in range" vs. an
    # unbounded fetch snapshot when no period was given). Stored per-report
    # rather than assumed, since the semantics could change in a later
    # release and old reports must keep meaning what they said at the time.
    period_semantics: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Schedule(Base):
    __tablename__ = "schedules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connector: Mapped[str] = mapped_column(String(50), nullable=False, default="jira")
    board_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sprint_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    cron_expression: Mapped[str] = mapped_column(String(100), nullable=False)
    output_format: Mapped[str] = mapped_column(String(20), nullable=False, default="text")
    assigned_means_in_progress: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # last_run_at: the last occurrence this schedule *succeeded* at (kept
    # under its historical name for API/UI compatibility). last_attempted_at
    # is the separate cron-cursor timestamp — the last occurrence claimed
    # for dispatch regardless of outcome — so a run of failures doesn't
    # make _is_due() re-claim the same occurrence forever, and a transient
    # failure doesn't get reported as if the schedule last succeeded then.
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_attempted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReportJob(Base):
    """
    A durable unit of work: one report generation attempt (manual or from a
    schedule occurrence). Exists independently of whether a worker process
    is alive to run it — a crash mid-run leaves a `running` row a recovery
    sweep can find and requeue, instead of losing the request.
    """

    __tablename__ = "report_jobs"
    __table_args__ = (
        # The atomic claim for S3-02: a schedule cannot produce two jobs for
        # the same occurrence, even under concurrent/overlapping dispatch —
        # the database enforces it, not application-level locking.
        UniqueConstraint("schedule_id", "scheduled_for", name="uq_report_jobs_schedule_occurrence"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Client-supplied dedup key for manual (non-schedule) requests: retrying
    # the same logical request with the same key returns the existing job
    # instead of creating a duplicate. Schedule-originated jobs are deduped
    # by (schedule_id, scheduled_for) instead, so this stays NULL for those.
    idempotency_key: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=JOB_STATUS_QUEUED)

    # Request snapshot — captured at enqueue time so a job is fully
    # reproducible without depending on mutable Schedule state.
    connector: Mapped[str] = mapped_column(String(50), nullable=False)
    board_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sprint_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    output_format: Mapped[str] = mapped_column(String(20), nullable=False, default="text")
    assigned_means_in_progress: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    schedule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("schedules.id", ondelete="SET NULL"), nullable=True
    )
    # The cron occurrence this job represents, when schedule-originated.
    # Together with schedule_id this is the idempotent occurrence key.
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    report_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reports.id", ondelete="SET NULL"), nullable=True
    )
    error_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Set on either success or terminal failure — the one "this attempt is
    # over" timestamp, distinct from started_at ("this attempt began") and
    # from a hypothetical success-only timestamp, since a failed job has no
    # success time but still needs to record when it stopped running.
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReportTemplate(Base):
    __tablename__ = "report_templates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
