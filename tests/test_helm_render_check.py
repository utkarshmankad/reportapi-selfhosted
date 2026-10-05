"""Prove scripts/helm-render-check.sh fails when its absence assertions are violated."""

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "helm-render-check.sh"

# Satisfies every positive assertion in the script, so only the injected
# bundled URL can make it fail.
FAKE_HELM = """#!/usr/bin/env bash
[ "$1" = template ] || exit 0
echo 'DATABASE_URL: postgresql+asyncpg://user:pass@db.example/reportapi'
echo 'REDIS_URL: redis://cache.example:6379/0'
echo 'kind: PersistentVolumeClaim'
for _ in 1 2 3; do echo 'claimName: persistence-reportapi-runtime-config'; done
[ -z "$FAKE_BUNDLED_URL" ] || echo "LEAKED: $FAKE_BUNDLED_URL"
"""


def run_with_fake_helm(tmp_path, bundled_url=""):
    helm = tmp_path / "helm"
    helm.write_text(FAKE_HELM)
    helm.chmod(0o755)
    env = {"PATH": f"{tmp_path}:/usr/bin:/bin", "FAKE_BUNDLED_URL": bundled_url}
    return subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True)


def test_clean_external_render_passes(tmp_path):
    result = run_with_fake_helm(tmp_path)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("bundled_url", ["external-postgresql:5432", "external-redis-master:6379"])
def test_bundled_url_in_external_mode_fails(tmp_path, bundled_url):
    result = run_with_fake_helm(tmp_path, bundled_url)
    assert result.returncode != 0
    assert f"external mode rendered bundled URL: {bundled_url}" in result.stderr


@pytest.mark.skipif(shutil.which("helm") is None, reason="helm not installed")
def test_real_chart_render_passes():
    result = subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
