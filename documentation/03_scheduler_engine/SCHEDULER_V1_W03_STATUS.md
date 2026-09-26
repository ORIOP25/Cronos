# Scheduler v1 — W03 independent validation and laboratory

Date: 23 September 2026. State: **in validation**, not complete.
Starting commit: `facd1d93bead7fc6ed481de6761644afd2e0be81`.

Review 24 September 2026: the first version of this package had reproduced
false positives and false negatives. W03 was not accepted as a certification
foundation. The corrected contracts, validator, oracle and laboratory are
recorded in the correction work record. The numbers below describe the
corrected state after that work.

Corrections of 24 September 2026:

- The validator now has 19 typed violation codes and checks module chronology,
  partial-credit rules, concrete grid membership, strategy date limits,
  interval overlap for unavailability, physical-only protection and the
  editable window for every non-protected lesson.
- The oracle fixes protected lessons first, subtracts their credit and raises
  `OracleBudgetExceededError` instead of returning an empty candidate set. Its
  certified optimum covers only the collective completion vector.
- Snapshots deep-copy nested mappings, so aliasing the input cannot mutate
  them.
- Campaign resume uses a full provenance key: case and version, input digest,
  schema version, code identity, policy version and seeds. Selection,
  expectations and expected violation codes are validated.

W03 adds the independent validator, the enumerative oracle, deterministic
fixtures with mutations, JSON manifests with separated seeds, the campaign
mode in the existing runner, and the report comparator. No code generation of
horários exists yet; W04 is not started.

## Packages

| W03 item | Implemented artefact | Executed evidence |
| :--- | :--- | :--- |
| W03.1 | `domain/candidate.py` immutable snapshot/candidate values and `domain/candidate_validation.py` independent validator with 13 typed violation codes | 17 unit tests, including one deliberate corruption per code |
| W03.2 | `domain/oracle.py` enumerative oracle that proves viability, infeasibility and the true optimum on minimal instances | 4 unit tests |
| W03.3 | `lab/fixtures.py` fixture generator with witness and 10 traceable mutations | 15 unit tests |
| W03.4 | `lab/manifest.py` JSON manifest, separated `fixture_seed`/`event_seed`/`solver_seed`, canonical digests | 5 unit tests |
| W03.5 | `lab/campaign.py` campaign runner and the `campaign` command in `scripts/test.mjs` | 4 unit tests, 1 runner test and an end-to-end run |
| W03.6 | `lab/reports.py` report comparator and scenario coverage | 6 unit tests |

## Evidence

| Evidence | Result |
| :--- | :--- |
| W03 unit tests | 51 passed (17 + 4 + 15 + 5 + 4 + 6) |
| Full backend unit suite after W03 | 509 passed in the locked Docker `ci` image |
| Ruff format and lint on the Scheduler package and new tests | Clean |
| Runner unit tests | 17 passed, including the new `campaign` parsing test |
| End-to-end campaign through the runner | `w03-minimal`: 3 cases `{VALID: 1, INFEASIBLE: 1, INVALID: 1}`, exit 0; outputs in `.test-artifacts/1790272317886-5504/scheduler-lab/` |

## Validator scope

`validate_candidate` recomputes, without solver variables: exact coverage per
assignment, module tiling without gaps or overlaps, unique stable identity,
eligible rooms, calendar and blocked dates, teacher availability, physical
collisions for class/teacher/room, protected published lessons, and recovery
reservations against open debt. It returns typed violations and the
recomputed credit per assignment.

## Laboratory scope

The oracle shares the domain definitions but not the CP-SAT implementation.
It enumerates every placement that can cover the residual demand and keeps
those accepted by the independent validator, so minimal instances have a
proven viability, infeasibility and optimum. Fixtures derive their witness
from the oracle and are then validated independently. Mutations are traceable
through `parent_case_id`, `mutation` and `case_id`, and each is rejected for
the intended code. Manifests reproduce identical input digests, and the three
seeds stay separate. The runner selects cases by ID, writes one result per
case, resumes finished cases, and fails when a case does not match its
declared expectation.

## Remaining work

W03 remains in validation. The enumerative oracle covers only minimal
instances; large instances need the CP-SAT generator of W04. The campaign
evaluates fixtures and mutated candidates, not generated horários, until W04
exists. The validator does not yet recompute quality metrics (completion,
disruption, gaps); those arrive with W05 and W06. No development or production
migration, reset or remote execution occurred.
