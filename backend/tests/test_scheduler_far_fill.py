from copy import deepcopy
from datetime import date

from app.services.scheduler_candidates import CandidateUniverseBuilder
from app.services.scheduler_complete_demand import CompleteDemandLedgerBuilder
from app.services.scheduler_far_fill import FarFutureFiller
from tests.test_scheduler_candidates import _snapshot


def _universes(snapshot: dict):
    ledger = CompleteDemandLedgerBuilder().build(snapshot)
    builder = CandidateUniverseBuilder()
    near = builder.build(
        snapshot,
        ledger,
        window_start=date(2025, 9, 1),
        window_end=date(2025, 9, 1),
    )
    far = builder.build(
        snapshot,
        ledger,
        window_start=date(2025, 9, 2),
        window_end=date.fromisoformat(snapshot["hard_end_date"]),
    )
    return ledger, near, far


def test_far_fill_completes_modules_in_sequence_without_overstatement():
    snapshot = _snapshot()
    snapshot["lunch_rules"] = None
    snapshot["module_accounting"] = [
        {"id": 7, "subject_id": 2, "hours_total": 1, "sequence": 1},
        {"id": 8, "subject_id": 2, "hours_total": 1, "sequence": 2},
    ]
    ledger, near, far = _universes(snapshot)
    near_selected = (near.candidates[0],)

    assembly = FarFutureFiller().fill(
        ledger,
        near_selected,
        far,
        snapshot,
    )

    assert assembly.is_complete is True
    assert assembly.required_minutes == assembly.scheduled_minutes == 120
    assert [row.module_sequence_index for row in assembly.blocks] == [1, 2]
    assert [row.source for row in assembly.blocks] == ["optimized", "provisional"]
    assert assembly.projected_completion_date == date(2025, 9, 15)


def test_far_fill_reports_residual_demand_when_capacity_is_insufficient():
    snapshot = deepcopy(_snapshot())
    snapshot["hard_end_date"] = "2025-09-01"
    snapshot["lunch_rules"] = None
    snapshot["module_accounting"] = [
        {"id": 7, "subject_id": 2, "hours_total": 2, "sequence": 1}
    ]
    ledger, near, far = _universes(snapshot)

    assembly = FarFutureFiller().fill(
        ledger,
        (near.candidates[0],),
        far,
        snapshot,
    )

    assert assembly.is_complete is False
    assert assembly.scheduled_minutes == 60
    assert any("Residual demand of 60 minutes" in row for row in assembly.blockers)


def test_far_fill_keeps_shared_teacher_out_of_overlapping_blocks():
    snapshot = deepcopy(_snapshot())
    snapshot["lunch_rules"] = None
    snapshot["hard_end_date"] = "2025-09-01"
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
        {"id": 7, "subject_id": 2, "hours_total": 1, "sequence": 1}
    ]
    ledger = CompleteDemandLedgerBuilder().build(snapshot)
    universe = CandidateUniverseBuilder().build(
        snapshot,
        ledger,
        window_start=date(2025, 9, 1),
        window_end=date(2025, 9, 1),
    )

    assembly = FarFutureFiller().fill(ledger, (), universe, snapshot)

    assert assembly.is_complete is True
    assert len(assembly.blocks) == 2
    assert len({row.timeslot_id for row in assembly.blocks}) == 2
