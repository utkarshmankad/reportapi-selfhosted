from fastapi.testclient import TestClient

from app.main import app


def test_health_is_public():
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
