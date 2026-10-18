"""Final-lesson encoding and model lifetime of the exact placement (scheduler v1).

The last window must keep one final lesson per assignment, every placed lesson
no later than that final lesson, and the partial waste on the final lesson only.
The encoding must stay linear in the number of eligible periods, and each
window's model must be released before the next window is built.
"""

from __future__ import annotations

import gc
import itertools
import weakref
from datetime import date, time, timedelta
from math import comb

from ortools.sat.python import cp_model

from app.scheduler.domain.calendar import normalize_period
from app.scheduler.domain.candidate import SchedulingStrategy
from app.scheduler.infrastructure import placement_model
from app.scheduler.infrastructure.annual_model import QuotaDistribution, plan_annual_quotas
from app.scheduler.lab.fixtures import AssignmentSpec, FixtureSpec, build_snapshot

TZ = "Europe/Lisbon"
ORIGIN = date(2026, 9, 21)
ASSIGNMENT_ID = 1


def _snapshot(periods, module_minutes):
    """One class, one teacher and one room over the given (date, start, end) periods."""
    grid = tuple(dict.fromkeys((day.weekday(), start, end) for day, start, end in periods))
    return build_snapshot(
        FixtureSpec(
            strategy=SchedulingStrategy.COMPLETE_GENERATION,
            origin=ORIGIN,
            preferred_end_date=date(2026, 12, 31),
            hard_end_date=date(2027, 1, 31),
            timezone_name=TZ,
            grid_slots=grid,
            periods=tuple(periods),
            assignments=(AssignmentSpec(1, 7, module_minutes, (500,)),),
        )
    )


def _periods(rows):
    return tuple(normalize_period(day, start, end, TZ) for day, start, end in rows)


def _consecutive_day_periods(count):
    return tuple((ORIGIN + timedelta(days=offset), time(9), time(10)) for offset in range(count))


def _linear_references(model):
    return sum(
        len(constraint.linear.vars)
        for constraint in model.Proto().constraints
        if constraint.has_linear()
    )


def _placement_periods(scope):
    return scope.assignments[ASSIGNMENT_ID].periods


def _expected_solutions(durations, credit_target, *, final_mask, groups=None, waste_target=None):
    """The window rule, enumerated over every placement, last index and waste value.

    Each solution is a tuple of (placed, last, waste) per period, in chronological order.
    """
    count = len(durations)
    expected = set()
    for placed in itertools.product((0, 1), repeat=count):
        if not any(placed):
            continue
        if groups is not None and any(
            sum(p for d, p in zip(durations, placed, strict=True) if d == duration) != quota
            for duration, quota in groups.items()
        ):
            continue
        physical = sum(d for d, p in zip(durations, placed, strict=True) if p)
        for last in range(count):
            if not placed[last] or not final_mask[last]:
                continue
            if any(placed[index] for index in range(last + 1, count)):
                continue
            for waste in range(durations[last]):
                if physical - waste != credit_target:
                    continue
                if waste_target is not None and waste != waste_target:
                    continue
                expected.add(
                    tuple(
                        (p, int(index == last), waste if index == last else 0)
                        for index, p in enumerate(placed)
                    )
                )
    return expected


class _SolutionCollector(cp_model.CpSolverSolutionCallback):
    def __init__(self, state, keys):
        super().__init__()
        self._state = state
        self._keys = keys
        self.solutions = set()

    def on_solution_callback(self):
        projected = []
        for key in self._keys:
            last = self._state.last.get(key)
            waste = self._state.waste.get(key)
            projected.append(
                (
                    self.Value(self._state.x[key]),
                    self.Value(last) if last is not None else 0,
                    self.Value(waste) if waste is not None else 0,
                )
            )
        self.solutions.add(tuple(projected))


def _enumerate(state, keys):
    solver = cp_model.CpSolver()
    solver.parameters.enumerate_all_solutions = True
    solver.parameters.num_workers = 1
    collector = _SolutionCollector(state, keys)
    status = solver.Solve(state.model, collector)
    assert status == cp_model.OPTIMAL
    return collector.solutions


def test_final_lesson_encoding_grows_linearly_with_eligible_periods():
    """R1: the reference count for 2N periods stays near twice the count for N."""

    def references(count):
        rows = _consecutive_day_periods(count)
        snapshot = _snapshot(rows, (90,))
        scope = placement_model._unrestricted_scope(snapshot, _periods(rows))
        return _linear_references(placement_model._build_scope_state(snapshot, scope).model)

    small = references(40)
    large = references(80)

    assert large <= 2.5 * small, (small, large)


def test_unrestricted_final_lesson_solutions_match_the_window_rule():
    """R2: a partial final lesson, unrestricted scope, 2 to 5 periods."""
    for count in range(2, 6):
        rows = _consecutive_day_periods(count)
        snapshot = _snapshot(rows, (90,))
        scope = placement_model._unrestricted_scope(snapshot, _periods(rows))
        state = placement_model._build_scope_state(snapshot, scope)
        keys = [(ASSIGNMENT_ID, period) for period in _placement_periods(scope)]

        expected = _expected_solutions([60] * count, 90, final_mask=[True] * count)

        assert len(expected) == comb(count, 2)
        assert _enumerate(state, keys) == expected


def test_distribution_final_group_and_quota_solutions_match_the_window_rule():
    """R2: final-duration domain and the quota groups branch in one window.

    The 60-minute final group restricts the last lesson, and the quota needs one
    30-minute and one 60-minute lesson. Waste is 30 minutes on the final lesson.
    """
    periods = (
        (ORIGIN, time(9), time(9, 30)),
        (ORIGIN, time(9, 30), time(10, 30)),
        (ORIGIN, time(10, 30), time(11)),
        (ORIGIN, time(11), time(12)),
    )
    snapshot = _snapshot(periods, (60,))
    periods = _periods(periods)
    distribution = QuotaDistribution(
        counts={(ASSIGNMENT_ID, 0, 60): 1, (ASSIGNMENT_ID, 0, 30): 1},
        final_groups={ASSIGNMENT_ID: (0, 60)},
    )
    (scope,) = placement_model._window_scopes(snapshot, periods, distribution)
    row = scope.assignments[ASSIGNMENT_ID]
    assert (row.credit_target, row.waste_target, row.groups) == (60, 30, ((30, 1), (60, 1)))
    state = placement_model._build_scope_state(snapshot, scope)
    keys = [(ASSIGNMENT_ID, period) for period in row.periods]
    durations = [period.duration_minutes for period in row.periods]
    final_mask = [period in row.final_periods for period in row.periods]

    expected = _expected_solutions(
        durations,
        60,
        final_mask=final_mask,
        groups={30: 1, 60: 1},
        waste_target=30,
    )

    assert len(expected) == 3
    assert _enumerate(state, keys) == expected


def test_each_window_model_is_released_before_the_next_window_is_built(monkeypatch):
    """C2: the previous window's model is garbage before the next one is built."""
    rows = ((ORIGIN, time(9), time(10)), (ORIGIN + timedelta(days=7), time(9), time(10)))
    periods = _periods(rows)
    snapshot = _snapshot(rows, (120,))
    plan = plan_annual_quotas(snapshot, periods, time_limit_seconds=5)
    assert plan.distribution is not None
    real_build = placement_model._build_scope_state
    built = []

    def build_and_check_release(snapshot, scope):
        gc.collect()
        if built:
            assert built[-1]() is None, "the previous window's model is still alive"
        state = real_build(snapshot, scope)
        built.append(weakref.ref(state))
        return state

    monkeypatch.setattr(placement_model, "_build_scope_state", build_and_check_release)

    outcome = placement_model.solve_placement(
        snapshot, periods, distribution=plan.distribution, time_limit_seconds=5
    )

    assert outcome.status == placement_model.STATUS_COMPLETE
    assert len(built) == 2
