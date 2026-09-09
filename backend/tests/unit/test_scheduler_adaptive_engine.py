from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from app import models
from app.services.scheduler_adaptive_engine import AdaptiveRepairEngine
from app.services.scheduler_job_runtime import (
    GenerationExecutionContext,
    GenerationValidationError,
    NoValidGenerationOutput,
    SchedulerJobRuntime,
)


def _snapshot(*, hard_end: str) -> dict:
    return {
        "organization_id": 1,
        "school_year_id": 1,
        "strategy": "ADAPTIVE_REPAIR",
        "start_date": "2026-01-01",
        "hard_end_date": hard_end,
        "scheduler_state_version": 4,
        "approved_scheduler_state_version": 4,
        "timetable_grid": [
            {
                "id": 10,
                "day_of_week": 0,
                "start_time": "09:00:00",
                "end_time": "10:00:00",
            }
        ],
        "calendar_events": [],
        "constraints": [],
        "lunch_rules": None,
        "classes": [{"id": 1, "size": 20}],
        "subjects": [{"id": 2, "required_room_type": "normal"}],
        "teachers": [{"id": 3}],
        "teacher_subject_eligibility": [{"teacher_id": 3, "subject_id": 2}],
        "class_subject_requirements": [{"class_id": 1, "subject_id": 2, "teacher_id": 3}],
        "teacher_availability": [],
        "rooms": [{"id": 4, "capacity": 30, "type": "normal"}],
        "module_accounting": [],
        "active_schedule": [
            {
                "id": 50,
                "schedule_version_id": "v1",
                "stable_block_key": "published-50",
                "class_id": 1,
                "subject_id": 2,
                "teacher_id": 3,
                "room_id": 4,
                "date": "2026-06-01",
                "timeslot_id": 10,
                "duration_minutes": 60,
                "is_recovery_block": False,
                "recovery_source_occurrence_id": None,
                "recovery_source_occurrence_revision": None,
                "lesson_log_status": None,
            }
        ],
    }


def _debt(minutes: int) -> dict:
    return {
        "organization_id": 1,
        "school_year_id": 1,
        "items": [
            {
                "occurrence_id": 70,
                "occurrence_revision": 2,
                "class_id": 1,
                "subject_id": 2,
                "teacher_id": 3,
                "unresolved_debt_minutes": minutes,
            }
        ],
    }


def _context(*, hard_end: str, stability_days: int) -> GenerationExecutionContext:
    now = datetime.now(UTC)
    editable = "2026-06-08" if stability_days else "2026-06-01"
    return GenerationExecutionContext(
        job_id=1,
        organization_id=1,
        school_year_id=1,
        strategy=models.ScheduleGenerationStrategy.ADAPTIVE_REPAIR,
        trigger_type=models.ScheduleGenerationTrigger.EXPLICIT_DEBT,
        immutable_snapshot={
            "generation_input": _snapshot(hard_end=hard_end),
            "debt_basis": _debt(120),
            "repair_policy": {
                "school_today": "2026-06-01",
                "editable_start_date": editable,
                "repair_stability_window_days": stability_days,
            },
        },
        started_at=now,
        deadline_at=now + timedelta(minutes=5),
    )


def _change_context(
    *,
    stability_days: int = 0,
    eligible_replacement: bool = True,
    current_room_valid: bool = False,
) -> GenerationExecutionContext:
    now = datetime.now(UTC)
    snapshot = _snapshot(hard_end="2026-06-15")
    snapshot["scheduler_state_version"] = 5
    snapshot["rooms"][0]["capacity"] = 30 if current_room_valid else 10
    if eligible_replacement:
        snapshot["rooms"].append({"id": 5, "capacity": 30, "type": "normal"})
    return GenerationExecutionContext(
        job_id=2,
        organization_id=1,
        school_year_id=1,
        strategy=models.ScheduleGenerationStrategy.ADAPTIVE_REPAIR,
        trigger_type=models.ScheduleGenerationTrigger.SCHEDULER_CHANGE,
        immutable_snapshot={
            "generation_input": snapshot,
            "debt_basis": None,
            "repair_policy": {
                "school_today": "2026-06-01",
                "editable_start_date": "2026-06-08" if stability_days else "2026-06-01",
                "repair_stability_window_days": stability_days,
            },
        },
        started_at=now,
        deadline_at=now + timedelta(minutes=5),
    )


async def test_full_recovery_produces_complete_target_with_exact_lineage():
    result = await AdaptiveRepairEngine().generate(
        _context(hard_end="2026-06-15", stability_days=7)
    )

    assert result.result_category == models.ScheduleGenerationResultCategory.COMPLETE_SUCCESS
    assert result.summary["recovered_minutes"] == 120
    assert result.summary["remaining_unscheduled_minutes"] == 0
    assert len(result.blocks) == 3
    recovery = [block for block in result.blocks if block.is_recovery_block]
    assert [block.duration_minutes for block in recovery] == [60, 60]
    assert {block.recovery_source_occurrence_id for block in recovery} == {70}
    assert {block.recovery_source_occurrence_revision for block in recovery} == {2}
    assert result.partial_recovery_blocker_type is None


async def test_newly_assigned_subjects_create_complete_module_aware_additions():
    context = _change_context(current_room_valid=True)
    snapshot = context.immutable_snapshot["generation_input"]
    snapshot["subjects"].extend(
        [
            {"id": 6, "required_room_type": "normal"},
            {"id": 7, "required_room_type": "normal"},
        ]
    )
    snapshot["teachers"].extend([{"id": 8}, {"id": 9}])
    snapshot["teacher_subject_eligibility"].extend(
        [
            {"teacher_id": 8, "subject_id": 6},
            {"teacher_id": 9, "subject_id": 7},
        ]
    )
    snapshot["class_subject_requirements"].extend(
        [
            {"class_id": 1, "subject_id": 6, "teacher_id": 8},
            {"class_id": 1, "subject_id": 7, "teacher_id": 9},
        ]
    )
    snapshot["module_accounting"].extend(
        [
            {"id": 16, "subject_id": 6, "required_minutes": 60, "sequence": 1},
            {"id": 18, "subject_id": 6, "required_minutes": 60, "sequence": 2},
            {"id": 17, "subject_id": 7, "required_minutes": 60, "sequence": 1},
        ]
    )
    snapshot["timetable_grid"].append(
        {
            "id": 11,
            "day_of_week": 0,
            "start_time": "10:00:00",
            "end_time": "11:00:00",
        }
    )

    result = await AdaptiveRepairEngine().generate(context)

    assert result.result_category == models.ScheduleGenerationResultCategory.COMPLETE_SUCCESS
    additions = [block for block in result.blocks if block.reason_code == "NEW_CURRICULUM_DEMAND"]
    assert {(block.subject_id, block.teacher_id) for block in additions} == {
        (6, 8),
        (7, 9),
    }
    assert sorted((block.subject_id, block.module_sequence_index) for block in additions) == [
        (6, 1),
        (6, 2),
        (7, 1),
    ]
    subject_six = sorted(
        (block.date, block.timeslot_id, block.module_sequence_index)
        for block in additions
        if block.subject_id == 6
    )
    assert [sequence for _, _, sequence in subject_six] == [1, 2]
    assert all(
        block.change_type == models.ScheduleDraftBlockChangeType.ADDED
        and not block.is_recovery_block
        and block.source_active_block_id is None
        and block.module_sequence_index in {1, 2}
        for block in additions
    )
    assert len({block.stable_block_key for block in additions}) == 3
    assert result.summary["required_curriculum_minutes"] == 180
    assert result.summary["scheduled_curriculum_minutes"] == 180
    assert result.metrics["required_curriculum_minutes"] == 180
    assert result.metrics["scheduled_curriculum_minutes"] == 180
    SchedulerJobRuntime._validate_adaptive_repair(context, result)


async def test_new_curriculum_without_capacity_returns_no_valid_output():
    context = _change_context(current_room_valid=True)
    snapshot = context.immutable_snapshot["generation_input"]
    snapshot["subjects"].append({"id": 6, "required_room_type": "normal"})
    snapshot["teachers"].append({"id": 8})
    snapshot["teacher_subject_eligibility"].append({"teacher_id": 8, "subject_id": 6})
    snapshot["class_subject_requirements"].append({"class_id": 1, "subject_id": 6, "teacher_id": 8})
    snapshot["module_accounting"].append(
        {"id": 16, "subject_id": 6, "required_minutes": 60, "sequence": 1}
    )
    snapshot["hard_end_date"] = "2026-06-01"

    result = await AdaptiveRepairEngine().generate(context)

    assert isinstance(result, NoValidGenerationOutput)
    assert result.metrics["required_curriculum_minutes"] == 60
    assert result.metrics["scheduled_curriculum_minutes"] == 0
    assert any("Curriculum addition" in blocker for blocker in result.blockers)


async def test_mixed_repair_keeps_curriculum_and_explicit_debt_metrics_separate():
    context = _context(hard_end="2026-06-22", stability_days=0)
    snapshot = context.immutable_snapshot["generation_input"]
    snapshot["scheduler_state_version"] = 5
    snapshot["subjects"].append({"id": 6, "required_room_type": "normal"})
    snapshot["teachers"].append({"id": 8})
    snapshot["teacher_subject_eligibility"].append({"teacher_id": 8, "subject_id": 6})
    snapshot["class_subject_requirements"].append({"class_id": 1, "subject_id": 6, "teacher_id": 8})
    snapshot["module_accounting"].append(
        {"id": 16, "subject_id": 6, "required_minutes": 60, "sequence": 1}
    )
    context = replace(
        context,
        trigger_type=models.ScheduleGenerationTrigger.MIXED,
    )

    result = await AdaptiveRepairEngine().generate(context)

    assert result.result_category == models.ScheduleGenerationResultCategory.COMPLETE_SUCCESS
    assert result.summary["recovered_minutes"] == 120
    assert result.summary["remaining_unscheduled_minutes"] == 0
    assert result.summary["required_curriculum_minutes"] == 60
    assert result.summary["scheduled_curriculum_minutes"] == 60
    assert len([block for block in result.blocks if block.is_recovery_block]) == 2
    assert (
        len([block for block in result.blocks if block.reason_code == "NEW_CURRICULUM_DEMAND"]) == 1
    )
    SchedulerJobRuntime._validate_adaptive_repair(context, result)


async def test_runtime_rejects_forged_curriculum_target_that_omits_one_subject():
    context = _change_context(current_room_valid=True)
    snapshot = context.immutable_snapshot["generation_input"]
    snapshot["subjects"].append({"id": 6, "required_room_type": "normal"})
    snapshot["teachers"].append({"id": 8})
    snapshot["teacher_subject_eligibility"].append({"teacher_id": 8, "subject_id": 6})
    snapshot["class_subject_requirements"].append({"class_id": 1, "subject_id": 6, "teacher_id": 8})
    snapshot["module_accounting"].append(
        {"id": 16, "subject_id": 6, "required_minutes": 60, "sequence": 1}
    )
    result = await AdaptiveRepairEngine().generate(context)

    omitted = replace(
        result,
        blocks=tuple(block for block in result.blocks if block.subject_id != 6),
    )
    with pytest.raises(GenerationValidationError, match="incremental curriculum"):
        SchedulerJobRuntime._validate_adaptive_repair(context, omitted)


async def test_partial_recovery_reports_stability_window_blocker_exactly():
    result = await AdaptiveRepairEngine().generate(
        _context(hard_end="2026-06-08", stability_days=7)
    )

    assert result.result_category == models.ScheduleGenerationResultCategory.PARTIAL_RECOVERY
    assert result.summary["message"] == "Partial recovery generated."
    assert result.summary["recovered_minutes"] == 60
    assert result.summary["remaining_unscheduled_minutes"] == 60
    assert result.partial_recovery_blocker_type == "STABILITY_WINDOW"
    assert result.main_blocker_message == (
        "The stability window protects too much of the remaining schedule before the hard end date."
    )
    assert result.recommended_actions == (
        "Reduce the stability window.",
        "Allow broader future schedule changes.",
        "Generate the schedule again.",
    )
    assert result.summary["user_message"] == (
        "Partial recovery generated.\n\n"
        "1h were recovered, but 1h remain unscheduled before the hard end date.\n\n"
        "Main blocker:\n"
        "The stability window protects too much of the remaining schedule before the hard end date.\n\n"
        "Recommended actions:\n"
        "- Reduce the stability window.\n"
        "- Allow broader future schedule changes.\n"
        "- Generate the schedule again."
    )
    assert len(result.summary["escalation_history"]) == 5
    assert len(result.blocks) == 2


async def test_partial_recovery_reports_resource_capacity_without_stability_window():
    result = await AdaptiveRepairEngine().generate(
        _context(hard_end="2026-06-08", stability_days=0)
    )

    assert result.result_category == models.ScheduleGenerationResultCategory.PARTIAL_RECOVERY
    assert result.partial_recovery_blocker_type == "RESOURCE_CAPACITY"
    assert result.main_blocker_message == (
        "The remaining hours cannot fit with the current resources and hard end date."
    )
    assert result.metrics["residual_debt_minutes"] == 60


async def test_runtime_independently_rejects_forged_partial_recovery_metrics():
    context = _context(hard_end="2026-06-08", stability_days=7)
    result = await AdaptiveRepairEngine().generate(context)

    SchedulerJobRuntime._validate_adaptive_repair(context, result)
    forged = replace(
        result,
        summary={**result.summary, "remaining_unscheduled_minutes": 0},
    )
    with pytest.raises(GenerationValidationError, match="debt metrics"):
        SchedulerJobRuntime._validate_adaptive_repair(context, forged)


async def test_runtime_independently_rejects_changed_immutable_block():
    context = _context(hard_end="2026-06-08", stability_days=7)
    result = await AdaptiveRepairEngine().generate(context)
    immutable = result.blocks[0]
    changed = replace(immutable, duration_minutes=30)

    with pytest.raises(GenerationValidationError, match="immutable"):
        SchedulerJobRuntime._validate_adaptive_repair(
            context,
            replace(result, blocks=(changed, *result.blocks[1:])),
        )


async def test_scheduler_change_uses_smallest_same_time_resource_adaptation():
    context = _change_context()

    result = await AdaptiveRepairEngine().generate(context)

    assert result.result_category == models.ScheduleGenerationResultCategory.COMPLETE_SUCCESS
    assert result.adaptation_level == "SAME_TIME_RESOURCE_ADAPTATION"
    assert result.recovery_escalation_level is None
    assert len(result.blocks) == 1
    block = result.blocks[0]
    assert (block.date.isoformat(), block.timeslot_id, block.room_id) == (
        "2026-06-01",
        10,
        5,
    )
    assert block.change_type == models.ScheduleDraftBlockChangeType.ROOM_ONLY
    SchedulerJobRuntime._validate_adaptive_repair(context, result)


async def test_scheduler_change_returns_no_output_when_no_valid_future_exists():
    result = await AdaptiveRepairEngine().generate(_change_context(eligible_replacement=False))

    assert isinstance(result, NoValidGenerationOutput)
    assert any("cannot be re-placed" in blocker for blocker in result.blockers)


async def test_scheduler_change_never_modifies_invalid_protected_block():
    result = await AdaptiveRepairEngine().generate(_change_context(stability_days=7))

    assert isinstance(result, NoValidGenerationOutput)
    assert result.metrics["immutable_invalid_blocks"] == 1
    assert "Immutable block 50" in result.blockers[0]


async def test_relevant_change_can_produce_valid_unchanged_target():
    context = _change_context(
        eligible_replacement=False,
        current_room_valid=True,
    )

    result = await AdaptiveRepairEngine().generate(context)

    assert result.result_category == models.ScheduleGenerationResultCategory.COMPLETE_SUCCESS
    assert result.adaptation_level == "SAME_TIME_RESOURCE_ADAPTATION"
    assert result.blocks[0].change_type == models.ScheduleDraftBlockChangeType.UNCHANGED
    assert result.summary["changed_blocks"] == 0


def _custom_rule_context(rule_type: str, payload: dict) -> GenerationExecutionContext:
    context = _change_context(current_room_valid=True)
    snapshot = context.immutable_snapshot["generation_input"]
    snapshot["constraints"] = [{"rule_type": rule_type, "rule_payload": payload}]
    snapshot["timetable_grid"].extend(
        [
            {
                "id": 11,
                "day_of_week": 0,
                "start_time": "10:00:00",
                "end_time": "11:00:00",
            },
            {
                "id": 12,
                "day_of_week": 1,
                "start_time": "09:00:00",
                "end_time": "10:00:00",
            },
        ]
    )
    return context


async def test_specific_room_constraint_is_detected_and_repaired_at_same_time():
    context = _custom_rule_context(
        "specific_room",
        {"class_id": 1, "subject_id": 2, "room_id": 5},
    )
    result = await AdaptiveRepairEngine().generate(context)

    assert result.adaptation_level == "SAME_TIME_RESOURCE_ADAPTATION"
    assert (result.blocks[0].room_id, result.blocks[0].timeslot_id) == (5, 10)
    assert result.blocks[0].change_type is models.ScheduleDraftBlockChangeType.ROOM_ONLY


async def test_lock_time_constraint_moves_published_block():
    context = _custom_rule_context(
        "lock_time",
        {"class_id": 1, "subject_id": 2, "timeslot_id": 11},
    )
    result = await AdaptiveRepairEngine().generate(context)

    assert result.adaptation_level == "AFFECTED_RESOURCE_CLASS_TEACHER_REFIT"
    assert result.blocks[0].timeslot_id == 11
    assert result.blocks[0].change_type is models.ScheduleDraftBlockChangeType.MOVED


@pytest.mark.parametrize(
    ("payload", "forbidden"),
    [
        ({"teacher_id": 3, "timeslot_id": 10}, lambda block: block.timeslot_id == 10),
        ({"teacher_id": 3, "day_of_week": 0}, lambda block: block.date.weekday() == 0),
        (
            {"teacher_id": 3, "date": "2026-06-01"},
            lambda block: block.date.isoformat() == "2026-06-01",
        ),
        (
            {"teacher_id": 3, "date": "2026-06-01", "timeslot_id": 10},
            lambda block: block.date.isoformat() == "2026-06-01" and block.timeslot_id == 10,
        ),
    ],
)
async def test_teacher_unavailable_selector_is_repaired(payload, forbidden):
    context = _custom_rule_context("teacher_unavailable", payload)
    result = await AdaptiveRepairEngine().generate(context)

    assert result.result_category is models.ScheduleGenerationResultCategory.COMPLETE_SUCCESS
    assert not forbidden(result.blocks[0])
    assert result.blocks[0].change_type is models.ScheduleDraftBlockChangeType.MOVED


async def test_custom_rule_on_immutable_block_returns_no_valid_output_with_code():
    context = _custom_rule_context(
        "teacher_unavailable",
        {"teacher_id": 3, "timeslot_id": 10},
    )
    context = replace(
        context,
        immutable_snapshot={
            **context.immutable_snapshot,
            "repair_policy": {
                "school_today": "2026-06-01",
                "editable_start_date": "2026-06-08",
                "repair_stability_window_days": 7,
            },
        },
    )
    result = await AdaptiveRepairEngine().generate(context)

    assert isinstance(result, NoValidGenerationOutput)
    assert "teacher_unavailable" in result.blockers[0]
