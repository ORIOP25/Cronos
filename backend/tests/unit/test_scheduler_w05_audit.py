"""Adversarial cases found by the W00-W05 audit, independent of annual fixtures."""

from dataclasses import replace
from datetime import timedelta
from random import Random
from time import monotonic, sleep

import pytest
from ortools.sat.python import cp_model

from app.scheduler.application import generation
from app.scheduler.application.generation import generate_complete
from app.scheduler.composition import generate_schedule
from app.scheduler.domain.calendar import Period, normalize_period
from app.scheduler.domain.candidate import (
    CandidateSchedule,
    ScheduledLesson,
    Unavailability,
    UnavailableResource,
)
from app.scheduler.domain.candidate_validation import validate_candidate
from app.scheduler.domain.capacity import aggregate_capacity_check
from app.scheduler.domain.debt import RecoveryAllocation
from app.scheduler.domain.oracle import enumerate_candidates
from app.scheduler.domain.projection import ModuleSlice
from app.scheduler.domain.quality import measure_initial_quality
from app.scheduler.infrastructure import annual_model, placement_model
from app.scheduler.infrastructure.annual_model import QuotaDistribution, plan_annual_quotas
from app.scheduler.infrastructure.placement_model import (
    _optimize_rooms,
    _refine_room_positions,
    solve_placement,
)
from tests.unit.test_scheduler_w04_w05_regressions_v1 import period, snapshot


def lesson(identity, assignment, when, room, credit=None, offset=0):
    minutes = when.duration_minutes if credit is None else credit
    return ScheduledLesson(
        identity,
        assignment,
        when,
        room,
        minutes,
        (ModuleSlice(identity, assignment, offset, minutes),),
    )


def test_audit_cut_preserves_distributions_with_additional_duration_groups():
    periods = (period(0, end=9, end_min=30), period(0, start=10, end=12))
    target = snapshot(periods, minutes=90)
    excluded = QuotaDistribution({(1, 0, 120): 1}, {1: (0, 120)})
    plan = plan_annual_quotas(target, periods, excluded=(excluded,))
    assert plan.status == "FEASIBLE"
    assert dict(plan.distribution.counts) == {(1, 0, 30): 1, (1, 0, 120): 1}


def test_audit_annual_bound_does_not_become_the_incumbent(monkeypatch):
    periods = (period(7),)
    target = snapshot(periods)
    original = cp_model.CpSolver.Solve

    def feasible(self, model, *args, **kwargs):
        original(self, model, *args, **kwargs)
        return cp_model.FEASIBLE

    monkeypatch.setattr(cp_model.CpSolver, "Solve", feasible)
    monkeypatch.setattr(cp_model.CpSolver, "BestObjectiveBound", lambda self: 0.0)
    plan = plan_annual_quotas(target, periods)
    assert plan.latest_week == 1
    assert not plan.latest_week_proven
    assert plan.latest_week_bound == 0


def test_audit_room_postpass_preserves_partial_interval_conflicts():
    first, overlap, later = period(0), period(0, start_min=30, end_min=30), period(1)
    target = snapshot((first, overlap, later), minutes=120, count=2)
    target = replace(
        target,
        assignments=tuple(
            replace(a, eligible_room_ids=frozenset({1, 2})) for a in target.assignments
        ),
        soft_unavailable=tuple(
            Unavailability(UnavailableResource.ROOM, 2, p) for p in (first, overlap, later)
        ),
    )
    candidate = CandidateSchedule(
        (
            lesson(1, 1, first, 1),
            lesson(2, 1, later, 1, offset=60),
            lesson(3, 2, overlap, 2),
            lesson(4, 2, later, 2, offset=60),
        )
    )
    assert validate_candidate(target, candidate).valid
    optimized, _ = _optimize_rooms(
        target, candidate, deadline=monotonic() + 5, num_workers=1, random_seed=1
    )
    assert validate_candidate(target, optimized).valid


def test_audit_room_preferences_count_a_dispreferred_lesson_once():
    first, second = period(0), period(1)
    target = snapshot((first, second), minutes=120)
    target = replace(
        target,
        assignments=(replace(target.assignments[0], eligible_room_ids=frozenset({1, 2})),),
        unavailable=(Unavailability(UnavailableResource.ROOM, 2, first),),
        soft_unavailable=(
            Unavailability(UnavailableResource.TEACHER, 1, second),
            Unavailability(UnavailableResource.ROOM, 1, second),
        ),
    )
    candidate = CandidateSchedule((lesson(1, 1, first, 1), lesson(2, 1, second, 1, offset=60)))
    optimized, _ = _optimize_rooms(
        target, candidate, deadline=monotonic() + 5, num_workers=1, random_seed=1
    )
    quality = measure_initial_quality(target, optimized)
    assert quality.preference_cost_minutes == 60
    assert quality.room_change_cost == 0


@pytest.mark.parametrize("protected", [False, True])
def test_audit_satisfied_demand_returns_complete_without_new_lessons(protected):
    periods = (period(0),)
    target = snapshot(periods)
    if protected:
        target = replace(target, protected_lessons=(lesson(1, 1, periods[0], 1),))
    else:
        target = replace(target, executed_minutes={1: {1: 60}})
    result = generate_schedule(target, periods)
    assert result.outcome == "COMPLETE"
    assert result.report.valid
    assert result.candidate.lessons == target.protected_lessons


@pytest.mark.parametrize("override", [{"teacher_id": 99}, {"class_ids": (99,)}])
def test_audit_validator_rejects_unassigned_resources(override):
    when = period(0)
    target = snapshot((when,))
    candidate = CandidateSchedule((replace(lesson(1, 1, when, 1), **override),))
    assert not validate_candidate(target, candidate).valid


def test_audit_interrupted_window_is_not_cached_or_certified(monkeypatch):
    periods = (period(0), period(1))
    target = snapshot(periods)
    original = cp_model.CpSolver.Solve
    calls = 0

    def interrupt_threshold(self, model, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            return cp_model.UNKNOWN
        return original(self, model, *args, **kwargs)

    monkeypatch.setattr(cp_model.CpSolver, "Solve", interrupt_threshold)
    cache = {}
    result = solve_placement(target, periods, reuse=cache)
    assert result.status == "COMPLETE"
    assert result.evidence.certified_stages == 0
    assert not cache


def test_audit_gap_objective_includes_protected_occupancy():
    periods = (period(0), period(0, start=10, end=11), period(0, start=11, end=12))
    target = snapshot(periods, minutes=120)
    target = replace(
        target,
        protected_lessons=(lesson(9, 1, periods[0], 1),),
        soft_unavailable=(Unavailability(UnavailableResource.TEACHER, 1, periods[1]),),
    )
    result = generate_schedule(target, periods)
    assert result.outcome == "COMPLETE"
    assert result.report.valid
    assert result.quality.teacher_gap_minutes == 0
    assert result.quality.preference_cost_minutes == 60


@pytest.mark.parametrize("minutes", [1.9, True, "12"])
def test_audit_snapshot_does_not_silently_coerce_credit(minutes):
    with pytest.raises(ValueError):
        replace(snapshot((period(0),)), executed_minutes={1: {1: minutes}})


def test_audit_snapshot_copies_mutable_collections():
    target = snapshot((period(0),))
    rooms = {1}
    modules = list(target.assignments[0].modules)
    assignment = replace(target.assignments[0], eligible_room_ids=rooms, modules=modules)
    assignments = [assignment]
    blocked = set()
    protected = []
    target = replace(
        target, assignments=assignments, blocked_dates=blocked, protected_lessons=protected
    )
    rooms.add(99)
    modules.clear()
    assignments.clear()
    blocked.add(period(0).school_date)
    protected.append(lesson(1, 1, period(0), 1))
    assert target.assignments == (assignment,)
    assert assignment.eligible_room_ids == frozenset({1})
    assert len(assignment.modules) == 1
    assert not target.blocked_dates
    assert not target.protected_lessons


def test_audit_foreign_timezone_is_not_a_school_period():
    when = period(0)
    foreign = normalize_period(when.school_date, when.start_local, when.end_local, "UTC")
    target = snapshot((when,))
    assert not validate_candidate(target, CandidateSchedule((lesson(1, 1, foreign, 1),))).valid
    result = generate_schedule(target, (foreign,))
    assert result.outcome != "COMPLETE"


def test_audit_room_continuity_can_reopen_positions_in_one_window():
    periods = (period(0), period(0, start_min=30, end_min=30), period(1))
    target = snapshot(periods, minutes=120)
    target = replace(
        target,
        assignments=(replace(target.assignments[0], eligible_room_ids=frozenset({1, 2})),),
        unavailable=(
            Unavailability(UnavailableResource.ROOM, 2, period(0, end=9, end_min=30)),
            Unavailability(UnavailableResource.ROOM, 1, period(0, start=10, end=10, end_min=30)),
            Unavailability(UnavailableResource.ROOM, 2, periods[2]),
        ),
    )
    result = generate_schedule(target, periods)

    def quality(candidate):
        return measure_initial_quality(target, candidate).vector(
            origin=target.origin, preferred_end_date=target.preferred_end_date
        )

    assert result.report.valid
    assert quality(result.candidate) == min(
        quality(c) for c in enumerate_candidates(target, periods).candidates
    )


def test_audit_new_identity_does_not_collide_with_a_protected_lesson():
    periods = (period(0), period(1))
    target = snapshot(periods, minutes=120)
    protected = lesson(1_000_001, 1, periods[0], 1)
    target = replace(target, protected_lessons=(protected,))

    result = generate_schedule(target, periods)

    assert result.outcome == "COMPLETE"
    assert result.report.valid
    identities = [row.lesson_id for row in result.candidate.lessons]
    assert len(set(identities)) == len(identities)
    assert 1_000_001 in identities


def test_audit_new_lessons_follow_protected_lessons_chronologically():
    periods = (period(0), period(1), period(2))
    target = snapshot(periods, minutes=120)
    protected = lesson(7, 1, periods[1], 1)
    target = replace(target, protected_lessons=(protected,))

    result = generate_schedule(target, periods)

    assert result.outcome == "COMPLETE"
    assert result.report.valid
    new_lessons = [row for row in result.candidate.lessons if row.lesson_id != 7]
    assert new_lessons
    assert all(row.period.start_utc >= protected.period.end_utc for row in new_lessons)


def test_audit_oracle_identity_does_not_collide_with_a_protected_lesson():
    periods = (period(0), period(1))
    target = snapshot(periods, minutes=120)
    target = replace(target, protected_lessons=(lesson(100_001, 1, periods[0], 1),))

    oracle = enumerate_candidates(target, periods)

    assert oracle.feasible
    identities = [row.lesson_id for candidate in oracle.candidates for row in candidate.lessons]
    assert 100_001 in identities


@pytest.mark.parametrize(
    "executed",
    [
        {99: {1: 60}},
        {1: {99: 10}},
        {1: {1: -1}},
        {1: {1: 61}},
    ],
)
def test_audit_invalid_executed_input_is_rejected_at_the_snapshot(executed):
    with pytest.raises(ValueError):
        replace(snapshot((period(0),)), executed_minutes=executed)


def test_audit_protected_lesson_references_are_validated():
    when = period(0)
    target = snapshot((when,))

    with pytest.raises(ValueError):
        replace(target, protected_lessons=(lesson(1, 99, when, 1),))


def test_audit_protected_lesson_keeps_a_room_that_a_later_change_made_ineligible():
    """Owner decision 2026-10-18: a room may change type after lessons happened in it."""
    when = period(0)
    target = replace(snapshot((when,)), protected_lessons=(lesson(1, 1, when, 99),))

    assert target.protected_lessons[0].room_id == 99


def test_audit_protected_slices_must_reference_known_modules():
    when = period(0)
    broken = replace(lesson(1, 1, when, 1), slices=(ModuleSlice(1, 99, 0, 60),))

    with pytest.raises(ValueError):
        replace(snapshot((when,)), protected_lessons=(broken,))


def test_audit_protected_slices_must_form_a_chronological_prefix():
    periods = (period(0), period(1))
    target = snapshot(periods, minutes=120)

    with pytest.raises(ValueError):
        replace(target, protected_lessons=(lesson(7, 1, periods[0], 1, offset=60),))


def test_audit_debt_references_must_belong_to_the_snapshot():
    with pytest.raises(ValueError):
        replace(
            snapshot((period(0),)),
            open_debt_minutes={7: 30},
            claim_assignments={7: 99},
        )
    with pytest.raises(ValueError):
        replace(
            snapshot((period(0),)),
            reservations=(RecoveryAllocation(5, 1, 77, 30),),
            active_version_id=5,
        )


def test_audit_direct_period_construction_rejects_incoherent_instants():
    when = period(0)

    with pytest.raises(ValueError):
        Period(
            when.school_date,
            when.start_local,
            when.end_local,
            when.timezone_name,
            when.start_utc + timedelta(hours=1),
            when.end_utc,
        )
    with pytest.raises(ValueError):
        Period(
            when.school_date,
            when.start_local,
            when.end_local,
            when.timezone_name,
            when.start_utc,
            when.start_utc,
        )


def test_audit_safety_limit_has_priority_over_a_feasible_window(monkeypatch):
    periods = (period(0), period(7))
    target = snapshot(periods, minutes=120)
    distribution = QuotaDistribution(
        counts={(1, 0, 60): 1, (1, 1, 60): 1},
        final_groups={1: (1, 60)},
    )
    original = placement_model._solve_scope
    stops = [placement_model.STOP_FEASIBLE, placement_model.STOP_SAFETY]

    def with_stop(state, **kwargs):
        status, selections, records, _stop = original(state, **kwargs)
        return status, selections, records, stops.pop(0)

    monkeypatch.setattr(placement_model, "_solve_scope", with_stop)

    outcome = solve_placement(target, periods, distribution=distribution, time_limit_seconds=10)

    assert outcome.status == "COMPLETE"
    assert outcome.evidence is not None
    assert outcome.evidence.stop_reason == "SAFETY_LIMIT"
    assert outcome.evidence.certified_stages == 0


def test_audit_cache_does_not_reuse_room_optimized_windows_in_multi_window_mode():
    periods = (period(0), period(7))
    target = snapshot(periods, minutes=120)
    distribution = QuotaDistribution(
        counts={(1, 0, 60): 1, (1, 1, 60): 1},
        final_groups={1: (1, 60)},
    )
    scope = placement_model._window_scopes(target, periods, distribution)[0]
    cache = {
        placement_model._scope_cache_key(scope): placement_model._CachedWindow(
            selections={},
            records=(
                placement_model._StageRecord(
                    stage=placement_model.STAGE_ROOM_CHANGES,
                    value=0,
                    proven=True,
                    window=scope.week,
                ),
            ),
            room_continuity=True,
        )
    }

    outcome = solve_placement(
        target, periods, distribution=distribution, time_limit_seconds=10, reuse=cache
    )

    assert outcome.status == "COMPLETE"
    assert outcome.evidence is not None
    assert all(not stage.reused for stage in outcome.evidence.stages)


def test_audit_room_postpass_preserves_the_incumbent_on_unknown(monkeypatch):
    periods = (period(0), period(1))
    target = snapshot(periods, minutes=120)
    target = replace(
        target,
        assignments=(replace(target.assignments[0], eligible_room_ids=frozenset({1, 2})),),
        soft_unavailable=tuple(Unavailability(UnavailableResource.ROOM, 2, row) for row in periods),
    )
    candidate = CandidateSchedule(
        (lesson(1, 1, periods[0], 1), lesson(2, 1, periods[1], 2, offset=60))
    )
    monkeypatch.setattr(cp_model.CpSolver, "Solve", lambda self, model, *a, **k: cp_model.UNKNOWN)

    optimized, record = _optimize_rooms(
        target, candidate, deadline=monotonic() + 5, num_workers=1, random_seed=1
    )

    assert optimized == candidate
    assert record.proven is False


def test_audit_annual_second_solve_respects_the_monotonic_deadline(monkeypatch):
    periods = (period(0), period(7))
    target = snapshot(periods, minutes=120)
    clock = iter([0.0] * 8 + [1_000.0])
    monkeypatch.setattr(annual_model, "monotonic", lambda: next(clock, 1_000.0))
    solves = []
    original = cp_model.CpSolver.Solve

    def recording(self, model, *args, **kwargs):
        solves.append(self.parameters.max_time_in_seconds)
        return original(self, model, *args, **kwargs)

    monkeypatch.setattr(cp_model.CpSolver, "Solve", recording)

    plan = plan_annual_quotas(target, periods, time_limit_seconds=100)

    assert plan.status == "FEASIBLE"
    assert solves == [100.0]
    assert plan.wall_time_seconds >= 100.0


def test_audit_generation_stops_when_the_precheck_consumes_the_budget(monkeypatch):
    periods = (period(0),)
    target = snapshot(periods)

    def slow_capacity(snapshot, periods):
        sleep(0.05)
        return aggregate_capacity_check(snapshot, periods)

    def forbidden(*args, **kwargs):
        raise AssertionError("The search must not run without budget.")

    monkeypatch.setattr(generation, "aggregate_capacity_check", slow_capacity)

    result = generate_complete(target, periods, search=forbidden, time_limit_seconds=0.01)

    assert result.outcome == "INCONCLUSIVE"
    assert result.candidate is None


def test_audit_room_refinement_reopens_positions_without_degrading_priorities():
    first, earlier, alternative = period(0), period(7), period(7, start=10, end=11)
    periods = (first, earlier, alternative)
    target = snapshot(periods, minutes=120)
    target = replace(
        target,
        assignments=(replace(target.assignments[0], eligible_room_ids=frozenset({1, 2})),),
        unavailable=(
            Unavailability(UnavailableResource.ROOM, 2, first),
            Unavailability(UnavailableResource.ROOM, 1, earlier),
            Unavailability(UnavailableResource.ROOM, 2, alternative),
        ),
    )
    candidate = CandidateSchedule((lesson(1, 1, first, 1), lesson(2, 1, earlier, 2, offset=60)))
    before = measure_initial_quality(target, candidate).vector(
        origin=target.origin, preferred_end_date=target.preferred_end_date
    )
    assert before.room_change_cost == 1

    refined = _refine_room_positions(target, periods, candidate, deadline=monotonic() + 5)

    assert validate_candidate(target, refined).valid
    after = measure_initial_quality(target, refined).vector(
        origin=target.origin, preferred_end_date=target.preferred_end_date
    )
    assert after.room_change_cost == 0
    assert after == replace(before, room_change_cost=0)


def _full_vector(target, candidate):
    return measure_initial_quality(target, candidate).vector(
        origin=target.origin, preferred_end_date=target.preferred_end_date
    )


@pytest.mark.parametrize("seed", range(16))
def test_audit_full_vector_matches_the_enumerated_optimum(seed):
    rng = Random(seed)
    periods = (period(0), period(0, start_min=30, end_min=30), period(1), period(7))
    target = snapshot(periods, minutes=rng.choice((30, 60, 90, 120)), count=2)
    assignments = tuple(
        replace(a, teacher_id=rng.choice((1, 2)), eligible_room_ids=frozenset({1, 2}))
        for a in target.assignments
    )
    hard, soft = [], []
    for kind in UnavailableResource:
        for identity in (1, 2):
            for when in periods:
                chance = rng.random()
                row = Unavailability(kind, identity, when)
                if chance < 0.10:
                    hard.append(row)
                elif chance < 0.25:
                    soft.append(row)
    target = replace(
        target,
        assignments=assignments,
        unavailable=tuple(hard),
        soft_unavailable=tuple(soft),
    )
    oracle = enumerate_candidates(target, periods)
    best = min((_full_vector(target, row) for row in oracle.candidates), default=None)

    result = generate_schedule(target, periods, time_limit_seconds=5)

    if best is None:
        assert result.outcome == "INFEASIBLE"
        return
    assert result.outcome == "COMPLETE"
    assert result.report.valid
    assert _full_vector(target, result.candidate) == best


def test_audit_full_vector_is_invariant_to_entity_and_period_permutations():
    periods = (period(0), period(1), period(7))
    base = snapshot(periods, minutes=90, count=2)
    renamed = replace(
        base,
        assignments=tuple(
            replace(
                row,
                assignment_id=row.assignment_id + 10,
                class_ids=tuple(class_id + 10 for class_id in row.class_ids),
            )
            for row in base.assignments
        ),
    )
    vectors = []
    for target, ordered in ((base, periods), (renamed, tuple(reversed(periods)))):
        result = generate_schedule(target, ordered, time_limit_seconds=5)
        assert result.outcome == "COMPLETE"
        assert result.report.valid
        vectors.append(_full_vector(target, result.candidate))
        oracle = enumerate_candidates(target, ordered)
        assert _full_vector(target, result.candidate) == min(
            _full_vector(target, row) for row in oracle.candidates
        )

    assert vectors[0] == vectors[1]
