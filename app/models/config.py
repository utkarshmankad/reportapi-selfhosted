"""Config pydantic schemas — used by the config UI."""

from typing import Literal

from pydantic import BaseModel


class JiraConfigRequest(BaseModel):
    jira_url: str
    jira_email: str
    jira_api_token: str


class AsanaConfigRequest(BaseModel):
    asana_pat: str


class GitHubConfigRequest(BaseModel):
    github_pat: str


class LLMConfigRequest(BaseModel):
    llm_provider: Literal["openai", "anthropic", "ollama", "groq"]
    api_key: str | None = None
    ollama_base_url: str | None = None


class TestResult(BaseModel):
    ok: bool
    detail: str


class ConfigStatus(BaseModel):
    config_read_only: bool = False
    app_env: str
    llm_provider: str
    jira_configured: bool
    asana_configured: bool
    github_configured: bool
    openai_configured: bool
    anthropic_configured: bool
    ollama_base_url: str
    groq_configured: bool
