from __future__ import annotations

import asyncio
import threading
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from time import monotonic
from typing import Any

from ortools.sat.python import cp_model

from app import models
from app.scheduler.domain.constraints import PlacementFacts, SchedulerConstraintPolicy
from app.scheduler.domain.contracts import (
    DraftBlockSpec,
    NoValidGenerationOutput,
    ValidatedGenerationResult,
)
from app.scheduler.domain.quality import (
    QualityBlock,
    ScheduleQualityEvaluator,
    SolveWorkloadMode,
    quality_policy_from_snapshot,
    quality_slots_from_snapshot,
)
from app.scheduler.infrastructure.cp_sat_quality import (
    CpSatQualityAdapter,
    CpSatQualityConstructionStopped,
    SelectableQualityBlock,
)
from app.services.scheduler_adaptation_ladder import (
    AdaptationLevel,
    SchedulerChangeAdaptationLadder,
    SchedulerChangeImpactAnalyzer,
)
from app.services.scheduler_disruption import DisruptionScore, DisruptionScorer
from app.services.scheduler_editable_boundary import EditableBoundaryBuilder
from app.services.scheduler_incremental_demand import (
    IncrementalDemandLedger,
    IncrementalDemandLedgerBuilder,
)
from app.services.scheduler_job_runtime import (
    GenerationExecutionContext,
)
from app.services.scheduler_quality_service import evaluate_target_quality
from app.services.scheduler_recovery_ladder import (
    RecoveryEscalationLadder,
    RecoveryLevel,
    RecoveryScope,
)
from app.services.scheduler_repair_trigger import RepairTriggerClassifier

MAX_REPAIR_CANDIDATES = 250_000


class RepairTaskOrigin(StrEnum):
    ACTIVE_BLOCK = "ACTIVE_BLOCK"
    DEBT_RECOVERY = "DEBT_RECOVERY"
    CURRICULUM_ADDITION = "CURRICULUM_ADDITION"


@dataclass(frozen=True)
class _RepairTask:
    key: str
    class_id: int
    subject_id: int
    teacher_id: int
    duration_minutes: int
    source_block: dict[str, Any] | None
    debt_item: dict[str, Any] | None
    recovery_index: int | None
    origin: RepairTaskOrigin
    module_sequence_index: int | None = None
    module_id: int | None = None
    lesson_count: int = 1
    group_order: int = 0

    @property
    def is_recovery(self) -> bool:
        return self.origin is RepairTaskOrigin.DEBT_RECOVERY

    @property
    def is_curriculum_addition(self) -> bool:
        return self.origin is RepairTaskOrigin.CURRICULUM_ADDITION


@dataclass(frozen=True)
class _Placement:
    key: str
    task: _RepairTask
    output_date: date
    timeslot_id: int
    room_id: int
    start_minute: int
    end_minute: int
    availability_score: int


@dataclass(frozen=True)
class _ScopeSolution:
    blocks: tuple[DraftBlockSpec, ...]
    recovered_minutes: int
    disruption: DisruptionScore
    recovery_level: str | None
    adaptation_level: str | None
    solver_status: str
    candidate_count: int
    quality_completed_stage: str = "RECOVERED_MINUTES"
    quality_optimization_complete: bool = False
    feasibility_solver_status: str = "UNKNOWN"
    scope_rank: int = 0
    workload_cost_minutes: int = 0
    gap_and_availability_cost_minutes: int = 0
    stable_signature: tuple = ()
    workload_override_used: bool = False
    class_overload_count: int = 0
    class_overload_excess_minutes: int = 0
    teacher_overload_count: int = 0
    teacher_overload_excess_minutes: int = 0
    required_curriculum_minutes: int = 0
    scheduled_curriculum_minutes: int = 0
    construction_duration_ms: int = 0
    solve_duration_ms: int = 0
    feasibility_solve_duration_ms: int = 0
    quality_construction_duration_ms: int = 0
    quality_solve_duration_ms: int = 0
    result_extraction_duration_ms: int = 0
    variable_count: int = 0
    constraint_count: int = 0


@dataclass(frozen=True)
class _SolveScope:
    fixed_blocks: tuple[dict[str, Any], ...]
    movable_blocks: tuple[dict[str, Any], ...]
    affected_class_ids: tuple[int, ...]
    affected_teacher_ids: tuple[int, ...]
    recovery_level: str | None
    adaptation_level: str | None
    workload_mode: SolveWorkloadMode = SolveWorkloadMode.QUALITY_ONLY
    keep_date_and_time: bool = False


class AdaptiveRepairEngine:
    async def generate(
        self,
        context: GenerationExecutionContext,
    ) -> ValidatedGenerationResult | NoValidGenerationOutput:
        await context.ensure_can_continue()
        if context.strategy not in (
            models.ScheduleGenerationStrategy.ADAPTIVE_REPAIR,
            models.ScheduleGenerationStrategy.GRID_CHANGE,
        ):
            return NoValidGenerationOutput(
                blockers=("Adaptive repair engine received a complete-generation job.",)
            )
        snapshot = context.immutable_snapshot["generation_input"]
        debt = context.immutable_snapshot.get("debt_basis") or {"items": []}
        policy = context.immutable_snapshot.get("repair_policy")
        if policy is None:
            return NoValidGenerationOutput(
                blockers=("Adaptive repair policy snapshot is missing.",)
            )
        constraint_parse = SchedulerConstraintPolicy.from_snapshot(snapshot)
        if constraint_parse.configuration_violations:
            return NoValidGenerationOutput(
                blockers=tuple(row.message for row in constraint_parse.configuration_violations),
                metrics={
                    "constraint_configuration_violations": len(
                        constraint_parse.configuration_violations
                    )
                },
            )
        constraint_policy = constraint_parse.policy or SchedulerConstraintPolicy()
        try:
            trigger = RepairTriggerClassifier().classify(
                snapshot,
                debt,
                declared_trigger=context.trigger_type,
            )
            boundary = EditableBoundaryBuilder().build(snapshot, policy)
        except (KeyError, TypeError, ValueError) as exc:
            return NoValidGenerationOutput(blockers=(str(exc),))

        curriculum = IncrementalDemandLedgerBuilder().build(
            snapshot,
            immutable_block_ids={row["id"] for row in boundary.immutable_blocks},
        )
        if not curriculum.is_complete:
            return NoValidGenerationOutput(
                blockers=curriculum.blockers,
                metrics={
                    "required_recovery_minutes": trigger.unresolved_debt_minutes,
                    "required_curriculum_minutes": curriculum.required_minutes,
                    "scheduled_curriculum_minutes": 0,
                },
            )

        total_debt = trigger.unresolved_debt_minutes
        best: _ScopeSolution | None = None
        failures: list[str] = []
        if trigger.use_adaptation_ladder:
            impact = SchedulerChangeImpactAnalyzer().analyze(
                snapshot,
                boundary,
                constraint_policy,
            )
            if impact.immutable_invalid:
                return NoValidGenerationOutput(
                    blockers=tuple(
                        f"Immutable block {row.block['id']}: {' '.join(row.reasons)}"
                        for row in impact.immutable_invalid
                    ),
                    metrics={
                        "immutable_invalid_blocks": len(impact.immutable_invalid),
                        "required_recovery_minutes": total_debt,
                        "required_curriculum_minutes": curriculum.required_minutes,
                        "scheduled_curriculum_minutes": 0,
                    },
                )
            scopes = self._deduplicate_scopes(
                self._combined_scopes(snapshot, boundary, debt, impact, curriculum)
            )
        else:
            scopes = tuple(
                self._recovery_scope(scope)
                for scope in RecoveryEscalationLadder().scopes(boundary, debt)
                if scope.level != RecoveryLevel.IMPOSSIBLE
            )
        for scope_rank, scope in enumerate(scopes):
            await context.ensure_can_continue()
            if datetime.now(UTC) >= context.solve_deadline_at:
                failures.append("Adaptive repair exhausted its solve time budget.")
                break
            try:
                solution, blocker = await asyncio.to_thread(
                    self._solve_scope,
                    snapshot,
                    debt,
                    curriculum,
                    boundary.school_today,
                    boundary.editable_start_date,
                    scope,
                    constraint_policy,
                    deadline_at=context.solve_deadline_at,
                    stop_event=context.solver_stop_event,
                )
            except asyncio.CancelledError:
                context.stop_event.set()
                raise
            await context.ensure_can_continue()
            if blocker:
                level = scope.adaptation_level or scope.recovery_level or "ADAPTIVE_REPAIR"
                failures.append(f"{level}: {blocker}")
            if solution is None:
                continue
            solution = replace(solution, scope_rank=scope_rank)
            if self._better_partial(solution, best):
                best = solution
            if (
                solution.recovered_minutes == total_debt
                and solution.scheduled_curriculum_minutes == solution.required_curriculum_minutes
            ):
                return self._result(
                    snapshot,
                    trigger.summary,
                    solution,
                    total_debt=total_debt,
                    stability_constrained=self._stability_constrained(boundary),
                    escalation_history=tuple(failures),
                )
            level = scope.adaptation_level or scope.recovery_level or "ADAPTIVE_REPAIR"
            failures.append(
                f"{level}: recovered {solution.recovered_minutes} of {total_debt} "
                "minutes; full recovery was not possible."
            )

        if best is None:
            blockers = tuple(failures)
            if curriculum.required_minutes > 0:
                blockers = (
                    "The newly added curriculum could not be fully placed before the "
                    "hard end date.",
                    *blockers,
                )
            return NoValidGenerationOutput(
                blockers=blockers or ("No hard-valid adaptive recovery target could be produced.",),
                metrics={
                    "required_recovery_minutes": total_debt,
                    "required_curriculum_minutes": curriculum.required_minutes,
                    "scheduled_curriculum_minutes": 0,
                },
            )
        if best.scheduled_curriculum_minutes != best.required_curriculum_minutes:
            return NoValidGenerationOutput(
                blockers=(
                    "The newly added curriculum could not be fully placed before the "
                    "hard end date.",
                    *failures,
                ),
                metrics={
                    "required_recovery_minutes": total_debt,
                    "required_curriculum_minutes": best.required_curriculum_minutes,
                    "scheduled_curriculum_minutes": best.scheduled_curriculum_minutes,
                },
            )
        return self._result(
            snapshot,
            trigger.summary,
            best,
            total_debt=total_debt,
            stability_constrained=self._stability_constrained(boundary),
            escalation_history=tuple(failures),
        )

    def _solve_scope(
        self,
        snapshot: dict[str, Any],
        debt: dict[str, Any],
        curriculum: IncrementalDemandLedger,
        school_today: date,
        editable_start_date: date,
        scope: _SolveScope,
        constraint_policy: SchedulerConstraintPolicy,
        *,
        deadline_at: datetime,
        stop_event: threading.Event,
    ) -> tuple[_ScopeSolution | None, str | None]:
        construction_started = monotonic()
        if self._stop_requested(deadline_at, stop_event):
            return None, "Adaptive repair exhausted its solve time budget."
        slots, slot_blocker = self._slots(snapshot)
        if slot_blocker:
            return None, slot_blocker
        fixed_intervals, fixed_blocker = self._fixed_intervals(scope.fixed_blocks, slots)
        if fixed_blocker:
            return None, fixed_blocker
        tasks, task_blocker = self._build_tasks(snapshot, debt, curriculum, scope, slots)
        if task_blocker:
            return None, task_blocker
        placements, placement_blocker = self._build_placements(
            snapshot,
            tasks,
            scope,
            slots,
            fixed_intervals,
            editable_start_date,
            constraint_policy,
            deadline_at,
            stop_event,
        )
        if placement_blocker:
            return None, placement_blocker
        by_task: dict[str, list[_Placement]] = defaultdict(list)
        for placement in placements:
            by_task[placement.task.key].append(placement)
        for task in tasks:
            if not task.is_recovery and len(by_task[task.key]) < task.lesson_count:
                if task.origin is RepairTaskOrigin.ACTIVE_BLOCK:
                    message = f"Published block {task.source_block['id']} cannot be re-placed."
                else:
                    message = (
                        "Curriculum addition "
                        f"{task.class_id}/{task.subject_id}/{task.module_sequence_index} "
                        "cannot be placed."
                    )
                return None, message

        model = cp_model.CpModel()
        variables = {
            row.key: model.NewBoolVar(f"p_{index}") for index, row in enumerate(placements)
        }
        selected_by_task: dict[str, cp_model.IntVar] = {}
        for index, task in enumerate(tasks):
            task_vars = [variables[row.key] for row in by_task[task.key]]
            selected = model.NewIntVar(0, task.lesson_count, f"selected_{index}")
            selected_by_task[task.key] = selected
            if task_vars:
                model.Add(sum(task_vars) == selected)
            else:
                model.Add(selected == 0)
            if not task.is_recovery:
                model.Add(selected == task.lesson_count)
        recovery_groups: dict[int, list[_RepairTask]] = defaultdict(list)
        for task in tasks:
            if task.is_recovery:
                recovery_groups[int(task.debt_item["occurrence_id"])].append(task)
        for group in recovery_groups.values():
            ordered = sorted(group, key=lambda row: row.recovery_index)
            for previous, current in zip(ordered, ordered[1:], strict=False):
                model.Add(selected_by_task[previous.key] >= selected_by_task[current.key])
        self._add_curriculum_order_constraints(model, tasks, by_task, variables)

        grouped_intervals: dict[tuple[str, int, date], list[cp_model.IntervalVar]] = defaultdict(
            list
        )
        for index, row in enumerate(placements):
            variable = variables[row.key]
            for kind, resource_id in (
                ("class", row.task.class_id),
                ("teacher", row.task.teacher_id),
                ("room", row.room_id),
            ):
                grouped_intervals[(kind, resource_id, row.output_date)].append(
                    model.NewOptionalFixedSizeIntervalVar(
                        row.start_minute,
                        row.end_minute - row.start_minute,
                        variable,
                        f"{kind}_{index}",
                    )
                )
        for intervals in grouped_intervals.values():
            if len(intervals) > 1:
                model.AddNoOverlap(intervals)
        self._add_lunch_constraints(
            model,
            placements,
            variables,
            fixed_intervals,
            snapshot.get("lunch_rules"),
        )
        if scope.workload_mode is SolveWorkloadMode.PROTECT_COMFORT:
            self._add_comfort_constraints(
                model,
                snapshot,
                scope,
                placements,
                variables,
            )

        construction_duration_ms = round((monotonic() - construction_started) * 1000)
        solve_started = monotonic()

        recovered = sum(
            task.duration_minutes * selected_by_task[task.key] for task in tasks if task.is_recovery
        )

        def remaining() -> float:
            return max(0.0, (deadline_at - datetime.now(UTC)).total_seconds())

        if stop_event.is_set() or remaining() <= 0:
            return None, "Adaptive repair exhausted its solve time budget."
        solver = self._solver(remaining())
        model.Maximize(recovered)
        status = self._solve_model(solver, model, stop_event)
        feasibility_solve_duration_ms = round((monotonic() - solve_started) * 1000)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            if status == cp_model.INFEASIBLE:
                return None, "No hard-valid placement exists at this recovery level."
            return None, "Adaptive repair search exhausted its solve time budget."
        best_recovered = int(round(solver.ObjectiveValue()))
        feasibility_solver_status = self._solver_status_name(status)
        values = {key: solver.Value(value) for key, value in variables.items()}
        completed_stage = "RECOVERED_MINUTES"
        optimization_complete = status == cp_model.OPTIMAL
        if optimization_complete:
            model.Add(recovered == best_recovered)
            self._hint(model, variables, solver)

        quality_expressions = None
        quality_construction_duration_ms = 0
        quality_solve_duration_ms = 0
        if optimization_complete and not stop_event.is_set() and remaining() > 0:
            quality_construction_started = monotonic()
            quality_evaluator = ScheduleQualityEvaluator(
                quality_policy_from_snapshot(snapshot),
                quality_slots_from_snapshot(snapshot),
                snapshot.get("lunch_rules"),
            )
            quality_rows = tuple(
                SelectableQualityBlock(
                    row.key,
                    QualityBlock(
                        class_id=row.task.class_id,
                        subject_id=row.task.subject_id,
                        teacher_id=row.task.teacher_id,
                        room_id=row.room_id,
                        output_date=row.output_date,
                        timeslot_id=row.timeslot_id,
                        duration_minutes=row.task.duration_minutes,
                        availability_tier=row.availability_score,
                        is_recovery_block=row.task.is_recovery,
                    ),
                )
                for row in placements
            )
            fixed_quality = self._fixed_quality_blocks(snapshot, scope.fixed_blocks)
            try:
                quality_expressions = CpSatQualityAdapter(quality_evaluator).add_expressions(
                    model,
                    quality_rows,
                    variables,
                    fixed_quality,
                    should_stop=lambda: stop_event.is_set() or remaining() <= 0,
                )
            except CpSatQualityConstructionStopped:
                quality_expressions = None
            quality_construction_duration_ms = round(
                (monotonic() - quality_construction_started) * 1000
            )
            if quality_expressions is None:
                optimization_complete = False
        disruption_cost = sum(self._disruption_cost(row) * variables[row.key] for row in placements)
        first_date = min(
            (row.output_date for row in placements),
            default=school_today,
        )
        completion_cost = sum(
            (row.output_date - first_date).days * row.task.duration_minutes * variables[row.key]
            for row in placements
        )
        stable_signature = sum(
            (index + 1) * variables[row.key]
            for index, row in enumerate(
                sorted(
                    placements,
                    key=lambda candidate: (
                        candidate.output_date,
                        candidate.start_minute,
                        candidate.task.class_id,
                        candidate.task.subject_id,
                        candidate.task.teacher_id,
                        candidate.room_id,
                        candidate.key,
                    ),
                )
            )
        )
        if optimization_complete and quality_expressions is not None:
            quality_solve_started = monotonic()
            stages = (
                ("DISRUPTION", disruption_cost),
                ("EARLIEST_COMPLETION", completion_cost),
                ("WORKLOAD", quality_expressions.workload_cost),
                ("GAPS_AVAILABILITY", quality_expressions.gap_and_availability_cost),
                ("STABLE_TIE", stable_signature),
            )
            for stage_name, expression in stages:
                if stop_event.is_set() or remaining() <= 0:
                    optimization_complete = False
                    break
                model.Minimize(expression)
                stage_solver = self._solver(remaining())
                stage_status = self._solve_model(stage_solver, model, stop_event)
                if stage_status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                    optimization_complete = False
                    break
                solver = stage_solver
                status = stage_status
                values = {key: solver.Value(value) for key, value in variables.items()}
                completed_stage = stage_name
                if stage_status != cp_model.OPTIMAL:
                    optimization_complete = False
                    break
                optimum = solver.Value(expression)
                model.Add(expression == optimum)
                self._hint(model, variables, solver)
            quality_solve_duration_ms = round((monotonic() - quality_solve_started) * 1000)
        extraction_started = monotonic()
        chosen = [row for row in placements if values.get(row.key, 0)]
        required_curriculum_minutes = sum(
            task.duration_minutes * task.lesson_count
            for task in tasks
            if task.is_curriculum_addition
        )
        scheduled_curriculum_minutes = sum(
            row.task.duration_minutes for row in chosen if row.task.is_curriculum_addition
        )
        blocks = self._specs(snapshot, scope.fixed_blocks, chosen)
        proposed = [self._spec_dict(row) for row in blocks]
        disruption = DisruptionScorer().score(
            snapshot.get("active_schedule", []),
            proposed,
            school_today=school_today,
            affected_class_ids=set(scope.affected_class_ids),
            affected_teacher_ids=set(scope.affected_teacher_ids),
        )
        overload = self._workload_override_metrics(snapshot, blocks)
        override_used = scope.workload_mode is SolveWorkloadMode.DEADLINE_RESCUE and any(
            overload.values()
        )
        quality_metrics = evaluate_target_quality(snapshot, blocks)
        stable_signature = tuple(
            (
                row.date.toordinal(),
                row.timeslot_id,
                row.class_id,
                row.subject_id,
                row.teacher_id,
                row.room_id,
                row.stable_block_key,
            )
            for row in blocks
        )
        result_extraction_duration_ms = round((monotonic() - extraction_started) * 1000)
        return (
            _ScopeSolution(
                blocks=blocks,
                recovered_minutes=best_recovered,
                disruption=disruption,
                recovery_level=scope.recovery_level,
                adaptation_level=scope.adaptation_level,
                solver_status=("optimal" if optimization_complete else "feasible"),
                candidate_count=len(placements),
                quality_completed_stage=completed_stage,
                quality_optimization_complete=optimization_complete,
                feasibility_solver_status=feasibility_solver_status,
                workload_cost_minutes=int(quality_metrics.get("workload_cost_minutes", 0)),
                gap_and_availability_cost_minutes=(
                    int(quality_metrics.get("class_gap_minutes", 0))
                    + int(quality_metrics.get("teacher_gap_minutes", 0))
                    + int(quality_metrics.get("availability_disutility_minutes", 0))
                ),
                stable_signature=stable_signature,
                workload_override_used=override_used,
                required_curriculum_minutes=required_curriculum_minutes,
                scheduled_curriculum_minutes=scheduled_curriculum_minutes,
                construction_duration_ms=construction_duration_ms,
                solve_duration_ms=feasibility_solve_duration_ms + quality_solve_duration_ms,
                feasibility_solve_duration_ms=feasibility_solve_duration_ms,
                quality_construction_duration_ms=quality_construction_duration_ms,
                quality_solve_duration_ms=quality_solve_duration_ms,
                result_extraction_duration_ms=result_extraction_duration_ms,
                variable_count=len(model.Proto().variables),
                constraint_count=len(model.Proto().constraints),
                **overload,
            ),
            None,
        )

    def _build_tasks(
        self,
        snapshot: dict[str, Any],
        debt: dict[str, Any],
        curriculum: IncrementalDemandLedger,
        scope: _SolveScope,
        slots: dict[int, tuple[dict[str, int], ...]],
    ) -> tuple[list[_RepairTask], str | None]:
        assignments = {
            (row["class_id"], row["subject_id"]): row.get("teacher_id")
            for row in snapshot.get("class_subject_requirements", [])
        }
        tasks: list[_RepairTask] = []
        for block in scope.movable_blocks:
            teacher_id = assignments.get(
                (block["class_id"], block["subject_id"]),
                block["teacher_id"],
            )
            if teacher_id is None:
                return [], f"No teacher is assigned for movable block {block['id']}."
            tasks.append(
                _RepairTask(
                    key=f"A-{block['id']}",
                    class_id=block["class_id"],
                    subject_id=block["subject_id"],
                    teacher_id=teacher_id,
                    duration_minutes=int(block["duration_minutes"]),
                    source_block=block,
                    debt_item=None,
                    recovery_index=None,
                    origin=RepairTaskOrigin.ACTIVE_BLOCK,
                )
            )
        minimum_slot = min(row["end"] - row["start"] for rows in slots.values() for row in rows)
        for item in curriculum.items:
            for module in item.modules:
                full_count, remainder = divmod(module.required_minutes, minimum_slot)
                grouped_durations = (
                    (minimum_slot, full_count),
                    (remainder, int(remainder > 0)),
                )
                for group_order, (duration, count) in enumerate(grouped_durations):
                    if count == 0:
                        continue
                    tasks.append(
                        _RepairTask(
                            key=(
                                f"CURG-{item.class_id}-{item.subject_id}-{module.module_id}-"
                                f"{duration}"
                            ),
                            class_id=item.class_id,
                            subject_id=item.subject_id,
                            teacher_id=item.teacher_id,
                            duration_minutes=duration,
                            source_block=None,
                            debt_item=None,
                            recovery_index=None,
                            origin=RepairTaskOrigin.CURRICULUM_ADDITION,
                            module_sequence_index=module.sequence,
                            module_id=module.module_id,
                            lesson_count=count,
                            group_order=group_order,
                        )
                    )
        for item in debt.get("items", []):
            remaining = max(0, int(item.get("unresolved_debt_minutes", 0)))
            index = 0
            while remaining:
                duration = min(minimum_slot, remaining)
                tasks.append(
                    _RepairTask(
                        key=(f"R-{item['occurrence_id']}-{item['occurrence_revision']}-{index}"),
                        class_id=item["class_id"],
                        subject_id=item["subject_id"],
                        teacher_id=assignments.get(
                            (item["class_id"], item["subject_id"]),
                            item.get("teacher_id"),
                        ),
                        duration_minutes=duration,
                        source_block=None,
                        debt_item=item,
                        recovery_index=index,
                        origin=RepairTaskOrigin.DEBT_RECOVERY,
                    )
                )
                remaining -= duration
                index += 1
        return tasks, None

    def _build_placements(
        self,
        snapshot: dict[str, Any],
        tasks: list[_RepairTask],
        scope: _SolveScope,
        slots: dict[int, tuple[dict[str, int], ...]],
        fixed_intervals: dict[tuple[str, int, date], list[tuple[int, int]]],
        editable_start_date: date,
        constraint_policy: SchedulerConstraintPolicy,
        deadline_at: datetime,
        stop_event: threading.Event,
    ) -> tuple[list[_Placement], str | None]:
        classes = {row["id"]: row for row in snapshot.get("classes", [])}
        subjects = {row["id"]: row for row in snapshot.get("subjects", [])}
        rooms = snapshot.get("rooms", [])
        qualifications = {
            (row["teacher_id"], row["subject_id"])
            for row in snapshot.get("teacher_subject_eligibility", [])
        }
        teachers = {row["id"] for row in snapshot.get("teachers", [])}
        availability = {
            (row["teacher_id"], row["timeslot_id"]): int(row["score"])
            for row in snapshot.get("teacher_availability", [])
        }
        blocked_dates = self._blocked_dates(snapshot.get("calendar_events", []))
        hard_end = date.fromisoformat(snapshot["hard_end_date"])
        placements: list[_Placement] = []
        for task in tasks:
            if self._stop_requested(deadline_at, stop_event):
                return [], "Adaptive repair candidate construction exhausted its time budget."
            class_row = classes.get(task.class_id)
            subject_row = subjects.get(task.subject_id)
            if (
                class_row is None
                or subject_row is None
                or task.teacher_id not in teachers
                or (task.teacher_id, task.subject_id) not in qualifications
            ):
                if task.origin is RepairTaskOrigin.DEBT_RECOVERY:
                    continue
                if task.origin is RepairTaskOrigin.ACTIVE_BLOCK:
                    return [], (
                        f"Movable block {task.source_block['id']} has no eligible assignment."
                    )
                return [], (
                    "Curriculum addition "
                    f"{task.class_id}/{task.subject_id}/{task.module_sequence_index} "
                    "has no eligible assignment."
                )
            required_type = self._value(subject_row.get("required_room_type"))
            eligible_rooms = [
                row["id"]
                for row in rooms
                if int(row.get("capacity") or 0) >= int(class_row["size"])
                and self._value(row.get("type")) == required_type
            ]
            current = editable_start_date
            while current <= hard_end:
                if self._stop_requested(deadline_at, stop_event):
                    return [], "Adaptive repair candidate construction exhausted its time budget."
                if self._date_allowed(task, current, scope, blocked_dates):
                    for slot in slots.get(current.weekday(), ()):
                        if not self._slot_allowed(task, slot, scope, current):
                            continue
                        score = availability.get((task.teacher_id, slot["id"]), 1)
                        if score == -1:
                            continue
                        for room_id in eligible_rooms:
                            evaluation = constraint_policy.evaluate(
                                PlacementFacts(
                                    class_id=task.class_id,
                                    subject_id=task.subject_id,
                                    teacher_id=task.teacher_id,
                                    room_id=room_id,
                                    output_date=current,
                                    timeslot_id=slot["id"],
                                )
                            )
                            if evaluation.hard_violations:
                                continue
                            if self._conflicts_fixed(
                                task,
                                current,
                                slot["start"],
                                slot["end"],
                                room_id,
                                fixed_intervals,
                            ):
                                continue
                            placements.append(
                                _Placement(
                                    key=(
                                        f"{task.key}-{current.isoformat()}-{slot['id']}-{room_id}"
                                    ),
                                    task=task,
                                    output_date=current,
                                    timeslot_id=slot["id"],
                                    room_id=room_id,
                                    start_minute=slot["start"],
                                    end_minute=slot["end"],
                                    availability_score=min(
                                        2,
                                        score + evaluation.preference_tier_adjustment,
                                    ),
                                )
                            )
                            if len(placements) > MAX_REPAIR_CANDIDATES:
                                return [], "Adaptive repair candidate limit was exceeded."
                current += timedelta(days=1)
        return placements, None

    @staticmethod
    def _add_curriculum_order_constraints(
        model: cp_model.CpModel,
        tasks: list[_RepairTask],
        placements_by_task: dict[str, list[_Placement]],
        variables: dict[str, cp_model.IntVar],
    ) -> None:
        grouped: dict[tuple[int, int], list[_RepairTask]] = defaultdict(list)
        for task in tasks:
            if task.is_curriculum_addition:
                grouped[(task.class_id, task.subject_id)].append(task)
        for unordered_tasks in grouped.values():
            ordered_tasks = sorted(
                unordered_tasks,
                key=lambda row: (row.module_sequence_index, row.group_order),
            )
            for previous, current in zip(ordered_tasks, ordered_tasks[1:], strict=False):
                previous_rows = placements_by_task[previous.key]
                current_rows = placements_by_task[current.key]
                upper = max(
                    row.output_date.toordinal() * 1440 + row.start_minute
                    for row in (*previous_rows, *current_rows)
                )
                previous_latest = model.NewIntVar(0, upper, f"latest_{previous.key}")
                model.AddMaxEquality(
                    previous_latest,
                    [
                        (row.output_date.toordinal() * 1440 + row.start_minute) * variables[row.key]
                        for row in previous_rows
                    ],
                )
                current_earliest = model.NewIntVar(0, upper + 1, f"earliest_{current.key}")
                model.AddMinEquality(
                    current_earliest,
                    [
                        upper
                        + 1
                        - (upper + 1 - (row.output_date.toordinal() * 1440 + row.start_minute))
                        * variables[row.key]
                        for row in current_rows
                    ],
                )
                model.Add(previous_latest < current_earliest)

    @staticmethod
    def _date_allowed(
        task: _RepairTask,
        candidate_date: date,
        scope: _SolveScope,
        blocked_dates: set[date],
    ) -> bool:
        if candidate_date in blocked_dates:
            return False
        return not (
            scope.keep_date_and_time
            and task.source_block is not None
            and candidate_date.isoformat() != task.source_block["date"]
        )

    @staticmethod
    def _slot_allowed(
        task: _RepairTask,
        slot: dict[str, Any],
        scope: _SolveScope,
        candidate_date: date,
    ) -> bool:
        valid_from = slot.get("valid_from")
        valid_to = slot.get("valid_to")
        if valid_from is not None and candidate_date < date.fromisoformat(str(valid_from)):
            return False
        if valid_to is not None and candidate_date > date.fromisoformat(str(valid_to)):
            return False
        if task.duration_minutes > slot["end"] - slot["start"]:
            return False
        return not (
            scope.keep_date_and_time
            and task.source_block is not None
            and slot["id"] != task.source_block["timeslot_id"]
        )

    def _specs(
        self,
        snapshot: dict[str, Any],
        fixed: tuple[dict[str, Any], ...],
        chosen: list[_Placement],
    ) -> tuple[DraftBlockSpec, ...]:
        subject_types = {
            row["id"]: models.RoomType(self._value(row["required_room_type"]))
            for row in snapshot.get("subjects", [])
        }
        specs = [self._existing_spec(row, subject_types[row["subject_id"]]) for row in fixed]
        curriculum_indexes: dict[str, int] = defaultdict(int)
        for row in sorted(
            chosen,
            key=lambda item: (
                item.output_date,
                item.start_minute,
                item.room_id,
                item.key,
            ),
        ):
            task = row.task
            if task.is_recovery:
                item = task.debt_item
                specs.append(
                    DraftBlockSpec(
                        stable_block_key=(
                            f"REC-{item['occurrence_id']}-"
                            f"{item['occurrence_revision']}-{task.recovery_index}"
                        ),
                        class_id=task.class_id,
                        subject_id=task.subject_id,
                        teacher_id=task.teacher_id,
                        room_id=row.room_id,
                        room_type_id=subject_types[task.subject_id],
                        date=row.output_date,
                        timeslot_id=row.timeslot_id,
                        duration_minutes=task.duration_minutes,
                        change_type=models.ScheduleDraftBlockChangeType.ADDED,
                        is_recovery_block=True,
                        recovery_source_occurrence_id=item["occurrence_id"],
                        recovery_source_occurrence_revision=item["occurrence_revision"],
                        reason_code="EXPLICIT_DEBT_RECOVERY",
                    )
                )
                continue
            if task.is_curriculum_addition:
                lesson_index = curriculum_indexes[task.key]
                curriculum_indexes[task.key] += 1
                specs.append(
                    DraftBlockSpec(
                        stable_block_key=(
                            f"CUR-{task.class_id}-{task.subject_id}-{task.module_id}-"
                            f"{task.duration_minutes}-{lesson_index}"
                        ),
                        class_id=task.class_id,
                        subject_id=task.subject_id,
                        teacher_id=task.teacher_id,
                        room_id=row.room_id,
                        room_type_id=subject_types[task.subject_id],
                        date=row.output_date,
                        timeslot_id=row.timeslot_id,
                        duration_minutes=task.duration_minutes,
                        module_sequence_index=task.module_sequence_index,
                        change_type=models.ScheduleDraftBlockChangeType.ADDED,
                        reason_code="NEW_CURRICULUM_DEMAND",
                    )
                )
                continue
            before = task.source_block
            if (
                before["date"] != row.output_date.isoformat()
                or before["timeslot_id"] != row.timeslot_id
            ):
                change = models.ScheduleDraftBlockChangeType.MOVED
            elif before["teacher_id"] != task.teacher_id:
                change = models.ScheduleDraftBlockChangeType.REPLACED
            elif before["room_id"] != row.room_id:
                change = models.ScheduleDraftBlockChangeType.ROOM_ONLY
            else:
                change = models.ScheduleDraftBlockChangeType.UNCHANGED
            specs.append(
                DraftBlockSpec(
                    stable_block_key=before["stable_block_key"],
                    source_active_block_id=before["id"],
                    class_id=task.class_id,
                    subject_id=task.subject_id,
                    teacher_id=task.teacher_id,
                    room_id=row.room_id,
                    room_type_id=subject_types[task.subject_id],
                    date=row.output_date,
                    timeslot_id=row.timeslot_id,
                    duration_minutes=task.duration_minutes,
                    module_sequence_index=before.get("module_sequence_index"),
                    change_type=change,
                    is_recovery_block=bool(before.get("is_recovery_block")),
                    recovery_source_occurrence_id=before.get("recovery_source_occurrence_id"),
                    recovery_source_occurrence_revision=before.get(
                        "recovery_source_occurrence_revision"
                    ),
                    reason_code="RECOVERY_SCOPE_REFIT" if change.value != "UNCHANGED" else None,
                )
            )
        return tuple(
            sorted(specs, key=lambda row: (row.date, row.timeslot_id, row.stable_block_key))
        )

    @staticmethod
    def _existing_spec(row: dict[str, Any], room_type: models.RoomType) -> DraftBlockSpec:
        return DraftBlockSpec(
            stable_block_key=row["stable_block_key"],
            source_active_block_id=row["id"],
            class_id=row["class_id"],
            subject_id=row["subject_id"],
            teacher_id=row["teacher_id"],
            room_id=row["room_id"],
            room_type_id=room_type,
            date=date.fromisoformat(row["date"]),
            timeslot_id=row["timeslot_id"],
            duration_minutes=row["duration_minutes"],
            module_sequence_index=row.get("module_sequence_index"),
            change_type=models.ScheduleDraftBlockChangeType.UNCHANGED,
            is_recovery_block=bool(row.get("is_recovery_block")),
            recovery_source_occurrence_id=row.get("recovery_source_occurrence_id"),
            recovery_source_occurrence_revision=row.get("recovery_source_occurrence_revision"),
        )

    def _result(
        self,
        snapshot: dict[str, Any],
        trigger_summary: str,
        solution: _ScopeSolution,
        *,
        total_debt: int,
        stability_constrained: bool,
        escalation_history: tuple[str, ...],
    ) -> ValidatedGenerationResult:
        remaining = total_debt - solution.recovered_minutes
        partial = remaining > 0
        blocker_type = None
        blocker_message = None
        actions: tuple[str, ...] = ()
        if partial and stability_constrained:
            blocker_type = "STABILITY_WINDOW"
            blocker_message = (
                "The stability window protects too much of the remaining schedule "
                "before the hard end date."
            )
            actions = (
                "Reduce the stability window.",
                "Allow broader future schedule changes.",
                "Generate the schedule again.",
            )
        elif partial:
            blocker_type = "RESOURCE_CAPACITY"
            blocker_message = (
                "The remaining hours cannot fit with the current resources and hard end date."
            )
            actions = (
                "Add or free eligible resources before the hard end date.",
                "Allow broader future schedule changes.",
                "Generate the schedule again.",
            )
        projected = max(
            (row.date for row in solution.blocks),
            default=date.fromisoformat(snapshot["start_date"]),
        )
        summary = {
            "message": "Partial recovery generated." if partial else "Full recovery generated.",
            "trigger_summary": trigger_summary,
            "recovered_minutes": solution.recovered_minutes,
            "remaining_unscheduled_minutes": remaining,
            "recovered_hours": solution.recovered_minutes / 60,
            "remaining_unscheduled_hours": remaining / 60,
            "required_curriculum_minutes": solution.required_curriculum_minutes,
            "scheduled_curriculum_minutes": solution.scheduled_curriculum_minutes,
            "recovery_escalation_level": solution.recovery_level,
            "adaptation_level": solution.adaptation_level,
            "escalation_history": list(escalation_history),
            "quality_completed_stage": solution.quality_completed_stage,
            "quality_scope": "ADAPTIVE_REPAIR_SCOPE",
            **solution.disruption.to_metrics(),
        }
        quality_metrics = evaluate_target_quality(snapshot, solution.blocks)
        if solution.workload_override_used:
            summary.update(
                {
                    "workload_override_used": True,
                    "class_overload_count": solution.class_overload_count,
                    "class_overload_excess_minutes": solution.class_overload_excess_minutes,
                    "teacher_overload_count": solution.teacher_overload_count,
                    "teacher_overload_excess_minutes": solution.teacher_overload_excess_minutes,
                }
            )
        if partial:
            summary["user_message"] = self._partial_user_message(
                solution.recovered_minutes,
                remaining,
                blocker_message,
                actions,
            )
        return ValidatedGenerationResult(
            result_category=(
                models.ScheduleGenerationResultCategory.PARTIAL_RECOVERY
                if partial
                else models.ScheduleGenerationResultCategory.COMPLETE_SUCCESS
            ),
            projected_completion_date=projected,
            hard_end_date=date.fromisoformat(snapshot["hard_end_date"]),
            blocks=solution.blocks,
            summary=summary,
            recovery_escalation_level=solution.recovery_level,
            adaptation_level=solution.adaptation_level,
            partial_recovery_blocker_type=blocker_type,
            main_blocker_message=blocker_message,
            recommended_actions=actions,
            warnings=(
                ("DEADLINE_RESCUE_WORKLOAD_OVERRIDE",) if solution.workload_override_used else ()
            ),
            metrics={
                **solution.disruption.to_metrics(),
                "candidate_count": solution.candidate_count,
                "variable_count": solution.variable_count,
                "constraint_count": solution.constraint_count,
                "solver_status": solution.solver_status,
                "feasibility_solver_status": solution.feasibility_solver_status,
                "required_recovery_minutes": total_debt,
                "recovered_minutes": solution.recovered_minutes,
                "residual_debt_minutes": remaining,
                "required_curriculum_minutes": solution.required_curriculum_minutes,
                "scheduled_curriculum_minutes": solution.scheduled_curriculum_minutes,
                "construction_duration_ms": solution.construction_duration_ms,
                "solve_duration_ms": solution.solve_duration_ms,
                "feasibility_solve_duration_ms": solution.feasibility_solve_duration_ms,
                "quality_construction_duration_ms": solution.quality_construction_duration_ms,
                "quality_solve_duration_ms": solution.quality_solve_duration_ms,
                "result_extraction_duration_ms": solution.result_extraction_duration_ms,
                **quality_metrics,
                "quality_completed_stage": solution.quality_completed_stage,
                "quality_scope": "ADAPTIVE_REPAIR_SCOPE",
                "quality_optimization_complete": solution.quality_optimization_complete,
                "workload_override_used": solution.workload_override_used,
                "class_overload_count": solution.class_overload_count,
                "class_overload_excess_minutes": solution.class_overload_excess_minutes,
                "teacher_overload_count": solution.teacher_overload_count,
                "teacher_overload_excess_minutes": solution.teacher_overload_excess_minutes,
            },
        )

    @staticmethod
    def _recovery_scope(scope: RecoveryScope) -> _SolveScope:
        return _SolveScope(
            fixed_blocks=scope.fixed_blocks,
            movable_blocks=scope.movable_blocks,
            affected_class_ids=scope.affected_class_ids,
            affected_teacher_ids=scope.affected_teacher_ids,
            recovery_level=scope.level.value,
            adaptation_level=None,
            workload_mode=(
                SolveWorkloadMode.DEADLINE_RESCUE
                if scope.allow_workload_override
                else SolveWorkloadMode.PROTECT_COMFORT
            ),
        )

    @staticmethod
    def _combined_scopes(
        snapshot,
        boundary,
        debt,
        impact,
        curriculum: IncrementalDemandLedger,
    ) -> tuple[_SolveScope, ...]:
        adaptation_scopes = SchedulerChangeAdaptationLadder().scopes(
            boundary,
            impact,
            additional_class_ids={row.class_id for row in curriculum.items},
            additional_teacher_ids={row.teacher_id for row in curriculum.items},
        )
        recovery_scopes = (
            tuple(
                row
                for row in RecoveryEscalationLadder().scopes(boundary, debt)
                if row.level != RecoveryLevel.IMPOSSIBLE
            )
            if any(int(row.get("unresolved_debt_minutes", 0)) > 0 for row in debt.get("items", []))
            else (None,)
        )
        editable = list(boundary.editable_blocks)
        immutable = list(boundary.immutable_blocks)
        current_assignments = {
            (row["class_id"], row["subject_id"])
            for row in snapshot.get("class_subject_requirements", [])
        }
        removed_ids = {
            row["id"]
            for row in editable
            if (row["class_id"], row["subject_id"]) not in current_assignments
        }
        omitted_ids = set(curriculum.omitted_block_ids)
        impact_ids = {row.block["id"] for row in impact.affected if not row.immutable}
        affected_classes = {row.block["class_id"] for row in impact.affected}
        affected_teachers = {row.block["teacher_id"] for row in impact.affected}
        affected_classes.update(row.class_id for row in curriculum.items)
        affected_teachers.update(row.teacher_id for row in curriculum.items)
        combined: list[_SolveScope] = []
        for adaptation in adaptation_scopes:
            if adaptation.level == AdaptationLevel.IMPOSSIBLE:
                continue
            adaptation_ids = {row["id"] for row in adaptation.adaptable_blocks}
            if not impact_ids.issubset(adaptation_ids):
                continue
            for recovery in recovery_scopes:
                recovery_ids = (
                    set() if recovery is None else {row["id"] for row in recovery.movable_blocks}
                )
                movable_ids = (adaptation_ids | recovery_ids) - removed_ids - omitted_ids
                movable = [row for row in editable if row["id"] in movable_ids]
                fixed = immutable + [
                    row
                    for row in editable
                    if (
                        row["id"] not in movable_ids
                        and row["id"] not in removed_ids
                        and row["id"] not in omitted_ids
                    )
                ]
                classes = set(affected_classes)
                teachers = set(affected_teachers)
                if recovery is not None:
                    classes.update(recovery.affected_class_ids)
                    teachers.update(recovery.affected_teacher_ids)
                combined.append(
                    _SolveScope(
                        fixed_blocks=tuple(sorted(fixed, key=lambda row: (row["date"], row["id"]))),
                        movable_blocks=tuple(
                            sorted(movable, key=lambda row: (row["date"], row["id"]))
                        ),
                        affected_class_ids=tuple(sorted(classes)),
                        affected_teacher_ids=tuple(sorted(teachers)),
                        recovery_level=None if recovery is None else recovery.level.value,
                        adaptation_level=adaptation.level.value,
                        workload_mode=(
                            SolveWorkloadMode.QUALITY_ONLY
                            if recovery is None
                            else (
                                SolveWorkloadMode.DEADLINE_RESCUE
                                if recovery.allow_workload_override
                                else SolveWorkloadMode.PROTECT_COMFORT
                            )
                        ),
                        keep_date_and_time=(adaptation.keep_date_and_time and not recovery_ids),
                    )
                )
        return tuple(combined)

    @staticmethod
    def _deduplicate_scopes(scopes: tuple[_SolveScope, ...]) -> tuple[_SolveScope, ...]:
        unique: list[_SolveScope] = []
        seen: set[tuple[Any, ...]] = set()
        for scope in scopes:
            signature = (
                tuple((row.get("id"), row.get("stable_block_key")) for row in scope.fixed_blocks),
                tuple((row.get("id"), row.get("stable_block_key")) for row in scope.movable_blocks),
                scope.workload_mode,
                scope.keep_date_and_time,
            )
            if signature in seen:
                continue
            seen.add(signature)
            unique.append(scope)
        return tuple(unique)

    @staticmethod
    def _better_partial(candidate: _ScopeSolution, current: _ScopeSolution | None) -> bool:
        if current is None:
            return True
        return (
            -candidate.recovered_minutes,
            candidate.scope_rank,
            candidate.disruption.total,
            candidate.workload_cost_minutes,
            candidate.gap_and_availability_cost_minutes,
            candidate.stable_signature,
        ) < (
            -current.recovered_minutes,
            current.scope_rank,
            current.disruption.total,
            current.workload_cost_minutes,
            current.gap_and_availability_cost_minutes,
            current.stable_signature,
        )

    @staticmethod
    def _stability_constrained(boundary) -> bool:
        return any(row.immutable_reason == "STABILITY_WINDOW" for row in boundary.blocks)

    @staticmethod
    def _partial_user_message(
        recovered_minutes: int,
        remaining_minutes: int,
        blocker_message: str,
        actions: tuple[str, ...],
    ) -> str:
        recovered = AdaptiveRepairEngine._hours_label(recovered_minutes)
        remaining = AdaptiveRepairEngine._hours_label(remaining_minutes)
        action_lines = "\n".join(f"- {action}" for action in actions)
        return (
            "Partial recovery generated.\n\n"
            f"{recovered} were recovered, but {remaining} remain unscheduled before "
            "the hard end date.\n\n"
            f"Main blocker:\n{blocker_message}\n\n"
            f"Recommended actions:\n{action_lines}"
        )

    @staticmethod
    def _hours_label(minutes: int) -> str:
        hours = minutes / 60
        value = str(int(hours)) if hours.is_integer() else f"{hours:.2f}".rstrip("0")
        return f"{value}h"

    @staticmethod
    def _slots(
        snapshot: dict[str, Any],
    ) -> tuple[dict[int, tuple[dict[str, Any], ...]], str | None]:
        slots: dict[int, list[dict[str, Any]]] = defaultdict(list)
        seen: set[int] = set()
        for row in snapshot.get("timetable_grid", []):
            start = AdaptiveRepairEngine._minute(row["start_time"])
            end = AdaptiveRepairEngine._minute(row["end_time"])
            if row["id"] in seen or row["day_of_week"] not in range(7) or end <= start:
                return {}, f"Timeslot {row['id']} is invalid or duplicated."
            seen.add(row["id"])
            slots[row["day_of_week"]].append(
                {
                    "id": row["id"],
                    "start": start,
                    "end": end,
                    "valid_from": row.get("valid_from"),
                    "valid_to": row.get("valid_to"),
                }
            )
        if not slots:
            return {}, "No valid timetable slots are configured."
        for weekday, rows in slots.items():
            rows.sort(key=lambda row: (row["start"], row["id"]))
            by_validity: dict[tuple[Any, Any], list[dict[str, Any]]] = {}
            for row in rows:
                by_validity.setdefault((row["valid_from"], row["valid_to"]), []).append(row)
            for validity_rows in by_validity.values():
                if any(
                    current["start"] < previous["end"]
                    for previous, current in zip(validity_rows, validity_rows[1:], strict=False)
                ):
                    return {}, f"Timetable slots overlap on weekday {weekday}."
        return {key: tuple(value) for key, value in slots.items()}, None

    @staticmethod
    def _fixed_intervals(
        blocks: tuple[dict[str, Any], ...],
        slots: dict[int, tuple[dict[str, int], ...]],
    ) -> tuple[dict[tuple[str, int, date], list[tuple[int, int]]], str | None]:
        by_id = {row["id"]: row for rows in slots.values() for row in rows}
        intervals: dict[tuple[str, int, date], list[tuple[int, int]]] = defaultdict(list)
        for block in blocks:
            slot = by_id.get(block["timeslot_id"])
            block_date = date.fromisoformat(block["date"])
            if (
                slot is None
                or block_date.weekday() not in slots
                or slot not in slots[block_date.weekday()]
            ):
                return {}, f"Protected block {block['id']} is outside the current timetable grid."
            for kind, resource_id in (
                ("class", block["class_id"]),
                ("teacher", block["teacher_id"]),
                ("room", block["room_id"]),
            ):
                key = (kind, resource_id, block_date)
                if any(
                    slot["start"] < end and slot["end"] > start for start, end in intervals[key]
                ):
                    return {}, "Protected schedule contains a resource conflict."
                intervals[key].append((slot["start"], slot["end"]))
        return intervals, None

    @staticmethod
    def _conflicts_fixed(
        task: _RepairTask,
        output_date: date,
        start: int,
        end: int,
        room_id: int,
        fixed: dict[tuple[str, int, date], list[tuple[int, int]]],
    ) -> bool:
        return any(
            start < fixed_end and end > fixed_start
            for kind, resource_id in (
                ("class", task.class_id),
                ("teacher", task.teacher_id),
                ("room", room_id),
            )
            for fixed_start, fixed_end in fixed.get((kind, resource_id, output_date), ())
        )

    @staticmethod
    def _add_lunch_constraints(
        model: cp_model.CpModel,
        placements: list[_Placement],
        variables: dict[str, cp_model.IntVar],
        fixed: dict[tuple[str, int, date], list[tuple[int, int]]],
        rule: dict[str, Any] | None,
    ) -> None:
        if not rule or not rule.get("window_start") or not rule.get("window_end"):
            return
        start = AdaptiveRepairEngine._minute(rule["window_start"])
        end = AdaptiveRepairEngine._minute(rule["window_end"])
        minimum = int(rule.get("minimum_minutes") or 0)
        choices = [value for value in range(start, end - minimum + 1, 5)] if minimum > 0 else []
        grouped: dict[tuple[str, int, date], list[_Placement]] = defaultdict(list)
        for row in placements:
            grouped[("class", row.task.class_id, row.output_date)].append(row)
            grouped[("teacher", row.task.teacher_id, row.output_date)].append(row)
        for index, (key, rows) in enumerate(grouped.items()):
            valid_breaks = [
                value
                for value in choices
                if not any(
                    value < fixed_end and value + minimum > fixed_start
                    for fixed_start, fixed_end in fixed.get(key, ())
                )
            ]
            if not valid_breaks:
                model.Add(sum(variables[row.key] for row in rows) == 0)
                continue
            break_vars = [
                model.NewBoolVar(f"lunch_{index}_{offset}") for offset in range(len(valid_breaks))
            ]
            model.AddExactlyOne(break_vars)
            for choice, break_start in zip(break_vars, valid_breaks, strict=False):
                for row in rows:
                    if row.start_minute < break_start + minimum and row.end_minute > break_start:
                        model.Add(variables[row.key] + choice <= 1)

    @staticmethod
    def _disruption_cost(row: _Placement) -> int:
        if row.task.is_recovery:
            return 20
        if row.task.is_curriculum_addition:
            return 0
        before = row.task.source_block
        cost = 0
        if before["date"] != row.output_date.isoformat():
            cost += 800
        elif before["timeslot_id"] != row.timeslot_id:
            cost += 600
        if before["teacher_id"] != row.task.teacher_id:
            cost += 400
        if before["room_id"] != row.room_id:
            cost += 100
        return cost

    @staticmethod
    def _fixed_quality_blocks(
        snapshot: dict[str, Any],
        fixed_blocks: tuple[dict[str, Any], ...],
    ) -> tuple[QualityBlock, ...]:
        availability = {
            (row["teacher_id"], row["timeslot_id"]): int(row["score"])
            for row in snapshot.get("teacher_availability", [])
        }
        policy = SchedulerConstraintPolicy.from_snapshot(snapshot).policy
        result = []
        for block in fixed_blocks:
            output_date = date.fromisoformat(block["date"])
            preference = 0
            if policy is not None:
                preference = policy.evaluate(
                    PlacementFacts(
                        class_id=block["class_id"],
                        subject_id=block["subject_id"],
                        teacher_id=block["teacher_id"],
                        room_id=block["room_id"],
                        output_date=output_date,
                        timeslot_id=block["timeslot_id"],
                    )
                ).preference_tier_adjustment
            score = min(
                2,
                availability.get((block["teacher_id"], block["timeslot_id"]), 1) + preference,
            )
            result.append(
                QualityBlock(
                    class_id=block["class_id"],
                    subject_id=block["subject_id"],
                    teacher_id=block["teacher_id"],
                    room_id=block["room_id"],
                    output_date=output_date,
                    timeslot_id=block["timeslot_id"],
                    duration_minutes=int(block["duration_minutes"]),
                    availability_tier=score,
                    is_recovery_block=bool(block.get("is_recovery_block")),
                )
            )
        return tuple(result)

    @staticmethod
    def _add_comfort_constraints(
        model: cp_model.CpModel,
        snapshot: dict[str, Any],
        scope: _SolveScope,
        placements: list[_Placement],
        variables: dict[str, cp_model.IntVar],
    ) -> None:
        healthy = quality_policy_from_snapshot(snapshot).healthy_class_daily_minutes
        baseline: dict[tuple[str, int, date], int] = defaultdict(int)
        fixed: dict[tuple[str, int, date], int] = defaultdict(int)
        proposed: dict[
            tuple[str, int, date],
            list[tuple[int, cp_model.IntVar]],
        ] = defaultdict(list)
        for block in snapshot.get("active_schedule", []):
            output_date = date.fromisoformat(block["date"])
            for kind, resource_id in (
                ("class", block["class_id"]),
                ("teacher", block["teacher_id"]),
            ):
                baseline[(kind, resource_id, output_date)] += int(block["duration_minutes"])
        for block in scope.fixed_blocks:
            output_date = date.fromisoformat(block["date"])
            for kind, resource_id in (
                ("class", block["class_id"]),
                ("teacher", block["teacher_id"]),
            ):
                fixed[(kind, resource_id, output_date)] += int(block["duration_minutes"])
        for row in placements:
            for kind, resource_id in (
                ("class", row.task.class_id),
                ("teacher", row.task.teacher_id),
            ):
                proposed[(kind, resource_id, row.output_date)].append(
                    (row.task.duration_minutes, variables[row.key])
                )
        for key, terms in proposed.items():
            limit = max(healthy, baseline.get(key, 0))
            model.Add(
                fixed.get(key, 0) + sum(duration * variable for duration, variable in terms)
                <= limit
            )

    @staticmethod
    def _workload_override_metrics(
        snapshot: dict[str, Any],
        blocks: tuple[DraftBlockSpec, ...],
    ) -> dict[str, int]:
        healthy = quality_policy_from_snapshot(snapshot).healthy_class_daily_minutes
        baseline: dict[tuple[str, int, date], int] = defaultdict(int)
        proposed: dict[tuple[str, int, date], int] = defaultdict(int)
        for block in snapshot.get("active_schedule", []):
            output_date = date.fromisoformat(block["date"])
            baseline[("class", block["class_id"], output_date)] += int(block["duration_minutes"])
            baseline[("teacher", block["teacher_id"], output_date)] += int(
                block["duration_minutes"]
            )
        for block in blocks:
            proposed[("class", block.class_id, block.date)] += block.duration_minutes
            proposed[("teacher", block.teacher_id, block.date)] += block.duration_minutes
        result = {
            "class_overload_count": 0,
            "class_overload_excess_minutes": 0,
            "teacher_overload_count": 0,
            "teacher_overload_excess_minutes": 0,
        }
        for key, minutes in proposed.items():
            excess = max(0, minutes - max(healthy, baseline.get(key, 0)))
            if excess:
                prefix = key[0]
                result[f"{prefix}_overload_count"] += 1
                result[f"{prefix}_overload_excess_minutes"] += excess
        return result

    @staticmethod
    def _blocked_dates(rows: list[dict[str, Any]]) -> set[date]:
        blocked: set[date] = set()
        for row in rows:
            current = date.fromisoformat(row["start_date"])
            end = date.fromisoformat(row["end_date"])
            while current <= end:
                blocked.add(current)
                current += timedelta(days=1)
        return blocked

    @staticmethod
    def _spec_dict(row: DraftBlockSpec) -> dict[str, Any]:
        return {
            "stable_block_key": row.stable_block_key,
            "class_id": row.class_id,
            "teacher_id": row.teacher_id,
            "room_id": row.room_id,
            "timeslot_id": row.timeslot_id,
            "date": row.date.isoformat(),
            "is_recovery_block": row.is_recovery_block,
        }

    @staticmethod
    def _solver(seconds: float) -> cp_model.CpSolver:
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = max(0.01, seconds)
        solver.parameters.num_search_workers = 1
        solver.parameters.random_seed = 0
        return solver

    @staticmethod
    def _solver_status_name(status) -> str:
        return {
            cp_model.OPTIMAL: "OPTIMAL",
            cp_model.FEASIBLE: "FEASIBLE",
            cp_model.INFEASIBLE: "INFEASIBLE",
            cp_model.UNKNOWN: "UNKNOWN",
            cp_model.MODEL_INVALID: "MODEL_INVALID",
        }.get(status, str(status))

    @staticmethod
    def _solve_model(
        solver: cp_model.CpSolver,
        model: cp_model.CpModel,
        stop_event: threading.Event,
    ) -> cp_model.CpSolverStatus:
        finished = threading.Event()

        def stop_abandoned_search() -> None:
            while not finished.wait(0.02):
                if stop_event.is_set():
                    solver.StopSearch()
                    return

        watcher = threading.Thread(target=stop_abandoned_search, daemon=True)
        watcher.start()
        try:
            return solver.Solve(model)
        finally:
            finished.set()
            watcher.join(timeout=0.1)

    @staticmethod
    def _stop_requested(deadline_at: datetime, stop_event: threading.Event) -> bool:
        return stop_event.is_set() or datetime.now(UTC) >= deadline_at

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

    @staticmethod
    def _value(value: Any) -> str:
        return str(getattr(value, "value", value))

    @staticmethod
    def _remaining_seconds(context: GenerationExecutionContext) -> float:
        return max(
            0.0,
            (context.solve_deadline_at - datetime.now(UTC)).total_seconds(),
        )


async def run_adaptive_repair(
    context: GenerationExecutionContext,
) -> ValidatedGenerationResult | NoValidGenerationOutput:
    return await AdaptiveRepairEngine().generate(context)
