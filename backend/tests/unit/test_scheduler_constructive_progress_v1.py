"""Dense initial construction, shared-resource priority and parallel progress."""

from dataclasses import replace
from datetime import time

import pytest
from ortools.sat.python import cp_model

from app.scheduler.domain.candidate import LunchRule, Unavailability, UnavailableResource
from app.scheduler.domain.candidate_validation import validate_candidate
from app.scheduler.infrastructure.constructive import _select_period, construct_schedule
from tests.unit.test_scheduler_resource_exclusivity_v1 import assignment, lesson, plan
from tests.unit.test_scheduler_w04_w05_regressions_v1 import period


def construct(target, periods):
    candidate = construct_schedule(target, periods)
    assert candidate is not None
    assert validate_candidate(target, candidate).valid
    return candidate


def test_a_long_calendar_does_not_delay_subjects_when_earlier_capacity_exists():
    periods = tuple(
        period(day, start=hour, end=hour + 1) for day in range(8) for hour in range(9, 15)
    )
    target = plan(periods, [assignment(1, 1, 1, {1}, 240), assignment(2, 1, 1, {1}, 240)])

    candidate = construct(target, periods)

    assert {row.assignment_id for row in candidate.lessons[:2]} == {1, 2}
    assert max(row.period.school_date for row in candidate.lessons) == periods[6].school_date


@pytest.mark.parametrize("break_minutes", (0, 10))
def test_calendar_progress_prefers_contiguous_class_and_teacher_lessons(break_minutes):
    periods = tuple(
        period(
            day,
            start=hour,
            end=hour + 1 if break_minutes == 0 else hour,
            end_min=0 if break_minutes == 0 else 50,
        )
        for day in range(8)
        for hour in range(9, 15)
    )
    required = 4 * periods[0].duration_minutes
    target = plan(
        periods,
        [
            assignment(1, 1, 1, {1}, required),
            assignment(2, 1, 1, {1}, required),
            assignment(3, 2, 2, {1}, required),
            assignment(4, 2, 2, {1}, required),
        ],
    )

    candidate = construct(target, periods)

    for day in range(1, 8):
        for class_id in (1, 2):
            rows = sorted(
                (
                    row
                    for row in candidate.lessons
                    if row.period.school_date == period(day).school_date
                    and target.assignment_for(row.assignment_id).class_id == class_id
                ),
                key=lambda row: row.period.start_utc,
            )
            assert all(
                left.period.start_local.hour + 1 == right.period.start_local.hour
                for left, right in zip(rows, rows[1:], strict=False)
            )


def test_different_subject_loads_do_not_force_a_gap_inside_the_same_day():
    periods = tuple(
        period(day, start=hour, end=hour + 1) for day in range(8) for hour in range(9, 15)
    )
    target = plan(periods, [assignment(1, 1, 1, {1}, 360), assignment(2, 1, 1, {1}, 480)])

    candidate = construct(target, periods)

    for day in {row.period.school_date for row in candidate.lessons}:
        rows = sorted(
            (row for row in candidate.lessons if row.period.school_date == day),
            key=lambda row: row.period.start_utc,
        )
        assert all(
            left.period.end_utc == right.period.start_utc
            for left, right in zip(rows, rows[1:], strict=False)
        )


def test_shared_capacity_starts_all_classes_on_the_first_day():
    periods = tuple(
        period(day, start=hour, end=hour + 1) for day in range(4) for hour in (9, 10, 11)
    )
    target = plan(periods, [assignment(i, i, i, {1}, 240) for i in (1, 2, 3)])

    candidate = construct(target, periods)

    first_dates = {
        i: min(row.period.school_date for row in candidate.lessons if row.assignment_id == i)
        for i in (1, 2, 3)
    }
    assert set(first_dates.values()) == {periods[0].school_date}
    assert len(candidate.lessons) == len(periods)


def test_seven_subjects_start_together_and_keep_their_calendar_cadence():
    periods = tuple(
        period(day, start=hour, end=hour + 1) for day in range(3) for hour in range(9, 18)
    )
    target = plan(
        periods,
        [assignment(i, 1, i, {1}, 180) for i in range(1, 8)],
        lunch_rule=LunchRule(time(12), time(14), 60),
    )

    candidate = construct(target, periods)

    first_day = [
        row for row in candidate.lessons if row.period.school_date == periods[0].school_date
    ]
    assert {row.assignment_id for row in first_day} == set(range(1, 8))
    assert len(first_day) == 8
    assert max(row.period.school_date for row in candidate.lessons) == periods[-1].school_date
    for day in range(2):
        assert (
            sum(row.period.school_date == period(day).school_date for row in candidate.lessons) == 8
        )


def test_subject_progress_is_proportional_to_different_required_minutes():
    periods = tuple(
        period(day, start=hour, end=hour + 1) for day in range(8) for hour in range(9, 15)
    )
    target = plan(periods, [assignment(1, 1, 1, {1}, 120), assignment(2, 1, 2, {1}, 240)])

    candidate = construct(target, periods)

    credited = {1: 0, 2: 0}
    for day in sorted({row.period.school_date for row in candidate.lessons}):
        for row in candidate.lessons:
            if row.period.school_date == day:
                credited[row.assignment_id] += row.credit_minutes
        assert abs(credited[1] / 120 - credited[2] / 240) <= 0.5
    assert {row.assignment_id for row in candidate.lessons[:2]} == {1, 2}


def test_shared_resources_do_not_finish_one_subject_before_others_start():
    rows = (
        (1, 1, 2, (1, 2, 4), 180),
        (2, 1, 4, (1, 4), 120),
        (3, 1, 4, (4,), 180),
        (4, 2, 5, (4,), 180),
        (5, 2, 6, (1,), 180),
        (6, 2, 1, (1,), 240),
        (7, 3, 5, (4,), 240),
        (8, 3, 2, (1, 3), 120),
        (9, 3, 4, (2, 4), 120),
        (10, 4, 6, (4,), 180),
        (11, 4, 1, (1, 4), 240),
        (12, 4, 6, (1, 3), 180),
        (13, 5, 6, (1, 3, 4), 180),
        (14, 5, 3, (2, 3, 4), 240),
        (15, 5, 1, (2, 3), 180),
        (16, 6, 4, (2, 3, 4), 120),
        (17, 6, 4, (1, 2, 4), 180),
        (18, 6, 4, (1, 2, 4), 180),
    )
    assignments = [assignment(*row) for row in rows]
    periods = tuple(
        period(day, start=hour, end=hour + 1) for day in range(12) for hour in (9, 10, 11, 12)
    )
    target = plan(periods, assignments)

    candidate = construct(target, periods)

    credited = {row.assignment_id: 0 for row in assignments}
    for when in periods:
        for row in candidate.lessons:
            if row.period == when:
                credited[row.assignment_id] += row.credit_minutes
        for class_id in range(1, 7):
            members = [row for row in assignments if row.class_id == class_id]
            if any(
                credited[row.assignment_id] == row.modules[0].required_minutes for row in members
            ):
                assert all(credited[row.assignment_id] > 0 for row in members)


def test_a_shared_room_subset_sets_the_pace_of_flexible_subjects_too():
    periods = tuple(period(day) for day in range(12))
    assignments = [
        assignment(identity, class_id, identity, rooms, 180)
        for class_id in (1, 2, 3)
        for identity, rooms in ((2 * class_id - 1, {1}), (2 * class_id, {1, 2, 3}))
    ]
    target = plan(periods, assignments)

    candidate = construct(target, periods)

    credit = dict.fromkeys(range(1, 7), 0)
    for when in periods:
        for row in candidate.lessons:
            if row.period.school_date == when.school_date:
                credit[row.assignment_id] += row.credit_minutes
        for class_id in (1, 2, 3):
            assert abs(credit[2 * class_id - 1] - credit[2 * class_id]) <= 60
    assert max(row.period.school_date for row in candidate.lessons) <= periods[9].school_date


def test_a_shared_resource_favors_the_class_with_later_projected_completion():
    periods = tuple(period(day, start=hour, end=hour + 1) for day in range(3) for hour in (9, 10))
    target = plan(periods, [assignment(1, 1, 1, {1}, 60), assignment(2, 2, 1, {1}, 240)])

    candidate = construct(target, periods)

    ordered = sorted(candidate.lessons, key=lambda row: row.period.start_utc)
    assert ordered[0].assignment_id == 2
    assert {row.assignment_id for row in ordered[:2]} == {1, 2}
    assert ordered[-1].period == periods[4]


def test_an_independent_class_is_not_delayed_to_match_a_blocked_class():
    periods = tuple(period(day) for day in range(6))
    unavailable = tuple(Unavailability(UnavailableResource.TEACHER, 2, row) for row in periods[1:4])
    target = plan(
        periods,
        [assignment(1, 1, 1, {1}, 120), assignment(2, 2, 2, {2}, 180)],
        unavailable=unavailable,
    )

    candidate = construct(target, periods)

    assert (
        max(row.period.school_date for row in candidate.lessons if row.assignment_id == 1)
        == periods[1].school_date
    )
    assert (
        max(row.period.school_date for row in candidate.lessons if row.assignment_id == 2)
        == periods[-1].school_date
    )


def test_room_choices_preserve_capacity_for_a_subject_with_only_one_room():
    periods = (period(0),)
    target = plan(periods, [assignment(1, 1, 1, {1, 2}, 60), assignment(2, 2, 2, {1}, 60)])

    candidate = construct(target, periods)

    assert {row.assignment_id: row.room_id for row in candidate.lessons} == {1: 2, 2: 1}


def test_a_flexible_class_does_not_block_two_simultaneous_teacher_allocations():
    periods = (period(0), period(0, start=10, end=11))
    target = plan(
        periods,
        [assignment(1, 1, 1, {1}, 60), assignment(2, 1, 2, {1}, 60), assignment(3, 2, 1, {2}, 60)],
    )

    candidate = construct(target, periods)

    assert {row.assignment_id for row in candidate.lessons if row.period == periods[0]} == {2, 3}


def test_protected_credit_is_preserved_and_new_slices_continue_its_module():
    periods = tuple(period(day) for day in range(3))
    protected = lesson(42, 1, periods[0], 1)
    target = plan(periods, [assignment(1, 1, 1, {1}, 150)], protected_lessons=(protected,))

    candidate = construct(target, periods)

    assert protected in candidate.lessons
    mobile = sorted(
        (row for row in candidate.lessons if row.lesson_id != 42),
        key=lambda row: row.period.start_utc,
    )
    assert [row.credit_minutes for row in mobile] == [60, 30]
    assert [row.slices[0].offset_minutes for row in mobile] == [60, 120]


def test_executed_lesson_identities_are_not_reused_for_future_lessons():
    from app.scheduler.domain.serialization import snapshot_from_dict, snapshot_to_dict

    periods = tuple(period(day) for day in range(3))
    target = replace(
        plan(periods, [assignment(1, 1, 1, {1}, 120)]),
        executed_minutes={1: {1: 60}},
        reserved_lesson_ids=frozenset({1_000_001}),
    )

    restored = snapshot_from_dict(snapshot_to_dict(target))
    assert restored.reserved_lesson_ids == target.reserved_lesson_ids
    candidate = construct(restored, periods)

    assert len(candidate.lessons) == 1
    assert candidate.lessons[0].lesson_id != 1_000_001
    assert candidate.lessons[0].slices[0].offset_minutes == 60


def test_partial_overlaps_do_not_discard_a_valid_constructive_solution():
    periods = (period(0), period(0, start_min=30, end_min=30), period(0, start=10, end=11))
    target = plan(periods, [assignment(1, 1, 1, {1}, 120)])

    candidate = construct(target, periods)

    assert {row.period for row in candidate.lessons} == {periods[0], periods[2]}


def test_construction_is_independent_of_input_assignment_and_period_order():
    periods = tuple(period(day) for day in range(6))
    target = plan(periods, [assignment(1, 1, 1, {1}, 180), assignment(2, 2, 2, {1}, 180)])

    expected = construct(target, periods)
    actual = construct(
        replace(target, assignments=tuple(reversed(target.assignments))), tuple(reversed(periods))
    )

    assert actual == expected


def test_local_matching_does_not_repeat_room_choices_for_every_subject(monkeypatch):
    sizes = []
    original = cp_model.CpSolver.Solve

    def measure(solver, model, *args, **kwargs):
        sizes.append(len(model.Proto().variables))
        return original(solver, model, *args, **kwargs)

    monkeypatch.setattr(cp_model.CpSolver, "Solve", measure)
    for count in (4, 8):
        options = [(assignment(i, 1, 2, {2}, 60), (2,)) for i in range(1, count + 1)]
        options[0] = (assignment(1, 1, 1, {1}, 60), (1,))
        options.append((assignment(100, 2, 1, {2}, 60), (2,)))
        selected = _select_period(options, deadline=None)
        assert len(selected) == 1

    assert len(sizes) == 2
    assert sizes[1] <= sizes[0] + 4


def test_period_matching_reserves_search_time_for_the_rest_of_the_year(monkeypatch):
    from time import monotonic

    limits = []

    def inconclusive(solver, _model):
        limits.append(solver.parameters.max_time_in_seconds)
        return cp_model.UNKNOWN

    monkeypatch.setattr(cp_model.CpSolver, "Solve", inconclusive)
    options = [
        (assignment(1, 1, 1, {1}, 60), (1,)),
        (assignment(2, 1, 2, {2}, 60), (2,)),
        (assignment(3, 2, 1, {2}, 60), (2,)),
    ]

    selected = _select_period(options, deadline=monotonic() + 10)

    assert len(selected) == 1
    assert len(limits) == 1
    assert 0 < limits[0] <= 0.1


def test_uniform_class_rooms_fill_a_teacher_matching_without_sat_search(monkeypatch):
    def unexpected_sat(*_args, **_kwargs):
        raise AssertionError("Uniform room domains have a direct native flow solution.")

    monkeypatch.setattr(cp_model.CpSolver, "Solve", unexpected_sat)
    options = [
        (assignment(1, 1, 1, {1}, 60), (1,)),
        (assignment(2, 1, 2, {1}, 60), (1,)),
        (assignment(3, 2, 1, {2}, 60), (2,)),
    ]

    selected = _select_period(options, deadline=None)

    assert {row.assignment_id for row, _room in selected} == {2, 3}


def test_different_subject_rooms_use_flow_when_selected_subjects_fit(monkeypatch):
    def unexpected_sat(*_args, **_kwargs):
        raise AssertionError("A validated maximum flow needs no SAT search.")

    monkeypatch.setattr(cp_model.CpSolver, "Solve", unexpected_sat)
    options = [
        (assignment(1, 1, 1, {1}, 60), (1,)),
        (assignment(2, 1, 2, {2, 3}, 60), (2, 3)),
        (assignment(3, 2, 1, {2}, 60), (2,)),
    ]

    selected = _select_period(options, deadline=None)

    assert {row.assignment_id: room for row, room in selected} == {2: 3, 3: 2}


def test_first_complete_placement_skips_quality_and_room_search(monkeypatch):
    import app.scheduler.infrastructure.placement_model as placement

    original = cp_model.CpSolver.Solve
    calls = []

    def first_solve(solver, model, *args, **kwargs):
        assert solver.parameters.stop_after_first_solution
        calls.append(True)
        return original(solver, model, *args, **kwargs)

    def unexpected_rooms(*_args, **_kwargs):
        raise AssertionError("A first-complete placement must skip room optimization.")

    monkeypatch.setattr(cp_model.CpSolver, "Solve", first_solve)
    monkeypatch.setattr(placement, "_optimize_rooms", unexpected_rooms)
    periods = (period(0), period(1))
    target = plan(periods, [assignment(1, 1, 1, {1, 2}, 60)])

    result = placement.solve_placement(target, periods, stop_at_first_complete=True)

    assert result.status == "COMPLETE"
    assert validate_candidate(target, result.candidate).valid
    assert calls == [True]
    assert result.evidence.certified_stages == 0
