# Backup and restore

A docker-compose deployment has two pieces of state that aren't
reproducible from code: the Postgres database (reports, jobs,
schedules, webhook destinations/deliveries) and the `runtime_config`
volume (credentials the config UI wrote — `JIRA_API_TOKEN`,
`OPENAI_API_KEY`, etc — in plaintext). `scripts/backup.sh` and
`scripts/restore.sh` snapshot and restore both together, so a restore
never leaves the database and the credentials it references
out of sync.

## Taking a backup

```bash
./scripts/backup.sh /path/to/backup/dir   # defaults to ./backups
```

Produces `reportapi-backup-<UTC timestamp>.tar.gz` containing a
`pg_dump -Fc` database dump and a tarball of the `runtime_config`
volume. The archive and its containing directory are created `0600`/
`0700` — **it contains plaintext credentials**; store and transmit it
the way you would a `.env` file, not a log file.

Run it on a schedule (cron, a Kubernetes CronJob, your platform's
backup tooling) against wherever the compose stack is running. It
requires the `postgres` service to be reachable via `docker compose
exec` and the `runtime_config` named volume to exist.

## Restoring

```bash
./scripts/restore.sh /path/to/reportapi-backup-<timestamp>.tar.gz
docker compose restart api worker beat
```

This is destructive: it drops and recreates every object in the
`reportapi` database (`pg_restore --clean --if-exists`) and replaces
the entire contents of the `runtime_config` volume. It asks for
confirmation before proceeding; set `FORCE=1` to skip the prompt for
scripted use. Restart `api`/`worker`/`beat` afterward — they cache the
config file's contents in memory and won't see the restored
credentials until they restart.

## Restore drills

A backup nobody has restored is a hope, not a plan. `scripts/backup-restore-smoke.sh`
runs the full loop against a throwaway compose stack — inserts a
marker report row and a marker credential, backs up, deletes both,
restores, and asserts both came back — and runs on every PR as the
"Backup and restore" CI job. Run it locally the same way to validate a
change to either script:

```bash
./scripts/backup-restore-smoke.sh
```

## What isn't covered

- The `postgres_data` volume itself isn't backed up directly — the
  `pg_dump` inside the archive is the durable copy; the volume is
  disposable as long as backups exist.
- Redis holds only ephemeral state (the Celery broker/result backend
  and the scheduler heartbeat) — nothing there needs to survive a
  restore, and `restore.sh` doesn't touch it.
- The Helm deployment doesn't yet have an equivalent backup/restore Job
  — see the runbook for operating that deployment path in the meantime.
