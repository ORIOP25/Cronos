# Scheduler Engine Index

This section documents the Cronos scheduler v1: complete annual generation, adaptive repair, CP-SAT optimization, the global queue, proposal approval, and the test fixtures that validate them.

The scheduler v1 is active in production. The original execution plan and work breakdown (packages W00–W14) were removed once delivered; they remain in git history. Their binding product decisions (D01–D31) now live in section 1.1 of the technical specification.

## Documents

- [SCHEDULER_V1_TECH_SPEC_V2.md](SCHEDULER_V1_TECH_SPEC_V2.md): Technical specification — product decisions, contracts, models, quality policy, queue, API and operations.

## Engine

The composition root is `backend/app/scheduler/composition.py`. It exposes two use cases:

- `generate_schedule` (CompleteGeneration) builds a first, complete annual schedule.
- `repair_published_schedule` (AdaptiveRecovery) repairs an already published schedule after real execution, debt or planning changes.

The domain (`backend/app/scheduler/domain/`) is pure: no ORM, HTTP, Celery, CP-SAT or ambient clock. Infrastructure (`infrastructure/`) holds CP-SAT models, persistence, the queue and task dispatch. The independent validator `candidate_validation.py` recomputes every invariant from the snapshot and the materialized candidate; it never consults solver variables. Its version and typed violation codes are owned by [`candidate_validation.py`](../../backend/app/scheduler/domain/candidate_validation.py).

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

Class module selection. `infrastructure/curriculum.py` `sync_curricular_projection` projects one `curricular_requirement` per selected module of each class/subject link, with `sequence = module.order + 1`. A module deselected with execution credits keeps a `planned = false` row; a module deselected without credits is deleted. An active link (teacher assigned, in range and not archived) without a selected module raises `CLASS_SUBJECT_WITHOUT_MODULES`. `infrastructure/progress.py` `load_planning_requirements` loads every row, reproduces the history with the catalogue minutes, and applies `close_retired_modules`: a retired module with executed minutes is closed at those minutes and receives no new credit. The snapshot, dashboard, grid changes and progress readers use this planning view.

Joint lessons. `domain/teaching_units.py` `build_teaching_units` splits class assignments into teaching units: an unsplit `A` unit, separate-segment `S` units, shared joint-segment `J` units, and per-class deficit `D` units. Joint modules credit every member class with the joint progress, and a class behind gets a `D` unit whose requirement is that progress. Units carry strict stage-to-stage precedences, per-member eligibility and a shared room. Construction (`infrastructure/constructive.py`) and recovery (`infrastructure/recovery_construction.py`) only start a unit after its predecessors finish. A `D` unit is an ordinary residual unit and uses the same priority every open debt uses; it needs no `teaching_unit_key` on the snapshot. A single joint unit left without any eligible shared period is diagnosed as `JOINT_NO_COMMON_TIME` in `domain/diagnostics.py`; complete generation carries the code on the result stop reason and the diagnostic message, and the search outcome uses the same message. General infeasibility, cancellations and interrupted searches keep their generic diagnosis. `lab/typology.py` `build_joint_typology_fixture` builds the joint family (general subjects shared, technical subjects separate).

Compact resource exclusivity. `infrastructure/placement_model.py` `_add_resource_exclusivity` adds at most one option per resource and period with `AddAtMostOne`, grouped by equal interval. It merges only partially overlapping groups and never groups that overlap only through transitivity, so the ends of an overlap chain stay available. It is used for class, teacher and room exclusivity and during room optimization. This replaced pairwise constraints to avoid `OOM`.

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
| `GET /jobs/{job_id}` | Phase, result and summary. |
| `POST /jobs/{job_id}/cancel` | Idempotent cancellation. |
| `GET /drafts/current` | Current pending proposal. |
| `GET /drafts/{proposal_id}/diff` | Physical changes and modular updates, separated. |
| `POST /drafts/{proposal_id}/approve` | Atomic approval with revalidation. |
| `POST /drafts/{proposal_id}/reject` | Audited rejection. |

## Test fixtures and verification

The retained `backend/app/scheduler/lab/` modules build deterministic minimal, scale, annual, recovery, and typology fixtures.
Unit tests use those fixtures to verify the actual engine and independent validator.
Historical campaign commands, JSON corpora, matrix reports, and stored-candidate revalidation tools were removed.
The joint family (`lab/typology.py` `build_joint_typology_fixture`) shares the general subjects of each course and keeps the technical subjects separate. Its `backend/tests/unit/test_joint_lesson_lab.py` pilot runs the constructive route against the no-joint peer at 48 classes.

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
