"""Isolated defaults: tests never load developer credentials or runtime config."""

import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://reportapi:reportapi@localhost:5432/reportapi"
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

import pytest

from app.config import settings


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch, tmp_path):
    from app.core import env_writer

    monkeypatch.setattr(env_writer, "ENV_PATH", tmp_path / "runtime.env")
    for key in (
        "jira_url",
        "jira_email",
        "jira_api_token",
        "asana_pat",
        "github_pat",
        "openai_api_key",
        "anthropic_api_key",
        "groq_api_key",
        "config_api_token",
    ):
        monkeypatch.setattr(settings, key, None)
    monkeypatch.setattr(settings, "llm_provider", "openai")
    monkeypatch.setattr(settings, "ollama_base_url", "http://ollama:11434")

    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "config_read_only", False)
    monkeypatch.setattr(
        settings, "jira_allowed_origins", "https://test.atlassian.net,https://example.com"
    )
    monkeypatch.setattr(settings, "ollama_allowed_origins", "http://ollama:11434")
    monkeypatch.setattr(settings, "outbound_private_origins", "http://ollama:11434")
