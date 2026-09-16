"""Persist credential overrides to a shared runtime configuration file."""

import fcntl
import os
import tempfile
from pathlib import Path

from dotenv import set_key

from app.config import settings

ENV_PATH = Path(settings.config_store_path)

# Only these keys can be written by the config UI — prevents a caller from
# injecting arbitrary env vars (e.g. overwriting DATABASE_URL or PYTHONPATH).
ALLOWED_KEYS = {
    "JIRA_URL",
    "JIRA_EMAIL",
    "JIRA_API_TOKEN",
    "ASANA_PAT",
    "GITHUB_PAT",
    "LLM_PROVIDER",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "OLLAMA_BASE_URL",
    "GROQ_API_KEY",
}


class InvalidEnvValueError(Exception):
    pass


def upsert_env_values(values: dict[str, str]) -> None:
    """
    Atomically update quoted KEY=VALUE overrides shared by the API and workers.
    """
    for key, value in values.items():
        if key not in ALLOWED_KEYS:
            raise InvalidEnvValueError(f"'{key}' is not a writable config key")
        if any(c in value for c in ("\n", "\r")):
            raise InvalidEnvValueError(f"Value for '{key}' contains a line break")

    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    lock_path = ENV_PATH.with_suffix(".lock")
    with lock_path.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        fd, temporary = tempfile.mkstemp(dir=ENV_PATH.parent, prefix=".config-")
        try:
            with os.fdopen(fd, "w") as output:
                if ENV_PATH.exists():
                    output.write(ENV_PATH.read_text())
            for key, value in values.items():
                set_key(temporary, key, value, quote_mode="always")
            os.chmod(temporary, 0o600)
            os.replace(temporary, ENV_PATH)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
