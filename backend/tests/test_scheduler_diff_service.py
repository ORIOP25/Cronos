from datetime import date, datetime, timedelta, timezone

from app import models
from app.services.scheduler_diff_service import SchedulerDiffService
from app.services.scheduler_job_runtime import DraftBlockSpec, GenerationExecutionContext


def _active(block_id: int, key: str, block_date: str) -> dict:
    return {
        "id": block_id,
        "stable_block_key": key,
        "class_id": 1,
        "subject_id": 2,
        "teacher_id": 3,
        "room_id": 4,
        "date": block_date,
        "timeslot_id": 5,
        "duration_minutes": 60,
        "is_recovery_block": False,
        "recovery_source_occurrence_id": None,
        "recovery_source_occurrence_revision": None,
    }


def test_diff_builder_records_moved_and_removed_sides_without_patch_rows():
    now = datetime.now(timezone.utc)
    context = GenerationExecutionContext(
        job_id=9,
        organization_id=1,
        school_year_id=2,
        strategy=models.ScheduleGenerationStrategy.ADAPTIVE_REPAIR,
        trigger_type=models.ScheduleGenerationTrigger.SCHEDULER_CHANGE,
        immutable_snapshot={
            "generation_input": {
                "active_schedule": [
                    _active(10, "kept-and-moved", "2026-06-01"),
                    _active(11, "removed", "2026-06-02"),
                ]
            }
        },
        started_at=now,
        deadline_at=now + timedelta(minutes=5),
    )
    spec = DraftBlockSpec(
        stable_block_key="kept-and-moved",
        source_active_block_id=10,
        class_id=1,
        subject_id=2,
        teacher_id=3,
        room_id=4,
        room_type_id=models.RoomType.normal,
        date=date(2026, 6, 8),
        timeslot_id=5,
        duration_minutes=60,
        change_type=models.ScheduleDraftBlockChangeType.MOVED,
        reason_code="CALENDAR_REFLOW",
    )
    draft = models.ScheduleDraft(id=20)
    target = models.ScheduleDraftBlock(id=30)

    entries = SchedulerDiffService(None).build_entries(
        context,
        draft,
        (spec,),
        [target],
    )

    assert [row.change_type for row in entries] == [
        models.ScheduleDiffChangeType.MOVED,
        models.ScheduleDiffChangeType.REMOVED,
    ]
    moved, removed = entries
    assert moved.before_active_block_id == 10
    assert moved.after_draft_block_id == 30
    assert moved.before_snapshot_json["date"] == "2026-06-01"
    assert moved.after_snapshot_json["date"] == "2026-06-08"
    assert removed.before_active_block_id == 11
    assert removed.after_draft_block_id is None
    assert removed.before_snapshot_json is not None
    assert removed.after_snapshot_json is None
