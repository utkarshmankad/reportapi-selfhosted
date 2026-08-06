"""Persist config-UI form submissions to the .env file on disk."""
from pathlib import Path

ENV_PATH = Path(".env")


def upsert_env_values(values: dict[str, str]) -> None:
    """
    Update or append KEY=VALUE lines in .env. Takes effect after the next
    process restart (Settings is loaded once at import time).
    """
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

    ENV_PATH.write_text("\n".join(lines) + "\n")
