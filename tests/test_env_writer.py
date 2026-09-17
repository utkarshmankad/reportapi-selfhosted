import pytest

from app.core.env_writer import ALLOWED_KEYS, InvalidEnvValueError, upsert_env_values


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
    assert "ANTHROPIC_API_KEY" in ALLOWED_KEYS
    assert "OLLAMA_BASE_URL" in ALLOWED_KEYS
    assert "GROQ_API_KEY" in ALLOWED_KEYS


def test_repairs_existing_permissions_and_quotes_credentials(tmp_path, monkeypatch):
    from dotenv import dotenv_values

    path = tmp_path / "runtime.env"
    path.write_text("JIRA_EMAIL='retained@example.com'\n")
    path.chmod(0o644)
    monkeypatch.setattr("app.core.env_writer.ENV_PATH", path)
    secret = "spaces 'quotes' #literal $DOLLAR"
    upsert_env_values({"ASANA_PAT": secret, "GITHUB_PAT": secret})
    assert path.stat().st_mode & 0o777 == 0o600
    assert dotenv_values(path, interpolate=False) == {
        "JIRA_EMAIL": "retained@example.com",
        "ASANA_PAT": secret,
        "GITHUB_PAT": secret,
    }


def test_concurrent_processes_preserve_independent_updates(tmp_path):
    import os
    import subprocess
    import sys

    from dotenv import dotenv_values

    path = tmp_path / "runtime.env"
    code = "from app.core.env_writer import upsert_env_values; import sys; upsert_env_values({sys.argv[1]: sys.argv[2]})"
    values = {key: f"value-{key}" for key in ALLOWED_KEYS}
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", code, key, value],
            env=os.environ | {"CONFIG_STORE_PATH": str(path), "APP_ENV": "development"},
        )
        for key, value in values.items()
    ]
    assert all(process.wait(timeout=20) == 0 for process in processes)
    assert dotenv_values(path) == values
    assert path.stat().st_mode & 0o777 == 0o600


def test_external_config_mode_ignores_overrides_and_rejects_writes(monkeypatch):
    from app.config import reload_runtime_settings, settings

    upsert_env_values({"GITHUB_PAT": "override"})
    monkeypatch.setattr(settings, "config_read_only", True)
    monkeypatch.setattr(settings, "github_pat", "operator-value")
    reload_runtime_settings()
    assert settings.github_pat == "operator-value"
    with pytest.raises(InvalidEnvValueError, match="read-only"):
        upsert_env_values({"GITHUB_PAT": "change"})


def test_snapshot_precedence_literal_secrets_and_removing_override(monkeypatch):
    from app.config import reload_runtime_settings, settings
    from app.core.env_writer import ENV_PATH

    monkeypatch.setattr(settings, "github_pat", "startup")
    secret = "literal-${DATABASE_URL}-$HOME-'quoted'"
    upsert_env_values({"GITHUB_PAT": secret})
    first = reload_runtime_settings()
    assert first.github_pat == secret
    assert settings.github_pat == "startup"
    upsert_env_values({"GITHUB_PAT": "next"})
    assert reload_runtime_settings().github_pat == "next"
    assert first.github_pat == secret
    ENV_PATH.unlink()
    assert reload_runtime_settings().github_pat == "startup"
