#!/usr/bin/env bash
# Installs the chart into a throwaway kind cluster and proves it actually
# comes up healthy — a `helm lint`/`helm template` pass only proves the
# YAML is well-formed, not that the release deploys, migrates, and serves
# traffic. Synthetic credentials only; never reads .env.
set -euo pipefail
cd "$(dirname "$0")/.."

cluster="reportapi-helm-smoke"
release="smoke"
pf_pid=""

cleanup() {
  result=$?
  if [ "$result" -ne 0 ]; then kubectl get pods -o wide || true; kubectl describe pods || true; fi
  [ -n "$pf_pid" ] && kill "$pf_pid" 2>/dev/null || true
  helm uninstall "$release" >/dev/null 2>&1 || true
  kind delete cluster --name "$cluster" || true
  exit "$result"
}
trap cleanup EXIT

helm dependency update helm/reportapi

# Exercise deployment modes the live smoke does not use. External services
# must replace (rather than duplicate) bundled URLs, and writable runtime
# configuration must mount the same claim in API, worker, and scheduler.
external_render="$(helm template external helm/reportapi \
  --set postgresql.enabled=false \
  --set redis.enabled=false \
  --set-string externalDatabase.url=postgresql+asyncpg://user:pass@db.example/reportapi \
  --set-string externalRedis.url=redis://cache.example:6379/0)"
echo "$external_render" | grep -q 'postgresql+asyncpg://user:pass@db.example/reportapi'
echo "$external_render" | grep -q 'redis://cache.example:6379/0'
! echo "$external_render" | grep -q 'external-postgresql:5432'
! echo "$external_render" | grep -q 'external-redis-master:6379'

# Each bundled dependency can also be disabled independently. This catches
# subchart image-verification/global-value interactions that a both-external
# render cannot expose.
helm template external-db helm/reportapi \
  --set postgresql.enabled=false \
  --set-string externalDatabase.url=postgresql+asyncpg://user:pass@db.example/reportapi \
  >/dev/null
helm template external-redis helm/reportapi \
  --set redis.enabled=false \
  --set-string externalRedis.url=redis://cache.example:6379/0 \
  >/dev/null

persistence_render="$(helm template persistence helm/reportapi \
  --set runtimeConfig.persistence.enabled=true)"
echo "$persistence_render" | grep -q 'kind: PersistentVolumeClaim'
[ "$(echo "$persistence_render" | grep -c 'claimName: persistence-reportapi-runtime-config')" = "3" ]

kind create cluster --name "$cluster"

docker build -t reportapi/engine:ci -f Dockerfile .
docker build -t reportapi/config-ui:ci ./config-ui
kind load docker-image reportapi/engine:ci reportapi/config-ui:ci --name "$cluster"

helm install "$release" helm/reportapi \
  --set image.repository=reportapi/engine \
  --set image.tag=ci \
  --set image.pullPolicy=Never \
  --set configUiImage.repository=reportapi/config-ui \
  --set configUiImage.tag=ci \
  --set configUiImage.pullPolicy=Never \
  --set envSecret.CONFIG_API_TOKEN=smoke-test-token \
  --set envSecret.JIRA_URL=http://example.invalid \
  --set envSecret.JIRA_EMAIL=test@example.com \
  --set envSecret.JIRA_API_TOKEN=synthetic \
  --set envSecret.OPENAI_API_KEY=synthetic \
  --set redis.master.persistence.enabled=false \
  --set postgresql.primary.persistence.enabled=false \
  --wait --timeout 6m

kubectl port-forward svc/smoke-reportapi-api 18000:8000 >/tmp/helm-smoke-pf.log 2>&1 &
pf_pid=$!

for _ in $(seq 1 30); do
  if curl --max-time 3 -fsS http://127.0.0.1:18000/health/ready > /dev/null; then break; fi
  sleep 2
done

ready="$(curl --max-time 5 -fsS http://127.0.0.1:18000/health/ready)"
echo "$ready"
echo "$ready" | grep -q '"status":"ok"'
echo "$ready" | grep -q '"database":"ok"'
echo "$ready" | grep -q '"redis":"ok"'

status="$(curl --max-time 5 -fsS -H "X-Config-Token: smoke-test-token" http://127.0.0.1:18000/api/ops/status)"
echo "$status"
echo "$status" | grep -q '"scheduler"'

config="$(curl --max-time 5 -fsS -H "X-Config-Token: smoke-test-token" http://127.0.0.1:18000/api/config)"
echo "$config" | grep -q '"config_read_only":true'

echo "Helm chart deployed and serving traffic successfully."
