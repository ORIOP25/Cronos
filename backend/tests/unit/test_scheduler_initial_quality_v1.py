from datetime import date, time, timedelta

import pytest

from app.scheduler.domain.calendar import normalize_period
from app.scheduler.domain.candidate import (
    CandidateSchedule,
    ScheduledLesson,
    SchedulingStrategy,
)
from app.scheduler.domain.quality import initial_quality_vector, measure_initial_quality
from app.scheduler.lab.fixtures import AssignmentSpec, FixtureSpec, build_snapshot

START = date(2026, 9, 1)
PREFERRED = date(2026, 10, 1)
TZ = "Europe/Lisbon"
DAY = date(2026, 9, 21)


def quality(first_day, second_day, *, teacher_gaps=0, class_gaps=0):
    return initial_quality_vector(
        {1: START + timedelta(days=first_day), 2: START + timedelta(days=second_day)},
        class_ids=(1, 2),
        origin=START,
        preferred_end_date=PREFERRED,
        teacher_gap_minutes=teacher_gaps,
        class_gap_minutes=class_gaps,
        preference_cost=0,
        room_change_cost=0,
    )


def test_sorted_completion_vector_beats_equal_sum_with_later_worst_class():
    assert quality(8, 6) < quality(10, 4)


def test_earlier_other_class_wins_when_latest_completion_is_equal():
    assert quality(5, 8) < quality(6, 8)


def test_t19_teacher_gaps_precede_class_gaps_after_completion_ties():
    assert quality(5, 8, teacher_gaps=0, class_gaps=30) < quality(
        5, 8, teacher_gaps=10, class_gaps=0
    )


def test_quality_is_independent_of_class_mapping_order():
    left = quality(5, 8)
    right = initial_quality_vector(
        {2: START + timedelta(days=8), 1: START + timedelta(days=5)},
        class_ids=(2, 1),
        origin=START,
        preferred_end_date=PREFERRED,
        teacher_gap_minutes=0,
        class_gap_minutes=0,
        preference_cost=0,
        room_change_cost=0,
    )

    assert left == right


def test_incomplete_or_late_candidate_has_no_quality_vector():
    with pytest.raises(ValueError):
        initial_quality_vector(
            {1: START},
            class_ids=(1, 2),
            origin=START,
            preferred_end_date=PREFERRED,
            teacher_gap_minutes=0,
            class_gap_minutes=0,
            preference_cost=0,
            room_change_cost=0,
        )
    with pytest.raises(ValueError):
        quality(5, 31)


def _slots():
    return (
        (0, time(9), time(10)),
        (0, time(10), time(11)),
        (0, time(11), time(12)),
        (0, time(12), time(13)),
    )


def _snapshot(*, assignments=None, soft_unavailable=()):
    spec = FixtureSpec(
        strategy=SchedulingStrategy.COMPLETE_GENERATION,
        origin=DAY,
        preferred_end_date=date(2026, 10, 30),
        hard_end_date=date(2026, 11, 30),
        timezone_name=TZ,
        grid_slots=_slots(),
        periods=tuple((DAY, start, end) for _, start, end in _slots()),
        assignments=assignments
        or (
            AssignmentSpec(1, 7, (120,), (500, 501)),
            AssignmentSpec(2, 7, (60,), (501,)),
        ),
        soft_unavailable=soft_unavailable,
    )
    return build_snapshot(spec)


def _lesson(lesson_id, assignment_id, start_hour, *, room_id=500):
    period = normalize_period(DAY, time(start_hour), time(start_hour + 1), TZ)
    return ScheduledLesson(lesson_id, assignment_id, period, room_id, 60, ())


def test_measure_quality_separates_teacher_gaps_from_class_gaps():
    snapshot = _snapshot()
    contiguous = CandidateSchedule(
        (
            _lesson(1, 1, 9),
            _lesson(2, 1, 10),
            _lesson(3, 2, 12, room_id=501),
        )
    )
    split = CandidateSchedule(
        (
            _lesson(1, 1, 9),
            _lesson(2, 1, 11),
            _lesson(3, 2, 10, room_id=501),
        )
    )

    with_teacher_gap = measure_initial_quality(snapshot, contiguous)
    with_class_gap = measure_initial_quality(snapshot, split)

    assert (with_teacher_gap.teacher_gap_minutes, with_teacher_gap.class_gap_minutes) == (60, 0)
    assert (with_class_gap.teacher_gap_minutes, with_class_gap.class_gap_minutes) == (0, 60)


def test_measure_quality_charges_dispreferred_placements_only():
    dispreferred = (("teacher", 7, (DAY, time(9), time(10))),)
    snapshot = _snapshot(soft_unavailable=dispreferred)

    charged = measure_initial_quality(snapshot, CandidateSchedule((_lesson(1, 1, 9),)))
    free = measure_initial_quality(snapshot, CandidateSchedule((_lesson(1, 1, 10),)))

    assert charged.preference_cost_minutes == 60
    assert free.preference_cost_minutes == 0


def test_measure_quality_counts_room_changes_per_class_subject():
    snapshot = _snapshot()
    stable = CandidateSchedule((_lesson(1, 1, 9), _lesson(2, 1, 10)))
    changed = CandidateSchedule((_lesson(1, 1, 9), _lesson(2, 1, 10, room_id=501)))

    assert measure_initial_quality(snapshot, stable).room_change_cost == 0
    assert measure_initial_quality(snapshot, changed).room_change_cost == 1


def test_measure_quality_reports_completion_dates_per_class():
    snapshot = _snapshot(
        assignments=(
            AssignmentSpec(1, 7, (60,), (500,)),
            AssignmentSpec(2, 8, (60,), (501,)),
        )
    )
    candidate = CandidateSchedule((_lesson(1, 1, 9), _lesson(2, 2, 11, room_id=501)))

    metrics = measure_initial_quality(snapshot, candidate)

    assert metrics.completion_dates == {1: DAY, 2: DAY}
    vector = metrics.vector(origin=DAY, preferred_end_date=date(2026, 10, 30))
    assert vector == initial_quality_vector(
        metrics.completion_dates,
        class_ids=(1, 2),
        origin=DAY,
        preferred_end_date=date(2026, 10, 30),
        teacher_gap_minutes=0,
        class_gap_minutes=0,
        preference_cost=0,
        room_change_cost=0,
    )


def test_class_without_lessons_is_complete_at_the_origin():
    snapshot = _snapshot(
        assignments=(
            AssignmentSpec(1, 7, (60,), (500,)),
            AssignmentSpec(2, 8, (60,), (501,)),
        )
    )
    candidate = CandidateSchedule((_lesson(1, 1, 9),))

    metrics = measure_initial_quality(snapshot, candidate)

    assert metrics.completion_dates == {1: DAY, 2: DAY}
