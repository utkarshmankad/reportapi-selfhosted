"""HTTP boundary tests for the durable report job endpoints."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.db.models import ReportJob, Schedule
from app.db.session import get_db
from app.main import app


@pytest.fixture
def db():
    database = MagicMock()
    for method in ("commit", "refresh", "get", "delete", "execute", "rollback"):
        setattr(database, method, AsyncMock())
    database.get.return_value = None
    database.execute.return_value = MagicMock()
    database.execute.return_value.scalars.return_value.all.return_value = []
    database.execute.return_value.scalar_one_or_none.return_value = None

    def add(row):
        row.id = row.id or uuid4()
        row.created_at = datetime.now(timezone.utc)
        row.queued_at = getattr(row, "queued_at", None) or datetime.now(timezone.utc)
        if getattr(row, "attempts", None) is None:
            row.attempts = 0

    database.add.side_effect = add
    return database


@pytest.fixture
def client(db):
    async def override():
        yield db

    app.dependency_overrides[get_db] = override
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def _job(**overrides):
    defaults = dict(
        id=uuid4(),
        idempotency_key=None,
        status="queued",
        connector="jira",
        board_id="PROJ",
        sprint_id=None,
        output_format="text",
        assigned_means_in_progress=True,
        period_start=None,
        period_end=None,
        schedule_id=None,
        scheduled_for=None,
        report_id=None,
        error_reason=None,
        attempts=0,
        queued_at=datetime.now(timezone.utc),
        started_at=None,
        finished_at=None,
        created_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return ReportJob(**defaults)


def test_create_job_dispatches_and_returns_queued(client, db, monkeypatch):
    delay = MagicMock()
    monkeypatch.setattr("app.worker.tasks.execute_report_job.delay", delay)

    result = client.post("/api/report/jobs", json={"connector": "jira", "board_id": "PROJ"})

    assert result.status_code == 200
    body = result.json()
    assert body["status"] == "queued"
    assert body["connector"] == "jira"
    delay.assert_called_once()


def test_create_job_persists_selected_template_id(client, db, monkeypatch):
    delay = MagicMock()
    monkeypatch.setattr("app.worker.tasks.execute_report_job.delay", delay)
    template_id = str(uuid4())

    result = client.post(
        "/api/report/jobs",
        json={"connector": "jira", "board_id": "PROJ", "template_id": template_id},
    )

    assert result.status_code == 200
    assert result.json()["template_id"] == template_id


def test_create_job_idempotent_replay_does_not_redispatch(client, db, monkeypatch):
    existing = _job(idempotency_key="abc-123")
    db.execute.return_value.scalar_one_or_none.return_value = existing
    delay = MagicMock()
    monkeypatch.setattr("app.worker.tasks.execute_report_job.delay", delay)

    result = client.post(
        "/api/report/jobs",
        json={"connector": "jira", "board_id": "PROJ", "idempotency_key": "abc-123"},
    )

    assert result.status_code == 200
    assert result.json()["id"] == str(existing.id)
    delay.assert_not_called()


def test_create_job_rejects_malformed_idempotency_key(client):
    result = client.post(
        "/api/report/jobs",
        json={"connector": "jira", "board_id": "PROJ", "idempotency_key": "has a space"},
    )
    assert result.status_code == 422


def test_get_job_returns_current_state(client, db):
    job = _job(status="succeeded", report_id=uuid4())
    db.get.return_value = job

    result = client.get(f"/api/report/jobs/{job.id}")

    assert result.status_code == 200
    assert result.json()["status"] == "succeeded"
    assert result.json()["report_id"] == str(job.report_id)


def test_get_job_missing_returns_404(client):
    result = client.get(f"/api/report/jobs/{uuid4()}")
    assert result.status_code == 404


def test_list_jobs_returns_rows(client, db):
    db.execute.return_value.scalars.return_value.all.return_value = [_job(), _job()]
    result = client.get("/api/report/jobs")
    assert result.status_code == 200
    assert len(result.json()) == 2


def test_schedule_run_history_returns_jobs(client, db):
    schedule = Schedule(
        id=uuid4(),
        connector="jira",
        board_id="PROJ",
        cron_expression="0 9 * * 1",
        created_at=datetime.now(timezone.utc),
    )
    db.get.return_value = schedule
    db.execute.return_value.scalars.return_value.all.return_value = [
        _job(schedule_id=schedule.id, scheduled_for=datetime.now(timezone.utc))
    ]

    result = client.get(f"/api/schedule/{schedule.id}/jobs")

    assert result.status_code == 200
    assert len(result.json()) == 1


def test_schedule_run_history_missing_schedule_returns_404(client):
    result = client.get(f"/api/schedule/{uuid4()}/jobs")
    assert result.status_code == 404
