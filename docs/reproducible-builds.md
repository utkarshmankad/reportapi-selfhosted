# Reproducible builds

Every base image this project pulls — in `Dockerfile`, `config-ui/Dockerfile`,
`docker-compose.yml`, and `docker-compose.ci.yml` — is pinned by digest
(`image:tag@sha256:...`), not just by tag. A floating tag like
`python:3.12-slim` can point to a different image tomorrow than it does
today; a digest can't. Application dependencies are already pinned the
same way via `poetry.lock` and `config-ui/package-lock.json`.

## Updating a pinned digest

Pull the new tag, read its digest, and update every file that
references it — the tag stays the same (so the Dockerfile/compose files
document which minor version you're on), only the digest changes:

```bash
docker pull python:3.12-slim
docker inspect --format='{{index .RepoDigests 0}}' python:3.12-slim
```

Rebuild and run the full test suite (unit, integration, e2e) before
committing a digest bump — a base image update can change system
library versions the way a WeasyPrint/Pango upgrade did in the past.

## What isn't pinned by digest

`apt-get install` packages in `Dockerfile` are not pinned to exact
versions — Debian's `slim` base images are frozen at a point release
already (pinned above), so the packages available to `apt-get` from
that base don't drift the way a rolling base image would.
