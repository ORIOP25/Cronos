from app.services.scheduler_editable_boundary import EditableBoundaryBuilder
from app.services.scheduler_recovery_ladder import (
    RecoveryEscalationLadder,
    RecoveryLevel,
)


def _block(block_id, class_id, teacher_id, block_date="2026-03-01"):
    return {
        "id": block_id,
        "class_id": class_id,
        "teacher_id": teacher_id,
        "date": block_date,
        "lesson_log_status": None,
    }


def test_recovery_scopes_escalate_without_unfreezing_immutable_blocks():
    generation = {
        "active_schedule": [
            _block(1, 10, 20, "2026-02-01"),
            _block(2, 10, 21),
            _block(3, 11, 20),
            _block(4, 12, 22),
        ]
    }
    policy = {
        "school_today": "2026-02-10",
        "editable_start_date": "2026-02-10",
        "repair_stability_window_days": 0,
    }
    debt = {
        "items": [
            {
                "class_id": 10,
                "teacher_id": 20,
                "unresolved_debt_minutes": 60,
            }
        ]
    }
    boundary = EditableBoundaryBuilder().build(generation, policy)

    scopes = RecoveryEscalationLadder().scopes(boundary, debt)

    assert [scope.level for scope in scopes] == list(RecoveryLevel)
    assert [row["id"] for row in scopes[0].movable_blocks] == []
    assert [row["id"] for row in scopes[1].movable_blocks] == [2]
    assert [row["id"] for row in scopes[2].movable_blocks] == [2, 3]
    assert [row["id"] for row in scopes[3].movable_blocks] == [2, 3, 4]
    assert scopes[4].allow_workload_override is True
    assert all(
        1 in {row["id"] for row in scope.fixed_blocks}
        for scope in scopes[:-1]
    )
