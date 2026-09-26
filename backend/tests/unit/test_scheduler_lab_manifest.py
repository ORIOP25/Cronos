import json
from datetime import date, time

import pytest

from app.scheduler.domain.candidate import SchedulingStrategy
from app.scheduler.lab.fixtures import AssignmentSpec, CaseExpectation, FixtureSpec
from app.scheduler.lab.manifest import (
    CaseSeeds,
    LabCase,
    build_case,
    from_manifest,
    input_digest,
    manifest_digest,
    to_manifest,
)

ORIGIN = date(2026, 9, 21)
FEASIBLE_SPEC = FixtureSpec(
    strategy=SchedulingStrategy.COMPLETE_GENERATION,
    origin=ORIGIN,
    preferred_end_date=date(2026, 10, 30),
    hard_end_date=date(2026, 11, 30),
    timezone_name="Europe/Lisbon",
    grid_slots=((0, time(9), time(10)), (2, time(9), time(10))),
    periods=(
        (date(2026, 9, 21), time(9), time(10)),
        (date(2026, 9, 23), time(9), time(10)),
    ),
    assignments=(AssignmentSpec(1, 100, (100,), (500, 501)),),
)

INFEASIBLE_SPEC = FixtureSpec(
    **{**FEASIBLE_SPEC.__dict__, "assignments": (AssignmentSpec(1, 100, (200,), (500,)),)}
)

CASES = (
    LabCase(
        case_id="case-feasible",
        family="minimal",
        version=1,
        expectation=CaseExpectation.FEASIBLE_WITH_WITNESS,
        spec=FEASIBLE_SPEC,
        seeds=CaseSeeds(11, 22, 33),
    ),
    LabCase(
        case_id="case-infeasible",
        family="frontier",
        version=1,
        expectation=CaseExpectation.INFEASIBLE_PROVEN,
        spec=INFEASIBLE_SPEC,
        seeds=CaseSeeds(44, 55, 66),
    ),
    LabCase(
        case_id="case-mutated",
        family="minimal",
        version=1,
        expectation=CaseExpectation.FEASIBLE_WITH_WITNESS,
        spec=FEASIBLE_SPEC,
        seeds=CaseSeeds(77, 88, 99),
        mutation="DROP_LESSON",
        expected_violations=("COVERAGE_MISMATCH",),
    ),
)


def test_manifest_round_trip_reconstructs_identical_inputs():
    manifest = to_manifest("campaign-1", CASES)
    reloaded = json.loads(json.dumps(manifest))
    _, rebuilt = from_manifest(reloaded)

    first = [input_digest(build_case(case)) for case in CASES]
    second = [input_digest(build_case(case)) for case in rebuilt]

    assert first == second
    assert [case.seeds for case in rebuilt] == [case.seeds for case in CASES]


def test_manifest_digest_is_stable_for_identical_manifests():
    assert manifest_digest(to_manifest("campaign-1", CASES)) == manifest_digest(
        to_manifest("campaign-1", CASES)
    )


def test_changing_the_demand_changes_the_input_digest():
    changed = LabCase(
        case_id="case-feasible",
        family="minimal",
        version=2,
        expectation=CaseExpectation.FEASIBLE_WITH_WITNESS,
        spec=FixtureSpec(
            **{**FEASIBLE_SPEC.__dict__, "assignments": (AssignmentSpec(1, 100, (120,), (500,)),)}
        ),
        seeds=CaseSeeds(11, 22, 33),
    )

    assert input_digest(build_case(CASES[0])) != input_digest(build_case(changed))


def test_solver_seed_changes_the_manifest_but_not_the_inputs():
    baseline = CASES[0]
    reseeded = LabCase(
        case_id=baseline.case_id,
        family=baseline.family,
        version=baseline.version,
        expectation=baseline.expectation,
        spec=baseline.spec,
        seeds=CaseSeeds(baseline.seeds.fixture_seed, baseline.seeds.event_seed, 1234),
    )

    assert manifest_digest(to_manifest("campaign-1", (baseline,))) != manifest_digest(
        to_manifest("campaign-1", (reseeded,))
    )
    assert input_digest(build_case(baseline)) == input_digest(build_case(reseeded))


def test_mutation_case_rebuilds_the_invalid_variant_traceably():
    _, rebuilt = from_manifest(to_manifest("campaign-1", CASES))
    variant = build_case(rebuilt[2])

    assert variant.expectation is CaseExpectation.INVALID_INPUT
    assert variant.parent_case_id == "case-mutated"
    assert variant.mutation == "DROP_LESSON"
    assert variant.witness is not None


def test_manifest_rejects_unknown_schema_and_duplicate_case_ids():
    with pytest.raises(ValueError):
        from_manifest({"schema_version": "unknown", "campaign_id": "x", "cases": []})
    with pytest.raises(ValueError):
        from_manifest(to_manifest("campaign-1", (CASES[0], CASES[0])))
