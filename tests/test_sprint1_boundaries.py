"""Security regression tests at settings, HTTP payload and render boundaries."""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from app.config import Settings, settings
from app.connectors.base import FetchResult
from app.core import render_process
from app.core.render_process import TemplateRenderError
from app.core.report_service import generate_report
from app.core.template_renderer import render_template, validate_template
from app.models.ticket import Ticket
from tests.test_template_renderer import make_report


@pytest.mark.parametrize("token", [None, "", "   "])
def test_production_refuses_missing_token(token):
    with pytest.raises(ValidationError, match="CONFIG_API_TOKEN is required"):
        Settings(_env_file=None, app_env="production", config_api_token=token)


def test_local_mode_and_production_with_token():
    assert (
        Settings(_env_file=None, app_env="development", config_api_token=None).app_env
        == "development"
    )
    assert (
        Settings(_env_file=None, app_env="production", config_api_token="secret").config_api_token
        == "secret"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["openai", "anthropic", "groq", "ollama"])
async def test_all_provider_request_bodies_are_sanitized(monkeypatch, respx_mock, provider):
    monkeypatch.setattr(settings, "llm_provider", provider)
    for key in ("openai_api_key", "anthropic_api_key", "groq_api_key"):
        monkeypatch.setattr(settings, key, "synthetic")
    now = datetime.now(timezone.utc)
    sensitive = "Alice Smith; 4111-1111-1111-1111; 4111 1111 1111 1111; alice@example.com; 192.0.2.1; 2001:db8::1; ABCDE1234F; 234567890123; 9876543210"
    ticket = Ticket(
        id="D-1",
        title=sensitive,
        description=sensitive,
        status="blocked",
        assignee="Alice Smith",
        priority="high " + sensitive,
        labels=[sensitive],
        sprint=sensitive,
        url="https://example.com",
        created_at=now,
        updated_at=now,
    )
    monkeypatch.setattr(
        "app.core.report_service.JiraConnector",
        lambda config: MagicMock(fetch=AsyncMock(return_value=FetchResult(tickets=[ticket]))),
    )
    response = {
        "choices": [{"message": {"content": "Safe report"}}],
        "usage": {"total_tokens": 10, "input_tokens": 5, "output_tokens": 5},
        "content": [{"text": "Safe report"}],
        "message": {"content": "Safe report"},
    }
    request = respx_mock.route().respond(200, json=response)
    db = MagicMock(commit=AsyncMock(), refresh=AsyncMock())
    await generate_report(db, "jira", "D", None)
    outbound = request.calls.last.request.content.decode()
    for original in (
        "Alice Smith",
        "4111-1111-1111-1111",
        "alice@example.com",
        "192.0.2.1",
        "2001:db8::1",
        "4111 1111 1111 1111",
        "ABCDE1234F",
        "234567890123",
        "9876543210",
    ):
        assert original not in outbound
    assert "Person 1" in outbound
    body = json.loads(outbound)
    assert body["messages"]


def test_template_input_output_and_context_limits():
    with pytest.raises(TemplateRenderError, match="size limit"):
        validate_template("x" * 50_001)
    with pytest.raises(TemplateRenderError, match="resource limit"):
        render_template("{{ 'x' * 2000001 }}", make_report())
    report = make_report()
    report.narrative = "x" * 1_000_001
    with pytest.raises(TemplateRenderError, match="input size"):
        render_template("{{ report.narrative }}", report)


def test_timeout_kills_worker_and_releases_slot(monkeypatch):
    monkeypatch.setattr(render_process, "WALL_SECONDS", 0.3)
    huge = "{% for a in range(100000) %}{% for b in range(100000) %}{% set c = a+b %}{% endfor %}{% endfor %}"
    with pytest.raises(TemplateRenderError, match="time limit"):
        render_template(huge, make_report())
    monkeypatch.setattr(render_process, "WALL_SECONDS", 15)
    assert render_template("safe", make_report()) == "safe"


def test_concurrent_renderer_limit(monkeypatch):
    import threading

    semaphore = threading.BoundedSemaphore(1)
    semaphore.acquire()
    monkeypatch.setattr(render_process, "_slots", semaphore)
    with pytest.raises(TemplateRenderError, match="busy"):
        validate_template("safe")


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "https://example.com/image.png",
        "http://169.254.169.254/",
        "data:image/svg+xml,test",
    ],
)
def test_pdf_resource_fetching_is_default_deny(url):
    from app.core.pdf_renderer import deny_resource

    with pytest.raises(ValueError, match="disabled"):
        deny_resource(url)


@pytest.mark.skipif(__import__("sys").platform != "linux", reason="Linux container memory limit")
def test_renderer_memory_limit():
    with pytest.raises(TemplateRenderError, match="resource limit"):
        render_template("{{ 'x' * 1000000000 }}", make_report())


@pytest.mark.asyncio
async def test_job_keeps_provider_snapshot_during_config_change(monkeypatch, respx_mock):
    monkeypatch.setattr(settings, "openai_api_key", "initial-key")
    monkeypatch.setattr(settings, "groq_api_key", "next-key")
    now = datetime.now(timezone.utc)
    ticket = Ticket(
        id="1",
        title="Release",
        description="",
        status="done",
        assignee=None,
        priority=None,
        labels=[],
        sprint=None,
        url="https://example.com",
        created_at=now,
        updated_at=now,
    )

    async def fetch(config):
        settings.llm_provider = "groq"
        settings.openai_api_key = "changed-key"
        return FetchResult(tickets=[ticket])

    monkeypatch.setattr(
        "app.core.report_service.JiraConnector", lambda config: MagicMock(fetch=fetch)
    )
    reply = {"choices": [{"message": {"content": "Safe report"}}], "usage": {"total_tokens": 1}}
    old = respx_mock.post("https://api.openai.com/v1/chat/completions").respond(200, json=reply)
    new = respx_mock.post("https://api.groq.com/openai/v1/chat/completions").respond(
        200, json=reply
    )
    db = MagicMock(commit=AsyncMock(), refresh=AsyncMock())
    first, _ = await generate_report(db, "jira", "D", None)
    second, _ = await generate_report(db, "jira", "D", None)
    assert first.model_used == "openai" and second.model_used == "groq"
    assert old.calls.last.request.headers["Authorization"] == "Bearer initial-key"
    assert new.calls.last.request.headers["Authorization"] == "Bearer next-key"
