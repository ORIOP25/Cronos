"""R10.1/F02: events must target future lessons that the perturbation affects."""

from dataclasses import replace
from datetime import timedelta

from app.scheduler.domain.candidate import CandidateSchedule, ScheduledLesson
from app.scheduler.lab.annual import build_annual_fixture
from app.scheduler.lab.longitudinal import _consume_executed
from app.scheduler.lab.recovery import (
    EVENTS,
    TEACHER_ABSENCE,
    apply_event,
    apply_event_with_effect,
)


def _fixture():
    return build_annual_fixture(4, profile="loose", seed=1)


def _teacher_for(snapshot, lesson: ScheduledLesson) -> int:
    assignment = snapshot.assignment_for(lesson.assignment_id)
    assert assignment is not None
    return assignment.teacher_id


def _target_teacher(snapshot, event_seed: int) -> int:
    teachers = sorted({row.teacher_id for row in snapshot.assignments})
    return teachers[(event_seed // len(EVENTS)) % len(teachers)]


def test_a_teacher_absence_intersects_the_future_lessons_of_that_teacher():
    fixture = _fixture()
    clock = fixture.snapshot.origin + timedelta(days=21)
    active, executed = _consume_executed(
        fixture.witness.lessons, fixture.snapshot.executed_minutes, clock
    )
    snapshot = replace(fixture.snapshot, executed_minutes=executed, baseline_lessons=active)
    seed = 1
    teacher_id = _target_teacher(snapshot, seed)
    before = len(snapshot.unavailable)

    perturbed, effect = apply_event_with_effect(
        snapshot, fixture.periods, CandidateSchedule(active), TEACHER_ABSENCE, seed
    )

    assert effect.applied is True
    assert effect.resource_type == "teacher"
    assert effect.resource_id == teacher_id
    added = perturbed.unavailable[before:]
    future_teacher_lessons = [
        lesson for lesson in active if _teacher_for(snapshot, lesson) == teacher_id
    ]
    assert future_teacher_lessons, "The fixture must have future lessons for the teacher."
    assert effect.affected_lessons == len(added)
    assert any(row.overlaps(lesson.period) for row in added for lesson in future_teacher_lessons)
    assert all(row.period.school_date >= clock for row in added)


def test_a_teacher_without_future_lessons_reports_a_no_effect_event():
    fixture = _fixture()
    clock = fixture.snapshot.origin + timedelta(days=21)
    active, _executed = _consume_executed(
        fixture.witness.lessons, fixture.snapshot.executed_minutes, clock
    )
    seed = 1
    teacher_id = _target_teacher(fixture.snapshot, seed)
    other_lessons = tuple(
        lesson for lesson in active if _teacher_for(fixture.snapshot, lesson) != teacher_id
    )
    assert other_lessons

    _perturbed, effect = apply_event_with_effect(
        fixture.snapshot,
        fixture.periods,
        CandidateSchedule(other_lessons),
        TEACHER_ABSENCE,
        seed,
    )

    assert effect.applied is False
    assert effect.affected_lessons == 0


def test_apply_event_keeps_its_previous_snapshot_only_contract():
    fixture = _fixture()
    snapshot = apply_event(
        fixture.snapshot,
        fixture.periods,
        fixture.witness,
        TEACHER_ABSENCE,
        1,
    )

    assert snapshot.baseline_lessons == fixture.witness.lessons
    assert len(snapshot.unavailable) >= 1


def test_the_absence_duration_respects_the_seed():
    fixture = _fixture()

    for seed in (1, 4, 7, 10):
        _snapshot, effect = apply_event_with_effect(
            fixture.snapshot,
            fixture.periods,
            fixture.witness,
            TEACHER_ABSENCE,
            seed,
        )
        if effect.applied:
            assert 1 <= effect.affected_lessons
