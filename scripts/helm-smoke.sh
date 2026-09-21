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

kind create cluster --name "$cluster"

docker build -t reportapi/engine:ci -f Dockerfile .
docker build -t reportapi/config-ui:ci ./config-ui
kind load docker-image reportapi/engine:ci reportapi/config-ui:ci --name "$cluster"

helm dependency update helm/reportapi

helm install "$release" helm/reportapi \
  --set image.repository=reportapi/engine \
  --set image.tag=ci \
  --set image.pullPolicy=Never \
  --set configUiImage.repository=reportapi/config-ui \
  --set configUiImage.tag=ci \
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

echo "Helm chart deployed and serving traffic successfully."
