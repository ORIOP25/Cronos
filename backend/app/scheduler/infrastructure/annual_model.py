"""Annual quota relaxation for CompleteGeneration (tech spec 8.3).

The model distributes each assignment residual over school weeks and concrete
period durations. It is a relaxation of the detailed placement: it proves
aggregate deficits and supplies candidate distributions. Exact credit,
partial-credit waste and the final week of each assignment are modelled.

A distribution is a complete description of one subproblem: the positive period
counts, the final ``(week, duration)`` group that carries the partial lesson and
the waste minutes. Absent groups mean zero periods. The detailed placement must
materialize exactly that description.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from time import monotonic
from types import MappingProxyType
from typing import Any

from ortools.sat.python import cp_model

from app.scheduler.domain.calendar import Period
from app.scheduler.domain.candidate import PlanningSnapshot
from app.scheduler.domain.capacity import eligible_periods, residual_minutes
from app.scheduler.infrastructure import diagnostics

STATUS_FEASIBLE = "FEASIBLE"
STATUS_INFEASIBLE = "INFEASIBLE"
STATUS_INCONCLUSIVE = "INCONCLUSIVE"
PROVEN_SCOPE = "ANNUAL_QUOTA_RELAXATION"

QuotaKey = tuple[int, int, int]
FinalGroup = tuple[int, int]


def week_index(origin: date, period: Period) -> int:
    if type(origin) is not date:
        raise ValueError("The scheduling origin must be a date.")
    return (period.school_date - origin).days // 7


@dataclass(frozen=True)
class QuotaDistribution:
    """Physical period counts and the final partial group per assignment."""

    counts: Mapping[QuotaKey, int]
    final_groups: Mapping[int, FinalGroup]

    def __post_init__(self) -> None:
        frozen = {}
        for key, value in self.counts.items():
            if (
                type(key) is not tuple
                or len(key) != 3
                or any(type(part) is not int for part in key)
            ):
                raise ValueError("Quota keys are assignment, week and duration integers.")
            if type(value) is not int or value <= 0:
                raise ValueError("Quota counts must be positive integers.")
            frozen[key] = value
        finals: dict[int, FinalGroup] = {}
        for assignment_id, group in self.final_groups.items():
            if (
                type(assignment_id) is not int
                or type(group) is not tuple
                or len(group) != 2
                or any(type(part) is not int for part in group)
            ):
                raise ValueError("Final groups are assignment to (week, duration) values.")
            if frozen.get((assignment_id, group[0], group[1]), 0) <= 0:
                raise ValueError("A final group needs a positive quota.")
            finals[assignment_id] = group
        object.__setattr__(self, "counts", MappingProxyType(frozen))
        object.__setattr__(self, "final_groups", MappingProxyType(finals))

    def key(self) -> tuple[tuple[Any, ...], ...]:
        rows = [
            (assignment_id, week, duration, count, None)
            for (assignment_id, week, duration), count in sorted(self.counts.items())
        ]
        for assignment_id, (week, duration) in sorted(self.final_groups.items()):
            rows.append((assignment_id, week, duration, None, "final"))
        return tuple(rows)

    def total_physical_minutes(self) -> int:
        return sum(duration * count for (_, _, duration), count in self.counts.items())

    def assignment_physical_minutes(self, assignment_id: int) -> int:
        return sum(
            duration * count
            for (owner, _, duration), count in self.counts.items()
            if owner == assignment_id
        )


@dataclass(frozen=True)
class AnnualPlan:
    status: str
    distribution: QuotaDistribution | None
    latest_week: int | None
    latest_week_bound: int | None
    waste_minutes: int
    latest_week_proven: bool
    wall_time_seconds: float
    statistics: Mapping[str, int]
    proven_scope: str = PROVEN_SCOPE


def _availability_minutes(
    demands,
    origin: date,
) -> tuple[
    dict[tuple[str, int, int], int],
    dict[tuple[int, int], int],
]:
    """Union of eligible period minutes per class/teacher, room and week.

    Reuses the periods already computed for the demand groups instead of
    recomputing the joint eligibility intersection a second time. Every eligible
    room of every assignment contributes, so a shared room set has a physical
    capacity bound instead of being treated as unlimited.
    """
    available: dict[tuple[str, int, int], set[tuple]] = defaultdict(set)
    room_available: dict[tuple[int, int], set[tuple]] = defaultdict(set)
    for assignment, _remaining, groups in demands:
        for (week, _duration), rows in groups.items():
            for period in rows:
                row = (period.start_utc, period.end_utc, period.duration_minutes)
                available[("class", assignment.class_id, week)].add(row)
                available[("teacher", assignment.teacher_id, week)].add(row)
                for room_id in assignment.eligible_room_ids:
                    room_available[(room_id, week)].add(row)
    return (
        {key: sum(row[2] for row in rows) for key, rows in sorted(available.items())},
        {key: sum(row[2] for row in rows) for key, rows in sorted(room_available.items())},
    )


def _counts(q: Mapping[QuotaKey, Any], solver: cp_model.CpSolver) -> dict[QuotaKey, int]:
    return {
        key: solver.Value(variable) for key, variable in q.items() if solver.Value(variable) > 0
    }


def _greedy_hint(
    demands: list,
    available: Mapping[tuple[str, int, int], int],
    room_minutes: Mapping[tuple[int, int], int],
) -> tuple[dict[QuotaKey, int], dict[QuotaKey, int], dict[QuotaKey, int], dict[int, int]] | None:
    """Earliest-week feasible starting point so the relaxation does not stall."""
    used: dict[tuple[str, int, int], int] = defaultdict(int)
    used_room: dict[tuple[int, int], int] = defaultdict(int)

    def headroom(assignment, week: int, duration: int) -> bool:
        if used[("class", assignment.class_id, week)] + duration > available.get(
            ("class", assignment.class_id, week), 0
        ):
            return False
        if used[("teacher", assignment.teacher_id, week)] + duration > available.get(
            ("teacher", assignment.teacher_id, week), 0
        ):
            return False
        if len(assignment.eligible_room_ids) == 1:
            room_id = next(iter(assignment.eligible_room_ids))
            if used_room[(room_id, week)] + duration > room_minutes.get((room_id, week), 0):
                return False
        return True

    def reserve(assignment, week: int, duration: int, times: int) -> None:
        minutes = duration * times
        used[("class", assignment.class_id, week)] += minutes
        used[("teacher", assignment.teacher_id, week)] += minutes
        if len(assignment.eligible_room_ids) == 1:
            room_id = next(iter(assignment.eligible_room_ids))
            used_room[(room_id, week)] += minutes

    q: dict[QuotaKey, int] = {}
    final: dict[QuotaKey, int] = {}
    waste: dict[QuotaKey, int] = {}
    last_weeks: dict[int, int] = {}
    for assignment, remaining, groups in demands:
        need = remaining
        chosen: dict[tuple[int, int], int] = {}
        final_group: tuple[int, int] | None = None
        for (week, duration), rows in sorted(groups.items()):
            capacity = len(rows)
            while chosen.get((week, duration), 0) < capacity and need >= duration:
                if not headroom(assignment, week, duration):
                    break
                chosen[(week, duration)] = chosen.get((week, duration), 0) + 1
                reserve(assignment, week, duration, 1)
                need -= duration
                final_group = (week, duration)
        if need > 0:
            for (week, duration), rows in sorted(groups.items()):
                if final_group is not None and week < final_group[0]:
                    continue
                if chosen.get((week, duration), 0) >= len(rows):
                    continue
                if not headroom(assignment, week, duration):
                    continue
                chosen[(week, duration)] = chosen.get((week, duration), 0) + 1
                reserve(assignment, week, duration, 1)
                waste[(assignment.assignment_id, week, duration)] = duration - need
                need = 0
                final_group = (week, duration)
                break
        if need > 0 or final_group is None:
            return None
        for (week, duration), count in chosen.items():
            q[(assignment.assignment_id, week, duration)] = count
        final[(assignment.assignment_id, final_group[0], final_group[1])] = 1
        last_weeks[assignment.assignment_id] = final_group[0]
    return q, final, waste, last_weeks


def _impose_room_set_capacity(
    model: cp_model.CpModel,
    room_set_terms: Mapping[tuple[frozenset[int], int], list[Any]],
    room_minutes: Mapping[tuple[int, int], int],
) -> int:
    """Necessary capacity bound per eligible room set and week.

    For every distinct eligible room set ``E`` (and the global set), the minutes
    any subset of ``E`` may consume in a week cannot exceed the physical minutes
    of the rooms in ``E``. This is Hall's necessary condition for matching
    assignments to rooms; an over-counted capacity only weakens the bound, so a
    viable distribution is never cut.
    """
    if not room_set_terms:
        return 0
    room_sets = {rooms for rooms, _week in room_set_terms}
    weeks = {week for _rooms, week in room_set_terms}
    global_rooms = frozenset().union(*room_sets)
    targets = set(room_sets)
    targets.add(global_rooms)
    imposed = 0
    for target in sorted(targets, key=lambda rooms: (len(rooms), sorted(rooms))):
        for week in sorted(weeks):
            terms = [
                term
                for (rooms, term_week), group in room_set_terms.items()
                if term_week == week and rooms <= target
                for term in group
            ]
            if not terms:
                continue
            capacity = sum(room_minutes.get((room_id, week), 0) for room_id in target)
            model.Add(sum(terms) <= capacity)
            imposed += 1
    return imposed


def plan_annual_quotas(
    snapshot: PlanningSnapshot,
    periods: tuple[Period, ...],
    *,
    excluded: Iterable[QuotaDistribution] = (),
    latest_week_limit: int | None = None,
    time_limit_seconds: float = 10.0,
    num_workers: int = 1,
    random_seed: int = 1,
    stop_at_first_complete: bool = False,
) -> AnnualPlan:
    """Plan a weekly quota distribution, excluding proven-infeasible ones."""
    if type(snapshot) is not PlanningSnapshot:
        raise ValueError("Annual planning needs a planning snapshot.")
    if time_limit_seconds <= 0:
        raise ValueError("The time limit must be positive.")
    if num_workers < 1:
        raise ValueError("At least one worker is required.")
    start = monotonic()
    deadline = start + time_limit_seconds

    demands = []
    for assignment in snapshot.assignments:
        if monotonic() >= deadline:
            return AnnualPlan(
                STATUS_INCONCLUSIVE,
                None,
                None,
                None,
                0,
                False,
                monotonic() - start,
                {"variables": 0},
            )
        remaining = residual_minutes(snapshot, assignment.assignment_id)
        if remaining <= 0:
            continue
        eligible = eligible_periods(snapshot, assignment, periods)
        if not eligible:
            return AnnualPlan(
                STATUS_INFEASIBLE,
                None,
                None,
                None,
                0,
                True,
                monotonic() - start,
                {"variables": 0},
            )
        groups: dict[tuple[int, int], list[Period]] = defaultdict(list)
        for period in eligible:
            groups[(week_index(snapshot.origin, period), period.duration_minutes)].append(period)
        demands.append((assignment, remaining, dict(groups)))

    build_start = monotonic()
    diagnostics.phase_started("ANNUAL")
    model = cp_model.CpModel()
    q: dict[QuotaKey, Any] = {}
    final: dict[QuotaKey, Any] = {}
    waste: dict[QuotaKey, Any] = {}
    last_week_vars: list[Any] = []
    last_week_by_assignment: dict[int, Any] = {}
    load_terms: dict[tuple[str, int, int], list[Any]] = defaultdict(list)
    room_set_terms: dict[tuple[frozenset[int], int], list[Any]] = defaultdict(list)
    max_week = max((week for _, _, groups in demands for week, _ in groups), default=0)
    for assignment, remaining, groups in demands:
        if monotonic() >= deadline:
            return AnnualPlan(
                STATUS_INCONCLUSIVE,
                None,
                None,
                None,
                0,
                False,
                monotonic() - start,
                {"variables": len(model.Proto().variables)},
            )
        for (week, duration), rows in sorted(groups.items()):
            key = (assignment.assignment_id, week, duration)
            capacity = len(rows)
            q[key] = model.NewIntVar(0, capacity, f"q_{key}")
            final[key] = model.NewBoolVar(f"f_{key}")
            waste[key] = model.NewIntVar(0, duration - 1, f"u_{key}")
            model.Add(q[key] >= final[key])
            model.Add(waste[key] <= (duration - 1) * final[key])
            load_terms[("class", assignment.class_id, week)].append(duration * q[key])
            load_terms[("teacher", assignment.teacher_id, week)].append(duration * q[key])
            room_set_terms[(assignment.eligible_room_ids, week)].append(duration * q[key])
        keys = sorted((assignment.assignment_id, week, duration) for week, duration in groups)
        model.Add(sum(final[key] for key in keys) == 1)
        model.Add(sum(key[2] * q[key] - waste[key] for key in keys) == remaining)
        last_week = model.NewIntVar(0, max_week, f"last_week_{assignment.assignment_id}")
        model.Add(last_week == sum(key[1] * final[key] for key in keys))
        last_week_vars.append(last_week)
        last_week_by_assignment[assignment.assignment_id] = last_week
        for (week, duration), rows in sorted(groups.items()):
            after = model.NewBoolVar(f"after_{assignment.assignment_id}_{week}_{duration}")
            model.Add(week >= last_week + 1).OnlyEnforceIf(after)
            model.Add(week <= last_week).OnlyEnforceIf(after.Not())
            capacity = len(rows)
            key = (assignment.assignment_id, week, duration)
            model.Add(q[key] + capacity * after <= capacity)

    available, room_minutes = _availability_minutes(demands, snapshot.origin)
    for key, minutes in sorted(available.items()):
        terms = load_terms.get(key)
        if terms:
            model.Add(sum(terms) <= minutes)
    room_set_constraints = _impose_room_set_capacity(model, room_set_terms, room_minutes)

    hint = _greedy_hint(demands, available, room_minutes)
    if hint is not None:
        hint_q, hint_final, hint_waste, hint_weeks = hint
        for key, variable in q.items():
            model.AddHint(variable, hint_q.get(key, 0))
        for key, variable in final.items():
            model.AddHint(variable, hint_final.get(key, 0))
        for key, variable in waste.items():
            model.AddHint(variable, hint_waste.get(key, 0))
        for assignment_id, variable in last_week_by_assignment.items():
            model.AddHint(variable, hint_weeks[assignment_id])

    for distribution in excluded:
        matches = []
        # Zero counts also condition the subproblem: extra short periods may
        # replace credit in the final period without changing positive counts.
        for key, variable in q.items():
            if key not in distribution.counts:
                match = model.NewBoolVar(f"cut_zero_{key}")
                model.Add(variable == 0).OnlyEnforceIf(match)
                model.Add(variable != 0).OnlyEnforceIf(match.Not())
                matches.append(match)
        for assignment_id, week, duration, count, final_marker in distribution.key():
            key = (assignment_id, week, duration)
            if key not in q:
                raise ValueError("An excluded distribution does not belong to the snapshot.")
            if final_marker == "final":
                match = model.NewBoolVar(f"cut_final_{key}")
                model.Add(final[key] == 1).OnlyEnforceIf(match)
                model.Add(final[key] == 0).OnlyEnforceIf(match.Not())
            else:
                match = model.NewBoolVar(f"cut_{key}")
                model.Add(q[key] == count).OnlyEnforceIf(match)
                model.Add(q[key] != count).OnlyEnforceIf(match.Not())
            matches.append(match)
        if matches:
            model.Add(sum(matches) <= len(matches) - 1)

    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = num_workers
    solver.parameters.random_seed = random_seed
    solver.parameters.stop_after_first_solution = stop_at_first_complete
    latest = model.NewIntVar(0, max_week, "latest_week")
    if last_week_vars:
        model.AddMaxEquality(latest, last_week_vars)
    else:
        model.Add(latest == 0)
    if latest_week_limit is not None:
        if type(latest_week_limit) is not int or latest_week_limit < 0:
            raise ValueError("The latest-week limit must be a nonnegative integer.")
        model.Add(latest <= latest_week_limit)
    model.Minimize(latest)
    diagnostics.model_built("ANNUAL", model)
    statistics = {
        "variables": len(model.Proto().variables),
        "build_ms": int((monotonic() - build_start) * 1000),
        "solve_ms": 0,
        "room_set_constraints": room_set_constraints,
    }
    solve_start = monotonic()
    diagnostics.phase_started("ANNUAL", stage="LATEST_WEEK")
    solver.parameters.max_time_in_seconds = max(0.0, deadline - monotonic())
    status = solver.Solve(model)
    diagnostics.phase_finished(
        "ANNUAL",
        stage="LATEST_WEEK",
        started_at=solve_start,
        status=solver.StatusName(status),
    )
    statistics["solve_ms"] += int((monotonic() - solve_start) * 1000)
    if status == cp_model.INFEASIBLE:
        diagnostics.phase_finished("ANNUAL", started_at=start, status=STATUS_INFEASIBLE)
        return AnnualPlan(
            STATUS_INFEASIBLE, None, None, None, 0, True, monotonic() - start, statistics
        )
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        diagnostics.phase_finished("ANNUAL", started_at=start, status=STATUS_INCONCLUSIVE)
        return AnnualPlan(
            STATUS_INCONCLUSIVE, None, None, None, 0, False, monotonic() - start, statistics
        )
    latest_value = int(solver.ObjectiveValue())
    latest_proven = status == cp_model.OPTIMAL
    bound_value = math.ceil(solver.BestObjectiveBound())
    counts = _counts(q, solver)
    finals = {
        assignment_id: (week, duration)
        for (assignment_id, week, duration), variable in final.items()
        if solver.Value(variable)
    }
    waste_minutes = sum(solver.Value(variable) for variable in waste.values())
    model.Add(latest == latest_value)
    model.Minimize(sum(waste.values()) if waste else 0)
    remaining_time = deadline - monotonic()
    if remaining_time > 0 and not stop_at_first_complete:
        solve_start = monotonic()
        diagnostics.phase_started("ANNUAL", stage="WASTE")
        solver.parameters.max_time_in_seconds = remaining_time
        status = solver.Solve(model)
        diagnostics.phase_finished(
            "ANNUAL", stage="WASTE", started_at=solve_start, status=solver.StatusName(status)
        )
        statistics["solve_ms"] += int((monotonic() - solve_start) * 1000)
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            counts = _counts(q, solver)
            finals = {
                assignment_id: (week, duration)
                for (assignment_id, week, duration), variable in final.items()
                if solver.Value(variable)
            }
            waste_minutes = sum(solver.Value(variable) for variable in waste.values())
    diagnostics.phase_finished("ANNUAL", started_at=start, status=STATUS_FEASIBLE)
    return AnnualPlan(
        STATUS_FEASIBLE,
        QuotaDistribution(counts, finals),
        latest_value,
        bound_value,
        waste_minutes,
        latest_proven,
        monotonic() - start,
        statistics,
    )
