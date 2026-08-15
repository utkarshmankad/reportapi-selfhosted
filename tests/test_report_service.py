from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from app.models.ticket import Ticket
from app.core.report_service import dedupe_tickets, generate_report

NOW = datetime.now(timezone.utc)


def _ticket(**overrides):
    defaults = dict(
        id="1", title="Some task", description="", status="in_progress",
        assignee="alice", priority=None, labels=[], created_at=NOW,
        updated_at=NOW, sprint=None, url="https://example.com",
    )
    defaults.update(overrides)
    return Ticket(**defaults)


def test_duplicate_id_collapses_to_one_ticket():
    tickets = [
        _ticket(id="26484", title="Fix view creation", updated_at=NOW - timedelta(days=2)),
        _ticket(id="26484", title="Fix view creation", updated_at=NOW - timedelta(days=2)),
    ]
    result = dedupe_tickets(tickets)
    assert len(result) == 1
    assert result[0].id == "26484"


def test_duplicate_id_keeps_most_recently_updated_record():
    stale = _ticket(id="26484", title="Fix view creation", status="in_progress", updated_at=NOW - timedelta(days=5))
    fresh = _ticket(id="26484", title="Fix view creation", status="blocked", updated_at=NOW)
    result = dedupe_tickets([stale, fresh])
    assert len(result) == 1
    assert result[0].status == "blocked"


def test_distinct_ids_are_all_kept():
    tickets = [_ticket(id="1"), _ticket(id="2"), _ticket(id="3")]
    result = dedupe_tickets(tickets)
    assert len(result) == 3


def test_empty_list_returns_empty():
    assert dedupe_tickets([]) == []


async def _run_generate_report_with_tickets(tickets):
    mock_connector = MagicMock()
    mock_connector.fetch = AsyncMock(return_value=tickets)
    mock_llm = MagicMock()
    mock_llm.generate = AsyncMock(return_value=("narrative", 10))
    db = MagicMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    with patch("app.core.report_service.GitHubConnector", return_value=mock_connector), \
         patch("app.core.report_service.get_llm_provider", return_value=mock_llm):
        return await generate_report(db=db, connector="github", board_id="x/y", sprint_id=None)


@pytest.mark.asyncio
async def test_generate_report_logs_warning_when_source_data_has_duplicate(caplog):
    dupe = [
        _ticket(id="26484", title="Fix view creation", assignee="yuhao-su"),
        _ticket(id="26484", title="Fix view creation", assignee="yuhao-su"),
    ]
    with caplog.at_level("WARNING", logger="app.core.report_service"):
        report, ticket_count = await _run_generate_report_with_tickets(dupe)

    assert ticket_count == 1
    assert any("duplicate id(s) in source data: ['26484']" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_generate_report_does_not_warn_when_no_duplicates(caplog):
    clean = [_ticket(id="1"), _ticket(id="2")]
    with caplog.at_level("WARNING", logger="app.core.report_service"):
        report, ticket_count = await _run_generate_report_with_tickets(clean)

    assert ticket_count == 2
    assert not any("duplicate id(s)" in r.message for r in caplog.records)
