from copy import deepcopy
from datetime import date

from app.services.scheduler_candidates import CandidateUniverseBuilder
from app.services.scheduler_complete_demand import CompleteDemandLedgerBuilder
from app.services.scheduler_near_optimizer import NearFutureOptimizer
from tests.test_scheduler_candidates import _snapshot


def _optimize(snapshot: dict):
    ledger = CompleteDemandLedgerBuilder().build(snapshot)
    universe = CandidateUniverseBuilder().build(
        snapshot,
        ledger,
        window_start=date.fromisoformat(snapshot["start_date"]),
        window_end=date.fromisoformat(snapshot["hard_end_date"]),
    )
    return NearFutureOptimizer().optimize(
        universe,
        ledger,
        snapshot,
        max_seconds=3,
    )


def test_optimizer_selects_earliest_feasible_date():
    snapshot = _snapshot()
    snapshot["module_accounting"] = [
        {"id": 7, "subject_id": 2, "required_minutes": 60, "sequence": 1}
    ]
    snapshot["lunch_rules"] = None

    result = _optimize(snapshot)

    assert result.status == "optimal"
    assert result.scheduled_blocks == 1
    assert result.selected[0].output_date == date(2025, 9, 1)


def test_optimizer_prevents_teacher_class_and_room_interval_conflicts():
    snapshot = _snapshot()
    snapshot["hard_end_date"] = "2025-09-01"
    snapshot["lunch_rules"] = None
    snapshot["timetable_grid"] = [
        {
            "id": 10,
            "day_of_week": 0,
            "start_time": "09:00:00",
            "end_time": "10:00:00",
        },
        {
            "id": 12,
            "day_of_week": 0,
            "start_time": "10:00:00",
            "end_time": "11:00:00",
        },
    ]
    snapshot["classes"].append({"id": 9, "size": 20, "grade_level": 10})
    snapshot["class_subject_requirements"].append(
        {"class_id": 9, "subject_id": 2, "grade_level": 10, "teacher_id": 3}
    )
    snapshot["module_accounting"] = [
        {"id": 7, "subject_id": 2, "required_minutes": 60, "sequence": 1}
    ]

    result = _optimize(snapshot)

    assert result.scheduled_blocks == 2
    assert len({row.timeslot_id for row in result.selected}) == 2
    assert len({(row.teacher_id, row.output_date, row.timeslot_id) for row in result.selected}) == 2


def test_optimizer_preserves_aggregate_contiguous_lunch_break():
    snapshot = deepcopy(_snapshot())
    snapshot["hard_end_date"] = "2025-09-01"
    snapshot["timetable_grid"] = [
        {
            "id": 11,
            "day_of_week": 0,
            "start_time": "12:00:00",
            "end_time": "13:00:00",
        },
        {
            "id": 12,
            "day_of_week": 0,
            "start_time": "13:00:00",
            "end_time": "14:00:00",
        },
    ]
    snapshot["module_accounting"] = [
        {"id": 7, "subject_id": 2, "required_minutes": 120, "sequence": 1}
    ]

    result = _optimize(snapshot)

    assert result.scheduled_blocks == 1
    assert result.target_blocks == 2


def test_lower_priority_preference_cannot_weaken_earliest_completion_stage():
    snapshot = _snapshot()
    snapshot["hard_end_date"] = "2025-09-02"
    snapshot["lunch_rules"] = None
    snapshot["timetable_grid"] = [
        {
            "id": 10,
            "day_of_week": 0,
            "start_time": "09:00:00",
            "end_time": "10:00:00",
        },
        {
            "id": 20,
            "day_of_week": 1,
            "start_time": "09:00:00",
            "end_time": "10:00:00",
        },
    ]
    snapshot["teacher_availability"] = [
        {"teacher_id": 3, "timeslot_id": 10, "score": 0},
        {"teacher_id": 3, "timeslot_id": 20, "score": 2},
    ]
    snapshot["module_accounting"] = [
        {"id": 7, "subject_id": 2, "required_minutes": 60, "sequence": 1}
    ]

    result = _optimize(snapshot)

    assert result.status == "optimal"
    assert result.metrics["scheduled_minutes"] == 60
    assert result.selected[0].output_date == date(2025, 9, 1)
    assert result.selected[0].availability_score == 0
