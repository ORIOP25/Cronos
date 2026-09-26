"""W10 failure reduction: shrink a failing case until every removal breaks it."""

from dataclasses import replace

from app.scheduler.lab.fixtures import CaseExpectation
from app.scheduler.lab.manifest import CaseSeeds, LabCase
from app.scheduler.lab.reduce import reduce_spec, reduced_case
from tests.unit.test_scheduler_lab_campaign import FEASIBLE_SPEC


def _fails_while_two_periods_and_enough_minutes(spec) -> bool:
    minutes = sum(sum(row.module_minutes) for row in spec.assignments)
    return len(spec.periods) >= 2 and minutes > 100


def _two_assignment_spec():
    return type(FEASIBLE_SPEC)(
        **{
            **FEASIBLE_SPEC.__dict__,
            "assignments": (
                FEASIBLE_SPEC.assignments[0],
                replace(FEASIBLE_SPEC.assignments[0], class_id=2, teacher_id=101),
            ),
        }
    )


def test_reduction_preserves_the_failure_and_removes_everything_else():
    result = reduce_spec(_two_assignment_spec(), _fails_while_two_periods_and_enough_minutes)

    assert _fails_while_two_periods_and_enough_minutes(result.spec)
    assert len(result.spec.assignments) == 2, "removing one assignment would break the failure"
    assert len(result.spec.periods) == 2, "removing one period would break the failure"
    assert sum(sum(row.module_minutes) for row in result.spec.assignments) == 101
    assert result.attempts > 0
    assert result.accepted > 0


def test_a_reduced_case_is_minimal_under_another_pass():
    result = reduce_spec(_two_assignment_spec(), _fails_while_two_periods_and_enough_minutes)

    again = reduce_spec(result.spec, _fails_while_two_periods_and_enough_minutes)

    assert again.accepted == 0
    assert again.spec == result.spec


def test_reduction_reports_accepted_attempts_and_keeps_a_stable_spec():
    result = reduce_spec(FEASIBLE_SPEC, lambda spec: spec == FEASIBLE_SPEC)

    assert result.spec == FEASIBLE_SPEC
    assert result.accepted == 0
    assert result.attempts > 0


def test_reduced_case_builds_a_deterministic_regression_lab_case():
    case = reduced_case(
        "w10-min-001",
        "C04",
        FEASIBLE_SPEC,
        expectation=CaseExpectation.FEASIBLE_WITH_WITNESS,
    )

    assert isinstance(case, LabCase)
    assert case.case_id == "w10-min-001"
    assert case.spec == FEASIBLE_SPEC
    assert case.seeds == CaseSeeds(0, 0, 0)
