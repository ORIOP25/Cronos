from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable, Mapping, Sequence

from ortools.sat.python import cp_model

from app.scheduler.domain.quality import (
    QualityBlock,
    QualitySlot,
    ScheduleQualityEvaluator,
    ScheduleQualityMetrics,
)


@dataclass(frozen=True)
class SelectableQualityBlock:
    key: str
    block: QualityBlock


@dataclass(frozen=True)
class CpSatQualityExpressions:
    class_daily_excess: Any
    teacher_daily_excess: Any
    consecutive_excess: Any
    late_slot_minutes: Any
    repeated_heavy_penalty: Any
    recovery_stack_excess: Any
    class_gap_minutes: Any
    teacher_gap_minutes: Any
    availability_disutility: Any
    room_inconsistency: Any

    @property
    def workload_cost(self):
        return (
            self.class_daily_excess
            + self.teacher_daily_excess
            + self.consecutive_excess
            + self.late_slot_minutes
            + self.repeated_heavy_penalty
            + self.recovery_stack_excess
        )

    @property
    def gap_and_availability_cost(self):
        return (
            self.class_gap_minutes
            + self.teacher_gap_minutes
            + self.availability_disutility
        )


@dataclass(frozen=True)
class _ResourceExpressions:
    daily_excess: Any
    consecutive_excess: Any
    repeated_heavy_penalty: Any
    gap_minutes: Any


class CpSatQualityAdapter:
    """CP-SAT representation of the duration-weighted baseline quality policy."""

    def __init__(self, evaluator: ScheduleQualityEvaluator):
        self.evaluator = evaluator

    def add_expressions(
        self,
        model: cp_model.CpModel,
        candidates: Iterable[SelectableQualityBlock],
        variables: Mapping[str, cp_model.IntVar],
        fixed_blocks: Iterable[QualityBlock] = (),
    ) -> CpSatQualityExpressions:
        rows = tuple(candidates)
        fixed = tuple(fixed_blocks)
        class_quality = self._resource_expressions(
            model,
            "class",
            "class_id",
            rows,
            variables,
            fixed,
            self.evaluator.policy.healthy_class_daily_minutes,
        )
        teacher_quality = self._resource_expressions(
            model,
            "teacher",
            "teacher_id",
            rows,
            variables,
            fixed,
            self.evaluator.policy.healthy_teacher_daily_minutes,
        )
        availability = sum(
            self.evaluator._availability_multiplier(row.block.availability_tier)
            * row.block.duration_minutes
            * variables[row.key]
            for row in rows
        ) + sum(
            self.evaluator._availability_multiplier(block.availability_tier)
            * block.duration_minutes
            for block in fixed
        )
        late = self._late_slot_minutes(rows, variables, fixed)
        recovery_stack = self._recovery_stack_excess(model, rows, variables, fixed)
        room_inconsistency = self._room_inconsistency(model, rows, variables, fixed)
        return CpSatQualityExpressions(
            class_daily_excess=class_quality.daily_excess,
            teacher_daily_excess=teacher_quality.daily_excess,
            consecutive_excess=(
                class_quality.consecutive_excess
                + teacher_quality.consecutive_excess
            ),
            late_slot_minutes=late,
            repeated_heavy_penalty=(
                class_quality.repeated_heavy_penalty
                + teacher_quality.repeated_heavy_penalty
            ),
            recovery_stack_excess=recovery_stack,
            class_gap_minutes=class_quality.gap_minutes,
            teacher_gap_minutes=teacher_quality.gap_minutes,
            availability_disutility=availability,
            room_inconsistency=room_inconsistency,
        )

    def _resource_expressions(
        self,
        model: cp_model.CpModel,
        prefix: str,
        attribute: str,
        rows: Sequence[SelectableQualityBlock],
        variables: Mapping[str, cp_model.IntVar],
        fixed: Sequence[QualityBlock],
        healthy_daily: int,
    ) -> _ResourceExpressions:
        variable_loads: dict[tuple[int, date, int], list[Any]] = defaultdict(list)
        fixed_loads: dict[tuple[int, date, int], int] = defaultdict(int)
        resource_days: set[tuple[int, date]] = set()
        for row in rows:
            key = (
                getattr(row.block, attribute),
                row.block.output_date,
                row.block.timeslot_id,
            )
            variable_loads[key].append(row.block.duration_minutes * variables[row.key])
            resource_days.add(key[:2])
        for block in fixed:
            key = (getattr(block, attribute), block.output_date, block.timeslot_id)
            fixed_loads[key] += block.duration_minutes
            resource_days.add(key[:2])

        daily_excesses: list[Any] = []
        run_excesses: list[Any] = []
        gap_totals: list[Any] = []
        heavy_by_week: dict[tuple[int, int, int], list[Any]] = defaultdict(list)
        for day_index, (resource_id, output_date) in enumerate(sorted(resource_days)):
            slots = self.evaluator.slots_by_day.get(output_date.weekday(), ())
            if not slots:
                continue
            occupancies: list[Any] = []
            loads: list[Any] = []
            maximum_daily = 0
            for slot_index, slot in enumerate(slots):
                key = (resource_id, output_date, slot.id)
                terms = variable_loads.get(key, ())
                fixed_minutes = fixed_loads.get(key, 0)
                occupancy = model.NewBoolVar(
                    f"{prefix}_occupied_{day_index}_{slot_index}"
                )
                if fixed_minutes:
                    model.Add(occupancy == 1)
                elif terms:
                    source_variables = self._variables_for_slot(
                        rows,
                        variables,
                        attribute,
                        resource_id,
                        output_date,
                        slot.id,
                    )
                    model.AddMaxEquality(occupancy, source_variables)
                else:
                    model.Add(occupancy == 0)
                load = fixed_minutes + sum(terms)
                occupancies.append(occupancy)
                loads.append(load)
                maximum_daily += fixed_minutes + sum(
                    row.block.duration_minutes
                    for row in rows
                    if getattr(row.block, attribute) == resource_id
                    and row.block.output_date == output_date
                    and row.block.timeslot_id == slot.id
                )

            daily_load = sum(loads)
            daily_excess = model.NewIntVar(
                0,
                max(0, maximum_daily),
                f"{prefix}_daily_excess_{day_index}",
            )
            model.AddMaxEquality(daily_excess, [daily_load - healthy_daily, 0])
            daily_excesses.append(daily_excess)
            heavy = model.NewBoolVar(f"{prefix}_heavy_{day_index}")
            model.Add(daily_load >= healthy_daily + 1).OnlyEnforceIf(heavy)
            model.Add(daily_load <= healthy_daily).OnlyEnforceIf(heavy.Not())
            iso_year, iso_week, _ = output_date.isocalendar()
            heavy_by_week[(resource_id, iso_year, iso_week)].append(heavy)

            run_excesses.extend(
                self._consecutive_run_excess(
                    model,
                    prefix,
                    day_index,
                    slots,
                    occupancies,
                    loads,
                    maximum_daily,
                )
            )
            gap_totals.append(
                self._gap_minutes(
                    model,
                    prefix,
                    day_index,
                    slots,
                    occupancies,
                )
            )

        repeated_heavy: list[Any] = []
        for week_index, values in enumerate(
            heavy_by_week[key] for key in sorted(heavy_by_week)
        ):
            excess = model.NewIntVar(
                0,
                len(values),
                f"{prefix}_repeated_heavy_{week_index}",
            )
            model.AddMaxEquality(excess, [sum(values) - 2, 0])
            repeated_heavy.append(
                self.evaluator.policy.standard_block_minutes * excess
            )
        return _ResourceExpressions(
            daily_excess=sum(daily_excesses),
            consecutive_excess=sum(run_excesses),
            repeated_heavy_penalty=sum(repeated_heavy),
            gap_minutes=sum(gap_totals),
        )

    @staticmethod
    def _variables_for_slot(
        rows,
        variables,
        attribute,
        resource_id,
        output_date,
        timeslot_id,
    ):
        return [
            variables[row.key]
            for row in rows
            if getattr(row.block, attribute) == resource_id
            and row.block.output_date == output_date
            and row.block.timeslot_id == timeslot_id
        ]

    def _consecutive_run_excess(
        self,
        model,
        prefix,
        day_index,
        slots,
        occupancies,
        loads,
        maximum_daily,
    ):
        result = []
        runs = []
        threshold = self.evaluator.policy.healthy_consecutive_minutes
        for index, (slot, occupancy, load) in enumerate(
            zip(slots, occupancies, loads, strict=True)
        ):
            run = model.NewIntVar(0, maximum_daily, f"{prefix}_run_{day_index}_{index}")
            if index == 0 or slots[index - 1].end_minute != slot.start_minute:
                model.Add(run == load).OnlyEnforceIf(occupancy)
                model.Add(run == 0).OnlyEnforceIf(occupancy.Not())
            else:
                previous_occupancy = occupancies[index - 1]
                continuation = self._and(
                    model,
                    occupancy,
                    previous_occupancy,
                    f"{prefix}_continue_{day_index}_{index}",
                )
                model.Add(run == runs[-1] + load).OnlyEnforceIf(continuation)
                model.Add(run == load).OnlyEnforceIf(
                    [occupancy, continuation.Not()]
                )
                model.Add(run == 0).OnlyEnforceIf(occupancy.Not())
            runs.append(run)
            excess = model.NewIntVar(
                0,
                maximum_daily,
                f"{prefix}_run_excess_{day_index}_{index}",
            )
            model.AddMaxEquality(excess, [run - threshold, 0])
            is_end = occupancy
            if index + 1 < len(slots) and slot.end_minute == slots[index + 1].start_minute:
                is_end = self._and_not(
                    model,
                    occupancy,
                    occupancies[index + 1],
                    f"{prefix}_run_end_{day_index}_{index}",
                )
            final_excess = model.NewIntVar(
                0,
                maximum_daily,
                f"{prefix}_final_run_excess_{day_index}_{index}",
            )
            model.Add(final_excess == excess).OnlyEnforceIf(is_end)
            model.Add(final_excess == 0).OnlyEnforceIf(is_end.Not())
            result.append(final_excess)
        return result

    def _gap_minutes(self, model, prefix, day_index, slots, occupancies):
        gap_terms = []
        lunch_terms = []
        for index, slot in enumerate(slots):
            if not index or index == len(slots) - 1:
                continue
            earlier = model.NewBoolVar(f"{prefix}_earlier_{day_index}_{index}")
            later = model.NewBoolVar(f"{prefix}_later_{day_index}_{index}")
            model.AddMaxEquality(earlier, occupancies[:index])
            model.AddMaxEquality(later, occupancies[index + 1 :])
            gap = self._and_three(
                model,
                earlier,
                later,
                occupancies[index].Not(),
                f"{prefix}_gap_{day_index}_{index}",
            )
            gap_terms.append(slot.duration_minutes * gap)
            lunch_overlap = self._lunch_overlap(slot)
            if lunch_overlap:
                lunch_terms.append(lunch_overlap * gap)
        raw_gap = sum(gap_terms)
        if not lunch_terms or not self.evaluator.lunch_rule:
            return raw_gap
        credit_limit = int(self.evaluator.lunch_rule.get("minimum_minutes") or 0)
        credit = model.NewIntVar(
            0,
            credit_limit,
            f"{prefix}_lunch_credit_{day_index}",
        )
        model.AddMinEquality(credit, [sum(lunch_terms), credit_limit])
        return raw_gap - credit

    def _lunch_overlap(self, slot: QualitySlot) -> int:
        if not self.evaluator.lunch_rule:
            return 0
        lunch_start = self.evaluator._minute(
            self.evaluator.lunch_rule.get("window_start")
        )
        lunch_end = self.evaluator._minute(
            self.evaluator.lunch_rule.get("window_end")
        )
        return max(
            0,
            min(slot.end_minute, lunch_end) - max(slot.start_minute, lunch_start),
        )

    def _recovery_stack_excess(self, model, rows, variables, fixed):
        variable_terms: dict[tuple[int, date], list[Any]] = defaultdict(list)
        fixed_minutes: dict[tuple[int, date], int] = defaultdict(int)
        for row in rows:
            if row.block.is_recovery_block:
                variable_terms[(row.block.class_id, row.block.output_date)].append(
                    row.block.duration_minutes * variables[row.key]
                )
        for block in fixed:
            if block.is_recovery_block:
                fixed_minutes[(block.class_id, block.output_date)] += block.duration_minutes
        excesses = []
        for index, key in enumerate(sorted(set(variable_terms) | set(fixed_minutes))):
            maximum = fixed_minutes.get(key, 0) + sum(
                row.block.duration_minutes
                for row in rows
                if row.block.is_recovery_block
                and (row.block.class_id, row.block.output_date) == key
            )
            excess = model.NewIntVar(0, maximum, f"recovery_stack_excess_{index}")
            load = fixed_minutes.get(key, 0) + sum(variable_terms.get(key, ()))
            model.AddMaxEquality(
                excess,
                [load - self.evaluator.policy.healthy_recovery_daily_minutes, 0],
            )
            excesses.append(excess)
        return sum(excesses)

    def _late_slot_minutes(self, rows, variables, fixed):
        late_ids = {
            (weekday, slots[-1].id)
            for weekday, slots in self.evaluator.slots_by_day.items()
            if len(slots) >= 3
        }
        return sum(
            row.block.duration_minutes * variables[row.key]
            for row in rows
            if (row.block.output_date.weekday(), row.block.timeslot_id) in late_ids
        ) + sum(
            block.duration_minutes
            for block in fixed
            if (block.output_date.weekday(), block.timeslot_id) in late_ids
        )

    @staticmethod
    def _room_inconsistency(model, rows, variables, fixed):
        grouped: dict[tuple[int, int, int], list[Any]] = defaultdict(list)
        fixed_rooms: set[tuple[int, int, int]] = set()
        for row in rows:
            grouped[(row.block.class_id, row.block.subject_id, row.block.room_id)].append(
                variables[row.key]
            )
        for block in fixed:
            fixed_rooms.add((block.class_id, block.subject_id, block.room_id))
        pair_rooms: dict[tuple[int, int], list[Any]] = defaultdict(list)
        for index, key in enumerate(sorted(set(grouped) | fixed_rooms)):
            used = model.NewBoolVar(f"quality_room_used_{index}")
            if key in fixed_rooms:
                model.Add(used == 1)
            else:
                model.AddMaxEquality(used, grouped[key])
            pair_rooms[key[:2]].append(used)
        inconsistencies = []
        for index, rooms in enumerate(pair_rooms.values()):
            inconsistency = model.NewIntVar(
                0,
                len(rooms),
                f"quality_room_inconsistency_{index}",
            )
            model.AddMaxEquality(inconsistency, [sum(rooms) - 1, 0])
            inconsistencies.append(inconsistency)
        return sum(inconsistencies)

    @staticmethod
    def _and(model, left, right, name):
        result = model.NewBoolVar(name)
        model.Add(result <= left)
        model.Add(result <= right)
        model.Add(result >= left + right - 1)
        return result

    @staticmethod
    def _and_not(model, left, right, name):
        result = model.NewBoolVar(name)
        model.Add(result <= left)
        model.Add(result + right <= 1)
        model.Add(result >= left - right)
        return result

    @staticmethod
    def _and_three(model, first, second, third, name):
        result = model.NewBoolVar(name)
        model.Add(result <= first)
        model.Add(result <= second)
        model.Add(result <= third)
        model.Add(result >= first + second + third - 2)
        return result

    def evaluate_selected(
        self,
        candidates: Iterable[SelectableQualityBlock],
        values: Mapping[str, int],
        fixed_blocks: Iterable[QualityBlock] = (),
    ) -> ScheduleQualityMetrics:
        selected = [row.block for row in candidates if values.get(row.key, 0)]
        return self.evaluator.evaluate((*fixed_blocks, *selected))
