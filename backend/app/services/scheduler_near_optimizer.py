from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, time
from math import ceil
from typing import Any

from ortools.sat.python import cp_model

from app.services.scheduler_candidates import CandidateUniverse, PlacementCandidate
from app.services.scheduler_complete_demand import CompleteDemandLedger


@dataclass(frozen=True)
class NearFutureResult:
    selected: tuple[PlacementCandidate, ...]
    status: str
    scheduled_blocks: int
    target_blocks: int
    metrics: dict[str, int | float]


class NearFutureOptimizer:
    def optimize(
        self,
        universe: CandidateUniverse,
        ledger: CompleteDemandLedger,
        snapshot: dict[str, Any],
        *,
        max_seconds: float,
    ) -> NearFutureResult:
        if not universe.is_usable or max_seconds <= 0:
            return NearFutureResult((), "infeasible", 0, 0, {})
        candidates = universe.candidates
        model = cp_model.CpModel()
        variables = {
            candidate.candidate_key: model.NewBoolVar(
                f"x_{index}"
            )
            for index, candidate in enumerate(candidates)
        }
        self._add_resource_intervals(model, candidates, variables)
        self._add_lunch_constraints(model, candidates, variables, snapshot)

        minimum_duration = min(row.duration_minutes for row in candidates)
        target_by_demand = {
            (item.class_id, item.subject_id): sum(
                ceil(module.required_minutes / minimum_duration)
                for module in item.modules
            )
            for item in ledger.items
        }
        demand_vars: dict[tuple[int, int], list[cp_model.IntVar]] = defaultdict(list)
        for candidate in candidates:
            demand_vars[(candidate.class_id, candidate.subject_id)].append(
                variables[candidate.candidate_key]
            )
        for key, target in target_by_demand.items():
            model.Add(sum(demand_vars.get(key, ())) <= target)

        total = sum(variables.values())
        solver = self._solver(max_seconds / 3)
        model.Maximize(total)
        status = solver.Solve(model)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return NearFutureResult(
                (), "infeasible", 0, sum(target_by_demand.values()), {}
            )
        best_total = int(round(solver.ObjectiveValue()))
        best_values = {
            key: solver.Value(variable) for key, variable in variables.items()
        }
        model.Add(total == best_total)
        self._hint(model, variables, solver)

        first_date = min(row.output_date for row in candidates)
        date_cost = sum(
            (candidate.output_date - first_date).days
            * variables[candidate.candidate_key]
            for candidate in candidates
        )
        model.Minimize(date_cost)
        solver = self._solver(max_seconds / 3)
        status = solver.Solve(model)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return self._result_from_values(
                candidates,
                best_values,
                target_blocks=sum(target_by_demand.values()),
                status="feasible",
                metrics={"scheduled_blocks": best_total, "optimization_stages": 1},
            )
        best_date_cost = int(round(solver.ObjectiveValue()))
        best_values = {
            key: solver.Value(variable) for key, variable in variables.items()
        }
        model.Add(date_cost == best_date_cost)
        self._hint(model, variables, solver)

        class_targets: dict[int, int] = defaultdict(int)
        class_selected: dict[int, list[cp_model.IntVar]] = defaultdict(list)
        for (class_id, _subject_id), target in target_by_demand.items():
            class_targets[class_id] += target
        for candidate in candidates:
            class_selected[candidate.class_id].append(variables[candidate.candidate_key])
        minimum_coverage = model.NewIntVar(0, 1000, "minimum_class_coverage")
        for class_id, target in class_targets.items():
            model.Add(sum(class_selected[class_id]) * 1000 >= minimum_coverage * target)
        preference = sum(
            candidate.availability_score * variables[candidate.candidate_key]
            for candidate in candidates
        )
        room_used: dict[tuple[int, int, int], cp_model.IntVar] = {}
        room_candidates: dict[tuple[int, int, int], list[cp_model.IntVar]] = defaultdict(list)
        daily_class: dict[tuple[int, date], list[cp_model.IntVar]] = defaultdict(list)
        for candidate in candidates:
            variable = variables[candidate.candidate_key]
            room_candidates[
                (candidate.class_id, candidate.subject_id, candidate.room_id)
            ].append(variable)
            daily_class[(candidate.class_id, candidate.output_date)].append(variable)
        for index, (key, room_variables) in enumerate(room_candidates.items()):
            used = model.NewBoolVar(f"room_used_{index}")
            model.AddMaxEquality(used, room_variables)
            room_used[key] = used
        overloads = []
        for index, daily_variables in enumerate(daily_class.values()):
            overload = model.NewIntVar(0, len(daily_variables), f"daily_overload_{index}")
            model.Add(overload >= sum(daily_variables) - 4)
            overloads.append(overload)
        quality_range = len(candidates) * 12 + len(room_used) + 1
        model.Maximize(
            minimum_coverage * quality_range
            + preference
            - sum(room_used.values())
            - sum(overloads) * 3
        )
        solver = self._solver(max_seconds / 3)
        status = solver.Solve(model)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return self._result_from_values(
                candidates,
                best_values,
                target_blocks=sum(target_by_demand.values()),
                status="feasible",
                metrics={
                    "scheduled_blocks": best_total,
                    "date_cost": best_date_cost,
                    "optimization_stages": 2,
                },
            )
        values = {key: solver.Value(variable) for key, variable in variables.items()}
        return self._result_from_values(
            candidates,
            values,
            target_blocks=sum(target_by_demand.values()),
            status="optimal" if status == cp_model.OPTIMAL else "feasible",
            metrics={
                "target_blocks": sum(target_by_demand.values()),
                "date_cost": best_date_cost,
                "minimum_class_coverage_per_mille": solver.Value(minimum_coverage),
                "rooms_used": sum(solver.Value(value) for value in room_used.values()),
                "daily_overload_blocks": sum(solver.Value(value) for value in overloads),
                "solver_wall_seconds": round(solver.WallTime(), 4),
                "optimization_stages": 3,
            },
        )

    @staticmethod
    def _result_from_values(
        candidates: tuple[PlacementCandidate, ...],
        values: dict[str, int],
        *,
        target_blocks: int,
        status: str,
        metrics: dict[str, int | float],
    ) -> NearFutureResult:
        selected = tuple(
            sorted(
                (
                    candidate
                    for candidate in candidates
                    if values.get(candidate.candidate_key, 0)
                ),
                key=lambda row: (
                    row.output_date,
                    row.start_minute,
                    row.class_id,
                    row.subject_id,
                    row.room_id,
                ),
            )
        )
        result_metrics = dict(metrics)
        result_metrics["scheduled_blocks"] = len(selected)
        result_metrics["preference_score"] = sum(
            row.availability_score for row in selected
        )
        return NearFutureResult(
            selected=selected,
            status=status,
            scheduled_blocks=len(selected),
            target_blocks=target_blocks,
            metrics=result_metrics,
        )

    @staticmethod
    def _add_resource_intervals(
        model: cp_model.CpModel,
        candidates: tuple[PlacementCandidate, ...],
        variables: dict[str, cp_model.IntVar],
    ) -> None:
        grouped: dict[tuple[str, int, date], list[cp_model.IntervalVar]] = defaultdict(list)
        for index, candidate in enumerate(candidates):
            variable = variables[candidate.candidate_key]
            for kind, resource_id in (
                ("class", candidate.class_id),
                ("teacher", candidate.teacher_id),
                ("room", candidate.room_id),
            ):
                grouped[(kind, resource_id, candidate.output_date)].append(
                    model.NewOptionalFixedSizeIntervalVar(
                        candidate.start_minute,
                        candidate.duration_minutes,
                        variable,
                        f"{kind}_{index}",
                    )
                )
        for intervals in grouped.values():
            if len(intervals) > 1:
                model.AddNoOverlap(intervals)

    def _add_lunch_constraints(
        self,
        model: cp_model.CpModel,
        candidates: tuple[PlacementCandidate, ...],
        variables: dict[str, cp_model.IntVar],
        snapshot: dict[str, Any],
    ) -> None:
        rule = snapshot.get("lunch_rules")
        if not rule or not rule.get("window_start") or not rule.get("window_end"):
            return
        lunch_start = self._minute(rule["window_start"])
        lunch_end = self._minute(rule["window_end"])
        minimum = int(rule.get("minimum_minutes") or 0)
        starts = sorted(
            {
                lunch_start,
                *(row.end_minute for row in candidates if lunch_start <= row.end_minute <= lunch_end),
            }
        )
        starts = [start for start in starts if start + minimum <= lunch_end]
        if minimum <= 0 or not starts:
            return
        grouped: dict[tuple[str, int, date], list[PlacementCandidate]] = defaultdict(list)
        for candidate in candidates:
            grouped[("class", candidate.class_id, candidate.output_date)].append(candidate)
            grouped[("teacher", candidate.teacher_id, candidate.output_date)].append(candidate)
        for group_index, rows in enumerate(grouped.values()):
            choices = [
                model.NewBoolVar(f"lunch_{group_index}_{index}")
                for index in range(len(starts))
            ]
            model.AddExactlyOne(choices)
            for choice, break_start in zip(choices, starts):
                break_end = break_start + minimum
                for candidate in rows:
                    if (
                        candidate.start_minute < break_end
                        and candidate.end_minute > break_start
                    ):
                        model.Add(
                            variables[candidate.candidate_key] + choice <= 1
                        )

    @staticmethod
    def _solver(seconds: float) -> cp_model.CpSolver:
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = max(0.05, seconds)
        solver.parameters.num_search_workers = 1
        solver.parameters.random_seed = 0
        return solver

    @staticmethod
    def _hint(
        model: cp_model.CpModel,
        variables: dict[str, cp_model.IntVar],
        solver: cp_model.CpSolver,
    ) -> None:
        model.ClearHints()
        for variable in variables.values():
            model.AddHint(variable, solver.Value(variable))

    @staticmethod
    def _minute(value: str | time) -> int:
        parsed = value if isinstance(value, time) else time.fromisoformat(value)
        return parsed.hour * 60 + parsed.minute
