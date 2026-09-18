"""Dependency readiness and scheduler-freshness checks."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client


def test_health_is_always_ok(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_readiness_all_healthy(client, monkeypatch):
    conn = AsyncMock()
    conn.execute = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(
        "app.api.routes.health.engine", MagicMock(connect=MagicMock(return_value=ctx))
    )

    redis_client = AsyncMock()
    redis_client.ping = AsyncMock(return_value=True)
    redis_client.get = AsyncMock(return_value=None)
    redis_client.aclose = AsyncMock()
    monkeypatch.setattr(
        "app.api.routes.health.Redis.from_url", MagicMock(return_value=redis_client)
    )

    result = client.get("/health/ready")
    assert result.status_code == 200
    body = result.json()
    assert body["checks"]["database"] == "ok"
    assert body["checks"]["redis"] == "ok"
    assert body["checks"]["scheduler"] == "unknown"
    assert body["status"] == "ok"


def test_readiness_reports_unreachable_database(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.health.engine",
        MagicMock(connect=MagicMock(side_effect=RuntimeError("down"))),
    )
    redis_client = AsyncMock()
    redis_client.ping = AsyncMock(return_value=True)
    redis_client.get = AsyncMock(return_value=None)
    redis_client.aclose = AsyncMock()
    monkeypatch.setattr(
        "app.api.routes.health.Redis.from_url", MagicMock(return_value=redis_client)
    )

    result = client.get("/health/ready")
    body = result.json()
    assert body["checks"]["database"] == "unreachable"
    assert body["status"] == "degraded"


def test_readiness_reports_unreachable_redis(client, monkeypatch):
    conn = AsyncMock()
    conn.execute = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(
        "app.api.routes.health.engine", MagicMock(connect=MagicMock(return_value=ctx))
    )
    monkeypatch.setattr(
        "app.api.routes.health.Redis.from_url", MagicMock(side_effect=RuntimeError("down"))
    )

    result = client.get("/health/ready")
    body = result.json()
    assert body["checks"]["redis"] == "unreachable"
    assert body["checks"]["scheduler"] == "unknown"
    assert body["status"] == "degraded"


def test_readiness_reports_fresh_scheduler_heartbeat(client, monkeypatch):
    import time

    conn = AsyncMock()
    conn.execute = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(
        "app.api.routes.health.engine", MagicMock(connect=MagicMock(return_value=ctx))
    )

    redis_client = AsyncMock()
    redis_client.ping = AsyncMock(return_value=True)
    redis_client.get = AsyncMock(return_value=str(time.time()).encode())
    redis_client.aclose = AsyncMock()
    monkeypatch.setattr(
        "app.api.routes.health.Redis.from_url", MagicMock(return_value=redis_client)
    )

    result = client.get("/health/ready")
    assert result.json()["checks"]["scheduler"] == "ok"


def test_readiness_reports_stale_scheduler_heartbeat(client, monkeypatch):
    import time

    conn = AsyncMock()
    conn.execute = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(
        "app.api.routes.health.engine", MagicMock(connect=MagicMock(return_value=ctx))
    )

    redis_client = AsyncMock()
    redis_client.ping = AsyncMock(return_value=True)
    redis_client.get = AsyncMock(return_value=str(time.time() - 10_000).encode())
    redis_client.aclose = AsyncMock()
    monkeypatch.setattr(
        "app.api.routes.health.Redis.from_url", MagicMock(return_value=redis_client)
    )

    result = client.get("/health/ready")
    body = result.json()
    assert body["checks"]["scheduler"] == "stale"
    assert body["status"] == "degraded"
