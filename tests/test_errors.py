"""Unit tests for stable public error codes and request correlation (S5-04)."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.errors import RequestIdMiddleware, register_error_handlers


def _make_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)
    register_error_handlers(app)

    @app.get("/not-found")
    async def not_found():
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Widget not found")

    @app.get("/boom")
    async def boom():
        raise RuntimeError("secret db connection string leaked here")

    @app.get("/ok")
    async def ok():
        return {"ok": True}

    return app


def test_http_exception_gets_stable_code_and_request_id():
    client = TestClient(_make_app(), raise_server_exceptions=False)
    resp = client.get("/not-found")

    assert resp.status_code == 404
    body = resp.json()
    assert body["code"] == "NOT_FOUND"
    assert body["detail"] == "Widget not found"
    assert "request_id" in body
    assert resp.headers["X-Request-Id"] == body["request_id"]


def test_unhandled_exception_returns_sanitized_500():
    client = TestClient(_make_app(), raise_server_exceptions=False)
    resp = client.get("/boom")

    assert resp.status_code == 500
    body = resp.json()
    assert body["code"] == "INTERNAL_ERROR"
    assert body["detail"] == "Internal server error"
    assert "secret db connection string" not in resp.text
    assert "request_id" in body
    assert resp.headers["X-Request-Id"] == body["request_id"]


def test_every_response_carries_a_request_id_header():
    client = TestClient(_make_app(), raise_server_exceptions=False)
    resp = client.get("/ok")

    assert resp.status_code == 200
    assert "X-Request-Id" in resp.headers
