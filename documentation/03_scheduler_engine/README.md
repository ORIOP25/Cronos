# Scheduler Engine Index

This section documents the Cronos scheduler v1: complete annual generation, adaptive repair, CP-SAT optimization, the global queue, proposal approval, and the test fixtures that validate them.

The scheduler v1 is active in production. The original execution plan and work breakdown (packages W00–W14) were removed once delivered; they remain in git history. Their binding product decisions (D01–D31) now live in section 1.1 of the technical specification.

## Documents

- [SCHEDULER_V1_TECH_SPEC_V2.md](SCHEDULER_V1_TECH_SPEC_V2.md): Technical specification — product decisions, contracts, models, quality policy, queue, API and operations.

## Engine

The composition root is `backend/app/scheduler/composition.py`. It exposes two use cases:

- `generate_schedule` (CompleteGeneration) builds a first, complete annual schedule.
- `repair_published_schedule` (AdaptiveRecovery) repairs an already published schedule after real execution, debt or planning changes.

The domain (`backend/app/scheduler/domain/`) is pure: no ORM, HTTP, Celery, CP-SAT or ambient clock. Infrastructure (`infrastructure/`) holds CP-SAT models, persistence, the queue and task dispatch. The independent validator `candidate_validation.py` recomputes every invariant from the snapshot and the materialized candidate; it never consults solver variables. `VALIDATOR_VERSION` is `v4` and enforces 21 typed violation codes.

## Key behaviors

Lunch break (mandatory). A configured lunch rule is a mandatory continuous break inside its local window, per class and per teacher on active days. Separated gaps never sum; only one uninterrupted interval satisfies the rule. The validator enforces it with `LUNCH_BREAK_VIOLATION`, and the CP-SAT placement model builds lunch options. A partially configured lunch rule fails the snapshot with `LUNCH_CONFIGURATION_INCOMPLETE`.

Stability window. The stability window protects only an already-published schedule. The snapshot computes `protected_dates` only when an ACTIVE `SchedulerVersionV1` exists; a first generation has empty `protected_dates`. The window counts grid days, not calendar days, and always preserves executed and past lessons.

Balanced classroom progression. Constructive priority favors subjects with less curricular progress and classes that have not started. Annual quotas are planned by `infrastructure/annual_model.py` `plan_annual_quotas`. Quality exposes `minimum_class_progress_per_mille` and `class_progress_spread_per_mille`.

Weekly pattern. The constructor remembers the first assignment and room used for each class, weekday and local grid interval. Repeating that assignment can compensate for one lesson of progress. Progress ties favor contiguous class and teacher lessons, then baseline intervals and assignments. The same room is preferred when available. These preferences never remove otherwise eligible resource combinations. Mandatory rules and simultaneous lesson capacity still apply; the pattern can change when resources or curricular progress require it.

Adaptive recovery. The production route compares two validated candidates within the existing budget.
One retains valid published positions and fills missing credit at the earliest available capacity.
The other rebuilds the editable future using the published weekly reference and parallel curricular progress.
The global recovery vector chooses between completion impact, disruption, gaps and preferences.
Both candidates use current calendar, teacher availability, room eligibility and manually corrected execution.
The default route avoids annual placement models and claims no optimality certificate.
Disabling `SCHEDULER_V1_STOP_AT_FIRST_COMPLETE` retains the existing master/detail optimization route.

Operational history. Logged `COMPLETED` and `OCCURRENCE` lessons remain visible across published versions.
Missed lessons contribute no planned credit, and completed lessons contribute through the execution ledger.
Future module slices are reprojected without moving frozen physical positions.
Manual ledger corrections never turn hypothetical future lessons into executed history.
New debt reservations use editable future lessons after the stability window.
Previously approved recovery reservations entering that window remain attached to their frozen lessons.
Planning a recovery never settles debt; actual execution does.
Future logged history reserves its class, teacher and room intervals during search and independent validation.
History remains outside planned credit. Approval cannot add a lesson over those reserved intervals.
Snapshots exclude recovery reservations for closed debt claims. Persisted versions retain their original reservation history.

Compact resource exclusivity. `infrastructure/placement_model.py` `_add_resource_exclusivity` adds at most one option per resource and period with `AddAtMostOne`, grouped by equal interval. It merges only partially overlapping groups and never groups that overlap only through transitivity, so the ends of an overlap chain stay available. It is used for class, teacher and room exclusivity and during room optimization. This replaced pairwise constraints to avoid `OOM`.

Class weekly preferences. The snapshot turns a class availability grid into hard and soft unavailability with `_preference_unavailability`, the same rule as teachers. An Impossível block is hard. An Evitar block is soft. One Preferencial block makes the other blocks count as Evitar. The class grid feeds `UnavailableResource.CLASS` in capacity, candidate validation, quality and placement.

Proven capacity diagnostics. `aggregate_capacity_check` in `domain/capacity.py` also returns `class_deficits`. The class deficit is the class-wide lower bound when the union of the class's eligible periods cannot hold its total residual demand. `diagnose_capacity` emits `INSUFFICIENT_CLASS_TIME` with scope `CLASS:{id}`. `generate_complete` and adaptive recovery return these diagnoses. An `INFEASIBLE` job stores them in `scheduler_job_v1.diagnostics_json`, and `GET /jobs/{id}` returns one entry per affected class.

## Queue and workers

Jobs run through Celery with a single global executor. `backend/app/scheduler_v1_worker.py` registers the task `scheduler.v1.run_next_job`; `backend/app/scheduler_recovery_worker.py` registers `scheduler.v1.supervise`, scheduled every 60 seconds. The supervisor reconciles abandoned attempts and wakes the executor when work waits.

Configuration in `backend/app/config.py`:

| Setting | Default |
| :--- | :--- |
| `SCHEDULER_V1_JOB_TIMEOUT_SECONDS` | `900` |
| `SCHEDULER_V1_HEARTBEAT_SECONDS` | `5.0` |
| `SCHEDULER_V1_ABANDONED_SECONDS` | `120` |
| `SCHEDULER_V1_NUM_WORKERS` | `1` |
| `SCHEDULER_V1_STOP_AT_FIRST_COMPLETE` | `True` |

Job lifecycle, queue, claim and heartbeat live in `infrastructure/jobs.py`; proposal persistence, approval and rejection in `infrastructure/proposals.py`; lesson logs and occurrences in `infrastructure/operations.py`; the progress ledger in `infrastructure/progress.py`; snapshot loading in `infrastructure/snapshot.py`; master/detail search in `infrastructure/search.py`; diagnostics and cgroup memory in `infrastructure/diagnostics.py`.

## API

Endpoints under `/api/v1/scheduler` (`backend/app/api/v1/endpoints/scheduler.py`):

| Operation | Contract |
| :--- | :--- |
| `GET /status` | State, eligibility reasons and current proposal. |
| `POST /generate` | Manual, idempotent request; returns `202` and the job; admin only. |
| `GET /jobs/{job_id}` | Phase, result, summary and proven per-class diagnostics. |
| `POST /jobs/{job_id}/cancel` | Idempotent cancellation. |
| `GET /drafts/current` | Current pending proposal. |
| `GET /drafts/{proposal_id}/diff` | Physical changes and modular updates, separated. |
| `POST /drafts/{proposal_id}/approve` | Atomic approval with revalidation. |
| `POST /drafts/{proposal_id}/reject` | Audited rejection. |

## Test fixtures and verification

The retained `backend/app/scheduler/lab/` modules build deterministic minimal, scale, annual, recovery, and typology fixtures.
Unit tests use those fixtures to verify the actual engine and independent validator.
Historical campaign commands, JSON corpora, matrix reports, and stored-candidate revalidation tools were removed.

Run maintained checks through the root runner:

```text
node scripts/test.mjs critical --scope backend
node scripts/test.mjs integration
node scripts/test.mjs capacity-smoke
```

The 48-class correctness regression lives in `backend/tests/unit/test_scheduler_typology_v1.py`.
It uses the configured 900-second safety budget and validates the first complete candidate.

## Current limitations

- A generation that stops at the safety limit reports quality `NOT_MEASURED`; this is not proof of impossibility.
- There is no rollback to a legacy engine; recovery uses only compatible v1 artifacts.
- After a data reset, local identity is rebuilt on the first admin login through session bootstrap.
