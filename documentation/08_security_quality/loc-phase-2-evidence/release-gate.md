# Phase 2 release gate

Phase 2 was implemented on `codex/loc-reduction-implementation` and documented on `codex/loc-reduction-phase-2`. The original approved baseline was revision `4290ad13d7ebbbdd54ea49605a85959198bb89e1`:

| Category | Original baseline | Phase 2 source revision `188987d` | Delta from original |
| --- | ---: | ---: | ---: |
| Backend production | 32,790 | 32,404 | −386 |
| Frontend production | 18,506 | 18,437 | −69 |
| Backend tests | 19,219 | 19,847 | +628 |
| Frontend tests | 5,966 | 5,966 | 0 |
| E2E tests | 3,217 | 3,217 | 0 |
| Total production | 51,296 | 50,841 | −455 |
| Total tests | 28,402 | 29,030 | +628 |

Phase 2 adds only 47 production lines of reduction beyond Phase 1: Phase 1 ended at 50,888 production lines, and the measured Phase 2 source revision ends at 50,841. The original baseline comparison remains in `loc-after.json` and in Git history.

The release quality fixes required after that measurement are recorded in source commits before this evidence update. The corrected release source head is `8a442df62f5e1754ed324b4016e197a1631bae8c`, with the following future baseline:

| Category | Corrected release baseline |
| --- | ---: |
| Backend production | 32,513 |
| Frontend production | 18,512 |
| Backend tests | 19,847 |
| Frontend tests | 5,966 |
| E2E tests | 3,217 |
| Total production | 51,025 |
| Total tests | 29,030 |

The corrected release adds 184 measured production lines beyond the earlier Phase 2 source measurement. This reflects Sonar remediation and typed dependency/refactoring changes; it is not a performance claim. `loc-baseline.json` accepts the corrected release head as the baseline for future work. Documentation files are excluded from LOC measurement.

Git physical-line statistics are separate from nonblank LOC. Across the implementation history, the record is 7,910 documentation additions, 862 test additions, and −549 physical production lines. The occurrence changes improve layering and testability, not measured performance.

Local validation completed:

- `node --test scripts/test.test.mjs` — 17 tooling tests passed.
- `frontend/npm run verify` — 64 files / 369 tests passed and build completed.
- Ruff and Python compilation passed for the corrected backend paths.
- The full local backend run reached 408 passed tests, but 300 database-backed tests could not initialize because PostgreSQL was not listening on `127.0.0.1:5432`; CI provisions its own database and Redis services.

Exact-source-head CI run `35441352200` passed for the corrected implementation head: 381 backend units, 287 integrations, 46 contracts, frontend verification/build, E2E, capacity, and image checks. The SonarCloud quality gate also passed. The earlier exact-source-head Phase 2 run `35000233982` remains the validation record for source revision `188987d`.

The evidence commit follows the measured source revision because documentation is excluded from LOC measurement. The evidence update itself changes only documentation; the source quality fixes are committed separately before it. Further performance optimization and occurrence-service reduction remain future work.
