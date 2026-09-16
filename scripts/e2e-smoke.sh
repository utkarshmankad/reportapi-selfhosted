#!/usr/bin/env bash
# Isolated project, synthetic credentials, and its own volumes. Never read .env.
set -euo pipefail
cd "$(dirname "$0")/.."
project="reportapi-ci-${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-1}-$$"
compose=(docker compose --env-file /dev/null -p "$project" -f docker-compose.ci.yml)
cleanup() {
  result=$?
  if [ "$result" -ne 0 ]; then "${compose[@]}" logs --tail=100 || true; fi
  "${compose[@]}" down -v --remove-orphans || true
  exit "$result"
}
trap cleanup EXIT
"${compose[@]}" up --build -d postgres redis upstream api worker beat config-ui
"${compose[@]}" run --rm api alembic upgrade head
wait_http() {
  for _ in $(seq 1 60); do
    if curl --max-time 3 -fsS "$1" > /dev/null; then return 0; fi
    sleep 2
  done
  echo "Service did not become ready: $1" >&2
  return 1
}
wait_http http://127.0.0.1:18000/health
wait_http http://127.0.0.1:18080
"${compose[@]}" exec -T api python - < scripts/smoke_check.py
SMOKE_UI_URL=http://127.0.0.1:18080 npm --prefix config-ui run test:e2e
