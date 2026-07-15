from datetime import date

import pytest
from ortools.sat.python import cp_model

from app.scheduler.domain.quality import (
    QualityBlock,
    QualitySlot,
    ScheduleQualityEvaluator,
    SchedulerQualityPolicy,
)
from app.scheduler.infrastructure.cp_sat_quality import (
    CpSatQualityAdapter,
    SelectableQualityBlock,
)


pytestmark = pytest.mark.unit


def test_daily_excess_and_availability_expressions_match_pure_evaluator():
    evaluator = ScheduleQualityEvaluator(
        SchedulerQualityPolicy(standard_block_minutes=60),
        tuple(QualitySlot(i, 0, i * 60, (i + 1) * 60) for i in range(1, 6)),
    )
    rows = tuple(
        SelectableQualityBlock(
            str(i),
            QualityBlock(1, 2, 3, 4, date(2026, 6, 1), i, 60, 1),
        )
        for i in range(1, 6)
    )
    model = cp_model.CpModel()
    variables = {row.key: model.NewBoolVar(row.key) for row in rows}
    for variable in variables.values():
        model.Add(variable == 1)
    expressions = CpSatQualityAdapter(evaluator).add_expressions(model, rows, variables)
    model.Minimize(expressions.workload_cost + expressions.availability_disutility)
    solver = cp_model.CpSolver()
    assert solver.Solve(model) == cp_model.OPTIMAL

    pure = evaluator.evaluate(row.block for row in rows)
    assert solver.Value(expressions.class_daily_excess) == pure.class_daily_excess_minutes
    assert solver.Value(expressions.teacher_daily_excess) == pure.teacher_daily_excess_minutes
    assert solver.Value(expressions.availability_disutility) == pure.availability_disutility_minutes


def test_all_cp_sat_quality_expressions_match_pure_evaluator_with_fixed_blocks():
    monday = date(2026, 6, 1)
    slots = tuple(
        QualitySlot(weekday * 10 + index, weekday, 480 + index * 60, 540 + index * 60)
        for weekday in range(3)
        for index in range(1, 7)
    )
    evaluator = ScheduleQualityEvaluator(
        SchedulerQualityPolicy(standard_block_minutes=60),
        slots,
        {"window_start": "11:00:00", "window_end": "13:00:00", "minimum_minutes": 60},
    )
    blocks = []
    for weekday in range(3):
        output_date = monday.replace(day=monday.day + weekday)
        for index in (1, 2, 3, 4, 6):
            blocks.append(
                QualityBlock(
                    class_id=1,
                    subject_id=2,
                    teacher_id=3,
                    room_id=5 if weekday == 2 and index == 6 else 4,
                    output_date=output_date,
                    timeslot_id=weekday * 10 + index,
                    duration_minutes=60,
                    availability_tier=1,
                    is_recovery_block=weekday == 0 and index in (1, 2, 3),
                )
            )
    fixed = (blocks[0],)
    rows = tuple(
        SelectableQualityBlock(str(index), block)
        for index, block in enumerate(blocks[1:], start=1)
    )
    model = cp_model.CpModel()
    variables = {row.key: model.NewBoolVar(row.key) for row in rows}
    for variable in variables.values():
        model.Add(variable == 1)
    expressions = CpSatQualityAdapter(evaluator).add_expressions(
        model,
        rows,
        variables,
        fixed,
    )
    model.Minimize(
        expressions.workload_cost
        + expressions.gap_and_availability_cost
        + expressions.room_inconsistency
    )
    solver = cp_model.CpSolver()
    assert solver.Solve(model) == cp_model.OPTIMAL

    pure = evaluator.evaluate(blocks)
    assert solver.Value(expressions.class_daily_excess) == pure.class_daily_excess_minutes
    assert solver.Value(expressions.teacher_daily_excess) == pure.teacher_daily_excess_minutes
    assert solver.Value(expressions.consecutive_excess) == pure.consecutive_excess_minutes
    assert solver.Value(expressions.late_slot_minutes) == pure.late_slot_minutes
    assert solver.Value(expressions.repeated_heavy_penalty) == pure.repeated_heavy_penalty_minutes
    assert solver.Value(expressions.recovery_stack_excess) == pure.recovery_stack_excess_minutes
    assert solver.Value(expressions.class_gap_minutes) == pure.class_gap_minutes
    assert solver.Value(expressions.teacher_gap_minutes) == pure.teacher_gap_minutes
    assert solver.Value(expressions.availability_disutility) == pure.availability_disutility_minutes
    assert solver.Value(expressions.room_inconsistency) == pure.room_inconsistency_count
