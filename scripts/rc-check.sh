#!/usr/bin/env bash
# Release-candidate acceptance gate: mechanically checks the things a
# human release checklist would otherwise have to remember to check by
# hand. Exits non-zero on the first failure, printing which gate failed.
set -uo pipefail
cd "$(dirname "$0")/.."

fail=0
check() {
  local description="$1"
  shift
  if "$@"; then
    echo "PASS: $description"
  else
    echo "FAIL: $description"
    fail=1
  fi
}

# --- Version consistency -----------------------------------------------
# pyproject.toml, app/main.py's FastAPI(version=...), and the Helm
# chart's appVersion are three independently-editable strings that all
# claim to describe the same released application version. A release
# candidate where they disagree means at least one was forgotten.
pyproject_version="$(grep -m1 '^version = ' pyproject.toml | sed -E 's/version = "(.*)"/\1/')"
main_version="$(grep -m1 'version=' app/main.py | sed -E 's/.*version="([^"]+)".*/\1/')"
chart_app_version="$(grep -m1 '^appVersion:' helm/reportapi/Chart.yaml | sed -E 's/appVersion: "(.*)"/\1/')"

echo "pyproject.toml version:        $pyproject_version"
echo "app/main.py version:           $main_version"
echo "helm Chart.yaml appVersion:    $chart_app_version"

check "app/main.py version matches pyproject.toml" \
  [ "$main_version" = "$pyproject_version" ]
check "Helm chart appVersion matches pyproject.toml" \
  [ "$chart_app_version" = "$pyproject_version" ]

# --- Working tree cleanliness -------------------------------------------
check "no uncommitted changes" \
  bash -c '[ -z "$(git status --porcelain)" ]'

# --- Required quality/security gates ------------------------------------
check "ruff lint clean" poetry run ruff check app/ tests/ alembic/
check "ruff format clean" poetry run ruff format --check app/ tests/ alembic/
check "unit test suite (>=80% coverage)" \
  poetry run pytest tests --ignore=tests/integration -m 'not integration and not e2e' \
    --cov=app --cov-branch --cov-fail-under=80 -q
check "bandit security scan clean" poetry run bandit -r app -ll
check "pip-audit clean" poetry run pip-audit --strict
check "helm lint clean" bash -c 'helm dependency update helm/reportapi > /dev/null && helm lint helm/reportapi'

echo
if [ "$fail" -eq 0 ]; then
  echo "All release-candidate gates passed."
else
  echo "One or more release-candidate gates failed — see FAIL lines above." >&2
fi
exit "$fail"
