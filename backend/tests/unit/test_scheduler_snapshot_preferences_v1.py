"""WBS 2.3.1/2.3.2: weekly preferences become hard and soft unavailability.

The pure conversion is exercised without a database; the class rows use the
same levels and names as the teachers (D01, D02).
"""

from dataclasses import replace

from app.scheduler.domain.candidate import (
    CandidateSchedule,
    GridSlot,
    ScheduledLesson,
    Unavailability,
    UnavailableResource,
)
from app.scheduler.domain.projection import ModuleSlice
from app.scheduler.domain.quality import measure_initial_quality
from app.scheduler.infrastructure.snapshot import _CalendarData, _preference_unavailability
from tests.unit.test_scheduler_class_capacity_v1 import _snapshot, assignment
from tests.unit.test_scheduler_w04_w05_regressions_v1 import period


def _calendar(periods, signatures):
    by_signature = {}
    by_date = {}
    timeslots_by_signature = {}
    for row in periods:
        signature = (row.school_date.weekday(), row.start_local, row.end_local)
        by_signature.setdefault(signature, []).append(row)
        by_date.setdefault(row.school_date, []).append(row)
    for timeslot_id, signature in signatures.items():
        timeslots_by_signature.setdefault(signature, set()).add(timeslot_id)
    return _CalendarData(
        grid_slots=tuple(
            dict.fromkeys(
                GridSlot(row.school_date.weekday(), row.start_local, row.end_local)
                for row in periods
            )
        ),
        periods=tuple(periods),
        blocked_dates=frozenset(),
        class_blocked_dates={},
        periods_by_signature={key: tuple(value) for key, value in by_signature.items()},
        periods_by_date={key: tuple(value) for key, value in by_date.items()},
        signature_by_timeslot=dict(signatures),
        timeslots_by_signature={
            key: frozenset(value) for key, value in timeslots_by_signature.items()
        },
    )


MONDAY = (0, period(0).start_local, period(0).end_local)
TUESDAY = (1, period(1).start_local, period(1).end_local)
WEDNESDAY = (2, period(2).start_local, period(2).end_local)
SIGNATURES = {10: MONDAY, 11: TUESDAY, 12: WEDNESDAY}


def test_an_impossible_block_is_hard_unavailability_for_every_matching_period():
    periods = (period(0), period(1))
    calendar = _calendar(periods, SIGNATURES)

    hard, soft = _preference_unavailability(UnavailableResource.CLASS, [(1, 10, -1)], calendar)

    assert [row.period for row in hard] == [periods[0]]
    assert all(row.resource_type is UnavailableResource.CLASS for row in hard)
    assert all(row.resource_id == 1 for row in hard)
    assert soft == []


def test_an_avoid_block_is_soft_unavailability():
    periods = (period(0), period(1))
    calendar = _calendar(periods, SIGNATURES)

    hard, soft = _preference_unavailability(UnavailableResource.CLASS, [(1, 10, 0)], calendar)

    assert hard == []
    assert [row.period for row in soft] == [periods[0]]


def test_a_preferred_block_makes_the_other_periods_soft():
    periods = (period(0), period(1), period(2))
    calendar = _calendar(periods, SIGNATURES)

    hard, soft = _preference_unavailability(UnavailableResource.CLASS, [(1, 10, 2)], calendar)

    assert hard == []
    assert {row.period for row in soft} == {periods[1], periods[2]}


def test_extra_preferred_timeslots_feed_the_preferred_rule():
    periods = (period(0), period(1), period(2))
    calendar = _calendar(periods, SIGNATURES)

    hard, soft = _preference_unavailability(
        UnavailableResource.TEACHER, [], calendar, extra_preferred=[(3, 10)]
    )

    assert hard == []
    assert {row.period for row in soft} == {periods[1], periods[2]}
    assert all(row.resource_type is UnavailableResource.TEACHER for row in soft)


def test_an_unknown_timeslot_is_ignored():
    periods = (period(0),)
    calendar = _calendar(periods, SIGNATURES)

    hard, soft = _preference_unavailability(UnavailableResource.CLASS, [(1, 99, -1)], calendar)

    assert hard == []
    assert soft == []


def test_a_class_avoid_period_counts_as_a_preference_violation():
    periods = (period(0),)
    snapshot = replace(
        _snapshot(periods, (assignment(1, 1, 1, 1, 60),)),
        soft_unavailable=(Unavailability(UnavailableResource.CLASS, 1, periods[0]),),
    )
    lesson = ScheduledLesson(
        lesson_id=1,
        assignment_id=1,
        period=periods[0],
        room_id=1,
        credit_minutes=60,
        slices=(ModuleSlice(1, 1, 0, 60),),
    )

    quality = measure_initial_quality(snapshot, CandidateSchedule((lesson,)))

    assert quality.preference_cost_minutes == 60
