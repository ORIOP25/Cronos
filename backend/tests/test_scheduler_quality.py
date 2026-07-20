from datetime import date, timedelta

from app.scheduler.domain.quality import (
    AvailabilityTier,
    QualityBlock,
    QualitySlot,
    ScheduleQualityEvaluator,
    SchedulerQualityPolicy,
)

SLOTS = tuple(
    QualitySlot(index + 1, 0, 9 * 60 + index * 60, 10 * 60 + index * 60) for index in range(6)
)
POLICY = SchedulerQualityPolicy.from_durations([45, 60, 60, 120])


def _block(index, *, class_id=1, teacher_id=2, day=date(2026, 6, 1), **kwargs):
    return QualityBlock(
        class_id=class_id,
        subject_id=3,
        teacher_id=teacher_id,
        room_id=kwargs.pop("room_id", 4),
        output_date=day,
        timeslot_id=index,
        duration_minutes=kwargs.pop("duration_minutes", 60),
        **kwargs,
    )


def test_policy_uses_lower_median_and_duration_weighted_daily_excess():
    evaluator = ScheduleQualityEvaluator(POLICY, SLOTS)
    metrics = evaluator.evaluate([_block(i) for i in range(1, 6)])
    assert POLICY.standard_block_minutes == 60
    assert metrics.class_daily_excess_minutes == 60
    assert metrics.teacher_daily_excess_minutes == 60


def test_consecutive_late_recovery_and_availability_costs():
    evaluator = ScheduleQualityEvaluator(POLICY, SLOTS)
    blocks = [
        _block(1, availability_tier=AvailabilityTier.PREFERRED),
        _block(2, availability_tier=AvailabilityTier.NEUTRAL),
        _block(3, availability_tier=AvailabilityTier.AVOID, is_recovery_block=True),
        _block(4, is_recovery_block=True),
        _block(6, is_recovery_block=True),
    ]
    metrics = evaluator.evaluate(blocks)
    assert metrics.consecutive_excess_minutes == 120
    assert metrics.late_slot_minutes == 60
    assert metrics.recovery_stack_excess_minutes == 60
    assert metrics.availability_disutility_minutes == 300


def test_repeated_heavy_days_are_counted_per_iso_week():
    evaluator = ScheduleQualityEvaluator(POLICY, SLOTS)
    blocks = []
    monday = date(2026, 6, 1)
    for offset in range(3):
        day = monday + timedelta(days=offset)
        blocks.extend(_block(i, day=day) for i in range(1, 6))
    metrics = evaluator.evaluate(blocks)
    assert metrics.class_high_load_days == 3
    assert metrics.teacher_high_load_days == 3
    assert metrics.repeated_heavy_penalty_minutes == 120


def test_class_and_teacher_gaps_receive_lunch_credit():
    lunch = {"window_start": "11:00:00", "window_end": "13:00:00", "minimum_minutes": 60}
    evaluator = ScheduleQualityEvaluator(POLICY, SLOTS, lunch)
    metrics = evaluator.evaluate([_block(1), _block(4)])
    assert metrics.class_gap_minutes == 60
    assert metrics.teacher_gap_minutes == 60


def test_completion_spread_progress_room_consistency_and_input_order_independence():
    evaluator = ScheduleQualityEvaluator(POLICY, SLOTS)
    blocks = [
        _block(1, class_id=1, room_id=4),
        _block(2, class_id=1, room_id=5),
        _block(1, class_id=8, teacher_id=9, day=date(2026, 6, 8)),
    ]
    first = evaluator.evaluate(blocks, required_minutes_by_class={1: 240, 8: 60})
    second = evaluator.evaluate(reversed(blocks), required_minutes_by_class={1: 240, 8: 60})
    assert first == second
    assert first.class_completion_spread_days == 7
    assert first.room_inconsistency_count == 1
    assert first.class_progress_per_mille == {1: 500, 8: 1000}
    assert first.minimum_class_progress_per_mille == 500
    assert first.class_progress_spread_per_mille == 500
