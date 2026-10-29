"""Recovery capacity checks inspect only frozen lessons on the relevant day."""

from dataclasses import replace
from datetime import timedelta

import pytest

from app.scheduler.domain.candidate import Unavailability, UnavailableResource
from app.scheduler.domain.capacity import (
    available_rooms,
    eligible_periods,
    is_released_from_window,
)
from tests.unit.test_scheduler_resource_exclusivity_v1 import assignment, lesson, plan
from tests.unit.test_scheduler_w04_w05_regressions_v1 import period

WINDOW = frozenset({period(0).school_date})


def released(published, unit, **overrides):
    options = {
        "now_utc": period(0).start_utc - timedelta(hours=1),
        "protected_dates": WINDOW,
        "blocked_dates": frozenset(),
        "class_blocked_dates": {},
        "unavailable": (),
    }
    options.update(overrides)
    return is_released_from_window(published, unit, **options)


def test_room_checks_do_not_scan_the_entire_frozen_window(monkeypatch):
    from app.scheduler.domain import capacity

    periods = tuple(period(day) for day in range(17))
    assignments = [assignment(identity, identity, identity, {1}, 60) for identity in range(1, 18)]
    protected = tuple(
        lesson(identity, identity, periods[identity - 1], 1) for identity in range(1, 17)
    )
    target = plan(periods, assignments, protected_lessons=protected)
    comparisons = 0
    original = capacity._overlaps

    def observed(left, right):
        nonlocal comparisons
        comparisons += 1
        return original(left, right)

    monkeypatch.setattr(capacity, "_overlaps", observed)

    assert available_rooms(target, assignments[-1], periods[-1]) == (1,)
    assert comparisons == 0
    assert available_rooms(target, assignments[-1], periods[0]) == ()
    assert comparisons == 1


def test_a_member_class_block_excludes_the_period_for_the_whole_unit():
    when = period(0)
    unit = replace(assignment(1, 1, 1, {1}, 60), class_ids=(1, 2))
    free = plan((when,), (unit,))
    blocked = plan(
        (when,),
        (unit,),
        unavailable=(Unavailability(UnavailableResource.CLASS, 2, when),),
    )

    assert eligible_periods(free, unit, (when,)) == (when,)
    assert eligible_periods(blocked, unit, (when,)) == ()


def test_a_protected_lesson_of_one_member_class_closes_the_unit_period():
    when = period(0)
    unit = replace(assignment(1, 1, 1, {1}, 60), class_ids=(1, 2))
    other = assignment(2, 2, 2, {2}, 60)
    target = plan((when,), (unit, other), protected_lessons=(lesson(2, 2, when, 2),))

    assert eligible_periods(target, unit, (when,)) == ()


def test_a_school_closure_releases_a_future_lesson_inside_the_window():
    when = period(0)

    assert released(
        lesson(1, 1, when, 1),
        assignment(1, 1, 1, {1}, 60),
        blocked_dates=WINDOW,
    )


def test_one_closed_class_releases_the_whole_joint_lesson():
    when = period(0)
    unit = replace(assignment(1, 1, 1, {1}, 60), class_ids=(1, 2))

    assert released(lesson(1, 1, when, 1), unit, class_blocked_dates={2: WINDOW})
    assert not released(lesson(1, 1, when, 1), unit, class_blocked_dates={3: WINDOW})


@pytest.mark.parametrize(
    "resource", [UnavailableResource.TEACHER, UnavailableResource.CLASS, UnavailableResource.ROOM]
)
def test_a_hard_unavailability_overlapping_the_lesson_releases_it(resource):
    when = period(0)

    assert released(
        lesson(1, 1, when, 1),
        assignment(1, 1, 1, {1}, 60),
        unavailable=(Unavailability(resource, 1, when),),
    )


def test_an_unavailability_that_does_not_overlap_keeps_the_lesson():
    when = period(0)

    assert not released(
        lesson(1, 1, when, 1),
        assignment(1, 1, 1, {1}, 60),
        unavailable=(Unavailability(UnavailableResource.TEACHER, 1, period(0, 10, 11)),),
    )


def test_another_teacher_or_room_does_not_release_the_lesson():
    when = period(0)

    assert not released(
        lesson(1, 1, when, 1),
        assignment(1, 1, 1, {1}, 60),
        unavailable=(
            Unavailability(UnavailableResource.TEACHER, 2, when),
            Unavailability(UnavailableResource.ROOM, 2, when),
        ),
    )


def test_a_lesson_outside_the_window_is_not_released_by_the_configuration():
    when = period(0)

    assert not released(
        lesson(1, 1, when, 1),
        assignment(1, 1, 1, {1}, 60),
        protected_dates=frozenset(),
        blocked_dates=WINDOW,
    )


def test_a_started_lesson_is_never_released():
    when = period(0)

    assert not released(
        lesson(1, 1, when, 1),
        assignment(1, 1, 1, {1}, 60),
        now_utc=when.end_utc,
        blocked_dates=WINDOW,
    )
