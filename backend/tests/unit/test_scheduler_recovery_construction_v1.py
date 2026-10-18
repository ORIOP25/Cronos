"""Production recovery preserves valid positions and repairs changed school data."""

from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from time import monotonic

import pytest

from app.scheduler.composition import repair_published_schedule
from app.scheduler.domain.calendar import normalize_period
from app.scheduler.domain.candidate import (
    Assignment,
    CandidateSchedule,
    GridSlot,
    HomeRoom,
    LunchRule,
    PlanningSnapshot,
    SchedulingStrategy,
    TeacherPresenceRule,
    Unavailability,
    UnavailableResource,
)
from app.scheduler.domain.candidate_validation import ValidationViolationCode, validate_candidate
from app.scheduler.domain.diagnostics import diagnose_protected_availability
from app.scheduler.domain.home_rooms import avoidable_room_changes
from app.scheduler.domain.projection import ModuleRequirement
from app.scheduler.domain.recovery import measure_disruption
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
    # The joint unit's teacher has the only shared period, so the availability
    # priority (spec D01, D10) lets the rebuild construction place it first.
    assert result.evidence.stop_reason == "CONSTRUCTIVE_RECOVERY"


def test_a_repair_consolidates_a_presence_invalid_baseline_onto_one_day():
    """A newly added presence minimum invalidates the baseline and forces a real repair.

    The setup proof below shows the same baseline is valid without the rule and
    invalid only through `TEACHER_PRESENCE_VIOLATION` with it, so no other
    constraint causes the change. The baseline keeps the shared teacher's two
    lessons on separate days, which the new 120-minute minimum forbids. With the
    availability priority (spec D01, D10) a validated construction repairs it
    (`CONSTRUCTIVE_RECOVERY`). No CP-SAT call is mocked.
    """
    periods = (
        period(0, start=9, end=10),
        period(0, start=10, end=11),
        period(1, start=9, end=10),
        period(1, start=10, end=11),
    )
    presence = (
        TeacherPresenceRule(
            teacher_id=7, lunch_required=False, minimum_minutes=120, max_gap_minutes=0
        ),
    )
    history = lesson(30, 3, periods[3], 3)
    baseline = (lesson(10, 1, periods[0], 1), lesson(11, 2, periods[2], 2), history)
    assignments = [
        assignment(1, 1, 7, {1}, 60),
        assignment(2, 2, 7, {2}, 60),
        assignment(3, 3, 8, {3}, 60),
    ]

    target, result = recover(
        periods,
        assignments,
        baseline,
        teacher_presence=presence,
        protected_lessons=(history,),
        unavailable=(Unavailability(UnavailableResource.CLASS, 2, periods[1]),),
    )

    # Setup: the baseline is valid under the old (absent) rule and rejected
    # solely by the new minimum, so the repair is caused by teacher presence.
    assert validate_candidate(
        replace(target, teacher_presence=()), CandidateSchedule(baseline)
    ).valid
    setup = validate_candidate(target, CandidateSchedule(baseline))
    assert not setup.valid
    assert {row.code for row in setup.violations} == {
        ValidationViolationCode.TEACHER_PRESENCE_VIOLATION
    }

    assert result.evidence.stop_reason == "CONSTRUCTIVE_RECOVERY"
    assert positions(result.candidate) != positions(CandidateSchedule(baseline))
    # The construction finishes as early as possible (scheduler D10), so the
    # shared teacher's day is the first one.
    assert {row.period for row in result.candidate.lessons if row.assignment_id in (1, 2)} == {
        periods[0],
        periods[1],
    }
    assert history in result.candidate.lessons
    assert any(row.kind.value == "MOVED" for row in result.quality.disruption.changes)
    assert sorted((row.assignment_id, row.credit_minutes) for row in result.candidate.lessons) == [
        (1, 60),
        (2, 60),
        (3, 60),
    ]


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


def test_a_started_protected_lesson_ignores_availability_declared_after_it_was_given():
    periods = (period(0), period(1))
    frozen = lesson(10, 1, periods[0], 1)
    target, result = recover(
        periods,
        [assignment(1, 1, 1, {1}, 120)],
        [frozen],
        protected_lessons=(frozen,),
        now_utc=datetime(2026, 9, 21, 12, 0, tzinfo=UTC),
        unavailable=(Unavailability(UnavailableResource.TEACHER, 1, periods[0]),),
    )

    assert result.outcome == "COMPLETE"
    assert frozen in result.candidate.lessons
    assert diagnose_protected_availability(target) == ()


def test_a_protected_lesson_that_has_not_started_keeps_the_availability_conflict():
    periods = (period(0), period(1))
    frozen = lesson(10, 1, periods[0], 1)
    target = replace(
        plan(periods, [assignment(1, 1, 1, {1}, 60)], protected_lessons=(frozen,)),
        strategy=SchedulingStrategy.ADAPTIVE_RECOVERY,
        protected_dates=frozenset({periods[0].school_date}),
        now_utc=datetime(2026, 9, 21, 7, 0, tzinfo=UTC),
        unavailable=(Unavailability(UnavailableResource.TEACHER, 1, periods[0]),),
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
    assert result.diagnoses[0].code == "PROTECTED_AVAILABILITY_CONFLICT"


MONDAY = date(2026, 9, 14)
TZ = "Europe/Lisbon"
GRID_HOURS = (9, 10, 11, 12, 14, 15, 16, 17)


def slot(day, hour):
    return normalize_period(MONDAY + timedelta(days=day), time(hour), time(hour + 1), TZ)


def week_grid():
    return tuple(slot(day, hour) for day in range(5) for hour in GRID_HOURS)


def block(resource, identity, day, start, end):
    when = normalize_period(MONDAY + timedelta(days=day), time(start), time(end), TZ)
    return Unavailability(resource, identity, when)


def unit(identity, teacher_id, class_ids, minutes):
    return Assignment(
        identity,
        class_ids,
        identity,
        teacher_id,
        frozenset({100 + identity}),
        (ModuleRequirement(identity, 1, minutes),),
    )


def week_snapshot(assignments, unavailable=(), soft=()):
    return PlanningSnapshot(
        strategy=SchedulingStrategy.ADAPTIVE_RECOVERY,
        origin=MONDAY,
        preferred_end_date=MONDAY + timedelta(days=4),
        hard_end_date=MONDAY + timedelta(days=4),
        timezone_name=TZ,
        grid_slots=tuple(
            GridSlot(day, time(hour), time(hour + 1)) for day in range(5) for hour in GRID_HOURS
        ),
        assignments=tuple(assignments),
        executed_minutes={},
        blocked_dates=frozenset(),
        unavailable=tuple(unavailable),
        soft_unavailable=tuple(soft),
    )


def test_a_class_with_scarce_hours_wins_the_shared_teacher_before_a_class_with_spare_hours():
    # R11: teacher 7 gives 20 h to class 1 (all day) and 20 h to class 2 (mornings only).
    # Class 1 has the lower assignment id, so only the availability order can favour class 2.
    impossible = [block(UnavailableResource.CLASS, 2, day, 13, 18) for day in range(5)]
    snapshot = week_snapshot(
        (unit(1, 7, (1,), 1200), unit(2, 7, (2,), 1200)),
        unavailable=impossible,
    )

    candidate = construct_recovery(snapshot, week_grid(), deadline=monotonic() + 30)

    assert candidate is not None
    assert validate_candidate(snapshot, candidate).valid
    assert len(candidate.lessons) == 40
    class_two = [row for row in candidate.lessons if row.assignment_id == 2]
    assert all(row.period.start_local < time(13) for row in class_two)


def test_recovery_uses_evitar_only_when_the_class_cannot_fit_without_it():
    # R12: one class. T1 (teacher 7) has Evitar on Monday and Tuesday and is impossible
    # from Wednesday to Friday except at 9h. T2 (teacher 8) is free only at 9h from Wednesday to Friday.
    soft = [block(UnavailableResource.TEACHER, 7, day, 9, 18) for day in range(2)]
    hard = [block(UnavailableResource.TEACHER, 7, day, 10, 18) for day in range(2, 5)]
    hard += [block(UnavailableResource.TEACHER, 8, day, 9, 18) for day in range(2)]
    hard += [block(UnavailableResource.TEACHER, 8, day, 10, 18) for day in range(2, 5)]
    snapshot = week_snapshot(
        (unit(1, 7, (1,), 180), unit(2, 8, (1,), 180)),
        unavailable=hard,
        soft=soft,
    )

    candidate = construct_recovery(snapshot, week_grid(), deadline=monotonic() + 30)

    assert candidate is not None
    assert validate_candidate(snapshot, candidate).valid
    first = [row.period for row in candidate.lessons if row.assignment_id == 1]
    second = [row.period for row in candidate.lessons if row.assignment_id == 2]
    assert len(first) == 3
    assert {period.school_date for period in first} == {MONDAY}
    assert sorted(second, key=lambda period: period.start_utc) == [
        slot(2, 9),
        slot(3, 9),
        slot(4, 9),
    ]


def _room_by_slot(candidate):
    """Rooms by (assignment, start hour): repaired lessons may receive new identities."""
    return {
        (row.assignment_id, row.period.start_local.hour): row.room_id for row in candidate.lessons
    }


def _published_rooms_plan():
    """Class 1 (protected 8h, then 9h and 10h) and class 2 (9h and 10h) use rooms 1 and 2."""
    periods = (period(0, 8, 9), period(0, 9, 10), period(0, 10, 11))
    protected = lesson(10, 1, periods[0], 1)
    baseline = (
        protected,
        lesson(1, 1, periods[1], 1, offset=60),
        lesson(2, 1, periods[2], 1, offset=120),
        lesson(3, 2, periods[1], 2),
        lesson(4, 2, periods[2], 2, offset=60),
    )
    assignments = [assignment(1, 1, 1, {1, 2, 3}, 180), assignment(2, 2, 2, {1, 2, 3}, 120)]
    return periods, assignments, protected, baseline


def test_r21_a_new_home_room_moves_the_future_editable_lessons_and_keeps_protected_ones():
    """❌ R21: a sala nova da turma leva as aulas editáveis; a protegida fica; custo 0."""
    periods, assignments, protected, baseline = _published_rooms_plan()

    target, result = recover(
        periods,
        assignments,
        baseline,
        protected_lessons=(protected,),
        home_rooms=(HomeRoom(class_id=1, room_id=3),),
    )

    assert _room_by_slot(result.candidate) == {
        (1, 8): 1,
        (1, 9): 3,
        (1, 10): 3,
        (2, 9): 2,
        (2, 10): 2,
    }
    metrics = measure_disruption(target, CandidateSchedule(baseline), result.candidate, POLICY)
    assert metrics.room_changes == 2
    assert metrics.total_cost == 0


def test_r23_without_home_room_changes_recovery_keeps_the_published_rooms_with_zero_avoidable():
    """❌ R21/R23: sem mudanças, a recuperação mantém as salas publicadas e não cria mudanças."""
    periods, assignments, protected, baseline = _published_rooms_plan()

    target, result = recover(periods, assignments, baseline, protected_lessons=(protected,))

    assert _room_by_slot(result.candidate) == {
        (1, 8): 1,
        (1, 9): 1,
        (1, 10): 1,
        (2, 9): 2,
        (2, 10): 2,
    }
    assert avoidable_room_changes(target, result.candidate) == 0


def test_rb1_room_continuity_beats_the_published_room_of_an_editable_lesson():
    """❌ RB1: sem mudanças, a sala publicada só desempata; a turma 1 fica numa sala só."""
    periods = (period(0, 8, 9), period(0, 9, 10), period(0, 10, 11))
    protected = lesson(10, 1, periods[0], 1)
    baseline = (
        protected,
        lesson(1, 1, periods[1], 2, offset=60),
        lesson(2, 1, periods[2], 1, offset=120),
        lesson(3, 2, periods[1], 1),
        lesson(4, 2, periods[2], 2, offset=60),
    )
    assignments = [assignment(1, 1, 1, {1, 2, 3}, 180), assignment(2, 2, 2, {1, 2, 3}, 120)]

    target, result = recover(periods, assignments, baseline, protected_lessons=(protected,))

    assert _room_by_slot(result.candidate) == {
        (1, 8): 1,
        (1, 9): 1,
        (1, 10): 1,
        (2, 9): 2,
        (2, 10): 2,
    }
    assert avoidable_room_changes(target, result.candidate) == 0
