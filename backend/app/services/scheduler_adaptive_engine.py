from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from ortools.sat.python import cp_model

from app import models
from app.services.scheduler_disruption import DisruptionScore, DisruptionScorer
from app.services.scheduler_adaptation_ladder import (
    AdaptationLevel,
    SchedulerChangeAdaptationLadder,
    SchedulerChangeImpactAnalyzer,
)
from app.services.scheduler_editable_boundary import EditableBoundaryBuilder
from app.services.scheduler_job_runtime import (
    DraftBlockSpec,
    GenerationExecutionContext,
    NoValidGenerationOutput,
    ValidatedGenerationResult,
)
from app.services.scheduler_recovery_ladder import (
    RecoveryEscalationLadder,
    RecoveryLevel,
    RecoveryScope,
)
from app.services.scheduler_repair_trigger import RepairTriggerClassifier


MAX_REPAIR_CANDIDATES = 250_000


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

    @property
    def is_recovery(self) -> bool:
        return self.debt_item is not None


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


@dataclass(frozen=True)
class _SolveScope:
    fixed_blocks: tuple[dict[str, Any], ...]
    movable_blocks: tuple[dict[str, Any], ...]
    affected_class_ids: tuple[int, ...]
    affected_teacher_ids: tuple[int, ...]
    recovery_level: str | None
    adaptation_level: str | None
    keep_date_and_time: bool = False


class AdaptiveRepairEngine:
    async def generate(
        self,
        context: GenerationExecutionContext,
    ) -> ValidatedGenerationResult | NoValidGenerationOutput:
        await context.ensure_can_continue()
        if context.strategy != models.ScheduleGenerationStrategy.ADAPTIVE_REPAIR:
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
        try:
            trigger = RepairTriggerClassifier().classify(
                snapshot,
                debt,
                declared_trigger=context.trigger_type,
            )
            boundary = EditableBoundaryBuilder().build(snapshot, policy)
        except (KeyError, TypeError, ValueError) as exc:
            return NoValidGenerationOutput(blockers=(str(exc),))

        total_debt = trigger.unresolved_debt_minutes
        best: _ScopeSolution | None = None
        failures: list[str] = []
        if trigger.use_adaptation_ladder:
            impact = SchedulerChangeImpactAnalyzer().analyze(snapshot, boundary)
            if impact.immutable_invalid:
                return NoValidGenerationOutput(
                    blockers=tuple(
                        f"Immutable block {row.block['id']}: {' '.join(row.reasons)}"
                        for row in impact.immutable_invalid
                    ),
                    metrics={"immutable_invalid_blocks": len(impact.immutable_invalid)},
                )
            scopes = self._combined_scopes(boundary, debt, impact)
        else:
            scopes = tuple(
                self._recovery_scope(scope)
                for scope in RecoveryEscalationLadder().scopes(boundary, debt)
                if scope.level != RecoveryLevel.IMPOSSIBLE
            )
        for scope in scopes:
            await context.ensure_can_continue()
            if datetime.now(timezone.utc) >= context.solve_deadline_at:
                failures.append("Adaptive repair exhausted its solve time budget.")
                break
            solution, blocker = await asyncio.to_thread(
                self._solve_scope,
                snapshot,
                debt,
                boundary.school_today,
                boundary.editable_start_date,
                scope,
                max_seconds=max(0.05, min(20.0, self._remaining_seconds(context) / 2)),
            )
            await context.ensure_can_continue()
            if blocker:
                level = scope.adaptation_level or scope.recovery_level or "ADAPTIVE_REPAIR"
                failures.append(f"{level}: {blocker}")
            if solution is None:
                continue
            if self._better_partial(solution, best):
                best = solution
            if solution.recovered_minutes == total_debt:
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
            return NoValidGenerationOutput(
                blockers=tuple(failures) or (
                    "No hard-valid adaptive recovery target could be produced.",
                ),
                metrics={"required_recovery_minutes": total_debt},
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
        school_today: date,
        editable_start_date: date,
        scope: _SolveScope,
        *,
        max_seconds: float,
    ) -> tuple[_ScopeSolution | None, str | None]:
        slots, slot_blocker = self._slots(snapshot)
        if slot_blocker:
            return None, slot_blocker
        fixed_intervals, fixed_blocker = self._fixed_intervals(scope.fixed_blocks, slots)
        if fixed_blocker:
            return None, fixed_blocker
        tasks, task_blocker = self._build_tasks(snapshot, debt, scope, slots)
        if task_blocker:
            return None, task_blocker
        placements, placement_blocker = self._build_placements(
            snapshot,
            tasks,
            scope,
            slots,
            fixed_intervals,
            editable_start_date,
        )
        if placement_blocker:
            return None, placement_blocker
        by_task: dict[str, list[_Placement]] = defaultdict(list)
        for placement in placements:
            by_task[placement.task.key].append(placement)
        for task in tasks:
            if not task.is_recovery and not by_task[task.key]:
                return None, f"Published block {task.source_block['id']} cannot be re-placed."

        model = cp_model.CpModel()
        variables = {
            row.key: model.NewBoolVar(f"p_{index}")
            for index, row in enumerate(placements)
        }
        selected_by_task: dict[str, cp_model.IntVar] = {}
        for index, task in enumerate(tasks):
            task_vars = [variables[row.key] for row in by_task[task.key]]
            selected = model.NewBoolVar(f"selected_{index}")
            selected_by_task[task.key] = selected
            if task_vars:
                model.Add(sum(task_vars) == selected)
            else:
                model.Add(selected == 0)
            if not task.is_recovery:
                model.Add(selected == 1)
        recovery_groups: dict[int, list[_RepairTask]] = defaultdict(list)
        for task in tasks:
            if task.is_recovery:
                recovery_groups[int(task.debt_item["occurrence_id"])].append(task)
        for group in recovery_groups.values():
            ordered = sorted(group, key=lambda row: row.recovery_index)
            for previous, current in zip(ordered, ordered[1:]):
                model.Add(selected_by_task[previous.key] >= selected_by_task[current.key])

        grouped_intervals: dict[tuple[str, int, date], list[cp_model.IntervalVar]] = defaultdict(list)
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

        recovered = sum(
            task.duration_minutes * selected_by_task[task.key]
            for task in tasks
            if task.is_recovery
        )
        solver = self._solver(max_seconds / 2)
        model.Maximize(recovered)
        status = solver.Solve(model)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return None, "No hard-valid placement exists at this recovery level."
        best_recovered = int(round(solver.ObjectiveValue()))
        first_values = {key: solver.Value(value) for key, value in variables.items()}
        model.Add(recovered == best_recovered)
        disruption_cost = sum(
            self._placement_cost(row, school_today) * variables[row.key]
            for row in placements
        )
        model.Minimize(disruption_cost)
        solver = self._solver(max_seconds / 2)
        second_status = solver.Solve(model)
        values = (
            {key: solver.Value(value) for key, value in variables.items()}
            if second_status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
            else first_values
        )
        chosen = [row for row in placements if values.get(row.key, 0)]
        blocks = self._specs(snapshot, scope.fixed_blocks, chosen)
        proposed = [self._spec_dict(row) for row in blocks]
        disruption = DisruptionScorer().score(
            snapshot.get("active_schedule", []),
            proposed,
            school_today=school_today,
            affected_class_ids=set(scope.affected_class_ids),
            affected_teacher_ids=set(scope.affected_teacher_ids),
        )
        return (
            _ScopeSolution(
                blocks=blocks,
                recovered_minutes=best_recovered,
                disruption=disruption,
                recovery_level=scope.recovery_level,
                adaptation_level=scope.adaptation_level,
                solver_status=(
                    "optimal" if second_status == cp_model.OPTIMAL else "feasible"
                ),
                candidate_count=len(placements),
            ),
            None,
        )

    def _build_tasks(
        self,
        snapshot: dict[str, Any],
        debt: dict[str, Any],
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
                )
            )
        minimum_slot = min(
            row["end"] - row["start"]
            for rows in slots.values()
            for row in rows
        )
        for item in debt.get("items", []):
            remaining = max(0, int(item.get("unresolved_debt_minutes", 0)))
            index = 0
            while remaining:
                duration = min(minimum_slot, remaining)
                tasks.append(
                    _RepairTask(
                        key=(
                            f"R-{item['occurrence_id']}-"
                            f"{item['occurrence_revision']}-{index}"
                        ),
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
            class_row = classes.get(task.class_id)
            subject_row = subjects.get(task.subject_id)
            if (
                class_row is None
                or subject_row is None
                or task.teacher_id not in teachers
                or (task.teacher_id, task.subject_id) not in qualifications
            ):
                if task.is_recovery:
                    continue
                return [], (
                    f"Movable block {task.source_block['id']} has no eligible assignment."
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
                if self._date_allowed(task, current, scope, blocked_dates):
                    for slot in slots.get(current.weekday(), ()):
                        if not self._slot_allowed(task, slot, scope):
                            continue
                        score = availability.get((task.teacher_id, slot["id"]), 1)
                        if score == -1:
                            continue
                        for room_id in eligible_rooms:
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
                                        f"{task.key}-{current.isoformat()}-"
                                        f"{slot['id']}-{room_id}"
                                    ),
                                    task=task,
                                    output_date=current,
                                    timeslot_id=slot["id"],
                                    room_id=room_id,
                                    start_minute=slot["start"],
                                    end_minute=slot["end"],
                                    availability_score=score,
                                )
                            )
                            if len(placements) > MAX_REPAIR_CANDIDATES:
                                return [], "Adaptive repair candidate limit was exceeded."
                current += timedelta(days=1)
        return placements, None

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
        slot: dict[str, int],
        scope: _SolveScope,
    ) -> bool:
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
        for row in chosen:
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
            before = task.source_block
            if before["date"] != row.output_date.isoformat() or before["timeslot_id"] != row.timeslot_id:
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
                    change_type=change,
                    is_recovery_block=bool(before.get("is_recovery_block")),
                    recovery_source_occurrence_id=before.get("recovery_source_occurrence_id"),
                    recovery_source_occurrence_revision=before.get("recovery_source_occurrence_revision"),
                    reason_code="RECOVERY_SCOPE_REFIT" if change.value != "UNCHANGED" else None,
                )
            )
        return tuple(sorted(specs, key=lambda row: (row.date, row.timeslot_id, row.stable_block_key)))

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
        projected = max(row.date for row in solution.blocks)
        summary = {
            "message": "Partial recovery generated." if partial else "Full recovery generated.",
            "trigger_summary": trigger_summary,
            "recovered_minutes": solution.recovered_minutes,
            "remaining_unscheduled_minutes": remaining,
            "recovered_hours": solution.recovered_minutes / 60,
            "remaining_unscheduled_hours": remaining / 60,
            "recovery_escalation_level": solution.recovery_level,
            "adaptation_level": solution.adaptation_level,
            "escalation_history": list(escalation_history),
            **solution.disruption.to_metrics(),
        }
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
            metrics={
                **solution.disruption.to_metrics(),
                "candidate_count": solution.candidate_count,
                "solver_status": solution.solver_status,
                "required_recovery_minutes": total_debt,
                "recovered_minutes": solution.recovered_minutes,
                "residual_debt_minutes": remaining,
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
        )

    @staticmethod
    def _combined_scopes(boundary, debt, impact) -> tuple[_SolveScope, ...]:
        adaptation_scopes = SchedulerChangeAdaptationLadder().scopes(boundary, impact)
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
        impact_ids = {row.block["id"] for row in impact.affected if not row.immutable}
        affected_classes = {row.block["class_id"] for row in impact.affected}
        affected_teachers = {row.block["teacher_id"] for row in impact.affected}
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
                movable_ids = adaptation_ids | recovery_ids
                movable = [row for row in editable if row["id"] in movable_ids]
                fixed = immutable + [row for row in editable if row["id"] not in movable_ids]
                classes = set(affected_classes)
                teachers = set(affected_teachers)
                if recovery is not None:
                    classes.update(recovery.affected_class_ids)
                    teachers.update(recovery.affected_teacher_ids)
                combined.append(
                    _SolveScope(
                        fixed_blocks=tuple(sorted(fixed, key=lambda row: (row["date"], row["id"]))),
                        movable_blocks=tuple(sorted(movable, key=lambda row: (row["date"], row["id"]))),
                        affected_class_ids=tuple(sorted(classes)),
                        affected_teacher_ids=tuple(sorted(teachers)),
                        recovery_level=None if recovery is None else recovery.level.value,
                        adaptation_level=adaptation.level.value,
                        keep_date_and_time=(
                            adaptation.keep_date_and_time and not recovery_ids
                        ),
                    )
                )
        return tuple(combined)

    @staticmethod
    def _better_partial(candidate: _ScopeSolution, current: _ScopeSolution | None) -> bool:
        return current is None or (
            candidate.recovered_minutes,
            -candidate.disruption.total,
        ) > (
            current.recovered_minutes,
            -current.disruption.total,
        )

    @staticmethod
    def _stability_constrained(boundary) -> bool:
        return any(
            row.immutable_reason == "STABILITY_WINDOW"
            for row in boundary.blocks
        )

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
    def _slots(snapshot: dict[str, Any]) -> tuple[dict[int, tuple[dict[str, int], ...]], str | None]:
        slots: dict[int, list[dict[str, int]]] = defaultdict(list)
        seen: set[int] = set()
        for row in snapshot.get("timetable_grid", []):
            start = AdaptiveRepairEngine._minute(row["start_time"])
            end = AdaptiveRepairEngine._minute(row["end_time"])
            if row["id"] in seen or row["day_of_week"] not in range(7) or end <= start:
                return {}, f"Timeslot {row['id']} is invalid or duplicated."
            seen.add(row["id"])
            slots[row["day_of_week"]].append({"id": row["id"], "start": start, "end": end})
        if not slots:
            return {}, "No valid timetable slots are configured."
        for weekday, rows in slots.items():
            rows.sort(key=lambda row: (row["start"], row["id"]))
            if any(current["start"] < previous["end"] for previous, current in zip(rows, rows[1:])):
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
            if slot is None or block_date.weekday() not in slots or slot not in slots[block_date.weekday()]:
                return {}, f"Protected block {block['id']} is outside the current timetable grid."
            for kind, resource_id in (
                ("class", block["class_id"]),
                ("teacher", block["teacher_id"]),
                ("room", block["room_id"]),
            ):
                key = (kind, resource_id, block_date)
                if any(slot["start"] < end and slot["end"] > start for start, end in intervals[key]):
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
                if not any(value < fixed_end and value + minimum > fixed_start for fixed_start, fixed_end in fixed.get(key, ()))
            ]
            if not valid_breaks:
                model.Add(sum(variables[row.key] for row in rows) == 0)
                continue
            break_vars = [model.NewBoolVar(f"lunch_{index}_{offset}") for offset in range(len(valid_breaks))]
            model.AddExactlyOne(break_vars)
            for choice, break_start in zip(break_vars, valid_breaks):
                for row in rows:
                    if row.start_minute < break_start + minimum and row.end_minute > break_start:
                        model.Add(variables[row.key] + choice <= 1)

    @staticmethod
    def _placement_cost(row: _Placement, school_today: date) -> int:
        if row.task.is_recovery:
            return 20 + max(0, (row.output_date - school_today).days)
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
        return cost - max(-10, min(10, row.availability_score))

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
        solver.parameters.max_time_in_seconds = max(0.05, seconds)
        solver.parameters.num_search_workers = 1
        solver.parameters.random_seed = 0
        return solver

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
            (context.solve_deadline_at - datetime.now(timezone.utc)).total_seconds(),
        )


async def run_adaptive_repair(
    context: GenerationExecutionContext,
) -> ValidatedGenerationResult | NoValidGenerationOutput:
    return await AdaptiveRepairEngine().generate(context)
