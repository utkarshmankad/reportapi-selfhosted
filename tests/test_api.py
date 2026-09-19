"""HTTP boundary tests: authentication, validation, CRUD, exports and config."""

import ipaddress
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.core.report_service import ReportGenerationError
from app.db.models import Report, ReportTemplate, Schedule
from app.db.session import get_db
from app.main import app


@pytest.fixture
def db():
    database = MagicMock()
    for method in ("commit", "refresh", "get", "delete", "execute"):
        setattr(database, method, AsyncMock())
    database.get.return_value = None
    database.execute.return_value = MagicMock()
    database.execute.return_value.scalars.return_value.all.return_value = []
    database.execute.return_value.scalar_one.return_value = 0

    def add(row):
        row.id = row.id or uuid4()
        row.created_at = datetime.now(timezone.utc)
        if isinstance(row, ReportTemplate):
            if getattr(row, "version", None) is None:
                row.version = 1
            if getattr(row, "archived", None) is None:
                row.archived = False
        if isinstance(row, Report):
            if getattr(row, "ticket_count", None) is None:
                row.ticket_count = 0
            if getattr(row, "prompt_version", None) is None:
                row.prompt_version = 1

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


def report():
    return Report(
        id=uuid4(),
        connector="jira",
        board_id="DEMO",
        sprint_id=None,
        status="complete",
        narrative="Released safely",
        model_used="test-model",
        tokens_used=20,
        ticket_count=4,
        prompt_version=1,
        output_format="text",
        is_truncated=False,
        truncation_reason=None,
        template_id=None,
        template_version=None,
        created_at=datetime.now(timezone.utc),
    )


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("GET", "/api/config", None),
        ("GET", "/api/reports", None),
        ("POST", "/api/report/generate", {"connector": "jira", "board_id": "DEMO"}),
        ("GET", "/api/schedule", None),
        ("POST", "/api/schedule", {}),
        ("GET", "/api/templates", None),
        ("POST", "/api/templates", {}),
        ("GET", f"/api/report/{uuid4()}/render", None),
        ("DELETE", f"/api/report/{uuid4()}", None),
        ("PUT", f"/api/schedule/{uuid4()}", {}),
        ("DELETE", f"/api/templates/{uuid4()}", None),
    ],
)
def test_all_data_endpoints_require_auth(client, monkeypatch, method, path, body):
    monkeypatch.setattr(settings, "config_api_token", "test-secret")
    assert client.request(method, path, json=body).status_code == 401
    assert (
        client.request(method, path, json=body, headers={"X-Config-Token": "wrong"}).status_code
        == 401
    )
    assert client.get("/api/config", headers={"X-Config-Token": "test-secret"}).status_code == 200


def test_report_lifecycle_and_exports(client, db, monkeypatch):
    row = report()
    generate = AsyncMock(return_value=(row, 4))
    monkeypatch.setattr("app.api.routes.report.generate_report", generate)
    result = client.post("/api/report/generate", json={"connector": "jira", "board_id": "DEMO"})
    assert result.status_code == 200
    assert result.json()["ticket_count"] == 4
    db.get.return_value = row
    db.execute.return_value.scalars.return_value.all.return_value = [row]
    assert client.get("/api/reports").json()[0]["id"] == str(row.id)
    assert client.get(f"/api/report/{row.id}").json()["narrative"] == row.narrative
    for format in ("text", "markdown", "pdf"):
        response = client.get(f"/api/report/{row.id}/render?format={format}")
        assert response.status_code == 200
        if format == "pdf":
            assert response.content.startswith(b"%PDF")
        else:
            assert row.narrative in response.text
    assert client.get(f"/api/report/{row.id}/render?format=invalid").status_code == 422
    assert client.delete(f"/api/report/{row.id}").status_code == 204
    db.delete.assert_awaited_with(row)
    assert client.get("/api/reports?limit=101").status_code == 422


def test_report_missing_and_generation_failures(client, monkeypatch):
    for suffix in ("", "/render"):
        assert client.get(f"/api/report/{uuid4()}{suffix}").status_code == 404
    assert client.delete(f"/api/report/{uuid4()}").status_code == 404
    assert client.post("/api/report/generate", json={"connector": "jira"}).status_code == 422
    assert (
        client.post(
            "/api/report/generate", json={"connector": "github", "sprint_id": "1"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/report/generate",
            json={"connector": "jira", "board_id": "D", "template_id": str(uuid4())},
        ).status_code
        == 422
    )
    monkeypatch.setattr(
        "app.api.routes.report.generate_report",
        AsyncMock(side_effect=ReportGenerationError(502, "Source failed")),
    )
    result = client.post("/api/report/generate", json={"connector": "jira", "board_id": "D"})
    assert result.status_code == 502


def test_template_crud_and_render_validation(client, db):
    payload = {"name": "Client", "content": "<h1>{{ report.narrative }}</h1>"}
    result = client.post("/api/templates", json=payload)
    assert result.status_code == 200
    template = ReportTemplate(
        id=uuid4(), created_at=datetime.now(timezone.utc), version=1, archived=False, **payload
    )
    db.get.return_value = template
    assert client.get(f"/api/templates/{template.id}").json()["name"] == "Client"
    assert (
        client.put(f"/api/templates/{template.id}", json={**payload, "name": "Updated"}).json()[
            "name"
        ]
        == "Updated"
    )
    assert (
        client.put(f"/api/templates/{template.id}", json={**payload, "content": "{{"}).status_code
        == 422
    )
    assert client.post("/api/templates", json={**payload, "content": "{{"}).status_code == 422
    assert client.get("/api/templates").status_code == 200
    row = report()
    db.get.side_effect = [row, template]
    assert (
        client.get(f"/api/report/{row.id}/render?format=pdf&template_id={template.id}").status_code
        == 200
    )
    db.get.side_effect = [row, None]
    assert (
        client.get(f"/api/report/{row.id}/render?format=pdf&template_id={template.id}").status_code
        == 404
    )
    template.content = "{{ ''.__class__.__mro__ }}"
    db.get.side_effect = [row, template]
    assert (
        client.get(f"/api/report/{row.id}/render?format=pdf&template_id={template.id}").status_code
        == 422
    )
    db.get.side_effect = None
    assert client.delete(f"/api/templates/{template.id}").status_code == 204
    db.get.return_value = None
    assert client.get(f"/api/templates/{template.id}").status_code == 404


def test_template_preview(client, db):
    template = ReportTemplate(
        id=uuid4(),
        name="Client",
        content="<h1>{{ report.narrative }}</h1>",
        version=1,
        archived=False,
        created_at=datetime.now(timezone.utc),
    )
    db.get.return_value = template
    result = client.post(f"/api/templates/{template.id}/preview")
    assert result.status_code == 200
    assert "Sample preview narrative" in result.json()["html"]

    template.content = "{{"
    result = client.post(f"/api/templates/{template.id}/preview")
    assert result.status_code == 422


def test_template_archive_and_restore(client, db):
    template = ReportTemplate(
        id=uuid4(),
        name="Client",
        content="<h1>x</h1>",
        version=1,
        archived=False,
        created_at=datetime.now(timezone.utc),
    )
    db.get.return_value = template
    assert client.post(f"/api/templates/{template.id}/archive").json()["archived"] is True
    assert client.post(f"/api/templates/{template.id}/restore").json()["archived"] is False


def test_list_templates_include_archived_flag(client, db):
    assert client.get("/api/templates").status_code == 200
    assert client.get("/api/templates?include_archived=true").status_code == 200


def test_delete_template_blocked_when_referenced(client, db):
    template = ReportTemplate(
        id=uuid4(),
        name="Client",
        content="<h1>x</h1>",
        version=1,
        archived=False,
        created_at=datetime.now(timezone.utc),
    )
    db.get.return_value = template
    db.execute.return_value.scalar_one.return_value = 1
    result = client.delete(f"/api/templates/{template.id}")
    assert result.status_code == 409
    assert "Archive it instead" in result.json()["detail"]


def test_schedule_create_edit_pause_delete(client, db):
    payload = {"connector": "jira", "board_id": "DEMO", "cron_expression": "0 9 * * 1"}
    response = client.post("/api/schedule", json=payload)
    assert response.status_code == 200
    row = Schedule(
        id=uuid4(),
        created_at=datetime.now(timezone.utc),
        output_format="text",
        active=True,
        **payload,
    )
    db.get.return_value = row
    result = client.put(f"/api/schedule/{row.id}", json={**payload, "active": False})
    assert result.status_code == 200 and result.json()["active"] is False
    assert client.get("/api/schedule").status_code == 200
    assert client.delete(f"/api/schedule/{row.id}").status_code == 204
    db.get.return_value = None
    assert client.put(f"/api/schedule/{row.id}", json=payload).status_code == 404
    assert client.delete(f"/api/schedule/{row.id}").status_code == 404
    for change in ({"cron_expression": "nonsense"}, {"connector": "unknown"}, {"board_id": None}):
        assert client.post("/api/schedule", json=payload | change).status_code == 422


def test_schedule_timezone_defaults_and_validates(client):
    payload = {"connector": "jira", "board_id": "DEMO", "cron_expression": "0 9 * * 1"}
    default_tz = client.post("/api/schedule", json=payload)
    assert default_tz.status_code == 200
    assert default_tz.json()["timezone"] == "UTC"

    explicit_tz = client.post("/api/schedule", json={**payload, "timezone": "America/New_York"})
    assert explicit_tz.status_code == 200
    assert explicit_tz.json()["timezone"] == "America/New_York"

    bad_tz = client.post("/api/schedule", json={**payload, "timezone": "Mars/Phobos"})
    assert bad_tz.status_code == 422


def test_schedule_next_runs_preview(client, db):
    schedule = Schedule(
        id=uuid4(),
        connector="jira",
        board_id="DEMO",
        cron_expression="0 9 * * 1",
        timezone="America/New_York",
        output_format="text",
        active=True,
        created_at=datetime.now(timezone.utc),
    )
    db.get.return_value = schedule
    result = client.get(f"/api/schedule/{schedule.id}/next-runs?count=3")
    assert result.status_code == 200
    runs = result.json()["next_runs_utc"]
    assert len(runs) == 3
    assert runs == sorted(runs)


def test_schedule_next_runs_missing_returns_404(client, db):
    db.get.return_value = None
    assert client.get(f"/api/schedule/{uuid4()}/next-runs").status_code == 404


@pytest.mark.parametrize(
    "connector,body",
    [
        (
            "jira",
            {
                "jira_url": "https://example.com",
                "jira_email": "tester@example.com",
                "jira_api_token": "test",
            },
        ),
        ("asana", {"asana_pat": "test"}),
        ("github", {"github_pat": "test"}),
    ],
)
def test_connector_configuration(client, respx_mock, monkeypatch, connector, body):
    monkeypatch.setattr(
        "app.core.ssrf_guard._resolve_ips", lambda host: [ipaddress.ip_address("93.184.216.34")]
    )
    assert client.post(f"/api/config/{connector}", json=body).json()["ok"]
    assert client.get("/api/config").json()[f"{connector}_configured"]
    route = respx_mock.route().mock(return_value=httpx.Response(200, json={}))
    assert client.post(f"/api/config/{connector}/test", json=body).json()["ok"]
    route.mock(return_value=httpx.Response(401))
    assert not client.post(f"/api/config/{connector}/test", json=body).json()["ok"]
    route.mock(side_effect=httpx.ConnectError("offline"))
    assert not client.post(f"/api/config/{connector}/test", json=body).json()["ok"]
    bad = {key: value + "\n" for key, value in body.items()}
    assert not client.post(f"/api/config/{connector}", json=bad).json()["ok"]


@pytest.mark.parametrize("provider", ["openai", "anthropic", "groq", "ollama"])
def test_llm_configuration(client, respx_mock, monkeypatch, provider):
    monkeypatch.setattr(
        "app.core.ssrf_guard._resolve_ips", lambda host: [ipaddress.ip_address("93.184.216.34")]
    )
    body = {"llm_provider": provider, "api_key": "test", "ollama_base_url": "http://ollama:11434"}
    assert client.post("/api/config/llm", json=body).json()["ok"]
    assert client.get("/api/config").json()["llm_provider"] == provider
    route = respx_mock.route().mock(return_value=httpx.Response(200, json={}))
    assert client.post("/api/config/llm/test", json=body).json()["ok"]
    route.mock(return_value=httpx.Response(401))
    assert not client.post("/api/config/llm/test", json=body).json()["ok"]
    route.mock(side_effect=httpx.ConnectError("offline"))
    assert not client.post("/api/config/llm/test", json=body).json()["ok"]
    body["api_key"] = "bad\nkey"
    if provider != "ollama":
        assert not client.post("/api/config/llm", json=body).json()["ok"]


@pytest.mark.parametrize(
    "service,body",
    [
        (
            "jira",
            {
                "jira_url": "https://evil.test",
                "jira_email": "synthetic",
                "jira_api_token": "synthetic",
            },
        ),
        ("llm", {"llm_provider": "ollama", "ollama_base_url": "http://127.0.0.1:11434"}),
    ],
)
def test_save_and_test_share_target_policy(client, service, body):
    from app.core.env_writer import ENV_PATH

    for suffix in ("", "/test"):
        response = client.post(f"/api/config/{service}{suffix}", json=body)
        assert response.status_code == 200
        assert not response.json()["ok"]
    assert not ENV_PATH.exists()


def test_readonly_status_and_secret_isolation(client, monkeypatch):
    monkeypatch.setattr(settings, "config_read_only", True)
    monkeypatch.setattr(settings, "github_pat", "private-operator-token")
    status = client.get("/api/config")
    assert status.json()["config_read_only"] is True
    assert "private-operator-token" not in status.text
    assert not client.post("/api/config/github", json={"github_pat": "replace"}).json()["ok"]
    assert settings.github_pat == "private-operator-token"


def test_every_registered_data_route_requires_token(client, monkeypatch):
    monkeypatch.setattr(settings, "config_api_token", "matrix-token")
    for route in app.routes:
        path = getattr(route, "path", "")
        if path.startswith("/api/"):
            for parameter in ("report_id", "template_id", "schedule_id"):
                path = path.replace("{" + parameter + "}", str(uuid4()))
            for method in route.methods:
                assert client.request(method, path).status_code == 401, (method, path)
    assert client.get("/api/reports", headers={"X-Config-Token": "matrix-token"}).status_code == 200
