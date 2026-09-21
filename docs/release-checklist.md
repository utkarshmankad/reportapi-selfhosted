# Release-candidate acceptance checklist

Before tagging a release candidate, run:

```bash
./scripts/rc-check.sh
```

It mechanically verifies the things a human checklist would otherwise
have to remember by hand:

- **Version consistency** — `pyproject.toml`, `app/main.py`'s
  `FastAPI(version=...)`, and `helm/reportapi/Chart.yaml`'s
  `appVersion` all agree. Three independently-editable strings
  claiming to describe the same release is exactly the kind of thing
  that drifts silently.
- **Clean working tree** — nothing staged or unstaged that didn't make
  it into a commit.
- **Every required CI gate, locally** — ruff lint and format, the full
  unit suite at ≥80% coverage, bandit (medium+ severity, matching CI's
  `-ll` threshold), pip-audit, and `helm lint`.

It does not replace CI — it's the same gates, runnable before you push,
so a release candidate isn't the first place they run.

## What it deliberately doesn't check

- **Integration tests** (`tests/integration -m integration`) and the
  **Helm/backup-restore/e2e smoke scripts** — these need real
  Postgres/Redis/kind, which `rc-check.sh` doesn't provision. Run them
  separately (`scripts/helm-smoke.sh`, `scripts/backup-restore-smoke.sh`,
  `pytest tests/integration -m integration`) or trust the same-named CI
  jobs, which already run all of them on every PR.
- **Manual verification of claims in the roadmap** — "reproducible
  build," "functional Helm deployment," and "verified backup/restore"
  are backed by the CI jobs and scripts referenced above, not by this
  checklist re-asserting them. Don't claim more than those checks
  actually prove (see `docs/security-boundaries.md`'s privacy-contract
  section for the same principle applied to anonymization claims).

## Bumping the version for a release

Update all three in the same commit:

1. `pyproject.toml`'s `version`
2. `app/main.py`'s `FastAPI(version=...)`
3. `helm/reportapi/Chart.yaml`'s `appVersion` (bump `version` too if the
   chart's own templates changed, independently of the app version)

Then run `./scripts/rc-check.sh` before tagging.
