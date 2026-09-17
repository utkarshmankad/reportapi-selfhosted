"""Exercise report orchestration and scheduler outcomes, not just helper functions."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import settings
from app.core.report_service import ReportGenerationError, generate_report
from app.db.models import Schedule
from app.models.ticket import Ticket
from app.worker import tasks


@pytest.fixture
def database():
    db = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
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
    source = MagicMock(return_value=MagicMock(fetch=AsyncMock(return_value=[ticket, ticket])))
    monkeypatch.setattr("app.core.report_service.JiraConnector", source)
    llm = MagicMock(generate=AsyncMock(return_value=("A report", 15)))
    monkeypatch.setattr("app.core.report_service.get_llm_provider", lambda config: llm)
    report, count = await generate_report(database, "jira", "DEMO", None)
    assert count == 1
    assert "test@example.com" not in llm.generate.call_args.kwargs["user_content"]
    assert report.narrative == "A report"
    database.commit.assert_awaited_once()
    database.add.assert_called_once_with(report)


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
                return_value=[
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
    if case == "credentials":
        source.side_effect = ValueError("Missing credentials")
    if case == "fetch":
        source.return_value.fetch.side_effect = RuntimeError("offline")
    if case == "empty":
        source.return_value.fetch.return_value = []
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


@pytest.mark.asyncio
async def test_scheduler_runs_due_and_skips_future(database, monkeypatch):
    now = datetime.now(timezone.utc)
    due = Schedule(
        connector="jira",
        board_id="D",
        cron_expression="* * * * *",
        created_at=now - timedelta(minutes=2),
    )
    future = Schedule(connector="jira", board_id="D", cron_expression="0 0 1 1 *", created_at=now)
    database.execute = AsyncMock(return_value=MagicMock())
    database.execute.return_value.scalars.return_value.all.return_value = [due, future]
    session = MagicMock()
    session.return_value.__aenter__ = AsyncMock(return_value=database)
    monkeypatch.setattr(tasks, "AsyncSessionLocal", session)
    generate = AsyncMock(side_effect=ReportGenerationError(502, "offline"))
    monkeypatch.setattr(tasks, "generate_report", generate)
    assert await tasks._run_due_schedules() == 1
    generate.assert_awaited_once()
    assert due.last_run_at is not None
    assert future.last_run_at is None


@pytest.mark.asyncio
async def test_worker_always_disposes_loop_bound_pool(monkeypatch):
    dispose = AsyncMock()
    monkeypatch.setattr(tasks, "engine", MagicMock(dispose=dispose))
    monkeypatch.setattr(
        tasks, "_run_due_schedules", AsyncMock(side_effect=RuntimeError("database unavailable"))
    )
    with pytest.raises(RuntimeError):
        await tasks._run_due_schedules_and_dispose()
    dispose.assert_awaited_once()


@pytest.mark.parametrize("provider", ["openai", "anthropic", "groq", "ollama"])
def test_factory_selects_provider(monkeypatch, provider):
    from app.llm.factory import get_llm_provider

    monkeypatch.setattr(settings, "llm_provider", provider)
    for field in ("openai_api_key", "anthropic_api_key", "groq_api_key"):
        monkeypatch.setattr(settings, field, "test")
    assert get_llm_provider().__class__.__name__.lower().startswith(provider)
