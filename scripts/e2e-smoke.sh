#!/usr/bin/env bash
# End-to-end smoke test: boots the real docker compose stack and checks that
# every container comes up healthy and the API answers over HTTP. Does not
# call Jira/OpenAI/Anthropic — those need real credentials this script
# doesn't have, so it only proves the stack itself wires together correctly.
set -euo pipefail

cd "$(dirname "$0")/.."

cleanup() {
  echo "--- docker compose logs (last 100 lines) ---"
  docker compose logs --tail=100 || true
  docker compose down -v --remove-orphans || true
}
trap cleanup EXIT

cp -n .env.example .env || true
# CI has no real Jira/LLM creds; the smoke test only needs the stack to boot.
echo "DATABASE_URL=postgresql+asyncpg://reportapi:reportapi@postgres:5432/reportapi" >> .env
echo "REDIS_URL=redis://redis:6379/0" >> .env

docker compose up --build -d api worker beat postgres redis config-ui

echo "Waiting for postgres to report healthy..."
for i in $(seq 1 30); do
  status=$(docker compose ps postgres --format json | python3 -c "import json,sys; print(json.load(sys.stdin).get('Health',''))" 2>/dev/null || echo "")
  if [ "$status" = "healthy" ]; then break; fi
  sleep 2
done

echo "Waiting for api on :8000/health..."
for i in $(seq 1 30); do
  if curl -sf http://localhost:8000/health > /tmp/health.json; then
    echo "api responded:"
    cat /tmp/health.json
    break
  fi
  sleep 2
done

if ! grep -q '"status"' /tmp/health.json 2>/dev/null; then
  echo "FAIL: api never became healthy"
  exit 1
fi

echo "Checking config UI on :8080..."
if ! curl -sf http://localhost:8080 > /dev/null; then
  echo "FAIL: config-ui did not respond on :8080"
  exit 1
fi

echo "Checking /api/schedule responds (no creds needed)..."
curl -sf http://localhost:8000/api/schedule > /dev/null

echo "E2E smoke test passed."
