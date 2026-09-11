from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from math import ceil
from typing import Any

from ortools.sat.python import cp_model

from app.scheduler.domain.quality import (
    IncrementalQualityState,
    QualityBlock,
    ScheduleQualityEvaluator,
    quality_policy_from_snapshot,
    quality_slots_from_snapshot,
)
from app.services.scheduler_candidates import CandidateUniverse, PlacementCandidate
from app.services.scheduler_complete_demand import CompleteDemandItem, CompleteDemandLedger


@dataclass(frozen=True)
class AssembledScheduleBlock:
    stable_block_key: str
    class_id: int
    subject_id: int
    teacher_id: int
    room_id: int
    output_date: date
    timeslot_id: int
    start_minute: int
    end_minute: int
    duration_minutes: int
    module_sequence_index: int
    availability_score: int
    source: str


@dataclass(frozen=True)
class CompleteScheduleAssembly:
    blocks: tuple[AssembledScheduleBlock, ...]
    blockers: tuple[str, ...]
    projected_completion_date: date | None
    required_minutes: int
    scheduled_minutes: int
    residual_repair_status: str | None = None
    residual_repair_solver_status: str | None = None
    residual_repair_variable_count: int | None = None
    residual_repair_constraint_count: int | None = None

    @property
    def is_complete(self) -> bool:
        return self.required_minutes == self.scheduled_minutes and not self.blockers


@dataclass(frozen=True)
class ResidualRepairOutcome:
    candidates: tuple[PlacementCandidate, ...] | None
    status: str
    raw_status: str
    variable_count: int | None = None
    constraint_count: int | None = None


class FarFutureFiller:
    def fill(
        self,
        ledger: CompleteDemandLedger,
        near_selected: tuple[PlacementCandidate, ...],
        far_universe: CandidateUniverse,
        snapshot: dict[str, Any],
        *,
        deadline_at: datetime | None = None,
    ) -> CompleteScheduleAssembly:
        capacity_blockers = {
            "Hard pruning removed every placement candidate.",
            "Candidate window does not intersect the school year.",
        }
        blockers = list(ledger.blockers) + [
            blocker for blocker in far_universe.blockers if blocker not in capacity_blockers
        ]
        items = {(row.class_id, row.subject_id): row for row in ledger.items}
        remaining = {key: item.required_minutes for key, item in items.items()}
        blocks: list[AssembledScheduleBlock] = []
        occupied: dict[tuple[str, int, date], list[tuple[int, int]]] = defaultdict(list)
        lunch = self._lunch_rule(snapshot.get("lunch_rules"))
        preferred_room: dict[tuple[int, int], int] = {}
        quality_evaluator = ScheduleQualityEvaluator(
            quality_policy_from_snapshot(snapshot),
            quality_slots_from_snapshot(snapshot),
            snapshot.get("lunch_rules"),
        )
        quality_state = IncrementalQualityState(quality_evaluator)

        for candidate in sorted(near_selected, key=self._candidate_order):
            placed = self._place(
                candidate,
                "optimized",
                items,
                remaining,
                blocks,
                occupied,
                lunch,
                preferred_room,
            )
            if placed is not None:
                quality_state.add(self._quality_block(placed))

        minimum_duration = min(
            (row.duration_minutes for row in far_universe.candidates),
            default=60,
        )

        time_buckets: dict[tuple[date, int, int, int], list[PlacementCandidate]] = defaultdict(list)
        for candidate in far_universe.candidates:
            time_buckets[
                (
                    candidate.output_date,
                    candidate.start_minute,
                    candidate.end_minute,
                    candidate.timeslot_id,
                )
            ].append(candidate)
        class_required: dict[int, int] = defaultdict(int)
        for item in ledger.items:
            class_required[item.class_id] += item.required_minutes

        timed_out = False
        residual_repair_status: str | None = None
        residual_repair_solver_status: str | None = None
        residual_repair_variable_count: int | None = None
        residual_repair_constraint_count: int | None = None
        for bucket_key in sorted(time_buckets):
            if deadline_at is not None and datetime.now(UTC) >= deadline_at:
                blockers.append("Far-future fill exhausted its time budget.")
                timed_out = True
                break
            bucket = time_buckets[bucket_key]
            while True:
                candidates_by_demand = self._available_opportunity_counts(
                    far_universe.candidates,
                    remaining,
                    occupied,
                    lunch,
                )
                usable = [
                    candidate
                    for candidate in bucket
                    if remaining.get((candidate.class_id, candidate.subject_id), 0) > 0
                    and self._resources_available(candidate, occupied)
                    and self._preserves_lunch(candidate, occupied, lunch)
                ]
                if not usable:
                    break
                candidate = min(
                    usable,
                    key=lambda row: self._far_rank(
                        row,
                        items,
                        remaining,
                        candidates_by_demand,
                        minimum_duration,
                        class_required,
                        quality_state,
                        preferred_room,
                    ),
                )
                placed = self._place(
                    candidate,
                    "provisional",
                    items,
                    remaining,
                    blocks,
                    occupied,
                    lunch,
                    preferred_room,
                )
                if placed is None:
                    break
                quality_state.add(self._quality_block(placed))
            if all(value <= 0 for value in remaining.values()):
                break

        if any(value > 0 for value in remaining.values()):
            repair = self._repair_residual(
                ledger,
                near_selected,
                far_universe.candidates,
                snapshot,
                deadline_at,
            )
            residual_repair_status = repair.status
            residual_repair_solver_status = repair.raw_status
            residual_repair_variable_count = repair.variable_count
            residual_repair_constraint_count = repair.constraint_count
            if repair.candidates is not None:
                remaining = {key: item.required_minutes for key, item in items.items()}
                blocks = []
                occupied = defaultdict(list)
                preferred_room = {}
                for candidate in sorted(
                    (*near_selected, *repair.candidates), key=self._candidate_order
                ):
                    self._place(
                        candidate,
                        "optimized" if candidate in near_selected else "provisional",
                        items,
                        remaining,
                        blocks,
                        occupied,
                        lunch,
                        preferred_room,
                    )

            if repair.status == "search_exhausted":
                blockers.append("Residual repair search exhausted its bounded time budget.")
            elif repair.status == "scope_infeasible":
                blockers.append(
                    "Residual repair scope is infeasible under the current constraints."
                )
            elif repair.status == "system_validation_failure":
                blockers.append("Residual repair model failed system validation.")

        if not timed_out and all(value <= 0 for value in remaining.values()):
            blocks = self._quality_post_pass(
                blocks,
                far_universe.candidates,
                quality_evaluator,
                lunch,
                deadline_at,
            )

        for key, subject_minutes in sorted(remaining.items()):
            residual = max(0, subject_minutes)
            if residual:
                blockers.append(
                    f"Residual demand of {residual} minutes remains for class {key[0]}, subject {key[1]}."
                )
        ordered_blocks = tuple(
            sorted(
                blocks,
                key=lambda row: (
                    row.output_date,
                    row.start_minute,
                    row.class_id,
                    row.subject_id,
                    row.room_id,
                ),
            )
        )
        scheduled_minutes = sum(row.duration_minutes for row in ordered_blocks)
        return CompleteScheduleAssembly(
            blocks=ordered_blocks,
            blockers=tuple(dict.fromkeys(blockers)),
            projected_completion_date=(
                max((row.output_date for row in ordered_blocks), default=None)
            ),
            required_minutes=ledger.required_minutes,
            scheduled_minutes=scheduled_minutes,
            residual_repair_status=residual_repair_status,
            residual_repair_solver_status=residual_repair_solver_status,
            residual_repair_variable_count=residual_repair_variable_count,
            residual_repair_constraint_count=residual_repair_constraint_count,
        )

    def _available_opportunity_counts(
        self,
        candidates: tuple[PlacementCandidate, ...],
        remaining: dict[tuple[int, int], int],
        occupied: dict[tuple[str, int, date], list[tuple[int, int]]],
        lunch: tuple[int, int, int] | None,
    ) -> dict[tuple[int, int], int]:
        """Count usable times, not room variants, against current contention."""

        opportunities: dict[tuple[int, int], set[tuple[date, int, int, int]]] = defaultdict(set)
        for candidate in candidates:
            key = (candidate.class_id, candidate.subject_id)
            if remaining.get(key, 0) <= 0:
                continue
            if not self._resources_available(candidate, occupied):
                continue
            if not self._preserves_lunch(candidate, occupied, lunch):
                continue
            opportunities[key].add(
                (
                    candidate.output_date,
                    candidate.start_minute,
                    candidate.end_minute,
                    candidate.timeslot_id,
                )
            )
        return {key: len(rows) for key, rows in opportunities.items()}

    def _repair_residual(
        self,
        ledger: CompleteDemandLedger,
        near_selected: tuple[PlacementCandidate, ...],
        candidates: tuple[PlacementCandidate, ...],
        snapshot: dict[str, Any],
        deadline_at: datetime | None,
    ) -> ResidualRepairOutcome:
        """Use a bounded exact residual solve after greedy placement strands demand."""

        if not candidates:
            return ResidualRepairOutcome(None, "scope_infeasible", "INFEASIBLE")
        module_remaining = self._module_remaining_after(ledger, near_selected)
        residual = {
            key: sum(values.values())
            for key, values in module_remaining.items()
            if sum(values.values()) > 0
        }
        if not residual:
            return ResidualRepairOutcome((), "optimal", "OPTIMAL")

        occupied: dict[tuple[str, int, date], list[tuple[int, int]]] = defaultdict(list)
        for candidate in near_selected:
            for kind, resource_id in (
                ("class", candidate.class_id),
                ("teacher", candidate.teacher_id),
                ("room", candidate.room_id),
            ):
                occupied[(kind, resource_id, candidate.output_date)].append(
                    (candidate.start_minute, candidate.end_minute)
                )

        options: list[tuple[PlacementCandidate, int, int]] = []
        for candidate in candidates:
            pair = (candidate.class_id, candidate.subject_id)
            if pair not in residual or not self._resources_available(candidate, occupied):
                continue
            for sequence, minutes in module_remaining.get(pair, {}).items():
                if minutes <= 0:
                    continue
                options.append((candidate, sequence, min(candidate.duration_minutes, minutes)))
        if not options:
            return ResidualRepairOutcome(None, "scope_infeasible", "INFEASIBLE")

        model = cp_model.CpModel()
        variables = [model.NewBoolVar(f"far_repair_{index}") for index in range(len(options))]
        by_candidate: dict[str, list[cp_model.IntVar]] = defaultdict(list)
        for variable, (candidate, _sequence, _minutes) in zip(variables, options, strict=True):
            by_candidate[candidate.candidate_key].append(variable)
        for rows in by_candidate.values():
            model.Add(sum(rows) <= 1)

        grouped: dict[tuple[str, int, date], list[cp_model.IntervalVar]] = defaultdict(list)
        for index, (candidate, _sequence, _minutes) in enumerate(options):
            variable = variables[index]
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
                        f"far_repair_{kind}_{index}",
                    )
                )
        for intervals in grouped.values():
            model.AddNoOverlap(intervals)
        self._add_residual_lunch_constraints(
            model,
            options,
            variables,
            occupied,
            snapshot.get("lunch_rules"),
        )
        for pair, modules in module_remaining.items():
            for sequence, minutes in modules.items():
                terms = [
                    credit * variables[index]
                    for index, (candidate, option_sequence, credit) in enumerate(options)
                    if (candidate.class_id, candidate.subject_id) == pair
                    and option_sequence == sequence
                ]
                model.Add(sum(terms) == minutes)

        # Exact residual coverage is primary. Stable candidate order is deterministic.
        tie = sum((index + 1) * variable for index, variable in enumerate(variables))
        model.Minimize(tie)
        solver = cp_model.CpSolver()
        if deadline_at is None:
            solver.parameters.max_time_in_seconds = 2.0
        else:
            solver.parameters.max_time_in_seconds = max(
                0.05,
                min(2.0, (deadline_at - datetime.now(UTC)).total_seconds()),
            )
        solver.parameters.num_search_workers = 1
        solver.parameters.random_seed = 0
        status = solver.Solve(model)
        raw_status = self._solver_status_name(status)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return ResidualRepairOutcome(
                None,
                self._solver_status_label(status),
                raw_status,
                len(model.Proto().variables),
                len(model.Proto().constraints),
            )
        return ResidualRepairOutcome(
            tuple(
                sorted(
                    {
                        options[index][0]
                        for index, variable in enumerate(variables)
                        if solver.Value(variable)
                    },
                    key=self._candidate_order,
                )
            ),
            self._solver_status_label(status),
            raw_status,
            len(model.Proto().variables),
            len(model.Proto().constraints),
        )

    @staticmethod
    def _solver_status_label(status: int) -> str:
        return {
            cp_model.OPTIMAL: "optimal",
            cp_model.FEASIBLE: "feasible",
            cp_model.INFEASIBLE: "scope_infeasible",
            cp_model.UNKNOWN: "search_exhausted",
            cp_model.MODEL_INVALID: "system_validation_failure",
        }.get(status, "search_exhausted")

    @staticmethod
    def _solver_status_name(status: int) -> str:
        return {
            cp_model.OPTIMAL: "OPTIMAL",
            cp_model.FEASIBLE: "FEASIBLE",
            cp_model.INFEASIBLE: "INFEASIBLE",
            cp_model.UNKNOWN: "UNKNOWN",
            cp_model.MODEL_INVALID: "MODEL_INVALID",
        }.get(status, str(status))

    @staticmethod
    def _module_remaining_after(
        ledger: CompleteDemandLedger,
        selected: tuple[PlacementCandidate, ...],
    ) -> dict[tuple[int, int], dict[int, int]]:
        items = {(item.class_id, item.subject_id): item for item in ledger.items}
        remaining = {
            (item.class_id, item.subject_id): {
                module.sequence: module.required_minutes
                for module in item.modules
                if module.required_minutes > 0
            }
            for item in ledger.items
        }
        for candidate in sorted(selected, key=FarFutureFiller._candidate_order):
            pair = (candidate.class_id, candidate.subject_id)
            item = items.get(pair)
            if item is None:
                continue
            modules = remaining.get(pair, {})
            left = min(candidate.duration_minutes, sum(modules.values()))
            for module in item.modules:
                if left <= 0:
                    break
                available = modules.get(module.sequence, 0)
                credit = min(left, available)
                modules[module.sequence] = available - credit
                left -= credit
        return remaining

    def _add_residual_lunch_constraints(
        self,
        model: cp_model.CpModel,
        options: list[tuple[PlacementCandidate, int, int]],
        variables: list[cp_model.IntVar],
        occupied: dict[tuple[str, int, date], list[tuple[int, int]]],
        rule: dict[str, Any] | None,
    ) -> None:
        lunch = self._lunch_rule(rule)
        if lunch is None:
            return
        lunch_start, lunch_end, minimum = lunch
        grouped: dict[tuple[str, int, date], list[tuple[PlacementCandidate, cp_model.IntVar]]] = (
            defaultdict(list)
        )
        for (candidate, _sequence, _credit), variable in zip(options, variables, strict=True):
            grouped[("class", candidate.class_id, candidate.output_date)].append(
                (candidate, variable)
            )
            grouped[("teacher", candidate.teacher_id, candidate.output_date)].append(
                (candidate, variable)
            )
        for group_key, rows in grouped.items():
            starts = sorted(
                {
                    lunch_start,
                    *(
                        candidate.end_minute
                        for candidate, _ in rows
                        if lunch_start <= candidate.end_minute <= lunch_end
                    ),
                }
            )
            starts = [start for start in starts if start + minimum <= lunch_end]
            choices = [
                model.NewBoolVar(f"far_lunch_{group_key[0]}_{group_key[1]}_{index}")
                for index in range(len(starts))
            ]
            if not choices:
                for _candidate, variable in rows:
                    model.Add(variable == 0)
                continue
            model.AddExactlyOne(choices)
            fixed = occupied.get(group_key, ())
            for choice, break_start in zip(choices, starts, strict=True):
                break_end = break_start + minimum
                if any(start < break_end and end > break_start for start, end in fixed):
                    model.Add(choice == 0)
                for candidate, variable in rows:
                    if candidate.start_minute < break_end and candidate.end_minute > break_start:
                        model.Add(variable + choice <= 1)

    def _place(
        self,
        candidate: PlacementCandidate,
        source: str,
        items: dict[tuple[int, int], CompleteDemandItem],
        remaining: dict[tuple[int, int], int],
        blocks: list[AssembledScheduleBlock],
        occupied: dict[tuple[str, int, date], list[tuple[int, int]]],
        lunch: tuple[int, int, int] | None,
        preferred_room: dict[tuple[int, int], int],
    ) -> AssembledScheduleBlock | None:
        key = (candidate.class_id, candidate.subject_id)
        item = items.get(key)
        subject_remaining = remaining.get(key)
        if item is None or subject_remaining is None or subject_remaining <= 0:
            return None
        scheduled_so_far = item.required_minutes - subject_remaining
        module_sequence = self._module_sequence_for_offset(item, scheduled_so_far)
        curriculum_minutes = min(
            candidate.duration_minutes,
            subject_remaining,
            self._module_remaining_for_offset(item, scheduled_so_far),
        )
        remaining[key] = subject_remaining - curriculum_minutes
        placed = AssembledScheduleBlock(
            stable_block_key=f"{candidate.candidate_key}-A{scheduled_so_far}",
            class_id=candidate.class_id,
            subject_id=candidate.subject_id,
            teacher_id=candidate.teacher_id,
            room_id=candidate.room_id,
            output_date=candidate.output_date,
            timeslot_id=candidate.timeslot_id,
            start_minute=candidate.start_minute,
            end_minute=candidate.end_minute,
            duration_minutes=curriculum_minutes,
            module_sequence_index=module_sequence,
            availability_score=candidate.availability_score,
            source=source,
        )
        blocks.append(placed)
        for kind, resource_id in (
            ("class", candidate.class_id),
            ("teacher", candidate.teacher_id),
            ("room", candidate.room_id),
        ):
            occupied[(kind, resource_id, candidate.output_date)].append(
                (candidate.start_minute, candidate.end_minute)
            )
        preferred_room.setdefault(key, candidate.room_id)
        return placed

    def _far_rank(
        self,
        candidate: PlacementCandidate,
        items: dict[tuple[int, int], CompleteDemandItem],
        remaining: dict[tuple[int, int], int],
        candidate_counts: dict[tuple[int, int], int],
        minimum_duration: int,
        class_required: dict[int, int],
        quality_state: IncrementalQualityState,
        preferred_room: dict[tuple[int, int], int],
    ) -> tuple:
        key = (candidate.class_id, candidate.subject_id)
        required_for_class = class_required.get(candidate.class_id, 0)
        remaining_for_class = sum(
            value
            for (class_id, _subject_id), value in remaining.items()
            if class_id == candidate.class_id
        )
        credited_for_class = max(0, required_for_class - remaining_for_class)
        pace = credited_for_class / required_for_class if required_for_class > 0 else 1.0
        item = items[key]
        normalized_remaining = remaining.get(key, 0) / max(1, item.required_minutes)
        predicted = self._quality_candidate(
            candidate,
            self._curriculum_minutes(candidate, item, remaining.get(key, 0)),
        )
        incremental = quality_state.incremental_vector(predicted)
        return (
            self._scarcity(
                candidate,
                items,
                remaining,
                candidate_counts,
                minimum_duration,
            ),
            pace,
            -normalized_remaining,
            incremental[0],
            incremental[1],
            incremental[2],
            0 if preferred_room.get(key) == candidate.room_id else 1,
            candidate.class_id,
            candidate.subject_id,
            candidate.teacher_id,
            candidate.room_id,
        )

    def _quality_post_pass(
        self,
        blocks: list[AssembledScheduleBlock],
        candidates: tuple[PlacementCandidate, ...],
        evaluator: ScheduleQualityEvaluator,
        lunch: tuple[int, int, int] | None,
        deadline_at: datetime | None,
    ) -> list[AssembledScheduleBlock]:
        """Apply bounded, deterministic hard-valid moves that improve quality."""
        if not blocks:
            return blocks
        result = list(blocks)
        projected_completion = max(row.output_date for row in result)
        proposals_left = min(10_000, 20 * len(result))
        alternatives: dict[tuple[int, int], list[PlacementCandidate]] = defaultdict(list)
        for candidate in candidates:
            if candidate.output_date <= projected_completion:
                alternatives[(candidate.class_id, candidate.subject_id)].append(candidate)
        for rows in alternatives.values():
            rows.sort(key=self._candidate_order)

        current_vector = self._quality_vector(evaluator, result)
        movable_keys = tuple(
            row.stable_block_key
            for row in sorted(result, key=self._assembled_order)
            if row.source == "provisional"
        )
        for stable_key in movable_keys:
            index = next(
                (
                    position
                    for position, row in enumerate(result)
                    if row.stable_block_key == stable_key
                ),
                None,
            )
            if index is None:
                continue
            current = result[index]
            for candidate in alternatives.get(
                (current.class_id, current.subject_id),
                (),
            ):
                if proposals_left <= 0:
                    return result
                if deadline_at is not None and datetime.now(UTC) >= deadline_at:
                    return result
                proposals_left -= 1
                if candidate.duration_minutes < current.duration_minutes:
                    continue
                replacement = self._replacement(current, candidate)
                if replacement == current:
                    continue
                proposed = [
                    replacement if position == index else row for position, row in enumerate(result)
                ]
                if not self._assembled_hard_valid(proposed, lunch):
                    continue
                proposed_completion = max(row.output_date for row in proposed)
                if proposed_completion > projected_completion:
                    continue
                proposed_vector = self._quality_vector(evaluator, proposed)
                if proposed_vector < current_vector:
                    result = proposed
                    current_vector = proposed_vector
                    current = replacement
        return result

    def _assembled_hard_valid(
        self,
        blocks: list[AssembledScheduleBlock],
        lunch: tuple[int, int, int] | None,
    ) -> bool:
        occupied: dict[tuple[str, int, date], list[tuple[int, int]]] = defaultdict(list)
        for block in sorted(blocks, key=self._assembled_order):
            candidate = self._candidate_from_block(block)
            if not self._resources_available(candidate, occupied):
                return False
            if not self._preserves_lunch(candidate, occupied, lunch):
                return False
            for kind, resource_id in (
                ("class", block.class_id),
                ("teacher", block.teacher_id),
                ("room", block.room_id),
            ):
                occupied[(kind, resource_id, block.output_date)].append(
                    (block.start_minute, block.end_minute)
                )
        return True

    @staticmethod
    def _quality_vector(
        evaluator: ScheduleQualityEvaluator,
        blocks: list[AssembledScheduleBlock],
    ) -> tuple[int, int, int, tuple]:
        metrics = evaluator.evaluate(FarFutureFiller._quality_block(row) for row in blocks)
        signature = tuple(
            (
                row.output_date.toordinal(),
                row.timeslot_id,
                row.class_id,
                row.subject_id,
                row.room_id,
            )
            for row in sorted(blocks, key=FarFutureFiller._assembled_order)
        )
        return (
            metrics.workload_cost_minutes,
            metrics.gap_and_availability_cost_minutes,
            metrics.room_inconsistency_count,
            signature,
        )

    @staticmethod
    def _quality_block(block: AssembledScheduleBlock) -> QualityBlock:
        return QualityBlock(
            class_id=block.class_id,
            subject_id=block.subject_id,
            teacher_id=block.teacher_id,
            room_id=block.room_id,
            output_date=block.output_date,
            timeslot_id=block.timeslot_id,
            duration_minutes=block.duration_minutes,
            availability_tier=block.availability_score,
        )

    @staticmethod
    def _quality_candidate(
        candidate: PlacementCandidate,
        duration_minutes: int,
    ) -> QualityBlock:
        return QualityBlock(
            class_id=candidate.class_id,
            subject_id=candidate.subject_id,
            teacher_id=candidate.teacher_id,
            room_id=candidate.room_id,
            output_date=candidate.output_date,
            timeslot_id=candidate.timeslot_id,
            duration_minutes=duration_minutes,
            availability_tier=candidate.availability_score,
        )

    @staticmethod
    def _candidate_from_block(block: AssembledScheduleBlock) -> PlacementCandidate:
        return PlacementCandidate(
            candidate_key=block.stable_block_key,
            class_id=block.class_id,
            subject_id=block.subject_id,
            teacher_id=block.teacher_id,
            room_id=block.room_id,
            output_date=block.output_date,
            timeslot_id=block.timeslot_id,
            start_minute=block.start_minute,
            end_minute=block.end_minute,
            duration_minutes=block.end_minute - block.start_minute,
            availability_score=block.availability_score,
        )

    @staticmethod
    def _replacement(
        block: AssembledScheduleBlock,
        candidate: PlacementCandidate,
    ) -> AssembledScheduleBlock:
        return AssembledScheduleBlock(
            stable_block_key=block.stable_block_key,
            class_id=block.class_id,
            subject_id=block.subject_id,
            teacher_id=block.teacher_id,
            room_id=candidate.room_id,
            output_date=candidate.output_date,
            timeslot_id=candidate.timeslot_id,
            start_minute=candidate.start_minute,
            end_minute=candidate.end_minute,
            duration_minutes=block.duration_minutes,
            module_sequence_index=block.module_sequence_index,
            availability_score=candidate.availability_score,
            source=block.source,
        )

    @staticmethod
    def _curriculum_minutes(
        candidate: PlacementCandidate,
        item: CompleteDemandItem,
        subject_remaining: int,
    ) -> int:
        scheduled_so_far = item.required_minutes - subject_remaining
        return min(
            candidate.duration_minutes,
            subject_remaining,
            FarFutureFiller._module_remaining_for_offset(item, scheduled_so_far),
        )

    @staticmethod
    def _assembled_order(block: AssembledScheduleBlock) -> tuple:
        return (
            block.output_date,
            block.start_minute,
            block.class_id,
            block.subject_id,
            block.teacher_id,
            block.room_id,
            block.stable_block_key,
        )

    @staticmethod
    def _resources_available(
        candidate: PlacementCandidate,
        occupied: dict[tuple[str, int, date], list[tuple[int, int]]],
    ) -> bool:
        for kind, resource_id in (
            ("class", candidate.class_id),
            ("teacher", candidate.teacher_id),
            ("room", candidate.room_id),
        ):
            for start, end in occupied[(kind, resource_id, candidate.output_date)]:
                if candidate.start_minute < end and candidate.end_minute > start:
                    return False
        return True

    def _preserves_lunch(
        self,
        candidate: PlacementCandidate,
        occupied: dict[tuple[str, int, date], list[tuple[int, int]]],
        lunch: tuple[int, int, int] | None,
    ) -> bool:
        if lunch is None:
            return True
        for kind, resource_id in (
            ("class", candidate.class_id),
            ("teacher", candidate.teacher_id),
        ):
            intervals = list(occupied[(kind, resource_id, candidate.output_date)])
            intervals.append((candidate.start_minute, candidate.end_minute))
            if not self._has_lunch_gap(intervals, lunch):
                return False
        return True

    @staticmethod
    def _has_lunch_gap(
        intervals: list[tuple[int, int]],
        lunch: tuple[int, int, int],
    ) -> bool:
        lunch_start, lunch_end, minimum = lunch
        clipped = sorted(
            (max(start, lunch_start), min(end, lunch_end))
            for start, end in intervals
            if start < lunch_end and end > lunch_start
        )
        cursor = lunch_start
        for start, end in clipped:
            if start - cursor >= minimum:
                return True
            cursor = max(cursor, end)
        return lunch_end - cursor >= minimum

    @staticmethod
    def _scarcity(
        candidate: PlacementCandidate,
        items: dict[tuple[int, int], CompleteDemandItem],
        remaining: dict[tuple[int, int], int],
        candidate_counts: dict[tuple[int, int], int],
        minimum_duration: int,
    ) -> float:
        key = (candidate.class_id, candidate.subject_id)
        sessions = ceil(max(0, remaining.get(key, 0)) / max(1, minimum_duration))
        return candidate_counts.get(key, 0) / max(1, sessions)

    @staticmethod
    def _candidate_order(candidate: PlacementCandidate) -> tuple:
        return (
            candidate.output_date,
            candidate.start_minute,
            candidate.class_id,
            candidate.subject_id,
            candidate.room_id,
        )

    @staticmethod
    def _module_sequence_for_offset(item: CompleteDemandItem, scheduled_minutes: int) -> int:
        cumulative = 0
        fallback = item.modules[-1].sequence
        for module in item.modules:
            if module.required_minutes <= 0:
                continue
            cumulative += module.required_minutes
            if scheduled_minutes < cumulative:
                return module.sequence
        return fallback

    @staticmethod
    def _module_remaining_for_offset(
        item: CompleteDemandItem,
        scheduled_minutes: int,
    ) -> int:
        cumulative = 0
        for module in item.modules:
            if module.required_minutes <= 0:
                continue
            cumulative += module.required_minutes
            if scheduled_minutes < cumulative:
                return cumulative - scheduled_minutes
        return item.modules[-1].required_minutes

    @staticmethod
    def _lunch_rule(row: dict[str, Any] | None) -> tuple[int, int, int] | None:
        if not row or not row.get("window_start") or not row.get("window_end"):
            return None
        start = FarFutureFiller._minute(row["window_start"])
        end = FarFutureFiller._minute(row["window_end"])
        minimum = int(row.get("minimum_minutes") or 0)
        if end <= start or minimum <= 0:
            return None
        return start, end, minimum

    @staticmethod
    def _minute(value: str | time) -> int:
        parsed = value if isinstance(value, time) else time.fromisoformat(value)
        return parsed.hour * 60 + parsed.minute
