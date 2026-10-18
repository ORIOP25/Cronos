"""Fallback search and diagnostics preservation (scheduler v1).

The seasonal master/detail search can exhaust its feedback rounds or stop on an
inconclusive window without an incumbent. These tests force that situation and
require the search to either return a complete candidate through the unrestricted
fallback or an inconclusive outcome that keeps its evidence and statistics.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

import app.scheduler.infrastructure.search as search_module
from app.scheduler.domain.candidate import CandidateSchedule, HomeRoom, SchedulingStrategy
from app.scheduler.domain.candidate_validation import validate_candidate
from app.scheduler.domain.home_rooms import avoidable_room_changes, home_room_misses
from app.scheduler.infrastructure.annual_model import (
    STATUS_INCONCLUSIVE as ANNUAL_INCONCLUSIVE,
)
from app.scheduler.infrastructure.annual_model import AnnualPlan
from app.scheduler.infrastructure.placement_model import (
    STATUS_INCONCLUSIVE as PLACEMENT_INCONCLUSIVE,
)
from app.scheduler.infrastructure.placement_model import PlacementOutcome
from app.scheduler.lab.scale import build_scale_fixture
from tests.unit.test_scheduler_generation_quality_v1 import home_room_fixture
from tests.unit.test_scheduler_recovery_solver_v1 import POLICY

INCONCLUSIVE_PLAN = AnnualPlan(
    ANNUAL_INCONCLUSIVE, None, None, None, 0, False, 0.0, {"variables": 0}
)


def _inconclusive_plan(*_args, **_kwargs) -> AnnualPlan:
    return INCONCLUSIVE_PLAN


def _inconclusive_placement(*_args, **_kwargs) -> PlacementOutcome:
    return PlacementOutcome(
        PLACEMENT_INCONCLUSIVE,
        None,
        None,
        0.0,
        "UNRESTRICTED",
        {"variables": 12, "windows": 1},
    )


def _no_construction(*_args, **_kwargs):
    return None


def test_fallback_completes_when_the_annual_relaxation_is_inconclusive(monkeypatch):
    fixture = build_scale_fixture(6, seed=1)
    monkeypatch.setattr(search_module, "plan_annual_quotas", _inconclusive_plan)
    monkeypatch.setattr(search_module, "construct_schedule", _no_construction)

    outcome = search_module.search_complete_schedule(
        fixture.snapshot, fixture.periods, time_limit_seconds=10.0, num_workers=2, random_seed=3
    )

    assert outcome.status == "COMPLETE"
    assert outcome.candidate is not None
    assert validate_candidate(fixture.snapshot, outcome.candidate).valid
    assert outcome.evidence is not None
    assert outcome.evidence.stop_reason == "FALLBACK_UNRESTRICTED"


def test_inconclusive_search_preserves_evidence_and_statistics(monkeypatch):
    fixture = build_scale_fixture(6, seed=1)
    monkeypatch.setattr(search_module, "plan_annual_quotas", _inconclusive_plan)
    monkeypatch.setattr(search_module, "solve_placement", _inconclusive_placement)
    monkeypatch.setattr(search_module, "construct_schedule", _no_construction)

    outcome = search_module.search_complete_schedule(
        fixture.snapshot, fixture.periods, time_limit_seconds=10.0, num_workers=2, random_seed=3
    )

    assert outcome.status == "INCONCLUSIVE"
    assert outcome.evidence is not None
    assert outcome.evidence.stop_reason == "SEARCH_STOPPED"
    assert outcome.statistics.get("variables") == 12


def test_the_constructive_fallback_settles_a_viable_case(monkeypatch):
    fixture = build_scale_fixture(6, seed=1)
    monkeypatch.setattr(search_module, "plan_annual_quotas", _inconclusive_plan)

    outcome = search_module.search_complete_schedule(
        fixture.snapshot, fixture.periods, time_limit_seconds=10.0, num_workers=2, random_seed=3
    )

    assert outcome.status == "COMPLETE"
    assert outcome.candidate is not None
    assert validate_candidate(fixture.snapshot, outcome.candidate).valid
    assert outcome.evidence is not None
    assert outcome.evidence.stop_reason == "CONSTRUCTIVE"


def test_stop_at_first_complete_returns_the_constructor_without_optimizing():
    fixture = build_scale_fixture(6, seed=1)

    outcome = search_module.search_complete_schedule(
        fixture.snapshot,
        fixture.periods,
        time_limit_seconds=10.0,
        num_workers=2,
        random_seed=3,
        stop_at_first_complete=True,
    )

    assert outcome.status == "COMPLETE"
    assert outcome.candidate is not None
    assert validate_candidate(fixture.snapshot, outcome.candidate).valid
    assert outcome.evidence is not None
    assert outcome.evidence.stop_reason == "CONSTRUCTIVE"


def test_search_passes_its_deadline_and_cancellation_to_construction(monkeypatch):
    from time import monotonic

    fixture = build_scale_fixture(6, seed=1)
    constructor = search_module.construct_schedule
    before = monotonic()

    def should_cancel():
        return False

    def measured_construction(snapshot, periods, *, deadline, should_cancel):
        assert before < deadline <= monotonic() + 10
        assert should_cancel is cancellation
        return constructor(snapshot, periods, deadline=deadline, should_cancel=should_cancel)

    cancellation = should_cancel
    monkeypatch.setattr(search_module, "construct_schedule", measured_construction)

    outcome = search_module.search_complete_schedule(
        fixture.snapshot,
        fixture.periods,
        time_limit_seconds=10,
        should_cancel=should_cancel,
        stop_at_first_complete=True,
    )

    assert outcome.status == "COMPLETE"


def test_first_complete_policy_reaches_fallback_placement(monkeypatch):
    fixture = build_scale_fixture(6, seed=1)
    candidate = search_module.construct_schedule(fixture.snapshot, fixture.periods)
    calls = []

    def first_placement(*_args, **kwargs):
        calls.append(kwargs["stop_at_first_complete"])
        return PlacementOutcome("COMPLETE", candidate, None, 0.0, "UNRESTRICTED", {})

    monkeypatch.setattr(search_module, "construct_schedule", _no_construction)
    monkeypatch.setattr(search_module, "plan_annual_quotas", _inconclusive_plan)
    monkeypatch.setattr(search_module, "solve_placement", first_placement)

    outcome = search_module.search_complete_schedule(
        fixture.snapshot, fixture.periods, time_limit_seconds=10, stop_at_first_complete=True
    )

    assert outcome.status == "COMPLETE"
    assert calls == [True]


def test_first_complete_policy_stops_after_the_first_annual_placement(monkeypatch):
    fixture = build_scale_fixture(6, seed=1)
    candidate = search_module.construct_schedule(fixture.snapshot, fixture.periods)
    annual = search_module.plan_annual_quotas
    calls = []

    def first_plan(*args, **kwargs):
        assert kwargs["stop_at_first_complete"] is True
        assert not calls
        return annual(*args, **kwargs)

    def first_placement(*_args, **kwargs):
        calls.append(kwargs["stop_at_first_complete"])
        return PlacementOutcome("COMPLETE", candidate, None, 0.0, "UNRESTRICTED", {})

    monkeypatch.setattr(search_module, "construct_schedule", _no_construction)
    monkeypatch.setattr(search_module, "plan_annual_quotas", first_plan)
    monkeypatch.setattr(search_module, "solve_placement", first_placement)

    outcome = search_module.search_complete_schedule(
        fixture.snapshot, fixture.periods, time_limit_seconds=10, stop_at_first_complete=True
    )

    assert outcome.status == "COMPLETE"
    assert calls == [True]


def test_the_search_never_returns_worse_than_the_constructor(monkeypatch):
    from dataclasses import replace

    from app.scheduler.domain.candidate import CandidateSchedule
    from app.scheduler.infrastructure.constructive import construct_schedule
    from app.scheduler.lab.typology import build_typology_fixture

    fixture = build_typology_fixture(3)
    snapshot, periods = fixture.snapshot, fixture.periods
    better = construct_schedule(snapshot, periods)
    assert better is not None
    latest = max(better.lessons, key=lambda lesson: lesson.period.start_utc)
    moved = replace(latest, period=periods[-1])
    worse = CandidateSchedule(
        tuple(
            moved if lesson.lesson_id == latest.lesson_id else lesson for lesson in better.lessons
        )
    )
    assert validate_candidate(snapshot, worse).valid

    def worse_placement(*_args, **_kwargs) -> PlacementOutcome:
        return PlacementOutcome("COMPLETE", worse, None, 0.0, "UNRESTRICTED", {})

    monkeypatch.setattr(search_module, "solve_placement", worse_placement)
    outcome = search_module.search_complete_schedule(
        snapshot, periods, time_limit_seconds=10.0, num_workers=1, random_seed=1
    )

    assert outcome.status == "COMPLETE"
    assert outcome.candidate is not None
    assert validate_candidate(snapshot, outcome.candidate).valid
    assert outcome.evidence is not None
    assert outcome.evidence.stop_reason == "CONSTRUCTIVE"
    assert max(lesson.period.school_date for lesson in outcome.candidate.lessons) == max(
        lesson.period.school_date for lesson in better.lessons
    )


def test_presence_rule_exact_search_completes_when_construction_returns_none(monkeypatch):
    """The constructor guard passes, then the real exact solver closes the gap."""
    from app.scheduler.domain.candidate import TeacherPresenceRule
    from app.scheduler.infrastructure.constructive import construct_schedule
    from tests.unit.test_scheduler_resource_exclusivity_v1 import assignment, plan
    from tests.unit.test_scheduler_w04_w05_regressions_v1 import period

    periods = (period(0, start=9, end=10), period(0, start=10, end=11))
    snapshot = plan(
        periods,
        [assignment(1, 1, 1, {1}, 120)],
        teacher_presence=(
            TeacherPresenceRule(
                teacher_id=1, lunch_required=False, minimum_minutes=120, max_gap_minutes=10_000
            ),
        ),
    )

    constructed = construct_schedule(snapshot, periods)
    assert constructed is None or validate_candidate(snapshot, constructed).valid

    calls = []

    def no_construction(*_args, **_kwargs):
        calls.append(True)
        return None

    monkeypatch.setattr(search_module, "construct_schedule", no_construction)

    outcome = search_module.search_complete_schedule(
        snapshot, periods, time_limit_seconds=30.0, num_workers=1, random_seed=1
    )

    assert calls
    assert outcome.status == "COMPLETE"
    assert outcome.candidate is not None
    assert validate_candidate(snapshot, outcome.candidate).valid


@pytest.mark.parametrize("interruption", ["deadline", "cancellation"])
def test_recovery_never_starts_fallback_placement_after_interruption(monkeypatch, interruption):
    fixture = build_scale_fixture(6, seed=1)
    snapshot = replace(fixture.snapshot, strategy=SchedulingStrategy.ADAPTIVE_RECOVERY)
    clock = [0.0]
    cancelled = [False]

    def failed_construction(*_args, **_kwargs):
        if interruption == "deadline":
            clock[0] = 11.0
        else:
            cancelled[0] = True
        return None

    def unexpected_placement(*_args, **_kwargs):
        pytest.fail("An interrupted recovery must not start placement.")

    monkeypatch.setattr(search_module, "monotonic", lambda: clock[0])
    monkeypatch.setattr(search_module, "construct_recovery", failed_construction)
    monkeypatch.setattr(search_module, "construct_schedule", failed_construction)
    monkeypatch.setattr(search_module, "solve_placement", unexpected_placement)

    outcome = search_module.search_adaptive_schedule(
        snapshot,
        fixture.periods,
        CandidateSchedule(()),
        POLICY,
        time_limit_seconds=10,
        stop_at_first_complete=True,
        should_cancel=lambda: cancelled[0],
    )

    assert outcome.status == ("CANCELLED" if interruption == "cancellation" else "INCONCLUSIVE")
    assert outcome.candidate is None


@pytest.mark.parametrize(
    ("annual_status", "cancel_requested"),
    [("CANCELLED", False), ("INFEASIBLE", True), ("INCONCLUSIVE", True), ("FEASIBLE", True)],
)
def test_scheduler_annual_cancellation_propagates_and_never_starts_fallback(
    monkeypatch, annual_status, cancel_requested
):
    fixture = build_scale_fixture(6, seed=1)
    cancelled = [False]

    def should_cancel():
        return cancelled[0]

    def cancelled_plan(*args, **kwargs):
        assert kwargs.get("should_cancel") is should_cancel
        cancelled[0] = cancel_requested
        return AnnualPlan(annual_status, None, None, None, 0, False, 0.0, {})

    def unexpected_placement(*args, **kwargs):
        raise AssertionError("Cancelled annual search must not start placement or fallback")

    monkeypatch.setattr(search_module, "construct_schedule", _no_construction)
    monkeypatch.setattr(search_module, "plan_annual_quotas", cancelled_plan)
    monkeypatch.setattr(search_module, "solve_placement", unexpected_placement)
    outcome = search_module.search_complete_schedule(
        fixture.snapshot,
        fixture.periods,
        time_limit_seconds=10,
        should_cancel=should_cancel,
    )
    assert outcome.status == "CANCELLED"
    assert outcome.candidate is None


def test_r23_the_stop_at_first_placement_route_reaches_zero_avoidable_room_changes(monkeypatch):
    """❌ R23: sem construção, a colocação com paragem no primeiro completo chega a 0 evitáveis."""
    fixture = home_room_fixture()
    snapshot = replace(fixture.snapshot, home_rooms=(HomeRoom(class_id=1, room_id=1),))
    monkeypatch.setattr(search_module, "construct_schedule", _no_construction)

    outcome = search_module.search_complete_schedule(
        snapshot,
        fixture.periods,
        time_limit_seconds=10.0,
        num_workers=1,
        random_seed=3,
        stop_at_first_complete=True,
    )

    assert outcome.status == "COMPLETE"
    assert validate_candidate(snapshot, outcome.candidate).valid
    assert home_room_misses(snapshot, outcome.candidate) == 0
    assert avoidable_room_changes(snapshot, outcome.candidate) == 0
