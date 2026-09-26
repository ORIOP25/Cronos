# Scheduler Engine Index

This section documents complete generation, adaptive repair, CP-SAT optimization, lifecycle state, and recovery operations.

## Documents

Current revision (Revision 2, 26 September 2026): W00–W12 have as-built records plus an independent-review correction cycle; the W12 local gate remains blocked on E2E credentials and owner acceptance, and W13–W14 are the remote-validation and final-cut plan.

- [SCHEDULER_V1_REVAMP_PLAN_V2.md](SCHEDULER_V1_REVAMP_PLAN_V2.md): Execution plan rev 2 — as-built W00–W05 and revised W06–W14 plan with the consolidated optimizations.
- [SCHEDULER_V1_WBS_V2.md](SCHEDULER_V1_WBS_V2.md): Work packages rev 2 — as-built W00–W05, revised W06 (incl. W06.6), campaigns and gates.
- [SCHEDULER_V1_TECH_SPEC_V2.md](SCHEDULER_V1_TECH_SPEC_V2.md): Technical specification rev 2 — implemented contracts and models (secs 2–11, 16–17) and W06+ specification.

Original revision (23 September 2026, historical reference):

- [SCHEDULER_V1_REVAMP_PLAN.md](SCHEDULER_V1_REVAMP_PLAN.md): Agreed v1 replacement plan, domain decisions, implementation gates, benchmarks, and production release.
- [SCHEDULER_V1_TECH_SPEC.md](SCHEDULER_V1_TECH_SPEC.md): Target v1 technical specification, domain contracts, mathematical models, persistence, APIs, tests, and rollout criteria.
- [SCHEDULER_V1_WBS.md](SCHEDULER_V1_WBS.md): Technical work packages, dependencies, iterative scenario campaigns, annual simulations, evidence, and acceptance gates.

Execution records (as-built evidence):

- [SCHEDULER_V1_W00_STATUS.md](SCHEDULER_V1_W00_STATUS.md): Environment, inventory, and execution-boundary work record.
- [SCHEDULER_V1_W01_STATUS.md](SCHEDULER_V1_W01_STATUS.md): Curricular and temporal domain work record.
- [SCHEDULER_V1_W02_STATUS.md](SCHEDULER_V1_W02_STATUS.md): Relational baseline work record.
- [SCHEDULER_V1_W03_STATUS.md](SCHEDULER_V1_W03_STATUS.md): Independent validator, oracle, laboratory, and campaign work record.
- [SCHEDULER_V1_W00_W04_REVIEW.md](SCHEDULER_V1_W00_W04_REVIEW.md): Independent review of W00–W03, reproduced discrepancies, and confirmation that W04 has not started in the reviewed snapshot.
- [SCHEDULER_V1_W00_W04_CORRECTION_WBS.md](SCHEDULER_V1_W00_W04_CORRECTION_WBS.md): Corrective work packages and gates before implementing and accepting W04.
- [SCHEDULER_V1_W00_W04_CORRECTION_STATUS.md](SCHEDULER_V1_W00_W04_CORRECTION_STATUS.md): Correction work record, completed and pending RC items.
- [SCHEDULER_V1_W04_W05_STATUS.md](SCHEDULER_V1_W04_W05_STATUS.md): CompleteGeneration and initial-quality work record with campaign evidence.
- [SCHEDULER_V1_W04_W05_REVIEW.md](SCHEDULER_V1_W04_W05_REVIEW.md): Independent W04/W05 review, reproduced generator failures, quality/proof discrepancies and limits of the test evidence.
- [SCHEDULER_V1_W04_W05_CORRECTION_WBS.md](SCHEDULER_V1_W04_W05_CORRECTION_WBS.md): Corrective packages R45.00–R45.09, adversarial loops and acceptance criteria before closing G2.
- [SCHEDULER_V1_W04_W05_G2_REVIEW.md](SCHEDULER_V1_W04_W05_G2_REVIEW.md): Re-execution of the review counterexamples, annual sample, artifact revalidation and the G2 decision.
- [SCHEDULER_V1_W00_W05_AUDIT_PLAN.md](SCHEDULER_V1_W00_W05_AUDIT_PLAN.md): Latest audit findings, local fixes, remaining defects and limits before reconfirming G2.
- [SCHEDULER_V1_W00_W05_AUDIT_WBS.md](SCHEDULER_V1_W00_W05_AUDIT_WBS.md): Corrective packages R55.00–R55.10 and acceptance criteria before W06.
- [SCHEDULER_V1_W00_W05_AUDIT_STATUS.md](SCHEDULER_V1_W00_W05_AUDIT_STATUS.md): Execution record of the audit packages, B01–B05 corrections, checks and remaining limits.
- [SCHEDULER_V1_W06_W07_STATUS.md](SCHEDULER_V1_W06_W07_STATUS.md): AdaptiveRecovery, adaptive search, diagnostics, stopping policy and honest budget work record.
- [SCHEDULER_V1_W06_W07_REVIEW_WBS.md](SCHEDULER_V1_W06_W07_REVIEW_WBS.md): Independent W06/W07 review, reproduced counterexamples E01–E08 and corrective work packages R67.01–R67.09.
- [SCHEDULER_V1_W06_W07_G3_REPORT.md](SCHEDULER_V1_W06_W07_G3_REPORT.md): Correction-cycle evidence, oracle battery, combined campaigns C02–C15, C19 trajectories and the G3 decision.
- [SCHEDULER_V1_W08_W09_STATUS.md](SCHEDULER_V1_W08_W09_STATUS.md): Global queue, snapshot freshness, proposal/publication transactions, school API and weekly map work record.
- [SCHEDULER_V1_W08_W09_REVIEW_WBS.md](SCHEDULER_V1_W08_W09_REVIEW_WBS.md): Independent W08/W09 review, reproduced continuity and recovery failures R89.01–R89.10.
- [SCHEDULER_V1_W08_W09_REVIEW_STATUS.md](SCHEDULER_V1_W08_W09_REVIEW_STATUS.md): Correction-cycle evidence for R89.01–R89.10 with red-first regressions.
- [SCHEDULER_V1_W10_W11_STATUS.md](SCHEDULER_V1_W10_W11_STATUS.md): Combined campaigns, factor matrix, annual replays, boundaries, worker/complexity calibration and versioned baseline manifest.
- [SCHEDULER_V1_W12_STATUS.md](SCHEDULER_V1_W12_STATUS.md): Legacy removal, consolidated Alembic baseline, clean install, full checks, reserved evaluation and the local gate dossier.
- [SCHEDULER_V1_W10_W12_REVIEW_CORRECTION_STATUS.md](SCHEDULER_V1_W10_W12_REVIEW_CORRECTION_STATUS.md): Independent-review correction cycle (F01–F10, R10.x–R12.x), repeated campaigns, frozen holdout and the current gate decision (blocked).
- [SCHEDULER_V1_ALEMBIC_CONSOLIDATION_PLAN.md](SCHEDULER_V1_ALEMBIC_CONSOLIDATION_PLAN.md): Consolidation plan executed at W12 (kept as the checkpoint record).

## Laboratory

Run a scheduler campaign through the existing runner:

```text
node scripts/test.mjs campaign [--manifest <path>] [--out <dir>] [--case <id>]... [--mode witness|generator|repair|trajectory|longitudinal] [--time-limit <s>] [--workers <n>] [--resume]
```

Manifests: `backend/tests/scheduler_lab/manifest.json` (witnesses),
`backend/tests/scheduler_lab/generation_manifest.json` (W04/W05 corpus),
`backend/tests/scheduler_lab/annual_manifest.json` (10/30/45/60-class annual
corpus), `backend/tests/scheduler_lab/repair_manifest.json` (combined
W06/W07 repair corpus C02–C15 plus an annual case),
`combined_manifest.json`/`boundary_manifest.json` (W10 matrix and feasibility
boundaries), `annual_replay_manifest.json` (W10 longitudinal replays) and
`reserved_manifest.json`/`reserved_annual_manifest.json` (W12 reserved
evaluation). The `repair` mode evaluates AdaptiveRecovery against the published
baseline; the `trajectory` mode records the incumbent trajectory and replays
explicit C19 stopping policies; the `longitudinal` mode chains simulated
execution and events over an annual baseline, validating and approving each
step. Results are written as one JSON file per case plus `report.json` with a
stored candidate, validation report, quality vector, search evidence and, for
repairs, the baseline assessment, diagnoses, budget and trajectory replays.

W10 matrix coverage from a campaign report:

```text
python -m app.scheduler.lab.matrix --manifest <manifest> --report <report.json> --out <matrix_report.json>
```

Revalidate a stored candidate without running the solver:

```text
python -m app.scheduler.lab.revalidate <case.json>
```

## Legacy engine (removed in W12)

- [SCHEDULER_BEHAVIOR.md](SCHEDULER_BEHAVIOR.md): Generation strategies, hard eligibility rules, and ordered quality objectives.
- [SCHEDULER_ARCHITECTURE.md](SCHEDULER_ARCHITECTURE.md): CP-SAT mathematical formulation, Celery execution, and draft lifecycle.
- [SCHEDULER_OPERATIONS.md](SCHEDULER_OPERATIONS.md): Frozen horizons, backlog resolution, draft diff auditing, and repair runbooks.
