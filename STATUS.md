# Status (last updated: 2026-11-02 12:27:28 UTC)

| Phase | Title | Tier | State | Checkpoint | Commit / tag |
|---|---|---|---|---|---|
| 0 | Project setup | MUST | done | pass | phase 0: project setup / checkpoint-0 |
| 1 | Data model and core services | MUST | done | pass | phase 1: data model and core services / checkpoint-1 |
| 2 | Intake pipeline | MUST | done | pass | phase 2: intake pipeline / checkpoint-2 |
| 3 | Checks | MUST | not started | n.a. | |
| 4 | Approvals, forms, final gate | MUST | not started | n.a. | |
| 5 | Documents | SHOULD | not started | n.a. | |
| 6 | Reminders, scheduler, errors | MUST | not started | n.a. | |
| 7 | Frontend dashboard | SHOULD | not started | n.a. | |
| 8 | Test suite and evidence | MUST | not started | n.a. | |
| 9 | AWS deployment | SHOULD | not started | n.a. | |
| 10 | Docs and demo polish | COULD | not started | n.a. | |

## Last checkpoint output

Phase 2 checkpoint passed on 2026-11-02 UTC:

- `make test` → `9 passed, 1 warning in 0.09s`.
- `make lint` → `ruff check .: All checks passed!`; `ruff format --check .:`
  `21 files already formatted`.
- `curl http://localhost:8000/health` → `{"status":"ok","db":"ok"}`.

The one warning is the FastAPI/Starlette TestClient deprecation warning and
does not fail the suite.

## Decisions made (and why)

- Run the backend in a Python 3.12 Docker image because the host has Python 3.13.
- Use Docker Compose as the authoritative local verification environment.
- Use PostgreSQL `ARRAY`/`JSONB` for the Phase 1 shared request state and payloads.
- Keep the audit log immutable with a PostgreSQL trigger, not application convention.
- Keep AI extraction behind an interface; local tests and the manual demo use deterministic
  `FakeAI`, while `AI_MODE=live` selects the Anthropic SDK implementation.
- Keep all Phase 2 validation and state transitions deterministic; AI only extracts fields.

## Known gaps / partial items

- The Gmail source has a complete batch-processing adapter contract, but OAuth credential
  wiring is deferred until a real Gmail deployment is configured.
- Compliance, financial, duplicate, and document checks intentionally begin in Phase 3.

## Next action

- Begin Phase 3: compliance, financial, duplicate, and country-document checks.

## Environment

- Local URL: http://localhost:8000
- Deployed URL: not deployed
- AWS account/region: not configured
