from datetime import date
from itertools import combinations
from random import Random

from app.services.scheduler_candidates import CandidateUniverse, PlacementCandidate
from app.services.scheduler_complete_demand import (
    CompleteDemandItem,
    CompleteDemandLedger,
    DemandModule,
)
from app.services.scheduler_near_optimizer import NearFutureOptimizer


def _ledger(required_minutes: int = 120) -> CompleteDemandLedger:
    item = CompleteDemandItem(
        class_id=1,
        subject_id=2,
        teacher_id=3,
        required_room_type="normal",
        eligible_room_ids=(4,),
        modules=(DemandModule(7, 1, required_minutes),),
        required_minutes=required_minutes,
    )
    return CompleteDemandLedger((item,), ())


def _candidates() -> tuple[PlacementCandidate, ...]:
    return tuple(
        PlacementCandidate(
            candidate_key=f"candidate-{index}",
            class_id=1,
            subject_id=2,
            teacher_id=3,
            room_id=4,
            output_date=date(2025, 9, 1 + (index // 2) * 7),
            timeslot_id=10 + index % 2,
            start_minute=540 + (index % 2) * 60,
            end_minute=600 + (index % 2) * 60,
            duration_minutes=60,
            availability_score=1,
        )
        for index in range(3)
    )


def _oracle_max_minutes(candidates, required_minutes: int) -> int:
    best = 0
    for size in range(len(candidates) + 1):
        for subset in combinations(candidates, size):
            if sum(row.duration_minutes for row in subset) > required_minutes:
                continue
            occupied = set()
            valid = True
            for row in subset:
                key = (row.output_date, row.start_minute)
                if key in occupied:
                    valid = False
                    break
                occupied.add(key)
            if valid:
                best = max(best, sum(row.duration_minutes for row in subset))
    return best


def _optimize(candidates, required_minutes=120):
    return NearFutureOptimizer().optimize(
        CandidateUniverse(tuple(candidates), (), {}),
        _ledger(required_minutes),
        {
            "timetable_grid": [
                {"id": 10, "day_of_week": 0, "start_time": "09:00:00", "end_time": "10:00:00"},
                {"id": 11, "day_of_week": 0, "start_time": "10:00:00", "end_time": "11:00:00"},
            ],
            "lunch_rules": None,
        },
        max_seconds=2,
    )


def test_small_exhaustive_oracle_matches_engine_feasibility():
    candidates = _candidates()
    expected = _oracle_max_minutes(candidates, 120)
    result = _optimize(candidates)

    assert result.metrics["scheduled_minutes"] == expected
    assert result.status == "optimal"


def test_metamorphic_added_capacity_cannot_reduce_feasibility():
    candidates = _candidates()
    baseline = _optimize(candidates[:2], required_minutes=120)
    expanded = _optimize(candidates, required_minutes=120)

    assert expanded.status in {"optimal", "feasible"}
    assert expanded.metrics["scheduled_minutes"] >= baseline.metrics["scheduled_minutes"]


def test_metamorphic_reduced_demand_cannot_require_more_minutes():
    candidates = _candidates()
    baseline = _optimize(candidates, required_minutes=120)
    reduced = _optimize(candidates, required_minutes=60)

    assert reduced.metrics["scheduled_minutes"] <= baseline.metrics["scheduled_minutes"]


def test_metamorphic_input_order_and_id_remapping_preserve_feasibility():
    candidates = _candidates()
    shuffled = list(candidates)
    Random(7).shuffle(shuffled)
    remapped = tuple(
        PlacementCandidate(
            candidate_key=f"remapped-{index}",
            class_id=row.class_id,
            subject_id=row.subject_id,
            teacher_id=row.teacher_id,
            room_id=row.room_id,
            output_date=row.output_date,
            timeslot_id=row.timeslot_id,
            start_minute=row.start_minute,
            end_minute=row.end_minute,
            duration_minutes=row.duration_minutes,
            availability_score=row.availability_score,
        )
        for index, row in enumerate(shuffled)
    )

    baseline = _optimize(candidates)
    remapped_result = _optimize(remapped)

    assert remapped_result.status == baseline.status
    assert remapped_result.metrics["scheduled_minutes"] == baseline.metrics["scheduled_minutes"]
