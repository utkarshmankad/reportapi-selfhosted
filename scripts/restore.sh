#!/usr/bin/env bash
# Restores a backup.sh archive: replaces the running Postgres database and
# the runtime_config volume's contents. Destructive by nature — asks for
# confirmation unless FORCE=1 is set (for scripted/CI use).
set -euo pipefail
cd "$(dirname "$0")/.."

archive="${1:?Usage: restore.sh <path-to-backup-archive.tar.gz>}"
[ -f "$archive" ] || { echo "No such file: $archive" >&2; exit 1; }

compose=(docker compose)
project="$("${compose[@]}" config --format json 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin)["name"])' 2>/dev/null || echo reportapi-selfhosted)"

if [ "${FORCE:-0}" != "1" ]; then
  read -r -p "This replaces the running database and runtime config. Continue? [y/N] " confirm
  [ "$confirm" = "y" ] || [ "$confirm" = "Y" ] || { echo "Aborted."; exit 1; }
fi

# Under the repo, not system /tmp: Docker Desktop/Colima only bind-mount
# the host's home directory into the VM by default, so a container-side
# volume mount of a system-temp path can silently see an empty directory.
work="$(mktemp -d ./.backup-work.XXXXXX)"
trap 'rm -rf "$work"' EXIT

tar xzf "$archive" -C "$work"
[ -f "$work/database.dump" ] || { echo "Archive missing database.dump" >&2; exit 1; }
[ -f "$work/runtime_config.tar.gz" ] || { echo "Archive missing runtime_config.tar.gz" >&2; exit 1; }

echo "Restoring database (dropping and recreating existing objects)..."
"${compose[@]}" exec -T postgres pg_restore -U reportapi -d reportapi --clean --if-exists --no-owner < "$work/database.dump"

echo "Restoring runtime config volume..."
docker run --rm \
  -v "${project}_runtime_config:/config" \
  -v "$work:/backup:ro" \
  postgres:16-alpine@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea \
  sh -c "rm -rf /config/* && tar xzf /backup/runtime_config.tar.gz -C /config"

echo "Restore complete. Restart the api/worker/beat containers to pick up the restored config:"
echo "  docker compose restart api worker beat"
