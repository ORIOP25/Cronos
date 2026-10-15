"""Production recovery preserves valid positions and repairs changed school data."""

from dataclasses import replace
from datetime import time
from time import monotonic

import pytest

from app.scheduler.composition import repair_published_schedule
from app.scheduler.domain.candidate import (
    CandidateSchedule,
    LunchRule,
    SchedulingStrategy,
    TeacherPresenceRule,
    Unavailability,
    UnavailableResource,
)
from app.scheduler.domain.candidate_validation import validate_candidate
from app.scheduler.infrastructure.recovery_construction import construct_recovery
from tests.unit.test_scheduler_recovery_solver_v1 import POLICY
from tests.unit.test_scheduler_resource_exclusivity_v1 import assignment, lesson, plan
from tests.unit.test_scheduler_w04_w05_regressions_v1 import period

DISPENSED_TEACHER = TeacherPresenceRule(teacher_id=7, lunch_required=False)
RECOVERY_LUNCH = LunchRule(window_start=time(12), window_end=time(14), minimum_minutes=60)


def _shared_teacher_assignments():
    return [assignment(1, 1, 7, {1}, 60), assignment(2, 2, 7, {2}, 120)]


def recover(periods, assignments, baseline, **changes):
    target = replace(
        plan(periods, assignments),
        strategy=SchedulingStrategy.ADAPTIVE_RECOVERY,
        baseline_lessons=tuple(baseline),
        **changes,
    )
    result = repair_published_schedule(
        target,
        periods,
        CandidateSchedule(tuple(baseline)),
        replace(POLICY, daily_slopes=tuple(range(1, 21))),
        stop_at_first_complete=True,
        time_limit_seconds=5,
    )
    assert result.outcome == "COMPLETE", result.message
    assert validate_candidate(target, result.candidate).valid
    return target, result


def positions(candidate):
    return {(row.assignment_id, row.period, row.room_id) for row in candidate.lessons}


def test_missing_hours_fill_a_gap_after_the_window_without_moving_valid_lessons():
    periods = (period(0), period(1), period(1, start=10, end=11), period(2))
    frozen = lesson(10, 1, periods[0], 1)
    future = lesson(11, 1, periods[2], 1, offset=60)
    target, result = recover(
        periods,
        [assignment(1, 1, 1, {1}, 180)],
        [frozen, future],
        protected_lessons=(frozen,),
        protected_dates=frozenset({periods[0].school_date}),
        open_debt_minutes={7: 60},
        claim_assignments={7: 1},
        active_version_id=1,
    )

    assert positions(result.candidate) == {(1, row, 1) for row in periods[:3]}
    assert frozen in result.candidate.lessons
    assert not any(row.kind.value == "MOVED" for row in result.quality.disruption.changes)
    assert result.evidence.certified_stages == 0


@pytest.mark.parametrize("calendar_scope", ["school", "class"])
def test_new_holidays_or_class_pauses_relocate_only_the_affected_lesson(calendar_scope):
    periods = tuple(period(day) for day in range(3))
    baseline = [lesson(10, 1, periods[1], 1), lesson(11, 1, periods[2], 1, offset=60)]
    change = (
        {"blocked_dates": frozenset({periods[1].school_date})}
        if calendar_scope == "school"
        else {"class_blocked_dates": {1: frozenset({periods[1].school_date})}}
    )
    _, result = recover(periods, [assignment(1, 1, 1, {1}, 120)], baseline, **change)

    assert positions(result.candidate) == {(1, periods[0], 1), (1, periods[2], 1)}


def test_a_withdrawn_room_changes_the_room_before_moving_the_lesson():
    periods = (period(0), period(1))
    _, result = recover(periods, [assignment(1, 1, 1, {2}, 60)], [lesson(10, 1, periods[0], 1)])

    assert positions(result.candidate) == {(1, periods[0], 2)}


def test_the_class_preference_breaks_a_tie_between_shared_teacher_options():
    periods = (period(0), period(1))
    _, result = recover(
        periods,
        [assignment(1, 1, 1, {1}, 60), assignment(2, 2, 1, {2}, 60)],
        [],
        soft_unavailable=(Unavailability(UnavailableResource.CLASS, 1, periods[0]),),
    )

    # Class 1 avoids Monday, so the shared teacher places class 2 first there.
    assert positions(result.candidate) == {(1, periods[1], 1), (2, periods[0], 2)}


def test_new_teacher_unavailability_keeps_the_unaffected_class_position():
    periods = (period(0), period(1))
    unchanged = lesson(11, 2, periods[0], 2)
    _, result = recover(
        periods,
        [assignment(1, 1, 3, {1}, 60), assignment(2, 2, 2, {2}, 60)],
        [replace(lesson(10, 1, periods[0], 1), teacher_id=1), unchanged],
        unavailable=(Unavailability(UnavailableResource.TEACHER, 3, periods[0]),),
    )

    assert positions(result.candidate) == {(1, periods[1], 1), (2, periods[0], 2)}


def test_manual_increase_in_demand_uses_newly_available_room_capacity():
    periods = (period(0), period(1))
    _, result = recover(
        periods,
        [assignment(1, 1, 1, {1, 2}, 120), assignment(2, 2, 2, {1, 2}, 60)],
        [lesson(10, 1, periods[0], 1)],
    )

    assert len(result.candidate.lessons) == 3
    assert max(row.period.school_date for row in result.candidate.lessons) == periods[1].school_date


def test_manual_progress_correction_does_not_duplicate_the_credited_hours():
    periods = (period(0), period(1))
    _, result = recover(
        periods,
        [assignment(1, 1, 1, {1}, 120)],
        [lesson(10, 1, periods[0], 1), lesson(11, 1, periods[1], 1, offset=60)],
        executed_minutes={1: {1: 60}},
    )

    assert sum(row.credit_minutes for row in result.candidate.lessons) == 60


def test_recovery_preserves_lunch_when_placing_missing_hours():
    periods = tuple(period(0, start=hour, end=hour + 1) for hour in (11, 12, 13, 14))
    _, result = recover(
        periods,
        [assignment(1, 1, 1, {1}, 120)],
        [lesson(10, 1, periods[0], 1)],
        lunch_rule=LunchRule(periods[1].start_local, periods[3].start_local, 60),
    )

    assert len(result.candidate.lessons) == 2


def test_recovery_construction_allows_a_teacher_dispensed_from_lunch():
    periods = tuple(period(0, start=hour, end=hour + 1) for hour in (12, 13, 14))
    _, result = recover(
        periods,
        _shared_teacher_assignments(),
        [],
        lunch_rule=RECOVERY_LUNCH,
        teacher_presence=(DISPENSED_TEACHER,),
    )

    assert len(result.candidate.lessons) == 3


def test_recovery_construction_keeps_the_lunch_rule_for_the_same_scenario():
    periods = tuple(period(0, start=hour, end=hour + 1) for hour in (12, 13, 14))
    target = replace(
        plan(periods, _shared_teacher_assignments(), lunch_rule=RECOVERY_LUNCH),
        strategy=SchedulingStrategy.ADAPTIVE_RECOVERY,
    )

    assert construct_recovery(target, periods, deadline=monotonic() + 20) is None


def test_partial_final_credit_is_reprojected_when_recovery_adds_a_later_lesson():
    periods = (period(0), period(1))
    _, result = recover(
        periods,
        [assignment(1, 1, 1, {1}, 100)],
        [lesson(10, 1, periods[0], 1, credit=40)],
    )

    assert [row.credit_minutes for row in result.candidate.lessons] == [60, 40]


def test_cancelled_recovery_never_returns_a_publishable_candidate():
    periods = (period(0), period(1))
    target = replace(
        plan(periods, [assignment(1, 1, 1, {1}, 120)]),
        strategy=SchedulingStrategy.ADAPTIVE_RECOVERY,
    )
    result = repair_published_schedule(
        target,
        periods,
        CandidateSchedule(()),
        POLICY,
        stop_at_first_complete=True,
        should_cancel=lambda: True,
    )

    assert result.outcome == "CANCELLED"
    assert result.candidate is None


def test_recovery_orders_a_successor_after_its_predecessor():
    periods = (
        period(0, start=9, end=10),
        period(0, start=10, end=11),
        period(0, start=11, end=12),
    )
    source = assignment(1, 1, 1, {1}, 60)
    successor = assignment(2, 2, 2, {2}, 60)
    baseline = (lesson(10, 2, periods[0], 2), lesson(11, 1, periods[1], 1))
    target = replace(
        plan(periods, [source, successor]),
        strategy=SchedulingStrategy.ADAPTIVE_RECOVERY,
        baseline_lessons=baseline,
        precedences=((1, 2),),
    )

    candidate = construct_recovery(target, periods, deadline=monotonic() + 20)

    assert candidate is not None
    assert validate_candidate(target, candidate).valid
    source_end = max(row.period.end_utc for row in candidate.lessons if row.assignment_id == 1)
    successor_start = min(
        row.period.start_utc for row in candidate.lessons if row.assignment_id == 2
    )
    assert successor_start >= source_end


@pytest.mark.parametrize("blocked_class", [1, 2])
def test_joint_availability_repair_moves_other_lessons_to_free_the_only_shared_period(
    blocked_class,
):
    periods = tuple(period(day) for day in range(4))
    separate = assignment(1, 1, 1, {1}, 120)
    joint = replace(assignment(2, 1, 2, {2}, 60), class_ids=(1, 2))
    baseline = (
        lesson(10, 2, periods[0], 2),
        lesson(11, 1, periods[1], 1),
        lesson(12, 1, periods[2], 1, offset=60),
    )
    _, result = recover(
        periods,
        [separate, joint],
        baseline,
        unavailable=(
            Unavailability(UnavailableResource.CLASS, blocked_class, periods[0]),
            Unavailability(UnavailableResource.TEACHER, 1, periods[0]),
            Unavailability(UnavailableResource.TEACHER, 2, periods[2]),
            Unavailability(UnavailableResource.TEACHER, 2, periods[3]),
        ),
    )

    assert positions(result.candidate) == {
        (2, periods[1], 2),
        (1, periods[2], 1),
        (1, periods[3], 1),
    }
    assert result.evidence.stop_reason == "FALLBACK_UNRESTRICTED"


@pytest.mark.parametrize(
    "resource, identity",
    [
        (UnavailableResource.CLASS, 1),
        (UnavailableResource.CLASS, 2),
        (UnavailableResource.TEACHER, 2),
        (UnavailableResource.ROOM, 2),
    ],
)
def test_protected_joint_availability_conflict_is_proven_before_search(resource, identity):
    periods = (period(0), period(1))
    joint = replace(assignment(2, 1, 2, {2}, 60), class_ids=(1, 2))
    frozen = lesson(10, 2, periods[0], 2)
    target = replace(
        plan(periods, [joint], protected_lessons=(frozen,)),
        strategy=SchedulingStrategy.ADAPTIVE_RECOVERY,
        protected_dates=frozenset({periods[0].school_date}),
        unavailable=(Unavailability(resource, identity, periods[0]),),
    )

    result = repair_published_schedule(
        target,
        periods,
        CandidateSchedule((frozen,)),
        replace(POLICY, daily_slopes=tuple(range(1, 21))),
        stop_at_first_complete=True,
        time_limit_seconds=5,
    )

    assert result.outcome == "INFEASIBLE"
    assert result.candidate is None
    assert result.search_seconds == 0
    assert result.diagnoses[0].code == "PROTECTED_AVAILABILITY_CONFLICT"
    assert result.diagnoses[0].affected_class_ids == (1, 2)
