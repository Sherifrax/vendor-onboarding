# Status (last updated: 2026-11-02 UTC)

| Phase | Title | Tier | State | Checkpoint | Commit / tag |
|---|---|---|---|---|---|
| 0 | Project setup | MUST | done | pass | phase 0: project setup / checkpoint-0 |
| 1 | Data model and core services | MUST | not started | n.a. | |
| 2 | Intake pipeline | MUST | not started | n.a. | |
| 3 | Checks | MUST | not started | n.a. | |
| 4 | Approvals, forms, final gate | MUST | not started | n.a. | |
| 5 | Documents | SHOULD | not started | n.a. | |
| 6 | Reminders, scheduler, errors | MUST | not started | n.a. | |
| 7 | Frontend dashboard | SHOULD | not started | n.a. | |
| 8 | Test suite and evidence | MUST | not started | n.a. | |
| 9 | AWS deployment | SHOULD | not started | n.a. | |
| 10 | Docs and demo polish | COULD | not started | n.a. | |

## Last checkpoint output

`make check-0` passed on 2026-11-02 UTC:

- `curl http://localhost:8000/health` → `{"status":"ok","db":"ok"}`
- `pytest` → `1 passed, 1 warning`
- `ruff check .` and `ruff format --check .` → passed

The warning is a FastAPI/Starlette TestClient deprecation warning and does not
fail the suite.

## Decisions made (and why)

- Run the backend in a Python 3.12 Docker image because the host has Python 3.13.
- Keep `make seed` unavailable until Phase 1 supplies real, idempotent seed data.
- Use Docker Compose as the authoritative local verification environment.

## Known gaps / partial items

- Alembic is initialized; its first schema migration is scheduled for Phase 1.

## Next action

- Begin Phase 1: define the database models and initial Alembic migration.

## Environment

- Local URL: http://localhost:8000
- Deployed URL: not deployed
- AWS account/region: not configured
