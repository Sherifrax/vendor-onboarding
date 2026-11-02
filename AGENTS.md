# Repository Guidelines

## Project Structure & Module Organization

This repository implements the Vendor Onboarding Automation plan in `codex-plan.md`. Keep the single-service layout: `backend/app/` holds FastAPI code and services; `backend/tests/` holds pytest coverage; and `backend/fixtures/` holds raw-email fixtures. Put migrations in `backend/migrations/`, the React/Vite dashboard in `frontend/`, deployment material in `infra/`, documents in `docs/`, and utilities in `scripts/`.

Keep orchestration thin. Put rules in `backend/app/services/` (for example, `financial.py` and `gate.py`); keep AI, email, and storage behind interfaces.

## Build, Test, and Development Commands

Once Phase 0 creates the tooling, use the Makefile as the normal entry point:

- `make up` starts PostgreSQL and the API; verify `curl localhost:8000/health`.
- `make down` stops local containers.
- `make seed` installs country requirements, compliance fixtures, and synthetic vendors; it must be idempotent.
- `make test` runs pytest, including the `T01`–`T23` matrix; `make lint` runs Ruff.
- `make evidence` refreshes `docs/TEST_EVIDENCE.md` after a passing test run.

Use `docker-compose` locally. Do not treat a command as available until Phase 0 implements it.

## Coding Style & Naming Conventions

Target Python 3.12, FastAPI, SQLAlchemy 2, and Pydantic v2. Use four-space indentation, type hints, `snake_case` modules/functions, `PascalCase` classes, and Pydantic models at API boundaries. Use TypeScript in `frontend/`, with `PascalCase` components and `camelCase` variables. Let Ruff enforce Python style.

Use consistent IDs: `VR-<thread_id>`, `VEN-<thread_id>`, and `VEND-<thread_id>`.

## Testing Guidelines

Write focused pytest tests plus end-to-end scenarios in `backend/tests/test_matrix.py`, named `T01` through `T23`. Mock AI, mail, and storage; use `httpx.AsyncClient` for endpoints. Maintain at least 85% coverage for `services/`. Test fail-closed paths, replays, token reuse/expiry, and concurrent final-gate calls.

## Security & Workflow Rules

Treat email and documents as untrusted. AI may extract or classify only; code makes every decision. Missing, ambiguous, unreadable, or errored data must produce `HOLD`. Mark simulated compliance as `SIMULATED`; never represent it as real screening. Do not commit secrets: use `.env`, ship `.env.example`, and use AWS SSM/Secrets Manager in deployment. Preserve the append-only audit log, hashed single-use action tokens, private storage, and admin-token protection.

## Commits, Pull Requests, and Status

Complete phases in order and mark checklist items only after checks pass. Update `STATUS.md` after each phase with checkpoint output, decisions, gaps, and next action. Make one commit per phase: `phase N: <title>`; tag passing checkpoints `checkpoint-N`. Pull requests should state the phase, list relevant tests, describe schema/environment changes, and include screenshots for UI changes.
