from copy import deepcopy
from datetime import date

from app.services.scheduler_complete_demand import CompleteDemandLedgerBuilder
from app.services.scheduler_horizon import AdaptiveHorizonSelector
from tests.unit.test_scheduler_candidates import _snapshot


def test_small_school_receives_larger_horizon_than_complex_school():
    small = _snapshot()
    small["hard_end_date"] = "2026-07-15"
    small_ledger = CompleteDemandLedgerBuilder().build(small)

    large = deepcopy(small)
    large["classes"] = [
        {"id": class_id, "size": 24, "grade_level": 10} for class_id in range(1, 31)
    ]
    large["class_subject_requirements"] = [
        {
            "class_id": class_id,
            "subject_id": 2,
            "grade_level": 10,
            "teacher_id": 3,
        }
        for class_id in range(1, 31)
    ]
    large_ledger = CompleteDemandLedgerBuilder().build(large)
    selector = AdaptiveHorizonSelector()

    small_horizon = selector.select(
        small,
        small_ledger,
        start_date=date(2025, 9, 1),
        remaining_solve_seconds=240,
    )
    large_horizon = selector.select(
        large,
        large_ledger,
        start_date=date(2025, 9, 1),
        remaining_solve_seconds=240,
    )

    assert small_horizon.horizon_days > large_horizon.horizon_days
    assert small_horizon.complexity_score < large_horizon.complexity_score


def test_horizon_shrinks_under_candidate_and_time_pressure():
    snapshot = _snapshot()
    snapshot["hard_end_date"] = "2026-07-15"
    snapshot["rooms"] = [
        {"id": room_id, "capacity": 30, "type": "normal"} for room_id in range(1, 101)
    ]
    ledger = CompleteDemandLedgerBuilder().build(snapshot)
    selector = AdaptiveHorizonSelector()

    generous = selector.select(
        snapshot,
        ledger,
        start_date=date(2025, 9, 1),
        remaining_solve_seconds=240,
    )
    constrained = selector.select(
        snapshot,
        ledger,
        start_date=date(2025, 9, 1),
        remaining_solve_seconds=5,
    )

    assert constrained.horizon_days < generous.horizon_days
    assert constrained.horizon_days >= selector.MIN_HORIZON_DAYS


def test_horizon_never_exceeds_remaining_school_year():
    snapshot = _snapshot()
    snapshot["hard_end_date"] = "2025-09-10"
    ledger = CompleteDemandLedgerBuilder().build(snapshot)

    selected = AdaptiveHorizonSelector().select(
        snapshot,
        ledger,
        start_date=date(2025, 9, 8),
        remaining_solve_seconds=240,
    )

    assert selected.horizon_days == 3
    assert selected.end_date == date(2025, 9, 10)
