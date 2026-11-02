# Status (last updated: 2026-11-02 17:41:09 UTC)

| Phase | Title | Tier | State | Checkpoint | Commit / tag |
|---|---|---|---|---|---|
| 0 | Project setup | MUST | done | pass | phase 0: project setup / checkpoint-0 |
| 1 | Data model and core services | MUST | done | pass | phase 1: data model and core services / checkpoint-1 |
| 2 | Intake pipeline | MUST | done | pass | phase 2: intake pipeline / checkpoint-2 |
| 3 | Checks | MUST | done | pass | phase 3: checks and requirements / checkpoint-3 |
| 4 | Approvals, forms, final gate | MUST | done | pass | phase 4: approvals and final gate / checkpoint-4 |
| 5 | Documents | SHOULD | done | pass | phase 5: document handling / checkpoint-5 |
| 6 | Reminders, scheduler, errors | MUST | done | pass | phase 6: reminders and error handling / checkpoint-6 |
| 7 | Frontend dashboard | SHOULD | not started | n.a. | |
| 8 | Test suite and evidence | MUST | not started | n.a. | |
| 9 | AWS deployment | SHOULD | not started | n.a. | |
| 10 | Docs and demo polish | COULD | not started | n.a. | |

## Last checkpoint output

Phase 6 checkpoint passed on 2026-11-02 UTC:

- `make check-6` → `make seed`, `make test`, and `make lint` all passed.
- `make test` → `35 passed, 1 warning in 0.39s`.
- `make lint` → `ruff check .: All checks passed!`; `ruff format --check .:`
  `39 files already formatted`.
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
- Keep local files outside the public HTTP path and expose them only through a short-lived
  download token. S3 uses private objects, server-side encryption, and presigned URLs.
- Keep document AI routing in `DOCUMENT_AI_MODE=fake` by default. Enabling `live` uses the
  existing OpenAI credential but still fails closed to `uncertain` on any error.
- Run local reminders at 09:00 Asia/Dubai only when `SCHEDULER_ENABLED=true`; production
  will use an external scheduler in Phase 9. The job endpoint requires the admin token.
- Record workflow alerts and `ERROR` audit events in independent transactions so a mail
  transport failure cannot erase the audit evidence.

## Known gaps / partial items

- The Gmail source has a complete batch-processing adapter contract, but OAuth credential
  wiring is deferred until a real Gmail deployment is configured.
- S3 storage is implemented but has not been integration-tested against a real AWS bucket.
- Outbound mail remains `ConsoleMailer`; SMTP, SES, and Gmail OAuth are not configured.
- The local APScheduler is disabled by default; it has unit coverage but is not left running
  during the checkpoint suite.

## Next action

- Begin Phase 7: frontend dashboard.

## Environment

- Local URL: http://localhost:8000
- Deployed URL: not deployed
- AWS account/region: not configured
