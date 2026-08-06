import pytest
from app.core.env_writer import upsert_env_values, InvalidEnvValueError, ALLOWED_KEYS


def test_rejects_non_allowed_key(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    monkeypatch.setattr("app.core.env_writer.ENV_PATH", env_file)
    with pytest.raises(InvalidEnvValueError):
        upsert_env_values({"DATABASE_URL": "postgresql://evil"})


def test_rejects_newline_injection(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    monkeypatch.setattr("app.core.env_writer.ENV_PATH", env_file)
    with pytest.raises(InvalidEnvValueError):
        upsert_env_values({"JIRA_URL": "https://x.com\nDATABASE_URL=evil"})


def test_writes_owner_only_permissions(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    monkeypatch.setattr("app.core.env_writer.ENV_PATH", env_file)
    upsert_env_values({"JIRA_URL": "https://real.atlassian.net"})
    mode = env_file.stat().st_mode & 0o777
    assert mode == 0o600


def test_allowed_keys_cover_jira_and_llm():
    assert "JIRA_API_TOKEN" in ALLOWED_KEYS
    assert "OPENAI_API_KEY" in ALLOWED_KEYS
