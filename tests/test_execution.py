"""Exercise report orchestration and scheduler outcomes, not just helper functions."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import settings
from app.connectors.base import FetchResult
from app.core.report_service import ReportGenerationError, generate_report
from app.db.models import Schedule
from app.models.ticket import Ticket
from app.worker import tasks


@pytest.fixture
def database():
    db = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.rollback = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_generation_scrubs_before_provider_and_persists(database, monkeypatch):
    ticket = Ticket(
        id="DEMO-1",
        title="Email test@example.com",
        description="test@example.com",
        status="done",
        assignee=None,
        priority=None,
        labels=[],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        url="https://example.com",
        sprint=None,
    )
    source = MagicMock(
        return_value=MagicMock(fetch=AsyncMock(return_value=FetchResult(tickets=[ticket, ticket])))
    )
    monkeypatch.setattr("app.core.report_service.JiraConnector", source)
    llm = MagicMock(generate=AsyncMock(return_value=("A report", 15, False)))
    monkeypatch.setattr("app.core.report_service.get_llm_provider", lambda config: llm)
    report, count = await generate_report(database, "jira", "DEMO", None)
    assert count == 1
    assert "test@example.com" not in llm.generate.call_args.kwargs["user_content"]
    assert report.narrative == "A report"
    assert report.is_truncated is False
    database.commit.assert_awaited_once()
    database.add.assert_called_once_with(report)


@pytest.mark.asyncio
async def test_empty_provider_response_raises(database, monkeypatch):
    now = datetime.now(timezone.utc)
    ticket = Ticket(
        id="1",
        title="t",
        description="",
        status="todo",
        assignee=None,
        priority=None,
        labels=[],
        created_at=now,
        updated_at=now,
        url="https://example.com",
        sprint=None,
    )
    source = MagicMock(
        return_value=MagicMock(fetch=AsyncMock(return_value=FetchResult(tickets=[ticket])))
    )
    monkeypatch.setattr("app.core.report_service.JiraConnector", source)
    llm = MagicMock(generate=AsyncMock(return_value=("   ", 5, False)))
    monkeypatch.setattr("app.core.report_service.get_llm_provider", lambda config: llm)

    with pytest.raises(ReportGenerationError) as error:
        await generate_report(database, "jira", "D", None)
    assert error.value.status_code == 502
    database.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_provider_truncation_marks_report_partial(database, monkeypatch):
    now = datetime.now(timezone.utc)
    ticket = Ticket(
        id="1",
        title="t",
        description="",
        status="todo",
        assignee=None,
        priority=None,
        labels=[],
        created_at=now,
        updated_at=now,
        url="https://example.com",
        sprint=None,
    )
    source = MagicMock(
        return_value=MagicMock(fetch=AsyncMock(return_value=FetchResult(tickets=[ticket])))
    )
    monkeypatch.setattr("app.core.report_service.JiraConnector", source)
    llm = MagicMock(generate=AsyncMock(return_value=("Cut off mid-", 5, True)))
    monkeypatch.setattr("app.core.report_service.get_llm_provider", lambda config: llm)

    report, _ = await generate_report(database, "jira", "D", None)
    assert report.status == "partial"
    assert report.is_truncated is True
    assert "output token limit" in report.truncation_reason


@pytest.mark.asyncio
async def test_input_budget_exclusion_marks_report_partial(database, monkeypatch):
    now = datetime.now(timezone.utc)
    tickets = [
        Ticket(
            id=str(i),
            title=f"Task {i}",
            description="",
            status="todo",
            assignee=None,
            priority=None,
            labels=[],
            created_at=now,
            updated_at=now,
            url="https://example.com",
            sprint=None,
        )
        for i in range(50)
    ]
    source = MagicMock(
        return_value=MagicMock(fetch=AsyncMock(return_value=FetchResult(tickets=tickets)))
    )
    monkeypatch.setattr("app.core.report_service.JiraConnector", source)
    monkeypatch.setattr("app.config.settings.max_tokens_input", 300)
    llm = MagicMock(generate=AsyncMock(return_value=("A report", 15, False)))
    monkeypatch.setattr("app.core.report_service.get_llm_provider", lambda config: llm)

    report, count = await generate_report(database, "jira", "D", None)
    assert count == 50
    assert report.status == "partial"
    assert report.is_truncated is True
    assert "input size budget" in report.truncation_reason


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case,status",
    [
        ("unknown", 400),
        ("missing_scope", 422),
        ("credentials", 500),
        ("fetch", 502),
        ("empty", 422),
        ("llm", 500),
    ],
)
async def test_generation_failures_do_not_commit(database, monkeypatch, case, status):
    now = datetime.now(timezone.utc)
    source = MagicMock(
        return_value=MagicMock(
            fetch=AsyncMock(
                return_value=FetchResult(
                    tickets=[
                        Ticket(
                            id="1",
                            title="t",
                            description="",
                            status="todo",
                            assignee=None,
                            priority=None,
                            labels=[],
                            created_at=now,
                            updated_at=now,
                            url="https://example.com",
                            sprint=None,
                        )
                    ]
                )
            )
        )
    )
    if case == "credentials":
        source.side_effect = ValueError("Missing credentials")
    if case == "fetch":
        source.return_value.fetch.side_effect = RuntimeError("offline")
    if case == "empty":
        source.return_value.fetch.return_value = FetchResult(tickets=[])
    monkeypatch.setattr("app.core.report_service.JiraConnector", source)
    monkeypatch.setattr(
        "app.core.report_service.get_llm_provider",
        MagicMock(side_effect=RuntimeError("Unavailable")),
    )
    with pytest.raises(ReportGenerationError) as error:
        await generate_report(
            database,
            "unknown" if case == "unknown" else "jira",
            None if case == "missing_scope" else "D",
            None,
        )
    assert error.value.status_code == status
    database.commit.assert_not_awaited()


def test_due_occurrences_includes_due_and_excludes_future():
    now = datetime.now(timezone.utc)
    due = Schedule(
        connector="jira",
        board_id="D",
        cron_expression="* * * * *",
        created_at=now - timedelta(minutes=2),
    )
    future = Schedule(connector="jira", board_id="D", cron_expression="0 0 1 1 *", created_at=now)

    assert len(tasks._due_occurrences(due, now, tasks.MAX_BACKFILL_OCCURRENCES)) >= 1
    assert tasks._due_occurrences(future, now, tasks.MAX_BACKFILL_OCCURRENCES) == []


def test_due_occurrences_bounded_by_max_count():
    now = datetime.now(timezone.utc)
    long_overdue = Schedule(
        connector="jira",
        board_id="D",
        cron_expression="* * * * *",
        created_at=now - timedelta(days=1),
    )
    occurrences = tasks._due_occurrences(long_overdue, now, 3)
    assert len(occurrences) == 3
    assert occurrences == sorted(occurrences)


@pytest.mark.asyncio
async def test_dispatch_due_schedules_always_disposes_loop_bound_pool(monkeypatch):
    dispose = AsyncMock()
    monkeypatch.setattr(tasks, "engine", MagicMock(dispose=dispose))
    monkeypatch.setattr(
        tasks,
        "_dispatch_due_schedules",
        AsyncMock(side_effect=RuntimeError("database unavailable")),
    )
    with pytest.raises(RuntimeError):
        await tasks._dispatch_due_schedules_and_dispose()
    dispose.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_report_job_always_disposes_loop_bound_pool(monkeypatch):
    dispose = AsyncMock()
    monkeypatch.setattr(tasks, "engine", MagicMock(dispose=dispose))
    monkeypatch.setattr(
        tasks, "_execute_report_job", AsyncMock(side_effect=RuntimeError("database unavailable"))
    )
    with pytest.raises(RuntimeError):
        await tasks._execute_report_job_and_dispose("job-id")
    dispose.assert_awaited_once()


@pytest.mark.asyncio
async def test_recover_stuck_report_jobs_always_disposes_loop_bound_pool(monkeypatch):
    dispose = AsyncMock()
    monkeypatch.setattr(tasks, "engine", MagicMock(dispose=dispose))
    monkeypatch.setattr(
        tasks,
        "_recover_stuck_report_jobs",
        AsyncMock(side_effect=RuntimeError("database unavailable")),
    )
    with pytest.raises(RuntimeError):
        await tasks._recover_stuck_report_jobs_and_dispose()
    dispose.assert_awaited_once()


def test_execute_report_job_task_reenqueues_on_retry(monkeypatch):
    monkeypatch.setattr(tasks, "_execute_report_job_and_dispose", AsyncMock(return_value="queued"))
    apply_async = MagicMock()
    monkeypatch.setattr(tasks.execute_report_job, "apply_async", apply_async)

    status = tasks.execute_report_job("job-id")

    assert status == "queued"
    apply_async.assert_called_once_with(args=["job-id"], countdown=tasks.RETRY_COUNTDOWN_SECONDS)


def test_execute_report_job_task_does_not_reenqueue_on_terminal_status(monkeypatch):
    monkeypatch.setattr(
        tasks, "_execute_report_job_and_dispose", AsyncMock(return_value="succeeded")
    )
    apply_async = MagicMock()
    monkeypatch.setattr(tasks.execute_report_job, "apply_async", apply_async)

    status = tasks.execute_report_job("job-id")

    assert status == "succeeded"
    apply_async.assert_not_called()


@pytest.mark.asyncio
async def test_recover_stuck_report_jobs_redispatches_queued(monkeypatch):
    queued_job = MagicMock(status="queued", id="job-1")
    failed_job = MagicMock(status="failed", id="job-2")
    monkeypatch.setattr(
        tasks, "recover_stuck_jobs", AsyncMock(return_value=[queued_job, failed_job])
    )
    delay = MagicMock()
    monkeypatch.setattr(tasks.execute_report_job, "delay", delay)
    db = MagicMock()
    session = MagicMock()
    session.return_value.__aenter__ = AsyncMock(return_value=db)
    session.return_value.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(tasks, "AsyncSessionLocal", session)

    count = await tasks._recover_stuck_report_jobs()

    assert count == 2
    delay.assert_called_once_with("job-1")


@pytest.mark.parametrize("provider", ["openai", "anthropic", "groq", "ollama"])
def test_factory_selects_provider(monkeypatch, provider):
    from app.llm.factory import get_llm_provider

    monkeypatch.setattr(settings, "llm_provider", provider)
    for field in ("openai_api_key", "anthropic_api_key", "groq_api_key"):
        monkeypatch.setattr(settings, field, "test")
    assert get_llm_provider().__class__.__name__.lower().startswith(provider)


@pytest.mark.asyncio
async def test_period_filter_excludes_tickets_outside_range(database, monkeypatch):
    from app.core.report_service import filter_by_period

    old = Ticket(
        id="1",
        title="old",
        description="",
        status="todo",
        assignee=None,
        priority=None,
        labels=[],
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        url="https://example.com",
        sprint=None,
    )
    recent = Ticket(
        id="2",
        title="recent",
        description="",
        status="todo",
        assignee=None,
        priority=None,
        labels=[],
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        url="https://example.com",
        sprint=None,
    )

    result = filter_by_period(
        [old, recent],
        datetime(2026, 5, 1, tzinfo=timezone.utc),
        datetime(2026, 7, 1, tzinfo=timezone.utc),
    )
    assert [t.id for t in result] == ["2"]

    assert filter_by_period([old, recent], None, None) == [old, recent]


@pytest.mark.asyncio
async def test_generate_report_rejects_period_with_no_matching_tickets(database, monkeypatch):
    ticket = Ticket(
        id="1",
        title="t",
        description="",
        status="todo",
        assignee=None,
        priority=None,
        labels=[],
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        url="https://example.com",
        sprint=None,
    )
    source = MagicMock(
        return_value=MagicMock(fetch=AsyncMock(return_value=FetchResult(tickets=[ticket])))
    )
    monkeypatch.setattr("app.core.report_service.JiraConnector", source)

    with pytest.raises(ReportGenerationError) as error:
        await generate_report(
            database,
            "jira",
            "D",
            None,
            period_start=datetime(2026, 6, 1, tzinfo=timezone.utc),
            period_end=datetime(2026, 7, 1, tzinfo=timezone.utc),
        )
    assert error.value.status_code == 422


@pytest.mark.asyncio
async def test_generate_report_persists_period_and_semantics(database, monkeypatch):
    ticket = Ticket(
        id="1",
        title="t",
        description="",
        status="todo",
        assignee=None,
        priority=None,
        labels=[],
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        url="https://example.com",
        sprint=None,
    )
    source = MagicMock(
        return_value=MagicMock(fetch=AsyncMock(return_value=FetchResult(tickets=[ticket])))
    )
    monkeypatch.setattr("app.core.report_service.JiraConnector", source)
    llm = MagicMock(generate=AsyncMock(return_value=("A report", 15, False)))
    monkeypatch.setattr("app.core.report_service.get_llm_provider", lambda config: llm)

    start = datetime(2026, 5, 1, tzinfo=timezone.utc)
    end = datetime(2026, 7, 1, tzinfo=timezone.utc)
    report, count = await generate_report(
        database, "jira", "D", None, period_start=start, period_end=end
    )
    assert count == 1
    assert report.period_start == start
    assert report.period_end == end
    assert report.period_semantics == "tickets_updated_in_range"


@pytest.mark.asyncio
async def test_generate_report_no_period_uses_unbounded_semantics(database, monkeypatch):
    ticket = Ticket(
        id="1",
        title="t",
        description="",
        status="todo",
        assignee=None,
        priority=None,
        labels=[],
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        url="https://example.com",
        sprint=None,
    )
    source = MagicMock(
        return_value=MagicMock(fetch=AsyncMock(return_value=FetchResult(tickets=[ticket])))
    )
    monkeypatch.setattr("app.core.report_service.JiraConnector", source)
    llm = MagicMock(generate=AsyncMock(return_value=("A report", 15, False)))
    monkeypatch.setattr("app.core.report_service.get_llm_provider", lambda config: llm)

    report, _ = await generate_report(database, "jira", "D", None)
    assert report.period_start is None
    assert report.period_end is None
    assert report.period_semantics == "unbounded_fetch_snapshot"


@pytest.mark.asyncio
async def test_persistence_failure_rolls_back_and_raises(database, monkeypatch):
    now = datetime.now(timezone.utc)
    ticket = Ticket(
        id="1",
        title="t",
        description="",
        status="todo",
        assignee=None,
        priority=None,
        labels=[],
        created_at=now,
        updated_at=now,
        url="https://example.com",
        sprint=None,
    )
    source = MagicMock(
        return_value=MagicMock(fetch=AsyncMock(return_value=FetchResult(tickets=[ticket])))
    )
    monkeypatch.setattr("app.core.report_service.JiraConnector", source)
    llm = MagicMock(generate=AsyncMock(return_value=("A report", 15, False)))
    monkeypatch.setattr("app.core.report_service.get_llm_provider", lambda config: llm)
    database.commit.side_effect = RuntimeError("db unavailable")

    with pytest.raises(ReportGenerationError) as error:
        await generate_report(database, "jira", "D", None)
    assert error.value.status_code == 500
    database.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_report_job_returns_new_queued_job(database, monkeypatch):
    from app.core.job_service import create_report_job

    database.execute = AsyncMock(return_value=MagicMock())
    database.execute.return_value.scalar_one_or_none = MagicMock(return_value=None)
    job, created = await create_report_job(
        database, connector="jira", board_id="PROJ", sprint_id=None
    )
    assert created is True
    assert job.status == "queued"
    database.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_report_job_idempotent_hit_skips_insert(database, monkeypatch):
    from app.core.job_service import create_report_job
    from app.db.models import ReportJob

    existing = ReportJob(connector="jira", board_id="PROJ", idempotency_key="k1")
    database.execute = AsyncMock(return_value=MagicMock())
    database.execute.return_value.scalar_one_or_none = MagicMock(return_value=existing)

    job, created = await create_report_job(
        database, connector="jira", board_id="PROJ", sprint_id=None, idempotency_key="k1"
    )
    assert created is False
    assert job is existing
    database.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_dispatch_due_schedules_claims_and_dispatches(monkeypatch):
    now = datetime.now(timezone.utc)
    due = Schedule(
        id="s1",
        connector="jira",
        board_id="D",
        cron_expression="* * * * *",
        created_at=now - timedelta(minutes=2),
        active=True,
    )
    db = MagicMock()
    db.commit = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock())
    db.execute.return_value.scalars.return_value.all.return_value = [due]
    session = MagicMock()
    session.return_value.__aenter__ = AsyncMock(return_value=db)
    session.return_value.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(tasks, "AsyncSessionLocal", session)

    fake_job = MagicMock(id="job-1")
    monkeypatch.setattr(tasks, "claim_schedule_occurrences", AsyncMock(return_value=[fake_job]))
    delay = MagicMock()
    monkeypatch.setattr(tasks.execute_report_job, "delay", delay)

    dispatched = await tasks._dispatch_due_schedules()

    assert dispatched == 1
    delay.assert_called_once_with("job-1")
    assert due.last_attempted_at is not None
