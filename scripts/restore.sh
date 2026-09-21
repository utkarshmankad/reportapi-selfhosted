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

# Extract only the two expected regular files and reject unsafe content in
# either tarball before stopping services or changing any state.  Besides
# catching corrupt/wrong archives, this prevents path traversal and special
# files in an operator-supplied backup from escaping the restore volume.
python3 - "$archive" "$work" <<'PY'
import pathlib
import shutil
import sys
import tarfile

archive, work = sys.argv[1:]
expected = {"database.dump", "runtime_config.tar.gz"}
with tarfile.open(archive, "r:gz") as outer:
    members = {member.name: member for member in outer.getmembers()}
    if set(members) != expected or not all(members[name].isfile() for name in expected):
        raise SystemExit("Backup must contain only database.dump and runtime_config.tar.gz")
    for name in expected:
        source = outer.extractfile(members[name])
        if source is None:
            raise SystemExit(f"Could not read {name} from backup")
        with open(pathlib.Path(work, name), "xb") as destination:
            shutil.copyfileobj(source, destination)

with tarfile.open(pathlib.Path(work, "runtime_config.tar.gz"), "r:gz") as runtime:
    for member in runtime.getmembers():
        path = pathlib.PurePosixPath(member.name)
        if path.is_absolute() or ".." in path.parts:
            raise SystemExit(f"Unsafe runtime-config path in backup: {member.name}")
        if member.issym() or member.islnk() or member.isdev():
            raise SystemExit(f"Unsafe runtime-config entry in backup: {member.name}")
PY

echo "Stopping application services so database objects are not in use..."
"${compose[@]}" stop api worker beat >/dev/null

echo "Restoring database (replacing the public schema)..."
"${compose[@]}" exec -T postgres psql -v ON_ERROR_STOP=1 -U reportapi -d reportapi \
  -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
"${compose[@]}" exec -T postgres pg_restore -U reportapi -d reportapi --no-owner \
  < "$work/database.dump"

echo "Restoring runtime config volume..."
docker run --rm \
  -v "${project}_runtime_config:/config" \
  -v "$work:/backup:ro" \
  postgres:16-alpine@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea \
  sh -c "rm -rf /config/* && tar xzf /backup/runtime_config.tar.gz -C /config"

echo "Restore complete. Restart the api/worker/beat containers to pick up the restored config:"
echo "  docker compose up -d api worker beat"
