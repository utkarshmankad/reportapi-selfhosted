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

# WebhookDelivery.status values — same forward-moving shape as ReportJob,
# for the same reason: an attempt-bounded retry is a deliberate, visible
# state transition, not a silent in-place mutation.
DELIVERY_STATUS_PENDING = "pending"
DELIVERY_STATUS_SENDING = "sending"
DELIVERY_STATUS_DELIVERED = "delivered"
DELIVERY_STATUS_FAILED = "failed"


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connector: Mapped[str] = mapped_column(String(50), nullable=False)
    # Source scope this report was generated from — the actual board/sprint
    # used, not just which connector, so a report is traceable without
    # depending on a schedule or job row that may since have been deleted.
    board_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sprint_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="complete")
    model_used: Mapped[str] = mapped_column(String(100), nullable=False)
    tokens_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Ticket count actually reported on, after dedup/period filtering — the
    # same number the API returned as ticket_count at generation time, now
    # persisted so it survives past that one response.
    ticket_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # SYSTEM_PROMPT_TEMPLATE version that produced this narrative (see
    # app.core.prompt_builder.PROMPT_VERSION).
    prompt_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
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
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("report_templates.id", ondelete="SET NULL"), nullable=True
    )
    template_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # A frozen copy of the template's content at generation time. PDF
    # rendering uses this, never the live template row, so editing or
    # deleting the template afterward can never change what a past report
    # renders as — a "protected historical reference."
    template_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Schedule(Base):
    __tablename__ = "schedules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connector: Mapped[str] = mapped_column(String(50), nullable=False, default="jira")
    board_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sprint_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    cron_expression: Mapped[str] = mapped_column(String(100), nullable=False)
    # An IANA zone name (e.g. "America/New_York"), not a fixed UTC offset —
    # cron fields are evaluated as wall-clock time in this zone, so a
    # schedule stays meaning "9am local" across DST transitions instead of
    # drifting by an hour twice a year. See docs/scheduling.md for the
    # DST/missed-run policy this implies.
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
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
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("report_templates.id", ondelete="SET NULL"), nullable=True
    )

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
    # Incremented on every content/name edit. Reports snapshot this value
    # (Report.template_version) alongside a frozen content copy, so a past
    # report's template reference stays meaningful — and distinguishable
    # from a later edit — without needing a full version history table.
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # Archived templates are hidden from new-report template pickers but
    # remain fetchable by id, since past reports may still reference them.
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReportProfile(Base):
    """
    A saved, named bundle of manual-generate parameters (connector, scope,
    template, format) an operator can re-run without re-entering every
    field — the on-demand equivalent of a Schedule, which exists for
    recurring generation instead. Generating from a profile does not
    create or modify a Schedule and is not itself scheduled.
    """

    __tablename__ = "report_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    connector: Mapped[str] = mapped_column(String(50), nullable=False)
    board_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sprint_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    output_format: Mapped[str] = mapped_column(String(20), nullable=False, default="text")
    assigned_means_in_progress: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("report_templates.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class WebhookDestination(Base):
    """
    An operator-approved delivery target. `url`'s origin must be present in
    WEBHOOK_ALLOWED_ORIGINS at both creation and delivery time — the same
    operator-controlled-allowlist pattern as Jira/Ollama — since a webhook
    URL is otherwise an SSRF vector supplied by whoever can reach this API.
    """

    __tablename__ = "webhook_destinations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    # HMAC-SHA256 signing secret for the X-Webhook-Signature header — lets
    # the receiver verify a delivery actually came from this instance.
    secret: Mapped[str] = mapped_column(String(255), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WebhookDelivery(Base):
    """
    The transactional outbox: one row per (destination, report) delivery
    attempt-series, inserted in the same transaction as the report/job
    state that triggered it. A worker crash between "decided to notify"
    and "sent the HTTP request" leaves a `pending` row a delivery task can
    still pick up — nothing is lost the way an in-memory fire-and-forget
    webhook call would lose it.
    """

    __tablename__ = "webhook_deliveries"
    __table_args__ = (
        UniqueConstraint(
            "destination_id", "report_id", name="uq_webhook_deliveries_destination_report"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    destination_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("webhook_destinations.id", ondelete="CASCADE"),
        nullable=False,
    )
    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reports.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=DELIVERY_STATUS_PENDING)
    # The exact JSON body sent (and re-sent on retry) — captured once at
    # enqueue time so a delivery's content never depends on the report's
    # current state, which may have changed or been deleted by retry time.
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # NULL means "never attempted, ready now". Set on a failed attempt so
    # the periodic dispatch sweep — the *only* thing that ever dispatches a
    # delivery — skips a row that's mid-backoff instead of double-sending
    # it alongside whatever already-scheduled retry exists for it.
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
