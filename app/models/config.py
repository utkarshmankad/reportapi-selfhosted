"""Config pydantic schemas — used by the config UI."""
from typing import Literal
from pydantic import BaseModel


class JiraConfigRequest(BaseModel):
    jira_url: str
    jira_email: str
    jira_api_token: str


class LLMConfigRequest(BaseModel):
    llm_provider: Literal["openai", "anthropic", "ollama"]
    api_key: str | None = None
    ollama_base_url: str | None = None


class TestResult(BaseModel):
    ok: bool
    detail: str


class ConfigStatus(BaseModel):
    app_env: str
    llm_provider: str
    jira_configured: bool
    openai_configured: bool
    anthropic_configured: bool
    ollama_base_url: str
