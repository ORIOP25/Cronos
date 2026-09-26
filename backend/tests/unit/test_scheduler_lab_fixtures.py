from datetime import date, time

import pytest

from app.scheduler.domain.candidate import SchedulingStrategy
from app.scheduler.domain.candidate_validation import ValidationViolationCode
from app.scheduler.lab.fixtures import (
    AssignmentSpec,
    CaseExpectation,
    FixtureSpec,
    build_fixture,
    expected_violations_for,
    mutate,
    witness_report,
)

ORIGIN = date(2026, 9, 21)
BASE_SPEC = FixtureSpec(
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

EXPECTED_CODES = {
    "DROP_LESSON": ValidationViolationCode.COVERAGE_MISMATCH,
    "DUPLICATE_IDENTITY": ValidationViolationCode.DUPLICATE_IDENTITY,
    "INELIGIBLE_ROOM": ValidationViolationCode.INELIGIBLE_ROOM,
    "OUT_OF_CALENDAR": ValidationViolationCode.NOT_IN_GRID,
    "RESOURCE_UNAVAILABLE": ValidationViolationCode.RESOURCE_UNAVAILABLE,
    "RESOURCE_CONFLICT": ValidationViolationCode.RESOURCE_CONFLICT,
    "PROTECTED_LESSON_CHANGED": ValidationViolationCode.PROTECTED_LESSON_CHANGED,
    "SLICE_MISMATCH": ValidationViolationCode.SLICE_MISMATCH,
    "MODULE_MISMATCH": ValidationViolationCode.MODULE_MISMATCH,
    "MODULE_ORDER": ValidationViolationCode.MODULE_MISMATCH,
    "PARTIAL_CREDIT_VIOLATION": ValidationViolationCode.PARTIAL_CREDIT_VIOLATION,
    "RESERVATION_VERSION_MISMATCH": ValidationViolationCode.RESERVATION_VERSION_MISMATCH,
    "DEBT_OVERFLOW": ValidationViolationCode.DEBT_OVERFLOW,
}


def _infeasible_spec() -> FixtureSpec:
    return FixtureSpec(
        **{**BASE_SPEC.__dict__, "assignments": (AssignmentSpec(1, 100, (200,), (500,)),)}
    )


def test_fixture_witness_is_independently_validated():
    fixture = build_fixture("minimal-1", BASE_SPEC)

    assert fixture.expectation is CaseExpectation.FEASIBLE_WITH_WITNESS
    assert fixture.witness is not None
    assert witness_report(fixture).valid
    assert [lesson.credit_minutes for lesson in fixture.witness.lessons] == [60, 40]


def test_fixture_rejects_a_spec_without_a_complete_witness():
    with pytest.raises(ValueError):
        build_fixture("impossible-1", _infeasible_spec())


def test_infeasible_fixture_is_proven_without_a_witness():
    fixture = build_fixture(
        "impossible-1", _infeasible_spec(), expectation=CaseExpectation.INFEASIBLE_PROVEN
    )

    assert fixture.witness is None
    assert fixture.expectation is CaseExpectation.INFEASIBLE_PROVEN


@pytest.mark.parametrize("mutation,code", sorted(EXPECTED_CODES.items()))
def test_each_mutation_is_rejected_for_the_correct_reason(mutation, code):
    fixture = build_fixture("minimal-1", BASE_SPEC)

    variant = mutate(fixture, mutation)
    report = witness_report(variant)

    assert not report.valid
    codes = {violation.code for violation in report.violations}
    assert code in codes
    assert code.value in expected_violations_for(mutation)


def test_mutations_are_traceable_to_their_parent_case():
    fixture = build_fixture("minimal-1", BASE_SPEC)

    variant = mutate(fixture, "DROP_LESSON")

    assert variant.parent_case_id == "minimal-1"
    assert variant.mutation == "DROP_LESSON"
    assert variant.case_id == "minimal-1~drop_lesson"
    assert variant.family == fixture.family


def test_unknown_mutation_is_rejected():
    fixture = build_fixture("minimal-1", BASE_SPEC)

    with pytest.raises(ValueError):
        mutate(fixture, "NOT_A_MUTATION")
