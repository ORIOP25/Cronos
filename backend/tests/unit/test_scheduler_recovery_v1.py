"""W06 domain: baseline assessment, disruption and adaptive recovery quality."""

from dataclasses import replace

import pytest

from app.scheduler.domain.calendar import Period
from app.scheduler.domain.candidate import (
    CandidateSchedule,
    ScheduledLesson,
    SchedulingStrategy,
)
from app.scheduler.domain.projection import ModuleSlice
from app.scheduler.domain.recovery import (
    BaselineIssueKind,
    LessonChangeKind,
    RecoveryPolicy,
    assess_baseline,
    measure_disruption,
    recovery_vector,
)
from tests.unit.test_scheduler_w04_w05_regressions_v1 import ORIGIN, period, snapshot

POLICY = RecoveryPolicy(
    version="laboratory-example",
    daily_slopes=tuple(range(1, 21)),
    disruption_weight=1,
    move_cost=10,
    insert_cost=12,
    remove_cost=15,
    room_change_cost=3,
    urgency_horizon_days=4,
    urgency_slope=1,
    recurrence_penalty=1,
)


def _lesson(
    identity,
    when: Period,
    room=1,
    teacher=None,
    source=None,
    slices=None,
    assignment_id=1,
):
    minutes = when.duration_minutes
    if slices is None:
        slices = (ModuleSlice(identity, 1, 0, minutes),)
    return ScheduledLesson(
        lesson_id=identity,
        assignment_id=assignment_id,
        period=when,
        room_id=room,
        credit_minutes=minutes,
        slices=slices,
        source_lesson_id=source,
        teacher_id=teacher,
    )


def _recovery_snapshot(periods, *, teacher_id=1, rooms=(1,), **kwargs):
    base = replace(
        snapshot(periods, **kwargs),
        strategy=SchedulingStrategy.ADAPTIVE_RECOVERY,
    )
    assignment = replace(
        base.assignments[0], teacher_id=teacher_id, eligible_room_ids=frozenset(rooms)
    )
    return replace(base, assignments=(assignment,))


def test_t20_a_teacher_reassignment_invalidates_the_published_baseline():
    when = period(0)
    target = _recovery_snapshot((when,), teacher_id=8)
    baseline = CandidateSchedule((_lesson(1, when, room=1, teacher=7),))

    assessment = assess_baseline(target, baseline.lessons)

    assert not assessment.valid
    assert BaselineIssueKind.RESOURCE_MISMATCH in {row.kind for row in assessment.issues}


def test_t20_a_withdrawn_room_invalidates_the_published_baseline():
    when = period(0)
    target = _recovery_snapshot((when,), rooms=(2,))
    baseline = CandidateSchedule((_lesson(1, when, room=1),))

    assessment = assess_baseline(target, baseline.lessons)

    assert not assessment.valid
    assert BaselineIssueKind.INELIGIBLE_ROOM in {row.kind for row in assessment.issues}


def test_a_complete_baseline_is_assessed_as_valid():
    when = period(0)
    target = _recovery_snapshot((when,))
    baseline = CandidateSchedule((_lesson(1, when),))

    assessment = assess_baseline(target, baseline.lessons)

    assert assessment.valid
    assert not assessment.requires_repair


def test_missing_and_excess_coverage_are_reported_separately():
    first, second = period(0), period(1)
    target = _recovery_snapshot((first, second), minutes=60)
    missing_assessment = assess_baseline(target, ())
    assert missing_assessment.missing_minutes_by_assignment == {1: 60}
    assert BaselineIssueKind.MISSING_COVERAGE in {row.kind for row in missing_assessment.issues}

    two_modules = replace(
        target.assignments[0],
        modules=(
            target.assignments[0].modules[0],
            replace(target.assignments[0].modules[0], module_id=2, sequence=2),
        ),
    )
    full = replace(target, assignments=(two_modules,), executed_minutes={1: {1: 60}})
    baseline = CandidateSchedule(
        (
            _lesson(1, first, slices=(ModuleSlice(1, 1, 0, 60),)),
            _lesson(2, second, slices=(ModuleSlice(2, 2, 0, 60),)),
        )
    )

    excess_assessment = assess_baseline(full, baseline.lessons)

    assert excess_assessment.excess_minutes_by_assignment == {1: 60}
    assert BaselineIssueKind.EXCESS_CREDIT in {row.kind for row in excess_assessment.issues}


def test_a_move_is_detected_once_and_costs_the_move_tariff():
    first, second = period(0), period(1)
    target = _recovery_snapshot((first, second), minutes=60)
    baseline = CandidateSchedule((_lesson(1, first),))
    moved = CandidateSchedule((_lesson(2, second, source=1),))

    metrics = measure_disruption(target, baseline, moved, POLICY)

    assert metrics.moved_lessons == 1
    assert metrics.inserted_lessons == 0
    assert metrics.removed_lessons == 0
    assert metrics.total_cost == POLICY.move_cost


def test_an_insertion_and_a_removal_are_counted_with_their_own_tariffs():
    first, second = period(0), period(1)
    target = _recovery_snapshot((first, second), minutes=60, count=2)
    baseline = CandidateSchedule((_lesson(1, first),))
    candidate = CandidateSchedule((_lesson(2, second, slices=(), assignment_id=2),))

    metrics = measure_disruption(target, baseline, candidate, POLICY)

    counts = {row.kind for row in metrics.changes}
    assert counts == {LessonChangeKind.REMOVED, LessonChangeKind.INSERTED}
    assert metrics.total_cost == POLICY.remove_cost + POLICY.insert_cost


def test_a_displacement_without_a_source_is_one_movement():
    first, second = period(0), period(1)
    target = _recovery_snapshot((first, second), minutes=60)
    baseline = CandidateSchedule((_lesson(1, first),))
    moved = CandidateSchedule((_lesson(2, second),))

    metrics = measure_disruption(target, baseline, moved, POLICY)

    assert metrics.moved_lessons == 1
    assert metrics.inserted_lessons == 0
    assert metrics.removed_lessons == 0
    assert metrics.total_cost == POLICY.move_cost


def test_a_room_change_is_not_a_movement():
    when = period(0)
    target = _recovery_snapshot((when,), rooms=(1, 2))
    baseline = CandidateSchedule((_lesson(1, when, room=1),))
    candidate = CandidateSchedule((_lesson(9, when, room=2, source=1),))

    metrics = measure_disruption(target, baseline, candidate, POLICY)

    assert metrics.room_changes == 1
    assert metrics.moved_lessons == 0
    assert metrics.total_cost == POLICY.room_change_cost


def test_swapping_lesson_ids_does_not_hide_an_identical_position():
    when = period(0)
    target = _recovery_snapshot((when,))
    baseline = CandidateSchedule((_lesson(1, when),))
    renamed = CandidateSchedule((_lesson(77, when),))

    metrics = measure_disruption(target, baseline, renamed, POLICY)

    assert metrics.changes == ()


def test_a_modular_projection_update_is_not_a_physical_change():
    when = period(0)
    target = _recovery_snapshot((when,))
    baseline = CandidateSchedule((_lesson(1, when),))
    reprojected = CandidateSchedule(
        (_lesson(1, when, slices=(ModuleSlice(1, 1, 0, when.duration_minutes),)),)
    )

    metrics = measure_disruption(target, baseline, reprojected, POLICY)

    assert metrics.changes == ()


def test_urgency_costs_more_close_to_the_editable_frontier():
    near, far = period(1), period(9)
    later_near, later_far = period(2), period(10)
    target = _recovery_snapshot(
        (near, far, later_near, later_far),
        minutes=60,
        protected_dates=frozenset({ORIGIN}),
    )
    baseline = CandidateSchedule((_lesson(1, near), _lesson(2, far)))
    candidate = CandidateSchedule(
        (_lesson(3, later_near, source=1), _lesson(4, later_far, source=2))
    )

    metrics = measure_disruption(target, baseline, candidate, POLICY)

    by_source = {row.source_lesson_id: row.cost for row in metrics.changes}
    assert by_source[1] > by_source[2]


def test_recurrence_penalizes_a_lesson_altered_more_than_once():
    first, second = period(0), period(1)
    target = _recovery_snapshot((first, second), minutes=60)
    baseline = CandidateSchedule((_lesson(1, first),))
    moved = CandidateSchedule((_lesson(2, second, source=1),))

    once = measure_disruption(target, baseline, moved, POLICY)
    again = measure_disruption(target, baseline, moved, POLICY, prior_changes=frozenset({1}))

    assert again.total_cost == once.total_cost * (1 + POLICY.recurrence_penalty)


def test_recovery_vector_prefers_margin_over_editable_disruption():
    """T18: one excess day dominates any amount of editable disruption."""
    preferred, hard = period(20), period(21)
    target = _recovery_snapshot((preferred, hard), minutes=60)
    baseline = CandidateSchedule((_lesson(1, hard),))
    on_time_but_disruptive = CandidateSchedule((_lesson(2, preferred, source=1),))
    late_but_stable = CandidateSchedule((_lesson(1, hard),))
    expensive = replace(POLICY, move_cost=10_000)

    on_time = recovery_vector(target, baseline, on_time_but_disruptive, expensive)
    late = recovery_vector(target, baseline, late_but_stable, expensive)

    assert on_time.excess_days_desc == (0,)
    assert late.excess_days_desc == (1,)
    assert on_time < late


def test_a_proposal_never_settles_debt_but_binds_active_reservations():
    from app.scheduler.domain.debt import (
        DebtClaim,
        DebtSettlement,
        RecoveryAllocation,
    )
    from app.scheduler.domain.recovery import reconcile_after_repair

    when = period(0)
    target = replace(_recovery_snapshot((when,)), active_version_id=7)
    candidate = CandidateSchedule((_lesson(1, when),))
    claims = (DebtClaim(4, ORIGIN, 30),)

    proposal = reconcile_after_repair(
        target, candidate, claims, allocations=(RecoveryAllocation(9, 1, 4, 30),)
    )
    assert proposal[0].open_minutes == 30
    assert proposal[0].reserved_minutes == 0

    active = reconcile_after_repair(
        target, candidate, claims, allocations=(RecoveryAllocation(7, 1, 4, 30),)
    )
    assert active[0].reserved_minutes == 30

    settled = reconcile_after_repair(
        target,
        candidate,
        claims,
        settlements=(DebtSettlement(4, ("lesson", 1), 30),),
        executed_credit_by_event={("lesson", 1): 30},
    )
    assert settled[0].open_minutes == 0


def test_policy_coefficients_are_explicit_and_validated():
    with pytest.raises(ValueError):
        replace(POLICY, move_cost=0)
    with pytest.raises(ValueError):
        replace(POLICY, urgency_slope=-1)
    with pytest.raises(ValueError):
        replace(POLICY, disruption_weight=0)
