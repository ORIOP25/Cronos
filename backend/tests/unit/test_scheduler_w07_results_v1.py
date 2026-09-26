"""W07: typed results, certificate scopes, honest budget and finish reasons."""

from app.scheduler.composition import repair_published_schedule
from app.scheduler.domain.candidate import CandidateSchedule
from app.scheduler.domain.diagnostics import DiagnosisCode, EvidenceKind
from app.scheduler.domain.results import OUTCOME_INCONCLUSIVE
from app.scheduler.domain.stop import BudgetPhase
from app.scheduler.infrastructure.annual_model import plan_annual_quotas
from app.scheduler.infrastructure.placement_model import (
    OBJECTIVE_SCOPE_CONDITIONAL,
    OBJECTIVE_SCOPE_UNRESTRICTED,
    solve_placement,
)
from app.scheduler.lab.fixtures import AssignmentSpec, CaseExpectation, build_fixture
from tests.unit.test_scheduler_recovery_solver_v1 import POLICY, _spec


def test_t26_a_window_optimum_stays_conditional_on_its_distribution():
    fixture = build_fixture("t26-window", _spec())
    plan = plan_annual_quotas(fixture.snapshot, fixture.periods, time_limit_seconds=5)

    outcome = solve_placement(
        fixture.snapshot,
        fixture.periods,
        distribution=plan.distribution,
        time_limit_seconds=5,
    )

    assert outcome.status == "COMPLETE"
    assert outcome.evidence is not None
    assert outcome.evidence.objective_scope == OBJECTIVE_SCOPE_CONDITIONAL
    assert outcome.evidence.stop_reason == "OPTIMAL_CONDITIONAL"


def test_t26_an_unrestricted_exact_model_is_labelled_as_such():
    fixture = build_fixture("t26-unrestricted", _spec())

    outcome = solve_placement(fixture.snapshot, fixture.periods, time_limit_seconds=5)

    assert outcome.status == "COMPLETE"
    assert outcome.evidence is not None
    assert outcome.evidence.objective_scope == OBJECTIVE_SCOPE_UNRESTRICTED


def test_t26_unknown_never_becomes_impossible():
    fixture = build_fixture("t26-unknown", _spec())

    result = repair_published_schedule(
        fixture.snapshot,
        fixture.periods,
        fixture.witness,
        POLICY,
        time_limit_seconds=1e-7,
    )

    assert result.outcome in {OUTCOME_INCONCLUSIVE, "COMPLETE", "INFEASIBLE"}
    if result.outcome == OUTCOME_INCONCLUSIVE:
        assert result.candidate is None
        diagnosis = result.diagnoses[0]
        assert diagnosis.evidence_kind is EvidenceKind.UNKNOWN
        assert diagnosis.code in {
            DiagnosisCode.SEARCH_INCONCLUSIVE,
            DiagnosisCode.EXECUTION_FAILURE,
        }


def test_budget_phases_cover_construction_search_and_persistence():
    fixture = build_fixture("t26-budget", _spec())

    result = repair_published_schedule(
        fixture.snapshot, fixture.periods, fixture.witness, POLICY, time_limit_seconds=5
    )

    assert result.outcome == "COMPLETE"
    assert result.budget is not None
    assert BudgetPhase.CONSTRUCTION in result.budget.phase_seconds
    assert BudgetPhase.SEARCH in result.budget.phase_seconds
    assert BudgetPhase.FINALIZATION in result.budget.phase_seconds
    assert result.within_budget is True

    result.budget.charge(BudgetPhase.PERSISTENCE, 500.0)

    assert result.budget.within_budget is False
    assert result.budget.as_dict()["within_budget"] is False


def test_a_proven_capacity_shortage_is_reported_with_its_minimum():
    spec = _spec(assignments=(AssignmentSpec(1, 7, (600,), (500,)),))
    fixture = build_fixture("t26-deficit", spec, expectation=CaseExpectation.INFEASIBLE_PROVEN)

    result = repair_published_schedule(
        fixture.snapshot,
        fixture.periods,
        CandidateSchedule(()),
        POLICY,
        time_limit_seconds=5,
    )

    assert result.outcome == "INFEASIBLE"
    diagnosis = result.diagnoses[0]
    assert diagnosis.evidence_kind is EvidenceKind.PROVEN_LOWER_BOUND
    assert diagnosis.minimum_missing_minutes is not None
