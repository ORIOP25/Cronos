from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, time
from math import ceil
from typing import Any

from ortools.sat.python import cp_model

from app.scheduler.domain.quality import (
    QualityBlock,
    ScheduleQualityEvaluator,
    quality_policy_from_snapshot,
    quality_slots_from_snapshot,
)
from app.scheduler.infrastructure.cp_sat_quality import (
    CpSatQualityAdapter,
    SelectableQualityBlock,
)
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
            candidate.candidate_key: model.NewBoolVar(f"x_{index}")
            for index, candidate in enumerate(candidates)
        }
        items_by_key = {(item.class_id, item.subject_id): item for item in ledger.items}
        credited_minutes = {
            candidate.candidate_key: min(
                candidate.duration_minutes,
                min(
                    (
                        module.required_minutes
                        for module in items_by_key[
                            (candidate.class_id, candidate.subject_id)
                        ].modules
                        if module.required_minutes > 0
                    ),
                    default=candidate.duration_minutes,
                ),
            )
            for candidate in candidates
        }
        self._add_resource_intervals(model, candidates, variables)
        self._add_lunch_constraints(model, candidates, variables, snapshot)
        quality_evaluator = ScheduleQualityEvaluator(
            quality_policy_from_snapshot(snapshot),
            quality_slots_from_snapshot(snapshot),
            snapshot.get("lunch_rules"),
        )
        quality_rows = tuple(
            SelectableQualityBlock(
                candidate.candidate_key,
                QualityBlock(
                    class_id=candidate.class_id,
                    subject_id=candidate.subject_id,
                    teacher_id=candidate.teacher_id,
                    room_id=candidate.room_id,
                    output_date=candidate.output_date,
                    timeslot_id=candidate.timeslot_id,
                    duration_minutes=credited_minutes[candidate.candidate_key],
                    availability_tier=candidate.availability_score,
                ),
            )
            for candidate in candidates
        )
        quality_expressions = CpSatQualityAdapter(quality_evaluator).add_expressions(
            model,
            quality_rows,
            variables,
        )

        minimum_duration = min(row.duration_minutes for row in candidates)
        target_by_demand = {
            (item.class_id, item.subject_id): item.required_minutes for item in ledger.items
        }
        target_blocks = sum(ceil(item.required_minutes / minimum_duration) for item in ledger.items)
        demand_vars: dict[
            tuple[int, int],
            list[tuple[int, cp_model.IntVar]],
        ] = defaultdict(list)
        for candidate in candidates:
            demand_vars[(candidate.class_id, candidate.subject_id)].append(
                (credited_minutes[candidate.candidate_key], variables[candidate.candidate_key])
            )
        for key, target in target_by_demand.items():
            model.Add(
                sum(duration * variable for duration, variable in demand_vars.get(key, ()))
                <= target
            )

        total = sum(
            credited_minutes[candidate.candidate_key] * variables[candidate.candidate_key]
            for candidate in candidates
        )
        # Nine bounded solves: seven policy stages plus the two ordered sub-stages.
        stage_budget = max_seconds / 9
        solver = self._solver(stage_budget)
        model.Maximize(total)
        status = solver.Solve(model)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return NearFutureResult((), "infeasible", 0, target_blocks, {})
        best_total = int(round(solver.ObjectiveValue()))
        best_values = {key: solver.Value(variable) for key, variable in variables.items()}
        model.Add(total == best_total)
        self._hint(model, variables, solver)

        first_date = min(row.output_date for row in candidates)
        latest_completion = model.NewIntVar(
            0,
            max((row.output_date - first_date).days for row in candidates),
            "latest_completion_day",
        )
        for candidate in candidates:
            model.Add(
                latest_completion
                >= (candidate.output_date - first_date).days * variables[candidate.candidate_key]
            )
        model.Minimize(latest_completion)
        solver = self._solver(stage_budget)
        status = solver.Solve(model)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return self._result_from_values(
                candidates,
                best_values,
                target_blocks=target_blocks,
                status="feasible",
                metrics={"scheduled_minutes": best_total, "optimization_stages": 1},
            )
        best_values = {key: solver.Value(variable) for key, variable in variables.items()}
        best_latest = solver.Value(latest_completion)
        if status != cp_model.OPTIMAL:
            return self._result_from_values(
                candidates,
                best_values,
                target_blocks=target_blocks,
                status="feasible",
                metrics={
                    "scheduled_minutes": best_total,
                    "latest_completion_day": best_latest,
                    "optimization_stages": 2,
                    "quality_optimization_complete": False,
                },
            )
        model.Add(latest_completion == best_latest)
        self._hint(model, variables, solver)

        date_cost = sum(
            (candidate.output_date - first_date).days
            * credited_minutes[candidate.candidate_key]
            * variables[candidate.candidate_key]
            for candidate in candidates
        )
        model.Minimize(date_cost)
        solver = self._solver(stage_budget)
        status = solver.Solve(model)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return self._result_from_values(
                candidates,
                best_values,
                target_blocks=target_blocks,
                status="feasible",
                metrics={
                    "scheduled_minutes": best_total,
                    "latest_completion_day": best_latest,
                    "optimization_stages": 2,
                },
            )
        best_date_cost = int(round(solver.ObjectiveValue()))
        best_values = {key: solver.Value(variable) for key, variable in variables.items()}
        if status != cp_model.OPTIMAL:
            return self._result_from_values(
                candidates,
                best_values,
                target_blocks=target_blocks,
                status="feasible",
                metrics={
                    "scheduled_minutes": best_total,
                    "latest_completion_day": best_latest,
                    "date_cost": best_date_cost,
                    "optimization_stages": 3,
                    "quality_optimization_complete": False,
                },
            )
        model.Add(date_cost == best_date_cost)
        self._hint(model, variables, solver)

        class_targets: dict[int, int] = defaultdict(int)
        class_selected: dict[int, list[tuple[int, cp_model.IntVar]]] = defaultdict(list)
        for (class_id, _subject_id), target in target_by_demand.items():
            class_targets[class_id] += target
        for candidate in candidates:
            class_selected[candidate.class_id].append(
                (credited_minutes[candidate.candidate_key], variables[candidate.candidate_key])
            )
        coverage_by_class: dict[int, cp_model.IntVar] = {}
        for class_id, target in class_targets.items():
            selected_minutes = sum(
                duration * variable for duration, variable in class_selected[class_id]
            )
            coverage = model.NewIntVar(0, 1000, f"class_coverage_{class_id}")
            model.Add(coverage * target <= selected_minutes * 1000)
            model.Add(selected_minutes * 1000 <= (coverage + 1) * target - 1)
            coverage_by_class[class_id] = coverage
        minimum_coverage = model.NewIntVar(0, 1000, "minimum_class_coverage")
        model.AddMinEquality(minimum_coverage, list(coverage_by_class.values()))
        model.Maximize(minimum_coverage)
        solver = self._solver(stage_budget)
        status = solver.Solve(model)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return self._result_from_values(
                candidates,
                best_values,
                target_blocks=target_blocks,
                status="feasible",
                metrics={
                    "scheduled_minutes": best_total,
                    "date_cost": best_date_cost,
                    "optimization_stages": 3,
                },
            )
        best_values = {key: solver.Value(variable) for key, variable in variables.items()}
        best_minimum_coverage = solver.Value(minimum_coverage)
        if status != cp_model.OPTIMAL:
            return self._result_from_values(
                candidates,
                best_values,
                target_blocks=target_blocks,
                status="feasible",
                metrics={
                    "scheduled_minutes": best_total,
                    "date_cost": best_date_cost,
                    "minimum_class_coverage_per_mille": best_minimum_coverage,
                    "optimization_stages": 4,
                    "quality_optimization_complete": False,
                },
            )
        model.Add(minimum_coverage == best_minimum_coverage)
        self._hint(model, variables, solver)

        maximum_coverage = model.NewIntVar(0, 1000, "maximum_class_coverage")
        model.AddMaxEquality(maximum_coverage, list(coverage_by_class.values()))
        coverage_spread = maximum_coverage - minimum_coverage
        model.Minimize(coverage_spread)
        solver = self._solver(stage_budget)
        status = solver.Solve(model)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return self._result_from_values(
                candidates,
                best_values,
                target_blocks=target_blocks,
                status="feasible",
                metrics={
                    "scheduled_minutes": best_total,
                    "date_cost": best_date_cost,
                    "optimization_stages": 4,
                },
            )
        best_values = {key: solver.Value(variable) for key, variable in variables.items()}
        best_spread = solver.Value(coverage_spread)
        if status != cp_model.OPTIMAL:
            return self._result_from_values(
                candidates,
                best_values,
                target_blocks=target_blocks,
                status="feasible",
                metrics={
                    "scheduled_minutes": best_total,
                    "date_cost": best_date_cost,
                    "minimum_class_coverage_per_mille": best_minimum_coverage,
                    "class_coverage_spread_per_mille": best_spread,
                    "optimization_stages": 5,
                    "quality_optimization_complete": False,
                },
            )
        model.Add(coverage_spread == best_spread)
        self._hint(model, variables, solver)

        workload_cost = quality_expressions.workload_cost
        model.Minimize(workload_cost)
        solver = self._solver(stage_budget)
        status = solver.Solve(model)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return self._result_from_values(
                candidates,
                best_values,
                target_blocks=target_blocks,
                status="feasible",
                metrics={"scheduled_minutes": best_total, "optimization_stages": 5},
            )
        best_values = {key: solver.Value(variable) for key, variable in variables.items()}
        best_workload = solver.Value(workload_cost)
        if status != cp_model.OPTIMAL:
            return self._result_from_values(
                candidates,
                best_values,
                target_blocks=target_blocks,
                status="feasible",
                metrics={
                    "scheduled_minutes": best_total,
                    "workload_cost_minutes": best_workload,
                    "optimization_stages": 6,
                    "quality_optimization_complete": False,
                },
            )
        model.Add(workload_cost == best_workload)
        self._hint(model, variables, solver)

        gap_and_availability = quality_expressions.gap_and_availability_cost
        model.Minimize(gap_and_availability)
        solver = self._solver(stage_budget)
        status = solver.Solve(model)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return self._result_from_values(
                candidates,
                best_values,
                target_blocks=target_blocks,
                status="feasible",
                metrics={"scheduled_minutes": best_total, "optimization_stages": 6},
            )
        best_values = {key: solver.Value(variable) for key, variable in variables.items()}
        best_gap_and_availability = solver.Value(gap_and_availability)
        if status != cp_model.OPTIMAL:
            return self._result_from_values(
                candidates,
                best_values,
                target_blocks=target_blocks,
                status="feasible",
                metrics={
                    "scheduled_minutes": best_total,
                    "gap_and_availability_cost_minutes": best_gap_and_availability,
                    "optimization_stages": 7,
                    "quality_optimization_complete": False,
                },
            )
        model.Add(gap_and_availability == best_gap_and_availability)
        self._hint(model, variables, solver)

        room_inconsistency = quality_expressions.room_inconsistency
        model.Minimize(room_inconsistency)
        solver = self._solver(stage_budget)
        status = solver.Solve(model)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return self._result_from_values(
                candidates,
                best_values,
                target_blocks=target_blocks,
                status="feasible",
                metrics={
                    "scheduled_minutes": best_total,
                    "date_cost": best_date_cost,
                    "optimization_stages": 7,
                },
            )
        values = {key: solver.Value(variable) for key, variable in variables.items()}
        best_room_inconsistency = solver.Value(room_inconsistency)
        if status == cp_model.OPTIMAL:
            model.Add(room_inconsistency == best_room_inconsistency)
            self._hint(model, variables, solver)
            tie_signature = sum(
                (index + 1) * variables[candidate.candidate_key]
                for index, candidate in enumerate(candidates)
            )
            model.Minimize(tie_signature)
            tie_solver = self._solver(stage_budget)
            tie_status = tie_solver.Solve(model)
            if tie_status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                solver = tie_solver
                status = tie_status
                values = {key: solver.Value(variable) for key, variable in variables.items()}
        return self._result_from_values(
            candidates,
            values,
            target_blocks=target_blocks,
            status="optimal" if status == cp_model.OPTIMAL else "feasible",
            metrics={
                "target_blocks": target_blocks,
                "scheduled_minutes": best_total,
                "latest_completion_day": best_latest,
                "date_cost": best_date_cost,
                "minimum_class_coverage_per_mille": best_minimum_coverage,
                "class_coverage_spread_per_mille": best_spread,
                "workload_cost_minutes": best_workload,
                "class_gap_minutes": solver.Value(quality_expressions.class_gap_minutes),
                "teacher_gap_minutes": solver.Value(quality_expressions.teacher_gap_minutes),
                "availability_disutility_minutes": solver.Value(
                    quality_expressions.availability_disutility
                ),
                "gap_and_availability_cost_minutes": best_gap_and_availability,
                "room_inconsistency_count": best_room_inconsistency,
                "solver_wall_seconds": round(solver.WallTime(), 4),
                "optimization_stages": 9,
                "quality_optimization_complete": status == cp_model.OPTIMAL,
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
                (candidate for candidate in candidates if values.get(candidate.candidate_key, 0)),
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
        result_metrics["preference_score"] = sum(row.availability_score for row in selected)
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
                *(
                    row.end_minute
                    for row in candidates
                    if lunch_start <= row.end_minute <= lunch_end
                ),
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
                model.NewBoolVar(f"lunch_{group_index}_{index}") for index in range(len(starts))
            ]
            model.AddExactlyOne(choices)
            for choice, break_start in zip(choices, starts, strict=False):
                break_end = break_start + minimum
                for candidate in rows:
                    if candidate.start_minute < break_end and candidate.end_minute > break_start:
                        model.Add(variables[candidate.candidate_key] + choice <= 1)

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
