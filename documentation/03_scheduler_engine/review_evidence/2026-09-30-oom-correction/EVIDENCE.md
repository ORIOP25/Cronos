# OOM correction — execution evidence

Date: 30 September 2026.
Baseline: `3e657e2f01762830747a714c11f4cb13db68e094`.

## Files in this work

- `backend/app/scheduler/infrastructure/placement_model.py`
- `backend/app/scheduler/infrastructure/annual_model.py`
- `backend/app/scheduler/infrastructure/search.py`
- `backend/app/scheduler/infrastructure/diagnostics.py` (new)
- `backend/app/scheduler_v1_worker.py`
- `backend/tests/unit/test_scheduler_resource_exclusivity_v1.py` (new)
- `backend/tests/unit/test_scheduler_diagnostics_v1.py` (new)

Pre-existing changes (deleted CSV templates, modified and new documentation)
are outside this work. They were not staged.

## Structural measurement

The measurement uses `build_scale_fixture(n, module_minutes=60)`, one period,
eight common eligible rooms, `_unrestricted_scope` and `_build_scope_state`.
Variables are unchanged. Constraints before and after the fix:

| n | variables | constraints before | constraints after |
| ---: | ---: | ---: | ---: |
| 8 | 96 | 295 | 75 |
| 16 | 192 | 1103 | 141 |
| 32 | 384 | 4255 | 275 |

Gate `C(32) <= 2 * C(16)`: before `4255 > 2206` (red), after `275 <= 282`
(green).

## Commands and results

| Command | Result |
| :--- | :--- |
| `pytest tests/unit/test_scheduler_resource_exclusivity_v1.py` | 14 passed |
| `pytest tests/unit/test_scheduler_diagnostics_v1.py` | 7 passed |
| `pytest tests/unit` (local, Python 3.12) | 812 passed |
| `node scripts/test.mjs fast --scope backend -- -k "scheduler_resource_exclusivity_v1 or scheduler_diagnostics_v1"` | 21 passed (Python 3.14) |
| `node scripts/test.mjs all --scope backend` | exit 0; 1278 passed |
| `git diff --check` | clean |

The `all --scope backend` run covers Ruff, unit tests, integration tests,
infrastructure contracts and the coverage gates.

## Continuous integration

- Commit: `000e4d9ec404cc0b60e06f58539cdc94e44eeab7` on `main`.
- CI run: https://github.com/ORIOP25/Cronos/actions/runs/36730219027
- Result: `success`. The `frontend`, `backend` and `e2e` jobs passed.

## Limitations

- OOM.05: the isolated measurement with the organization 27 snapshot was not
  executed. This environment has no read-only access to the production data.
  The structural regression and the incident data are the available evidence.
- OOM.07.3: the production validation in Railway was not executed here. It
  requires an operator to create a new job for organization 27 and to read the
  container peak and `oom_kill`.
