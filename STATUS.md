# Status (last updated: 2026-11-02 17:20:13 UTC)

| Phase | Title | Tier | State | Checkpoint | Commit / tag |
|---|---|---|---|---|---|
| 0 | Project setup | MUST | done | pass | phase 0: project setup / checkpoint-0 |
| 1 | Data model and core services | MUST | done | pass | phase 1: data model and core services / checkpoint-1 |
| 2 | Intake pipeline | MUST | done | pass | phase 2: intake pipeline / checkpoint-2 |
| 3 | Checks | MUST | done | pass | phase 3: checks and requirements / checkpoint-3 |
| 4 | Approvals, forms, final gate | MUST | done | pass | phase 4: approvals and final gate / checkpoint-4 |
| 5 | Documents | SHOULD | not started | n.a. | |
| 6 | Reminders, scheduler, errors | MUST | not started | n.a. | |
| 7 | Frontend dashboard | SHOULD | not started | n.a. | |
| 8 | Test suite and evidence | MUST | not started | n.a. | |
| 9 | AWS deployment | SHOULD | not started | n.a. | |
| 10 | Docs and demo polish | COULD | not started | n.a. | |

## Last checkpoint output

Phase 4 checkpoint passed on 2026-11-02 UTC:

- `make check-4` → `make seed`, `make test`, and `make lint` all passed.
- `make test` → `24 passed, 1 warning in 0.25s`.
- `make lint` → `ruff check .: All checks passed!`; `ruff format --check .:`
  `31 files already formatted`.
- `curl http://localhost:8000/health` → `{"status":"ok","db":"ok"}`.

The one warning is the FastAPI/Starlette TestClient deprecation warning and
does not fail the suite.

## Decisions made (and why)

- Run the backend in a Python 3.12 Docker image because the host has Python 3.13.
- Use Docker Compose as the authoritative local verification environment.
- Use PostgreSQL `ARRAY`/`JSONB` for the Phase 1 shared request state and payloads.
- Keep the audit log immutable with a PostgreSQL trigger, not application convention.
- Switched the live extractor from Anthropic to the OpenAI Responses API at the user's request.
  Local tests and the manual demo keep deterministic `FakeAI`; `AI_MODE=live` selects OpenAI.
- Keep all Phase 2 validation and state transitions deterministic; AI only extracts fields.
- Run compliance first and label every screening decision and notification `SIMULATED`;
  fixture data is not real compliance screening.
- Keep document checklist dispatch in Phase 4 alongside its signed upload token. Phase 3
  resolves requirements and holds unknown countries for human review.
- Dispatch all independent Phase 4 actions in one pass; action tokens are single-use for
  manager and duplicate decisions, while document upload remains available for Phase 5.
- Use a PostgreSQL row lock plus unique vendor keys at the final gate; 20 concurrent calls
  produced exactly one vendor in the checkpoint test.

## Known gaps / partial items

- The Gmail source has a complete batch-processing adapter contract, but OAuth credential
  wiring is deferred until a real Gmail deployment is configured.
- File upload, storage, and document review are deferred to Phase 5; the document link
  currently shows the exact checklist only.
- Outbound mail remains `ConsoleMailer`; SMTP, SES, and Gmail OAuth are not configured.

## Next action

- Begin Phase 5: private document upload, storage, classification, and review.

## Environment

- Local URL: http://localhost:8000
- Deployed URL: not deployed
- AWS account/region: not configured
