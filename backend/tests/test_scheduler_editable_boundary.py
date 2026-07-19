from app.services.scheduler_editable_boundary import (
    IMMUTABLE_EXECUTED,
    IMMUTABLE_PAST,
    IMMUTABLE_STABILITY_WINDOW,
    EditableBoundaryBuilder,
)


def _block(block_id: int, block_date: str, status=None):
    return {
        "id": block_id,
        "date": block_date,
        "lesson_log_status": status,
    }


def test_boundary_freezes_past_executed_and_stability_window():
    generation = {
        "active_schedule": [
            _block(1, "2026-02-09"),
            _block(2, "2026-02-10", "COMPLETED"),
            _block(3, "2026-02-12"),
            _block(4, "2026-02-17"),
        ]
    }
    policy = {
        "school_today": "2026-02-10",
        "editable_start_date": "2026-02-17",
        "repair_stability_window_days": 7,
    }

    boundary = EditableBoundaryBuilder().build(generation, policy)

    reasons = {row.block["id"]: row.immutable_reason for row in boundary.blocks}
    assert reasons == {
        1: IMMUTABLE_PAST,
        2: IMMUTABLE_EXECUTED,
        3: IMMUTABLE_STABILITY_WINDOW,
        4: None,
    }
    assert [row["id"] for row in boundary.editable_blocks] == [4]


def test_zero_day_stability_window_keeps_today_editable():
    generation = {
        "active_schedule": [
            _block(1, "2026-02-09"),
            _block(2, "2026-02-10"),
            _block(3, "2026-02-10", "OCCURRENCE"),
        ]
    }
    policy = {
        "school_today": "2026-02-10",
        "editable_start_date": "2026-02-10",
        "repair_stability_window_days": 0,
    }

    boundary = EditableBoundaryBuilder().build(generation, policy)

    reasons = {row.block["id"]: row.immutable_reason for row in boundary.blocks}
    assert reasons[1] == IMMUTABLE_PAST
    assert reasons[2] is None
    assert reasons[3] == IMMUTABLE_EXECUTED
