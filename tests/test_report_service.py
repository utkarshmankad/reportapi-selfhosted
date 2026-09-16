from datetime import datetime, timedelta, timezone

from app.core.report_service import dedupe_tickets
from app.models.ticket import Ticket

NOW = datetime.now(timezone.utc)


def _ticket(**overrides):
    defaults = dict(
        id="1",
        title="Some task",
        description="",
        status="in_progress",
        assignee="alice",
        priority=None,
        labels=[],
        created_at=NOW,
        updated_at=NOW,
        sprint=None,
        url="https://example.com",
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
    stale = _ticket(
        id="26484",
        title="Fix view creation",
        status="in_progress",
        updated_at=NOW - timedelta(days=5),
    )
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
