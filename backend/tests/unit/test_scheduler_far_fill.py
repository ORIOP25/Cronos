from copy import deepcopy
from datetime import date

from ortools.sat.python import cp_model

from app.services.scheduler_candidates import (
    CandidateUniverse,
    CandidateUniverseBuilder,
    PlacementCandidate,
)
from app.services.scheduler_complete_demand import (
    CompleteDemandItem,
    CompleteDemandLedger,
    CompleteDemandLedgerBuilder,
    DemandModule,
)
from app.services.scheduler_far_fill import FarFutureFiller
from tests.unit.test_scheduler_candidates import _snapshot


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
        {"id": 7, "subject_id": 2, "required_minutes": 60, "sequence": 1},
        {"id": 8, "subject_id": 2, "required_minutes": 60, "sequence": 2},
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
        {"id": 7, "subject_id": 2, "required_minutes": 120, "sequence": 1}
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
        {"id": 7, "subject_id": 2, "required_minutes": 60, "sequence": 1}
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


def test_far_fill_incremental_quality_avoids_worsening_an_already_full_day():
    monday = date(2025, 9, 1)
    tuesday = date(2025, 9, 2)
    ledger = CompleteDemandLedger(
        items=(
            CompleteDemandItem(1, 2, 3, "normal", (5,), (DemandModule(1, 1, 300),), 300),
            CompleteDemandItem(9, 2, 4, "normal", (5,), (DemandModule(2, 1, 300),), 300),
        ),
        blockers=(),
    )

    def candidate(class_id, teacher_id, day, slot_id, start):
        return PlacementCandidate(
            candidate_key=f"C{class_id}-D{day}-T{slot_id}",
            class_id=class_id,
            subject_id=2,
            teacher_id=teacher_id,
            room_id=5,
            output_date=day,
            timeslot_id=slot_id,
            start_minute=start,
            end_minute=start + 60,
            duration_minutes=60,
            availability_score=1,
        )

    near = tuple(candidate(9, 4, monday, index, 480 + index * 60) for index in range(1, 5)) + tuple(
        candidate(1, 3, tuesday, 10 + index, 480 + index * 60) for index in range(1, 5)
    )
    far = CandidateUniverse(
        candidates=(
            candidate(1, 3, tuesday, 15, 780),
            candidate(9, 4, tuesday, 15, 780),
        ),
        blockers=(),
        removed_by_reason={},
    )
    snapshot = {
        "lunch_rules": None,
        "timetable_grid": [
            {
                "id": weekday * 10 + index,
                "day_of_week": weekday,
                "start_time": f"{8 + index:02d}:00:00",
                "end_time": f"{9 + index:02d}:00:00",
            }
            for weekday in range(2)
            for index in range(1, 6)
        ],
    }

    assembly = FarFutureFiller().fill(ledger, near, far, snapshot)

    far_blocks = [row for row in assembly.blocks if row.source == "provisional"]
    assert [row.class_id for row in far_blocks] == [9]
    assert any("class 1, subject 2" in row for row in assembly.blockers)


def test_far_fill_post_pass_moves_to_better_availability_on_same_completion_date():
    output_date = date(2025, 9, 1)
    item = CompleteDemandItem(
        1,
        2,
        3,
        "normal",
        (5,),
        (DemandModule(1, 1, 60),),
        60,
    )

    def candidate(slot_id, start, availability):
        return PlacementCandidate(
            candidate_key=f"candidate-{slot_id}",
            class_id=1,
            subject_id=2,
            teacher_id=3,
            room_id=5,
            output_date=output_date,
            timeslot_id=slot_id,
            start_minute=start,
            end_minute=start + 60,
            duration_minutes=60,
            availability_score=availability,
        )

    universe = CandidateUniverse(
        candidates=(candidate(1, 540, 0), candidate(2, 600, 2)),
        blockers=(),
        removed_by_reason={},
    )
    snapshot = {
        "lunch_rules": None,
        "timetable_grid": [
            {"id": 1, "day_of_week": 0, "start_time": "09:00:00", "end_time": "10:00:00"},
            {"id": 2, "day_of_week": 0, "start_time": "10:00:00", "end_time": "11:00:00"},
            {"id": 3, "day_of_week": 0, "start_time": "11:00:00", "end_time": "12:00:00"},
        ],
    }

    assembly = FarFutureFiller().fill(
        CompleteDemandLedger((item,), ()),
        (),
        universe,
        snapshot,
    )

    assert assembly.is_complete is True
    assert [(row.timeslot_id, row.availability_score) for row in assembly.blocks] == [(2, 2)]


def test_far_fill_repairs_greedy_dead_end_with_exact_residual_solver():
    day = date(2025, 9, 1)
    items = (
        CompleteDemandItem(1, 2, 10, "normal", (2,), (DemandModule(2, 1, 60),), 60),
        CompleteDemandItem(1, 3, 11, "normal", (1, 2, 3), (DemandModule(3, 1, 60),), 60),
    )

    def candidate(subject, teacher, slot, room):
        start = 540 if slot == 1 else 660
        return PlacementCandidate(
            candidate_key=f"{subject}-{slot}-{room}",
            class_id=1,
            subject_id=subject,
            teacher_id=teacher,
            room_id=room,
            output_date=day,
            timeslot_id=slot,
            start_minute=start,
            end_minute=start + 60,
            duration_minutes=60,
            availability_score=1,
        )

    universe = CandidateUniverse(
        candidates=(
            candidate(2, 10, 1, 2),
            candidate(2, 10, 3, 2),
            candidate(3, 11, 1, 1),
            candidate(3, 11, 1, 2),
            candidate(3, 11, 1, 3),
        ),
        blockers=(),
        removed_by_reason={},
    )
    assembly = FarFutureFiller().fill(
        CompleteDemandLedger(items, ()),
        (),
        universe,
        {"lunch_rules": None},
    )

    assert assembly.is_complete is True
    assert {(block.subject_id, block.timeslot_id) for block in assembly.blocks} == {(2, 3), (3, 1)}


def test_far_residual_repair_preserves_search_exhaustion_status(monkeypatch):
    day = date(2025, 9, 1)
    item = CompleteDemandItem(1, 2, 10, "normal", (2,), (DemandModule(2, 1, 60),), 60)
    candidate = PlacementCandidate(
        candidate_key="candidate",
        class_id=1,
        subject_id=2,
        teacher_id=10,
        room_id=2,
        output_date=day,
        timeslot_id=1,
        start_minute=540,
        end_minute=600,
        duration_minutes=60,
        availability_score=1,
    )

    class UnknownSolver:
        class _Parameters:
            max_time_in_seconds = 0
            num_search_workers = 0
            random_seed = 0

        parameters = _Parameters()

        def Solve(self, _model):
            return cp_model.UNKNOWN

    monkeypatch.setattr("app.services.scheduler_far_fill.cp_model.CpSolver", UnknownSolver)
    outcome = FarFutureFiller()._repair_residual(
        CompleteDemandLedger((item,), ()),
        (),
        (candidate,),
        {"lunch_rules": None},
        None,
    )

    assert outcome.candidates is None
    assert outcome.status == "search_exhausted"
    assert outcome.raw_status == "UNKNOWN"


def test_far_residual_repair_preserves_scope_and_system_statuses(monkeypatch):
    day = date(2025, 9, 1)
    item = CompleteDemandItem(1, 2, 10, "normal", (2,), (DemandModule(2, 1, 60),), 60)
    candidate = PlacementCandidate(
        candidate_key="candidate",
        class_id=1,
        subject_id=2,
        teacher_id=10,
        room_id=2,
        output_date=day,
        timeslot_id=1,
        start_minute=540,
        end_minute=600,
        duration_minutes=60,
        availability_score=1,
    )

    class StatusSolver:
        status = cp_model.INFEASIBLE

        class _Parameters:
            max_time_in_seconds = 0
            num_search_workers = 0
            random_seed = 0

        parameters = _Parameters()

        def Solve(self, _model):
            return self.status

    monkeypatch.setattr("app.services.scheduler_far_fill.cp_model.CpSolver", StatusSolver)
    outcome = FarFutureFiller()._repair_residual(
        CompleteDemandLedger((item,), ()), (), (candidate,), {"lunch_rules": None}, None
    )
    assert outcome.status == "scope_infeasible"
    assert outcome.raw_status == "INFEASIBLE"

    StatusSolver.status = cp_model.MODEL_INVALID
    outcome = FarFutureFiller()._repair_residual(
        CompleteDemandLedger((item,), ()), (), (candidate,), {"lunch_rules": None}, None
    )
    assert outcome.status == "system_validation_failure"
    assert outcome.raw_status == "MODEL_INVALID"
