"""HTTP boundary tests for webhook destination/delivery endpoints."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.db.models import WebhookDelivery, WebhookDestination
from app.db.session import get_db
from app.main import app


@pytest.fixture(autouse=True)
def allow_webhook_origin(monkeypatch):
    monkeypatch.setattr(
        "app.config.settings.webhook_allowed_origins", "https://hooks.example.com:443"
    )


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
        row.created_at = datetime.now(timezone.utc)
        if isinstance(row, WebhookDelivery) and getattr(row, "attempts", None) is None:
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


def test_create_destination_returns_secret_once(client):
    result = client.post(
        "/api/webhooks/destinations",
        json={"name": "Slack relay", "url": "https://hooks.example.com/x"},
    )
    assert result.status_code == 200
    body = result.json()
    assert "secret" in body
    assert len(body["secret"]) >= 32


def test_create_destination_rejects_disallowed_origin(client):
    result = client.post(
        "/api/webhooks/destinations",
        json={"name": "Evil", "url": "https://attacker.example.com/x"},
    )
    assert result.status_code == 422


def test_create_destination_rejects_non_http_url(client):
    result = client.post(
        "/api/webhooks/destinations",
        json={"name": "Bad", "url": "ftp://hooks.example.com/x"},
    )
    assert result.status_code == 422


def test_list_destinations(client, db):
    destination = WebhookDestination(
        id=uuid4(),
        name="Slack relay",
        url="https://hooks.example.com/x",
        secret="s",
        active=True,
        created_at=datetime.now(timezone.utc),
    )
    db.execute.return_value.scalars.return_value.all.return_value = [destination]
    result = client.get("/api/webhooks/destinations")
    assert result.status_code == 200
    assert len(result.json()) == 1
    assert "secret" not in result.json()[0]


def test_update_destination(client, db):
    destination = WebhookDestination(
        id=uuid4(),
        name="Old",
        url="https://hooks.example.com/x",
        secret="s",
        active=True,
        created_at=datetime.now(timezone.utc),
    )
    db.get.return_value = destination
    result = client.put(
        f"/api/webhooks/destinations/{destination.id}",
        json={"name": "New", "url": "https://hooks.example.com/y", "active": False},
    )
    assert result.status_code == 200
    assert result.json()["name"] == "New"
    assert result.json()["active"] is False


def test_update_destination_missing_returns_404(client):
    result = client.put(
        f"/api/webhooks/destinations/{uuid4()}",
        json={"name": "New", "url": "https://hooks.example.com/y"},
    )
    assert result.status_code == 404


def test_delete_destination(client, db):
    destination = WebhookDestination(
        id=uuid4(),
        name="Old",
        url="https://hooks.example.com/x",
        secret="s",
        active=True,
        created_at=datetime.now(timezone.utc),
    )
    db.get.return_value = destination
    assert client.delete(f"/api/webhooks/destinations/{destination.id}").status_code == 204


def test_delete_destination_missing_returns_404(client):
    assert client.delete(f"/api/webhooks/destinations/{uuid4()}").status_code == 404


def test_list_deliveries(client, db):
    delivery = WebhookDelivery(
        id=uuid4(),
        destination_id=uuid4(),
        report_id=uuid4(),
        status="delivered",
        payload="{}",
        attempts=1,
        created_at=datetime.now(timezone.utc),
    )
    db.execute.return_value.scalars.return_value.all.return_value = [delivery]
    result = client.get("/api/webhooks/deliveries")
    assert result.status_code == 200
    assert len(result.json()) == 1


def test_retry_delivery(client, db):
    delivery = WebhookDelivery(
        id=uuid4(),
        destination_id=uuid4(),
        report_id=uuid4(),
        status="failed",
        payload="{}",
        attempts=5,
        created_at=datetime.now(timezone.utc),
    )
    db.get.return_value = delivery
    result = client.post(f"/api/webhooks/deliveries/{delivery.id}/retry")
    assert result.status_code == 200
    assert result.json()["status"] == "pending"


def test_retry_delivery_missing_returns_404(client):
    result = client.post(f"/api/webhooks/deliveries/{uuid4()}/retry")
    assert result.status_code == 404
