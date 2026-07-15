import pytest

from app.services.scheduler_adaptation_ladder import (
    AdaptationLevel,
    SchedulerChangeAdaptationLadder,
    SchedulerChangeImpactAnalyzer,
)
from app.services.scheduler_editable_boundary import EditableBoundaryBuilder


pytestmark = pytest.mark.unit


def _block(block_id, block_date, room_id=4):
    return {
        "id": block_id,
        "class_id": 1,
        "subject_id": 2,
        "teacher_id": 3,
        "room_id": room_id,
        "date": block_date,
        "timeslot_id": 10,
        "lesson_log_status": None,
    }


def _snapshot():
    return {
        "hard_end_date": "2026-07-15",
        "classes": [{"id": 1, "size": 24}],
        "subjects": [{"id": 2, "required_room_type": "normal"}],
        "teachers": [{"id": 3}],
        "teacher_subject_eligibility": [{"teacher_id": 3, "subject_id": 2}],
        "class_subject_requirements": [
            {"class_id": 1, "subject_id": 2, "teacher_id": 3}
        ],
        "rooms": [{"id": 4, "capacity": 10, "type": "normal"}],
        "timetable_grid": [
            {
                "id": 10,
                "day_of_week": 0,
                "start_time": "09:00:00",
                "end_time": "10:00:00",
            }
        ],
        "teacher_availability": [],
        "calendar_events": [
            {"start_date": "2026-03-09", "end_date": "2026-03-09"}
        ],
        "active_schedule": [
            _block(1, "2026-02-09"),
            _block(2, "2026-03-02"),
            _block(3, "2026-03-09"),
        ],
    }


def test_change_impact_and_adaptation_scopes_preserve_immutable_blocks():
    snapshot = _snapshot()
    boundary = EditableBoundaryBuilder().build(
        snapshot,
        {
            "school_today": "2026-02-10",
            "editable_start_date": "2026-02-10",
            "repair_stability_window_days": 0,
        },
    )

    impact = SchedulerChangeImpactAnalyzer().analyze(snapshot, boundary)
    scopes = SchedulerChangeAdaptationLadder().scopes(boundary, impact)

    assert [scope.level for scope in scopes] == list(AdaptationLevel)
    assert {row.block["id"] for row in impact.affected} == {1, 2, 3}
    assert {row.block["id"] for row in impact.immutable_invalid} == {1}
    assert [row["id"] for row in scopes[0].adaptable_blocks] == [2]
    assert scopes[0].keep_date_and_time is True
    assert [row["id"] for row in scopes[2].adaptable_blocks] == [2, 3]
    assert all(
        1 in {row["id"] for row in scope.fixed_blocks}
        for scope in scopes[:-1]
    )


def test_scheduler_change_can_run_when_current_blocks_remain_valid():
    snapshot = _snapshot()
    snapshot["rooms"][0]["capacity"] = 30
    snapshot["calendar_events"] = []
    snapshot["active_schedule"] = [_block(2, "2026-03-02")]
    boundary = EditableBoundaryBuilder().build(
        snapshot,
        {
            "school_today": "2026-02-10",
            "editable_start_date": "2026-02-10",
            "repair_stability_window_days": 0,
        },
    )

    impact = SchedulerChangeImpactAnalyzer().analyze(snapshot, boundary)
    scopes = SchedulerChangeAdaptationLadder().scopes(boundary, impact)

    assert impact.affected == ()
    assert scopes[0].adaptable_blocks == ()
    assert [row["id"] for row in scopes[3].adaptable_blocks] == [2]


def test_custom_constraint_impact_reports_every_code_and_requires_time_repair():
    snapshot = _snapshot()
    snapshot["rooms"][0]["capacity"] = 30
    snapshot["calendar_events"] = []
    snapshot["active_schedule"] = [_block(2, "2026-03-02")]
    snapshot["constraints"] = [
        {
            "rule_type": "specific_room",
            "rule_payload": {"class_id": 1, "subject_id": 2, "room_id": 9},
        },
        {
            "rule_type": "lock_time",
            "rule_payload": {"class_id": 1, "subject_id": 2, "timeslot_id": 11},
        },
        {
            "rule_type": "teacher_unavailable",
            "rule_payload": {"teacher_id": 3, "date": "2026-03-02"},
        },
    ]
    boundary = EditableBoundaryBuilder().build(
        snapshot,
        {
            "school_today": "2026-02-10",
            "editable_start_date": "2026-02-10",
            "repair_stability_window_days": 0,
        },
    )

    impact = SchedulerChangeImpactAnalyzer().analyze(snapshot, boundary)
    scopes = SchedulerChangeAdaptationLadder().scopes(boundary, impact)

    assert impact.affected[0].violation_codes == (
        "SPECIFIC_ROOM",
        "LOCK_TIME",
        "TEACHER_UNAVAILABLE",
    )
    assert impact.affected[0].category == "TIME"
    assert scopes[0].adaptable_blocks == ()
    assert [row["id"] for row in scopes[1].adaptable_blocks] == [2]
