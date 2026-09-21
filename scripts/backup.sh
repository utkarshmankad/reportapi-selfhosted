#!/usr/bin/env bash
# Snapshots the two pieces of state a docker-compose deployment can't
# regenerate: the Postgres database (reports, jobs, schedules, webhook
# destinations/deliveries) and the runtime_config volume (credentials the
# config UI wrote — JIRA_API_TOKEN, OPENAI_API_KEY, etc, in plaintext).
# Both land in one tarball; restore.sh reverses this exactly.
set -euo pipefail
cd "$(dirname "$0")/.."

compose=(docker compose)
project="$("${compose[@]}" config --format json 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin)["name"])' 2>/dev/null || echo reportapi-selfhosted)"

out_dir="${1:-./backups}"
mkdir -p "$out_dir"
# Refuse a world/group-readable backup directory: it's about to contain
# plaintext credentials copied straight out of the runtime_config volume.
chmod 700 "$out_dir"

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
# Under the repo, not system /tmp: Docker Desktop/Colima only bind-mount
# the host's home directory into the VM by default, so a container-side
# volume mount of a system-temp path can silently see an empty directory.
work="$(mktemp -d ./.backup-work.XXXXXX)"
trap 'rm -rf "$work"' EXIT

echo "Dumping database..."
"${compose[@]}" exec -T postgres pg_dump -U reportapi -Fc reportapi > "$work/database.dump"

echo "Archiving runtime config volume..."
docker run --rm \
  -v "${project}_runtime_config:/config:ro" \
  -v "$work:/backup" \
  postgres:16-alpine@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea \
  tar czf /backup/runtime_config.tar.gz -C /config .

archive="$out_dir/reportapi-backup-${stamp}.tar.gz"
# macOS tar otherwise adds AppleDouble ._ files, which makes the archive
# platform-dependent and fails restore's strict member validation.
COPYFILE_DISABLE=1 tar czf "$archive" -C "$work" database.dump runtime_config.tar.gz
chmod 600 "$archive"

echo "Backup written to $archive"
echo "This archive contains plaintext credentials — store it like a secret, not like a log file."
