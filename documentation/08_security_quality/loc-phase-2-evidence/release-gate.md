# Phase 2 release gate

The branch gate is the repository CI workflow. It runs Ruff, immutable migration checks, database audits, backend unit/integration/contract tests, frontend verification/build, and Clerk-backed E2E/capacity smoke checks.

Local checks completed for this implementation:

- `backend/.venv/Scripts/ruff.exe check .`
- `backend/.venv/Scripts/python.exe -m pytest -q tests/unit` — 381 passed
- `frontend/npm run verify` — 64 files / 369 tests passed and build completed

The local integration suite was not runnable because PostgreSQL is not listening on `127.0.0.1:5432`; CI provisions its own PostgreSQL and Redis services. The stored LOC evidence is intentionally not rebaselined: the phase records a reduction against the approved baseline and keeps the baseline immutable until a release owner accepts the new measurement.

Manual checks remain environment-dependent: authenticated CSS coverage and Clerk provider flows are exercised by CI E2E rather than by the local shell.
