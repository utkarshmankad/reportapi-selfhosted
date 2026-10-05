#!/usr/bin/env bash
# Cluster-free chart render assertions, run by helm-smoke.sh before it spends
# time on kind. Exercises deployment modes the live smoke does not use.
set -euo pipefail
cd "$(dirname "$0")/.."

helm dependency update helm/reportapi

# External services must replace (rather than duplicate) bundled URLs, and
# writable runtime configuration must mount the same claim in API, worker,
# and scheduler.
external_render="$(helm template external helm/reportapi \
  --set postgresql.enabled=false \
  --set redis.enabled=false \
  --set-string externalDatabase.url=postgresql+asyncpg://user:pass@db.example/reportapi \
  --set-string externalRedis.url=redis://cache.example:6379/0)"
echo "$external_render" | grep -q 'postgresql+asyncpg://user:pass@db.example/reportapi'
echo "$external_render" | grep -q 'redis://cache.example:6379/0'
# A negated pipeline never trips errexit, so absence checks must fail explicitly.
for bundled in 'external-postgresql:5432' 'external-redis-master:6379'; do
  if grep -qF "$bundled" <<<"$external_render"; then
    echo "external mode rendered bundled URL: $bundled" >&2
    exit 1
  fi
done

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
