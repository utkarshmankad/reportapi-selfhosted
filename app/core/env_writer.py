"""Persist config-UI form submissions to the .env file on disk."""
import os
from pathlib import Path

ENV_PATH = Path(".env")

# Only these keys can be written by the config UI — prevents a caller from
# injecting arbitrary env vars (e.g. overwriting DATABASE_URL or PYTHONPATH).
ALLOWED_KEYS = {
    "JIRA_URL", "JIRA_EMAIL", "JIRA_API_TOKEN",
    "LLM_PROVIDER", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "OLLAMA_BASE_URL",
}


class InvalidEnvValueError(Exception):
    pass


def upsert_env_values(values: dict[str, str]) -> None:
    """
    Update or append KEY=VALUE lines in .env. Takes effect after the next
    process restart (Settings is loaded once at import time).
    """
    for key, value in values.items():
        if key not in ALLOWED_KEYS:
            raise InvalidEnvValueError(f"'{key}' is not a writable config key")
        if any(c in value for c in ("\n", "\r")):
            raise InvalidEnvValueError(f"Value for '{key}' contains a line break")

    lines = ENV_PATH.read_text().splitlines() if ENV_PATH.exists() else []
    keys_remaining = dict(values)

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in keys_remaining:
            lines[i] = f"{key}={keys_remaining.pop(key)}"

    for key, value in keys_remaining.items():
        lines.append(f"{key}={value}")

    content = "\n".join(lines) + "\n"

    # Write owner-only (0600) — this file holds API tokens/keys.
    fd = os.open(str(ENV_PATH), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, content.encode("utf-8"))
    finally:
        os.close(fd)
