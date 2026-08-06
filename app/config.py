"""Application configuration via Pydantic Settings."""
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # App
    app_env: Literal["development", "production"] = "development"
    log_level: str = "info"

    # Database
    database_url: str

    # Redis
    redis_url: str

    # Jira
    jira_url: str | None = None
    jira_email: str | None = None
    jira_api_token: str | None = None

    # LLM
    llm_provider: Literal["openai", "anthropic", "ollama"] = "openai"
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    ollama_base_url: str = "http://ollama:11434"

    # Vector DB
    chroma_host: str = "chroma"
    chroma_port: int = 8000

    # Report defaults
    max_tokens_output: int = 800
    report_retention_days: int = 7

    # Licensing — Community tier needs no key; paid tiers check license_key
    license_tier: Literal["community", "paid"] = "community"
    license_key: str | None = None


settings = Settings()
