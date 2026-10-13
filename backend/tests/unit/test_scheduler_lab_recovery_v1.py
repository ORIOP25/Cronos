"""W06 lab: recovery fixtures and baseline serialization."""

from app.scheduler.domain.candidate import SchedulingStrategy
from app.scheduler.domain.serialization import snapshot_from_dict, snapshot_to_dict
from app.scheduler.lab.recovery import (
    EVENTS,
    build_recovery_case,
    laboratory_policy,
    recovery_event,
)
from tests.unit.test_scheduler_recovery_solver_v1 import _spec


def test_a_recovery_case_carries_an_adaptive_baseline_and_a_known_event():
    case = build_recovery_case("lab-recovery", _spec(), event_seed=0)

    assert case.snapshot.strategy is SchedulingStrategy.ADAPTIVE_RECOVERY
    assert case.snapshot.baseline_lessons == case.baseline.lessons
    assert case.event in EVENTS
    assert recovery_event(0) == EVENTS[0]
    assert case.expectation.value in {"FEASIBLE_WITH_WITNESS", "INFEASIBLE_PROVEN"}


def test_the_laboratory_policy_covers_exactly_the_preference_horizon():
    case = build_recovery_case("lab-policy", _spec(), event_seed=1)

    policy = laboratory_policy(case.snapshot)

    days = (case.snapshot.preferred_end_date - case.snapshot.origin).days
    assert len(policy.daily_slopes) == days
    assert policy.version == "laboratory-default"


def test_the_baseline_survives_snapshot_serialization():
    case = build_recovery_case("lab-roundtrip", _spec(), event_seed=2)

    restored = snapshot_from_dict(snapshot_to_dict(case.snapshot))

    assert restored.baseline_lessons == case.snapshot.baseline_lessons
