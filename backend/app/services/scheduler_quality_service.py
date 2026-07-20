from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from typing import Any

from app.scheduler.domain.constraints import SchedulerConstraintPolicy
from app.scheduler.domain.quality import (
    QualityBlock,
    ScheduleQualityEvaluator,
    quality_policy_from_snapshot,
    quality_slots_from_snapshot,
)


def evaluate_target_quality(
    snapshot: dict[str, Any],
    blocks: Iterable[Any],
) -> dict[str, Any]:
    policy = quality_policy_from_snapshot(snapshot)
    slots = quality_slots_from_snapshot(snapshot)
    availability = {
        (row["teacher_id"], row["timeslot_id"]): int(row["score"])
        for row in snapshot.get("teacher_availability", [])
    }
    parsed = SchedulerConstraintPolicy.from_snapshot(snapshot)
    constraints = parsed.policy or SchedulerConstraintPolicy()
    quality_blocks = []
    for block in blocks:
        score = availability.get((block.teacher_id, block.timeslot_id), 1)
        if (block.teacher_id, block.timeslot_id) in constraints.teacher_preferred_timeslots:
            score = min(2, score + 1)
        quality_blocks.append(
            QualityBlock(
                class_id=block.class_id,
                subject_id=block.subject_id,
                teacher_id=block.teacher_id,
                room_id=block.room_id,
                output_date=block.date,
                timeslot_id=block.timeslot_id,
                duration_minutes=block.duration_minutes,
                availability_tier=score,
                is_recovery_block=block.is_recovery_block,
            )
        )
    required: dict[int, int] = defaultdict(int)
    for row in snapshot.get("module_accounting", []):
        subject_id = row.get("subject_id")
        minutes = max(0, int(row.get("required_minutes") or 0))
        for assignment in snapshot.get("class_subject_requirements", []):
            if assignment.get("subject_id") == subject_id:
                required[int(assignment["class_id"])] += minutes
    metrics = ScheduleQualityEvaluator(
        policy,
        slots,
        snapshot.get("lunch_rules"),
    ).evaluate(quality_blocks, required_minutes_by_class=required)
    return metrics.as_dict()
