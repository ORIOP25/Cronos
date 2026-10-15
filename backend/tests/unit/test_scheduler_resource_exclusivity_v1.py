"""Resource-exclusivity regressions for the OOM correction.

The pair-by-pair conflict expansion grows quadratically and exhausted the
worker memory in production. These tests lock the compact contract: the model
size must stay sub-quadratic and the accepted selections must keep the exact
resource semantics. The small instances use the existing fixtures and the
CP-SAT model itself; the independent oracle is never the helper under test.
"""

from dataclasses import replace
from time import monotonic

from ortools.sat.python import cp_model

from app.scheduler.domain.candidate import (
    Assignment,
    CandidateSchedule,
    ScheduledLesson,
)
from app.scheduler.domain.candidate_validation import validate_candidate
from app.scheduler.domain.projection import ModuleRequirement, ModuleSlice
from app.scheduler.infrastructure.placement_model import (
    _build_scope_state,
    _optimize_rooms,
    _unrestricted_scope,
)
from app.scheduler.lab.scale import build_scale_fixture
from tests.unit.test_scheduler_w04_w05_regressions_v1 import period, snapshot


def assignment(identity, class_id, teacher_id, rooms, minutes):
    return Assignment(
        identity,
        (class_id,),
        identity,
        teacher_id,
        frozenset(rooms),
        (ModuleRequirement(identity, 1, minutes),),
    )


def lesson(identity, assignment_id, when, room, credit=None, offset=0):
    minutes = when.duration_minutes if credit is None else credit
    return ScheduledLesson(
        identity,
        assignment_id,
        when,
        room,
        minutes,
        (ModuleSlice(identity, assignment_id, offset, minutes),),
    )


def plan(periods, assignments, protected_lessons=(), **kwargs):
    target = replace(snapshot(periods, **kwargs), assignments=tuple(assignments))
    if protected_lessons:
        target = replace(target, protected_lessons=tuple(protected_lessons))
    return target


def scope_state(target, periods):
    return _build_scope_state(target, _unrestricted_scope(target, periods))


def solve(model):
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 1
    return solver.Solve(model)


def feasible(model):
    return solve(model) != cp_model.INFEASIBLE


def force(state, selections):
    for identity, when in selections:
        state.model.Add(state.x[(identity, when)] == 1)


SHARED_ROOMS = frozenset(range(1, 9))


def _shared_room_models(count):
    fixture = build_scale_fixture(count, module_minutes=60)
    target = replace(
        fixture.snapshot,
        assignments=tuple(
            replace(row, eligible_room_ids=SHARED_ROOMS) for row in fixture.snapshot.assignments
        ),
    )
    periods = (fixture.periods[0],)
    return scope_state(target, periods).model


def test_resource_exclusivity_growth_does_not_exceed_twice_the_smaller_model():
    counts = {count: len(_shared_room_models(count).Proto().constraints) for count in (8, 16, 32)}

    assert counts[32] <= 2 * counts[16]


def test_two_options_of_the_same_resource_at_the_same_period_conflict():
    when = period(0)
    target = plan((when,), (assignment(1, 1, 1, {1}, 60), assignment(2, 1, 2, {2}, 60)))
    state = scope_state(target, (when,))

    assert solve(state.model) == cp_model.INFEASIBLE


def test_partially_overlapping_options_conflict():
    first, overlap = period(0), period(0, start_min=30, end_min=30)
    target = plan((first, overlap), (assignment(1, 1, 1, {1}, 60), assignment(2, 1, 2, {2}, 60)))
    state = scope_state(target, (first, overlap))
    force(state, ((1, first), (2, overlap)))

    assert solve(state.model) == cp_model.INFEASIBLE


def test_adjacent_options_can_coexist():
    earliest, latest = period(0), period(0, start=10, end=11)
    target = plan((earliest, latest), (assignment(1, 1, 1, {1}, 60), assignment(2, 1, 2, {2}, 60)))
    state = scope_state(target, (earliest, latest))
    force(state, ((1, earliest), (2, latest)))

    assert feasible(state.model)


def test_a_contained_interval_conflicts_with_its_container():
    outer, inner = period(0, end=11), period(0, start=10, end=10, end_min=30)
    target = plan(
        (outer, inner),
        (assignment(1, 1, 1, {1}, 120), assignment(2, 1, 2, {2}, 30)),
    )
    state = scope_state(target, (outer, inner))
    force(state, ((1, outer), (2, inner)))

    assert solve(state.model) == cp_model.INFEASIBLE


def test_independent_resources_can_overlap():
    first, overlap = period(0), period(0, start_min=30, end_min=30)
    target = plan(
        (first, overlap),
        (assignment(1, 1, 1, {1}, 60), assignment(2, 2, 2, {2}, 60)),
    )
    state = scope_state(target, (first, overlap))
    force(state, ((1, first), (2, overlap)))

    assert feasible(state.model)


def test_one_assignment_cannot_use_overlapping_periods():
    first, overlap = period(0), period(0, start_min=30, end_min=30)
    target = plan((first, overlap), (assignment(1, 1, 1, {1, 2}, 120),))
    state = scope_state(target, (first, overlap))
    force(state, ((1, first), (1, overlap)))

    assert solve(state.model) == cp_model.INFEASIBLE


def test_an_overlap_chain_keeps_its_non_overlapping_ends_available():
    start, middle = period(0), period(0, start_min=30, end_min=30)
    end, spare = period(0, start=10, end=11), period(0, start=11, end=12)
    target = plan(
        (start, middle, end, spare),
        (
            assignment(1, 1, 1, {1}, 60),
            assignment(2, 1, 2, {2}, 60),
            assignment(3, 1, 3, {3}, 60),
        ),
    )
    state = scope_state(target, (start, middle, end, spare))
    force(state, ((1, start), (3, end)))

    assert feasible(state.model)


def test_resource_exclusivity_groups_identical_intervals_into_one_restriction():
    from app.scheduler.infrastructure.placement_model import _add_resource_exclusivity

    when = period(0)
    model = cp_model.CpModel()
    first, second, third = (model.NewBoolVar(name) for name in ("a", "b", "c"))
    _add_resource_exclusivity(model, [(when, first), (when, second), (when, third)])

    assert len(model.Proto().constraints) == 1


def test_resource_exclusivity_keeps_repeated_fixed_occupancies_conflicting():
    from app.scheduler.infrastructure.placement_model import _add_resource_exclusivity

    when = period(0)
    model = cp_model.CpModel()
    _add_resource_exclusivity(model, [(when, 1), (when, 1)])

    assert solve(model) == cp_model.INFEASIBLE


def test_resource_exclusivity_allows_the_ends_of_an_overlap_chain():
    from app.scheduler.infrastructure.placement_model import _add_resource_exclusivity

    start, middle, end = (
        period(0),
        period(0, start_min=30, end_min=30),
        period(0, start=10, end=11),
    )
    model = cp_model.CpModel()
    first, second, third = (model.NewBoolVar(name) for name in ("a", "b", "c"))
    _add_resource_exclusivity(model, [(start, first), (middle, second), (end, third)])
    model.Add(first == 1)
    model.Add(third == 1)

    assert feasible(model)


def test_placement_forbids_a_successor_before_its_predecessor():
    periods = (period(0, start=9, end=10), period(0, start=10, end=11))
    source = assignment(1, 1, 1, {1}, 60)
    successor = assignment(2, 2, 2, {2}, 60)
    target = replace(snapshot(periods), assignments=(source, successor), precedences=((1, 2),))
    state = scope_state(target, periods)
    state.model.Add(state.x[(2, periods[0])] == 1)
    state.model.Add(state.x[(1, periods[1])] == 1)

    assert solve(state.model) == cp_model.INFEASIBLE


def test_room_optimization_preserves_a_protected_room_and_uses_an_alternative():
    when = period(0)
    target = plan(
        (when,),
        (assignment(1, 1, 1, {1}, 60), assignment(2, 2, 2, {1, 2, 3}, 60)),
        protected_lessons=(lesson(1, 1, when, 1),),
    )
    candidate = CandidateSchedule((lesson(1, 1, when, 1), lesson(2, 2, when, 2)))

    optimized, _ = _optimize_rooms(
        target, candidate, deadline=monotonic() + 30, num_workers=1, random_seed=1
    )

    rooms = {row.lesson_id: row.room_id for row in optimized.lessons}
    assert rooms[1] == 1
    assert rooms[2] in {2, 3}
    assert validate_candidate(target, optimized).valid


def test_room_optimization_separates_partially_overlapping_mobile_lessons():
    first, overlap = period(0), period(0, start_min=30, end_min=30)
    target = plan(
        (first, overlap),
        (
            assignment(1, 1, 1, {1, 2}, 60),
            assignment(2, 2, 2, {1, 2}, 60),
        ),
    )
    candidate = CandidateSchedule((lesson(1, 1, first, 1), lesson(2, 2, overlap, 1)))

    optimized, _ = _optimize_rooms(
        target, candidate, deadline=monotonic() + 30, num_workers=1, random_seed=1
    )

    rooms = {row.lesson_id: row.room_id for row in optimized.lessons}
    assert rooms[1] != rooms[2]
    assert validate_candidate(target, optimized).valid


def test_room_optimization_cannot_fix_a_conflict_between_two_fixed_occupancies():
    first, overlap = period(0), period(0, start_min=30, end_min=30)
    target = plan(
        (first, overlap),
        (
            assignment(1, 1, 1, {1}, 60),
            assignment(2, 2, 2, {1}, 60),
            assignment(3, 3, 3, {2}, 60),
            assignment(4, 4, 4, {3, 4}, 60),
        ),
        protected_lessons=(lesson(1, 1, first, 1), lesson(2, 2, overlap, 1)),
    )
    candidate = CandidateSchedule(
        (
            lesson(1, 1, first, 1),
            lesson(2, 2, overlap, 1),
            lesson(3, 3, overlap, 2),
            lesson(4, 4, overlap, 3),
        )
    )

    optimized, record = _optimize_rooms(
        target, candidate, deadline=monotonic() + 30, num_workers=1, random_seed=1
    )

    assert record.proven is False
    assert optimized == candidate
