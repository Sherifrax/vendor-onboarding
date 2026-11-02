# Status (last updated: 2026-11-02 11:54:40 UTC)

| Phase | Title | Tier | State | Checkpoint | Commit / tag |
|---|---|---|---|---|---|
| 0 | Project setup | MUST | done | pass | phase 0: project setup / checkpoint-0 |
| 1 | Data model and core services | MUST | done | pass | phase 1: data model and core services / checkpoint-1 |
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

Phase 1 checkpoint passed on 2026-11-02 UTC:

- Fresh local `vendor` database: `alembic upgrade head` →
  `Running upgrade -> ac3ab4fbaa66, create core vendor onboarding tables`.
- `make check-1` (including `make seed` twice) → `4 passed, 1 warning in 0.07s`.
- `ruff check .` → `All checks passed!`; `ruff format --check .` →
  `15 files already formatted`.
- Seed verification after repeated runs → `country_requirements=5`,
  `compliance_fixtures=3`, `synthetic_vendors=3`.
- `curl http://localhost:8000/health` → `{"status":"ok","db":"ok"}`.

The one warning is the FastAPI/Starlette TestClient deprecation warning and
does not fail the suite.

## Decisions made (and why)

- Run the backend in a Python 3.12 Docker image because the host has Python 3.13.
- Use Docker Compose as the authoritative local verification environment.
- Use PostgreSQL `ARRAY`/`JSONB` for the Phase 1 shared request state and payloads.
- Keep the audit log immutable with a PostgreSQL trigger, not application convention.

## Known gaps / partial items

- No known Phase 1 gaps. Later-phase services and endpoints are intentionally not built yet.

## Next action

- Begin Phase 2: intake pipeline.

## Environment

- Local URL: http://localhost:8000
- Deployed URL: not deployed
- AWS account/region: not configured
