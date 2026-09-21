"""HTTP boundary tests for report profile CRUD endpoints."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.db.models import ReportProfile
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

    def add(row):
        row.id = row.id or uuid4()
        now = datetime.now(timezone.utc)
        row.created_at = now
        row.updated_at = now

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


def test_create_profile_returns_created_profile(client):
    result = client.post(
        "/api/report-profiles",
        json={"name": "Weekly demo", "connector": "jira", "board_id": "DEMO"},
    )
    assert result.status_code == 200
    body = result.json()
    assert body["name"] == "Weekly demo"
    assert body["connector"] == "jira"
    assert body["output_format"] == "text"


def test_create_profile_rejects_missing_scope(client):
    result = client.post(
        "/api/report-profiles",
        json={"name": "No scope", "connector": "jira"},
    )
    assert result.status_code == 422


def test_get_missing_profile_is_404(client):
    result = client.get(f"/api/report-profiles/{uuid4()}")
    assert result.status_code == 404


def test_update_missing_profile_is_404(client):
    result = client.put(f"/api/report-profiles/{uuid4()}", json={"name": "New name"})
    assert result.status_code == 404


def test_update_profile_only_changes_provided_fields(client, db):
    existing = ReportProfile(
        id=uuid4(),
        name="Old name",
        connector="jira",
        board_id="DEMO",
        sprint_id=None,
        output_format="text",
        assigned_means_in_progress=True,
        template_id=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.get.return_value = existing

    result = client.put(f"/api/report-profiles/{existing.id}", json={"name": "New name"})

    assert result.status_code == 200
    body = result.json()
    assert body["name"] == "New name"
    assert body["board_id"] == "DEMO"


def test_delete_missing_profile_is_404(client):
    result = client.delete(f"/api/report-profiles/{uuid4()}")
    assert result.status_code == 404


def test_delete_existing_profile_returns_204(client, db):
    existing = ReportProfile(id=uuid4(), name="X", connector="jira", board_id="DEMO")
    db.get.return_value = existing

    result = client.delete(f"/api/report-profiles/{existing.id}")

    assert result.status_code == 204
    db.delete.assert_awaited_once_with(existing)


def test_generate_from_missing_profile_is_404(client):
    result = client.post(f"/api/report-profiles/{uuid4()}/generate", json={})
    assert result.status_code == 404


def test_generate_from_profile_rejects_inverted_period(client, db):
    existing = ReportProfile(id=uuid4(), name="X", connector="jira", board_id="DEMO")
    db.get.return_value = existing

    result = client.post(
        f"/api/report-profiles/{existing.id}/generate",
        json={"period_start": "2026-02-01T00:00:00Z", "period_end": "2026-01-01T00:00:00Z"},
    )

    assert result.status_code == 422
