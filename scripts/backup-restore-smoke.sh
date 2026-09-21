#!/usr/bin/env bash
# Proves backup.sh/restore.sh actually round-trip data, against the real
# docker-compose.yml stack (not a mock) — synthetic data only, own
# throwaway volumes, no .env read.
set -euo pipefail
cd "$(dirname "$0")/.."

compose=(docker compose)

# docker-compose.yml's api/worker/beat services declare `env_file: .env`;
# compose validates that file exists for every service the file defines
# even when only postgres/redis are actually started. Never read a real
# .env here — synthetic-only — so create an empty placeholder if none
# exists, and remove it again only if we created it.
made_env_placeholder=0
if [ ! -f .env ]; then
  touch .env
  made_env_placeholder=1
fi

cleanup() {
  result=$?
  "${compose[@]}" down -v --remove-orphans || true
  docker rmi reportapi-engine-smoke > /dev/null 2>&1 || true
  [ "$made_env_placeholder" = 1 ] && rm -f .env
  exit "$result"
}
trap cleanup EXIT

# --wait blocks until postgres's own healthcheck (defined in
# docker-compose.yml) passes, instead of a fixed-iteration poll loop
# that can silently fall through on a slow/cold-cache runner.
"${compose[@]}" up -d --wait --wait-timeout 120 postgres redis

project="$("${compose[@]}" config --format json | python3 -c 'import json,sys; print(json.load(sys.stdin)["name"])')"

# docker-compose.yml deliberately doesn't publish postgres's port to the
# host (only the api/worker/beat containers can reach it, over the
# compose network) — so migrations run the same way the real
# deployment applies them: from a container on that network, addressing
# postgres by its service DNS name, not from the host via localhost.
docker build -q -t reportapi-engine-smoke -f Dockerfile . > /dev/null
docker run --rm --network "${project}_default" \
  -e DATABASE_URL=postgresql+asyncpg://reportapi:reportapi@postgres:5432/reportapi \
  -e REDIS_URL=redis://redis:6379/0 \
  reportapi-engine-smoke alembic upgrade head

"${compose[@]}" exec -T postgres psql -U reportapi -d reportapi -c \
  "INSERT INTO reports (id, connector, status, model_used, tokens_used, narrative, output_format, created_at) VALUES (gen_random_uuid(), 'jira', 'complete', 'openai', 1, 'backup-smoke-marker', 'text', now());"

docker run --rm -v "${project}_runtime_config:/config" alpine:3.20@sha256:d9e853e87e55526f6b2917df91a2115c36dd7c696a35be12163d44e6e2a4b6bc sh -c 'echo "JIRA_API_TOKEN=\"smoke-marker-token\"" > /config/runtime.env'

out_dir="./.backup-smoke-out"
rm -rf "$out_dir"
./scripts/backup.sh "$out_dir"
archive="$(ls "$out_dir"/*.tar.gz)"

"${compose[@]}" exec -T postgres psql -U reportapi -d reportapi -c "DELETE FROM reports;"
docker run --rm -v "${project}_runtime_config:/config" alpine:3.20@sha256:d9e853e87e55526f6b2917df91a2115c36dd7c696a35be12163d44e6e2a4b6bc sh -c 'rm -f /config/runtime.env'

FORCE=1 ./scripts/restore.sh "$archive"

count="$("${compose[@]}" exec -T postgres psql -U reportapi -d reportapi -tAc "SELECT count(*) FROM reports WHERE narrative = 'backup-smoke-marker';")"
[ "$(echo "$count" | tr -d '[:space:]')" = "1" ] || { echo "Database restore did not bring back the marker row" >&2; exit 1; }

token="$(docker run --rm -v "${project}_runtime_config:/config:ro" alpine:3.20@sha256:d9e853e87e55526f6b2917df91a2115c36dd7c696a35be12163d44e6e2a4b6bc cat /config/runtime.env)"
echo "$token" | grep -q "smoke-marker-token" || { echo "Runtime config restore did not bring back the marker token" >&2; exit 1; }

rm -rf "$out_dir"
echo "Backup/restore round trip verified."
