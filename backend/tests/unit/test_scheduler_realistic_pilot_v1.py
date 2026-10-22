"""The realistic pilot school follows the owner's brief of 20 October 2026."""

from collections import defaultdict
from datetime import time

import pytest

from app.scheduler.domain.candidate import UnavailableResource
from app.scheduler.domain.candidate_validation import validate_candidate
from app.scheduler.domain.priorities import DEFAULT_LEVELS, PriorityWeights
from app.scheduler.domain.priority_metrics import measure_priority_metrics
from app.scheduler.infrastructure.constructive import construct_schedule
from app.scheduler.lab.realistic_pilot import (
    AREA_INTEGRACAO,
    EDUCACAO_FISICA,
    INGLES,
    NORMAL,
    TEACHING_WEEKS,
    _room_type,
    build_realistic_pilot,
)


@pytest.fixture(scope="module")
def school():
    return build_realistic_pilot()


def test_the_grid_has_eight_lessons_with_ten_minute_breaks_and_a_lunch_window(school):
    starts = sorted({slot.start_local for slot in school.snapshot.grid_slots})
    rule = school.snapshot.lunch_rule

    assert starts == [
        time(9, 0),
        time(10, 10),
        time(11, 20),
        time(12, 30),
        time(13, 30),
        time(14, 40),
        time(15, 50),
        time(17, 0),
    ]
    assert (rule.window_start, rule.window_end, rule.minimum_minutes) == (
        time(12, 30),
        time(14, 30),
        60,
    )


def test_each_class_has_eight_or_nine_subjects_of_six_or_seven_modules(school):
    subjects = defaultdict(set)
    load = defaultdict(int)
    for unit in school.snapshot.assignments:
        for class_id in unit.class_ids:
            subjects[class_id].add(unit.subject_id)
            load[class_id] += sum(module.required_minutes for module in unit.modules)
        assert len(unit.modules) in (6, 7)
        assert all(16 * 60 <= module.required_minutes <= 22 * 60 for module in unit.modules)

    assert len(subjects) == 48
    assert {len(rows) for rows in subjects.values()} == {8, 9}
    assert all(950 * 60 <= minutes <= 1150 * 60 for minutes in load.values())


def test_same_year_classes_of_paired_courses_share_two_or_three_general_subjects(school):
    joint = defaultdict(set)
    for unit in school.snapshot.assignments:
        if len(unit.class_ids) > 1:
            joint[unit.class_ids].add(unit.subject_id)

    assert len(joint) == 24
    assert all(len(pair) == 2 for pair in joint)
    assert {len(rows) for rows in joint.values()} == {2, 3}
    assert set().union(*joint.values()) == {EDUCACAO_FISICA, INGLES, AREA_INTEGRACAO}


def test_external_teachers_are_at_least_thirty_percent_with_two_or_three_hour_minimums(school):
    teachers = {unit.teacher_id for unit in school.snapshot.assignments}
    rules = {rule.teacher_id: rule for rule in school.snapshot.teacher_presence}
    minimums = [rule.minimum_minutes for rule in rules.values()]

    assert len(school.external_teachers) >= 0.3 * len(teachers)
    assert set(rules) == school.external_teachers
    assert abs(minimums.count(120) - minimums.count(180)) <= 1
    assert {rule.max_gap_minutes for rule in rules.values()} == {60}


def test_internal_teachers_teach_up_to_twenty_five_lessons_a_week_and_externals_about_eleven(
    school,
):
    hours = defaultdict(int)
    for unit in school.snapshot.assignments:
        hours[unit.teacher_id] += sum(module.required_minutes for module in unit.modules) // 60
    weekly = {teacher: total / TEACHING_WEEKS for teacher, total in hours.items()}
    internal = [load for teacher, load in weekly.items() if teacher not in school.external_teachers]
    external = [load for teacher, load in weekly.items() if teacher in school.external_teachers]

    assert max(internal) <= 25
    assert sum(internal) / len(internal) >= 20
    assert all(10 <= load <= 12 for load in external)


def test_availability_follows_the_requested_shares(school):
    teachers = sorted({unit.teacher_id for unit in school.snapshot.assignments})
    soft_days = defaultdict(set)
    for row in school.snapshot.soft_unavailable:
        soft_days[(row.resource_type, row.resource_id)].add(row.period.school_date.weekday())
    hard_teachers = {row.resource_id for row in school.snapshot.unavailable}
    teacher_soft = {
        identity: days
        for (kind, identity), days in soft_days.items()
        if kind == UnavailableResource.TEACHER
    }
    one_afternoon = [days for days in teacher_soft.values() if len(days) == 1]
    every_afternoon = [days for days in teacher_soft.values() if len(days) == 5]
    friday_classes = [
        days for (kind, _identity), days in soft_days.items() if kind == UnavailableResource.CLASS
    ]

    positions = range(len(teachers))
    # One in three avoids one afternoon; one in five prefers mornings (every afternoon).
    assert len(every_afternoon) == sum(1 for p in positions if p % 5 == 1)
    assert len(one_afternoon) == sum(1 for p in positions if p % 3 == 0 and p % 5 != 1)
    assert len(one_afternoon) + len(every_afternoon) == len(teacher_soft)
    assert len(hard_teachers) == len(teachers[2::8])
    assert len(friday_classes) == 12 and all(days == {4} for days in friday_classes)


def test_the_school_has_forty_eight_rooms_and_is_built_the_same_every_time(school):
    again = build_realistic_pilot()

    assert len(school.labels["rooms"]) == 48
    assert again.snapshot == school.snapshot


def test_realistic_pilot_marks_assignments_that_require_special_rooms(school):
    assert all(
        assignment.needs_special_room is (_room_type(assignment.subject_id) != NORMAL)
        for assignment in school.snapshot.assignments
    )


@pytest.mark.slow_solver
def test_r24_recommended_weights_build_the_realistic_school_by_the_preferred_end(school):
    # With internal teachers at 20-25 lessons a week the unweighted construction leaves
    # hours unplaced at the end of the year; the weighted one must still complete it.
    weighted = construct_schedule(
        school.snapshot, school.periods, weights=PriorityWeights(DEFAULT_LEVELS)
    )

    assert weighted is not None
    assert validate_candidate(school.snapshot, weighted).valid is True
    finish = measure_priority_metrics(school.snapshot, weighted)["finish_early"]
    assert finish <= school.snapshot.preferred_end_date


@pytest.mark.slow_solver
def test_the_unweighted_construction_builds_the_realistic_school_validly(school):
    # Without weights the construction must not strand end-of-year hours a feasible plan teaches.
    candidate = construct_schedule(school.snapshot, school.periods)

    assert candidate is not None
    assert validate_candidate(school.snapshot, candidate).valid is True
