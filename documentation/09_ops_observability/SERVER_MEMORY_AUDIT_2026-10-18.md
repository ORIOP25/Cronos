# Server Memory Audit — 18 October 2026

## Purpose

Identify ways to reduce server RAM without weakening functionality, schedule quality, security, or recovery.
This audit changes documentation only. Experimental encoders remain outside the application.

## Intended Reader

The product owner and engineers implementing the measured improvements.

## Prerequisites

Read the [runtime architecture](../01_system_architecture/SYSTEM_ARCHITECTURE.md) and [cloud operations guide](CLOUD_OPERATIONS.md).
Use the [Command Reference](../00_getting_started/COMMAND_REFERENCE.md) for repository verification and delivery.

## What the System Does

The API handles requests and dispatches work through Redis.
The solver worker generates schedules and repairs published schedules.
Beat publishes periodic tasks. A separate supervisor recovers abandoned attempts.
PostgreSQL stores tenant data under forced RLS.
Cloudflare serves the frontend outside these backend services.

## Why the Behavior Exists

The largest identified RAM risk is an expanding placement model during adaptive recovery.
Permanent process overhead is a separate, smaller opportunity.
The first improvement should compress an equivalent constraint formulation rather than reduce the search scope.

### Executive findings

1. Production logs record an 8 GB memory peak and an OOM counter increase on 17 October.
2. One placement constraint grows quadratically with eligible periods.
3. A bounded experiment reduces full-model build RSS by approximately 33%, with an equivalent final-lesson rule.
4. Beat loads execution code it only needs to name. Removing those imports saves approximately 43.6 MiB in import experiments.
5. Redis uses little RAM. Replacing the broker or database is not justified by these measurements.

These are audit findings and experiments, not savings already delivered in production.

## Components and Ownership

### Scope and provenance

- Observation date: 18 October 2026, Europe/Lisbon.
- Railway project: `hopeful-enthusiasm`, environment `production`.
- API readiness reported revision: `b432db24be9d16a0844e5fc4c3e19a91e2c5c708`.
- Railway deployment metadata reported that revision for API, worker, Beat, and supervisor.
- The original local checkout was `05787f07`; experiments instead mounted an archive of the reported production revision.
- The local runtime image was `sha256:9c2be4b06321576734aa90d971d83aa64e6ae072aa4969dfe03f45c4729141a5`.
- Its Python version was 3.14.7. All 64 package versions checked matched the production lock file.

Railway MCP supplied topology, configuration, metrics, deployment metadata, HTTP totals, and filtered logs.
Local Docker supplied isolated import and model-build measurements.
No production configuration, secret, database row, task, or deployment changed during the audit.

Configuration reads included a pre-existing staged patch with three changes.
No per-service configuration changes were shown for the inspected services. The audit did not apply the staged patch.
MCP redacted variable values. Live pooling and CP-SAT thread settings therefore remain unverified.

### Production RAM baseline

The following values use decimal MB, converted from `MEMORY_USAGE_GB`.
The 24-hour query used 300-second sampling and returned 289 samples per service.

| Service | Latest sampled MB | Mean MB | Largest sampled MB |
| :--- | ---: | ---: | ---: |
| API | 148.4 | 173.7 | 473.2 |
| Solver worker | 164.1 | 193.3 | 1,666.5 |
| Supervisor | 132.3 | 141.4 | 380.6 |
| Beat | 99.6 | 107.7 | 222.5 |
| PostgreSQL | 250.3 | 268.5 | 322.8 |
| Redis | 12.6 | 12.6 | 12.8 |
| Sum | 807.4 | 897.2 | Not computed |

Service maxima need not occur together; adding them would not establish the peak of the whole application.
These measurements cross deployments and do not represent a controlled load test.
The API HTTP summary counted 798 requests, including 787 successful responses, 11 client errors, and no server errors.
That volume does not prove capacity under concurrent school use.

The seven-day query also used 300-second sampling.
It reported mean RAM of 160.7 MB for API, 180.2 MB for worker, 144.6 MB for supervisor, and 114.5 MB for Beat.
These averages do not establish a memory leak or its absence.

## Data or Request Flow

### Finding 1: unrestricted placement creates a large memory peak

The adaptive route tries retaining and rebuilding the schedule before using unrestricted placement.
The fallback expands the planning horizon and builds a single scope without annual quotas.
Each eligible assignment-period pair creates placement, room, final-lesson, and waste variables.

Sources:

- [Adaptive search and fallback](../../backend/app/scheduler/infrastructure/search.py): `search_adaptive_schedule`, `_unrestricted_fallback`.
- [Placement model](../../backend/app/scheduler/infrastructure/placement_model.py): `_unrestricted_scope`, `_add_assignment_options`, `_add_assignment_credit`.

Selected production log evidence from 17 October, with timestamps converted to Europe/Lisbon:

| Time | Evidence |
| :--- | :--- |
| 13:38 | Placement model: 3,955,579 variables, 1,497,227 constraints, approximately 5.94 GB current cgroup memory. |
| 14:32 | A subsequent attempt reports `container_memory_peak_bytes=8000000000` and `container_oom_kill_count=1`; earlier events reported zero kills. |
| 14:34 | Smaller placement model: 628,883 variables and 239,311 constraints. Memory reaches approximately 2.10 GB after solving. |
| 14:36 | Expanded placement model: 3,955,579 variables, 1,497,227 constraints, approximately 6.08 GB before solving. |

The cgroup high-water mark and counter are historical container signals.
They establish a recorded OOM event, but do not identify its exact kill timestamp or prove every later attempt failed.
The events span earlier deployments. They do not prove a new failure on the revision reported today.
The inspected production source still contains the quadratic formulation described below.

The sampled graph showed a much smaller maximum than these cgroup events.
Use both signals; sampled metrics are insufficient for selecting a safe memory limit.
[Railway documents continuous metrics across deployments](https://docs.railway.com/observability/metrics).

### Finding 2: the final-lesson rule repeats quadratic suffixes

The current rule requires each selected period to occur no later than the selected final period.
For each eligible period, it sums every remaining final-period indicator.
With N eligible periods, these suffixes contain N(N+1)/2 references per assignment, before other model terms.

An equivalent formulation introduces one integer identifying the selected final position.
Because exactly one final indicator is selected, its index is the weighted sum of final indicators.
Each placement then implies that its index cannot exceed that final index.
This expresses the same ordering with a linear number of references.

Experimental unrestricted-scope formulation:

```python
last_position = model.NewIntVar(0, len(keys) - 1, "")
model.Add(last_position == sum(i * state.last[key] for i, key in enumerate(keys)))
for i, key in enumerate(keys):
    model.Add(last_position >= i).OnlyEnforceIf(state.x[key])
```

Keep the existing exactly-one-final, credit, final-domain, waste, room, and conflict constraints.
This snippet is not a complete replacement for the function's quota branches.

#### Measured model-build experiment

The experiment used the repository's typology fixture: 12 classes, 84 assignments, and its first 400 periods.
It built the complete unrestricted placement model, without solving it or accessing any database.
Each container had no network, a read-only filesystem, one CPU, and a 768 MiB memory limit.
Three fresh containers measured each encoder.

| Measure | Current encoder | Experimental encoder |
| :--- | ---: | ---: |
| Variables | 169,039 | 169,123 |
| Constraints | 163,039 | 163,123 |
| Linear variable references | 7,142,923 | 439,723 |
| RSS after construction, range | 358,872–360,004 KiB | 241,524–242,472 KiB |
| Median RSS after construction | 360,000 KiB | 242,076 KiB |
| Build time, median | 17.793 seconds | 6.516 seconds |

Total process RSS after construction fell approximately 32.8%; linear references fell approximately 93.8%.
The RSS difference was approximately 115 MiB per process in this bounded case.
This is neither a measured reduction in full-year solving memory nor a production savings forecast.
Host load affects build timings.

Small exhaustive solver experiments compared both encoders with two through six periods and a partial final lesson.
All projected placement, final-lesson, and waste solutions matched: 1, 3, 6, 10, and 15 solutions respectively.
The ordering equivalence follows from the exactly-one-final invariant.
These experiments do not cover every quota branch, recovery policy, or time-bounded search trajectory.

### Finding 3: Beat imports execution dependencies unnecessarily

[Celery configuration](../../backend/app/celery_worker.py) imports member, privacy, and recovery task modules by default.
Celery's Beat loader initializes those imports even though Beat publishes task names rather than executing their handlers.
That loads SQLAlchemy models, database setup, and Clerk integration code into Beat.

Three isolated import measurements produced these median PSS values:

| Import scenario | Median PSS KiB |
| :--- | ---: |
| Celery application configuration only | 37,083 |
| Default execution task imports | 81,692 |
| Beat configuration with no execution imports | 37,022 |
| Supervisor task imported alone | 71,664 |
| Solver worker and default tasks | 135,170 |
| API application | 125,671 |

Removing execution imports from Beat saved approximately 43.6 MiB in this import-only experiment.
Restricting supervisor imports saved approximately 9.8 MiB before considering its process pool.
These experiments do not measure complete running-daemon savings.

Keep task registration explicit on executing workers when separating the imports.
Verify every periodic task and its queue before release.
Preserve one independent supervisor so a blocked solver cannot delay recovery.

### Finding 4: additional opportunities need narrower measurements

| Opportunity | Evidence and proposed next step | Priority |
| :--- | :--- | :--- |
| Solver imports in the parent | Worker startup imports composition, OR-Tools, NumPy, and pandas. Measure deferring solver imports into the executing child. | After the constraint fix |
| Previous model lifetime | `solve_placement` retains `state` and `solver` until rebinding. The previous state survives while Python evaluates the next model build. Release it after extracting selections and evidence. | Small follow-up |
| Snapshot row materialization | `load_version_lessons` materializes ORM lessons and slices before building domain values. Measure column projections and bounded grouping. | After worker peaks |
| Canonical serialization | `payload_digest` normalizes and serializes a full tree before encoding it for hashing. Measure incremental hashing while preserving byte-for-byte digests. | Secondary |
| Supervisor pool | Local inspection shows parent and child processes at concurrency one. Benchmark a suitable simpler pool only for this lightweight task. | Conditional |
| API database connections | The enabled pool uses library defaults. Read actual connection counts, settings, and query concurrency before changing it. | Unquantified |
| PostgreSQL memory | PostgreSQL accounts for approximately 268.5 MB mean. Inspect server settings, connection memory, and temporary-file activity before tuning. | Unquantified |

Use PSS and container memory when comparing prefork workers; summing their RSS counts shared pages repeatedly.
Import experiments confirmed that API and Beat did not load OR-Tools, NumPy, or pandas.
Only the solver scenario loaded these numerical packages.
Do not delete transitive dependencies merely because application code does not import them directly.

SQLAlchemy documents that calling `.all()` defeats bounded result consumption.
Streaming still offers no benefit when the application immediately rebuilds the complete list.
Preserve tenant filters, transaction semantics, grouping of joint lessons, and validation.
[SQLAlchemy large-result guidance](https://docs.sqlalchemy.org/en/20/orm/queryguide/api.html#fetching-large-result-sets-with-yield-per).

PostgreSQL memory depends on operations and concurrent sessions, not only database size.
Reducing buffers or work memory may increase disk work and latency.
No production SQL access or server-setting inspection was available during this audit.
[PostgreSQL resource settings](https://www.postgresql.org/docs/18/runtime-config-resource.html).

## Contracts and Invariants

- Preserve all existing hard constraints, quality objectives, validation, and tenant isolation.
- Preserve supervisor independence, cancellation, heartbeats, retries, and database advisory locking.
- Preserve worker child recycling after a Celery task.
- Do not lower time budgets, limit candidate rooms, or freeze extra weeks merely to report lower RAM.
- Do not treat a memory guard that returns fewer complete schedules as an equivalent optimization.
- Do not replace Redis, PostgreSQL, Celery, or the authentication SDK without measured evidence that simpler changes are insufficient.

The executor drains multiple database jobs inside one Celery task.
Therefore, `max-tasks-per-child=1` recycles after draining that task, not necessarily after every individual generation job.
This matters when investigating memory retained across a busy queue.
See [the worker entry point](../../backend/app/scheduler_v1_worker.py).

Celery documents child recycling as a response to worker memory high-water marks.
Changing the solver to a pool without child recycling would remove that protection.
[Celery memory guidance](https://docs.celeryq.dev/en/v5.6.3/userguide/optimizing.html), [pool capabilities](https://docs.celeryq.dev/en/stable/userguide/concurrency/index.html).

OR-Tools 9.15 documents `max_memory_in_mb` as specific to its pure SAT solver, not a general CP-SAT limit.
Its `ignore_names` parameter already defaults to true for the internal solver copy.
Neither setting is a demonstrated fix for the application's model-build growth.
[Pinned OR-Tools parameter source](https://github.com/google/or-tools/blob/v9.15/ortools/sat/sat_parameters.proto).

## States and Transitions

Recommended implementation order:

1. Replace the quadratic final-lesson encoding with an equivalent linear formulation.
2. Separate Beat and supervisor imports from execution-only dependencies.
3. Measure and reduce retained model and ORM representations.
4. Reassess production RAM under comparable generation and recovery workloads.
5. Consider provider limits only after measured headroom and quality checks support them.

Each step requires its own before-and-after evidence.
Do not add the experimental savings together as a guaranteed production result.

### Implementation status

Steps 1 and 2 and the previous-model release of Finding 4 are implemented. Steps 3 to 5 and the other Finding 4 items still need their own measurements.

- Finding 2: `_add_assignment_credit` in [`placement_model.py`](../../backend/app/scheduler/infrastructure/placement_model.py) uses one final-position integer. [`test_scheduler_placement_final_encoding_v1.py`](../../backend/tests/unit/test_scheduler_placement_final_encoding_v1.py) checks linear growth and exhaustive solution equivalence, including partial credit, a final-duration subset, and the quota branch.
- Finding 3: Beat imports no task module, and [`test_celery_task_imports.py`](../../backend/tests/unit/test_celery_task_imports.py) checks which process registers each periodic task.
- Finding 4, previous model lifetime: `solve_placement` releases each window's model before building the next one.
- Finding 4, solver imports in the parent: `_run_search` imports the solver composition on first use, so the prefork parent loads no OR-Tools, NumPy, or pandas. [`test_worker_lazy_solver_imports.py`](../../backend/tests/unit/test_worker_lazy_solver_imports.py) checks this. Parent PSS, median of three fresh processes in `cronos-backend-test:local`, fell from 143,366 kB to 87,793 kB.
- Finding 4, supervisor pool: the supervisor runs `--pool=solo`. Measured with a real Redis 8.2 broker and one worker container per run, the summed PSS of all processes was 109,129 kB with prefork (parent plus child) and 89,966 kB with solo, medians of three.
- The placement memory guard (`MAX_PLACEMENT_VARIABLES`) turns an oversized scope into `INCONCLUSIVE` instead of an OOM kill. It is a safety net, not a memory optimization.

Model-build measurement after the change, on 18 October 2026. It used the 48-class typology fixture, an unrestricted scope, one CPU, an 8 GiB container, one search worker, and 120 seconds of search:

| Horizon | Encoder | Variables | Linear references | RSS after build | Peak RSS during search |
| :--- | :--- | ---: | ---: | ---: | ---: |
| Half year | Previous | 735,062 | 33,629,270 | 1,237 MB | 5,984 MB |
| Half year | Linear | 735,398 | 1,912,550 | 709 MB | 3,235 MB |
| Full year | Previous | 1,444,778 | 126,427,850 | 3,320 MB | Not run |
| Full year | Linear | 1,445,114 | 3,759,290 | 1,283 MB | 5,796 MB |

No search reached a solution within 120 seconds, so this table compares memory, not schedule quality.

## Failure Modes

An equivalent mathematical model can still change search behavior within a finite deadline.
A changed encoder must therefore pass real generation and recovery quality comparisons.
Small-instance solution equivalence alone does not establish identical production schedules or completion rates.

Five-minute metrics can miss short peaks. Container high-water marks also survive between jobs within the same container.
Do not attribute a previous job's peak to the next job merely because the next event reports it.

No full-year failing production workload was replayed.
No heap profiler ran inside production, and no authenticated load test was sent to the live API.
The audit does not establish the exact retained heap of production API requests or PostgreSQL sessions.

## Verification Procedure

### Evidence collected during this audit

| Exact operation | Result |
| :--- | :--- |
| Railway MCP `get_service_metrics`, `hoursBack=24`, `sampleRateSeconds=300`, each service | Baseline table above. |
| Railway MCP `get_service_metrics`, `hoursBack=168`, `sampleRateSeconds=300`, Python services | Seven-day means above. |
| Railway MCP `get_logs`, worker, `startDate=2026-10-17T00:00:00Z`, `filter=container_memory`, `limit=200` | 28 memory events; selected events above. |
| `curl.exe -s https://api.cronos.pt/health/ready` | `status=ok`, PostgreSQL and Redis connected, revision recorded above. |
| `docker compose ps` | Local dependencies healthy; running backend processes inspected. |
| `docker stats --no-stream --format '{{.Name}} {{.MemUsage}} {{.CPUPerc}}'` | Local baseline used for corroboration only. |
| `python /audit/profile_imports.py` in isolated runtime container | 30 measurements: ten scenarios, three fresh processes each. |
| `python /audit/profile_credit_encoding.py` in isolated runtime container | Five exhaustive equivalence cases passed; six encoder-size measurements completed. |
| `python /audit/profile_full_model.py production` and `python /audit/profile_full_model.py compact` | Three complete-model builds each; results above. |
| Locked-package comparison with `importlib.metadata.version` | 64 pins checked, no mismatches. |

The `/audit` files are standalone audit artifacts, not production application modules.
They mount the archived production `app` directory over the runtime image.
The task provides the experimental scripts, raw measurements, and sanitized provider evidence separately.

### Required proof before implementing the findings

Use the [scheduler skill](../../.agents/skills/cronos-scheduler/SKILL.md) and [Command Reference](../00_getting_started/COMMAND_REFERENCE.md#verification-by-change-type).
For the encoder, add failing behavior tests first, including partial credits, final-domain restrictions, and quota branches.
Run scheduler unit and integration proof, the slow 48-class scenarios, and required CI gates.
Compare generation, adaptive recovery, infeasible cases, presence, availability, joint lessons, and room rules.
Compare valid completion, credited minutes, quality vectors, cancellation, deadlines, and peak cgroup memory.

For task imports, verify registration and dispatch of all periodic tasks, the supervisor queue, and abandoned-job recovery.
The audit itself changes no runtime behavior; application tests are not presented as proof that these experimental optimizations are production-ready.

## Source Map

- [Runtime image and dependency installation](../../backend/Dockerfile).
- [Production dependency lock](../../backend/requirements.txt).
- [Celery configuration](../../backend/app/celery_worker.py).
- [Database engine](../../backend/app/db/database.py).
- [Scheduler worker](../../backend/app/scheduler_v1_worker.py).
- [Scheduler supervisor](../../backend/app/scheduler_recovery_worker.py).
- [Placement model](../../backend/app/scheduler/infrastructure/placement_model.py).
- [Search orchestration](../../backend/app/scheduler/infrastructure/search.py).
- [Snapshot loading](../../backend/app/scheduler/infrastructure/snapshot.py).
- [Canonical serialization](../../backend/app/scheduler/domain/serialization.py).
- [Memory diagnostics](../../backend/app/scheduler/infrastructure/diagnostics.py).
- [Typology fixtures](../../backend/app/scheduler/lab/typology.py).
- [Existing typology tests](../../backend/tests/unit/test_scheduler_typology_v1.py).

## Related Documents

- [Scheduler Engine](../03_scheduler_engine/README.md).
- [Observability and Recovery](OBSERVABILITY_AND_RECOVERY.md).
- [Deployment Runbook](DEPLOYMENT_RUNBOOK.md).
