from datetime import date

from app.services.scheduler_candidates import CandidateUniverseBuilder
from app.services.scheduler_complete_demand import CompleteDemandLedgerBuilder
from tests.test_scheduler_complete_demand import _snapshot as demand_snapshot


def _snapshot() -> dict:
    snapshot = demand_snapshot()
    snapshot.update(
        {
            "start_date": "2025-09-01",
            "hard_end_date": "2025-09-15",
            "timetable_grid": [
                {
                    "id": 10,
                    "day_of_week": 0,
                    "start_time": "09:00:00",
                    "end_time": "10:00:00",
                },
                {
                    "id": 11,
                    "day_of_week": 0,
                    "start_time": "12:00:00",
                    "end_time": "14:00:00",
                },
            ],
            "calendar_events": [
                {
                    "start_date": "2025-09-08",
                    "end_date": "2025-09-08",
                    "event_type": "school_break",
                }
            ],
            "teacher_availability": [],
            "lunch_rules": {
                "window_start": "12:00:00",
                "window_end": "14:00:00",
                "minimum_minutes": 60,
            },
        }
    )
    return snapshot


def _build(snapshot: dict, **kwargs):
    ledger = CompleteDemandLedgerBuilder().build(snapshot)
    return CandidateUniverseBuilder().build(
        snapshot,
        ledger,
        window_start=date(2025, 9, 1),
        window_end=date(2025, 9, 15),
        **kwargs,
    )


def test_candidates_use_real_dates_and_prune_calendar_and_lunch():
    universe = _build(_snapshot())

    assert universe.is_usable is True
    assert len(universe.candidates) == 2
    assert {row.output_date for row in universe.candidates} == {
        date(2025, 9, 1),
        date(2025, 9, 15),
    }
    assert {row.room_id for row in universe.candidates} == {4}
    assert universe.removed_by_reason == {"lunch_hard": 2}


def test_candidates_prune_impossible_availability_and_fixed_conflicts():
    snapshot = _snapshot()
    snapshot["teacher_availability"] = [
        {"teacher_id": 3, "timeslot_id": 10, "score": -1}
    ]
    impossible = _build(snapshot)
    assert impossible.is_usable is False
    assert impossible.removed_by_reason["teacher_impossible"] == 2

    snapshot["teacher_availability"] = []
    conflicted = _build(
        snapshot,
        fixed_teacher_conflicts={(3, date(2025, 9, 1), 10)},
    )
    assert {row.output_date for row in conflicted.candidates} == {date(2025, 9, 15)}
    assert conflicted.removed_by_reason["teacher_conflict"] == 1


def test_candidates_apply_hard_scheduler_constraints():
    snapshot = _snapshot()
    snapshot["rooms"].append({"id": 9, "capacity": 30, "type": "normal"})
    snapshot["constraints"] = [
        {
            "rule_type": "specific_room",
            "rule_payload": {"class_id": 1, "subject_id": 2, "room_id": 9},
        },
        {
            "rule_type": "teacher_unavailable",
            "rule_payload": {"teacher_id": 3, "date": "2025-09-01"},
        },
    ]

    universe = _build(snapshot)

    assert universe.is_usable is True
    assert {row.room_id for row in universe.candidates} == {9}
    assert {row.output_date for row in universe.candidates} == {date(2025, 9, 15)}
    assert universe.removed_by_reason["scheduler_constraint"] == 3


def test_candidates_block_unsupported_scheduler_constraints():
    snapshot = _snapshot()
    snapshot["constraints"] = [
        {"rule_type": "min_gap", "rule_payload": {"class_id": 1, "minutes": 30}}
    ]

    universe = _build(snapshot)

    assert universe.is_usable is False
    assert any("not supported" in blocker for blocker in universe.blockers)


def test_candidates_reject_overlapping_or_invalid_timetable_grid():
    snapshot = _snapshot()
    snapshot["timetable_grid"].append(
        {
            "id": 12,
            "day_of_week": 0,
            "start_time": "09:30:00",
            "end_time": "10:30:00",
        }
    )

    universe = _build(snapshot)

    assert universe.is_usable is False
    assert any("overlap" in blocker for blocker in universe.blockers)


def test_candidate_window_is_clamped_to_school_year_and_hard_end():
    snapshot = _snapshot()
    ledger = CompleteDemandLedgerBuilder().build(snapshot)
    universe = CandidateUniverseBuilder().build(
        snapshot,
        ledger,
        window_start=date(2025, 8, 1),
        window_end=date(2025, 10, 1),
    )

    assert all(
        date(2025, 9, 1) <= row.output_date <= date(2025, 9, 15)
        for row in universe.candidates
    )


def test_candidate_universe_stops_at_safe_size_limit():
    snapshot = _snapshot()
    ledger = CompleteDemandLedgerBuilder().build(snapshot)

    universe = CandidateUniverseBuilder().build(
        snapshot,
        ledger,
        window_start=date(2025, 9, 1),
        window_end=date(2025, 9, 15),
        max_candidates=1,
    )

    assert universe.is_usable is False
    assert any("safe solve-size limit" in blocker for blocker in universe.blockers)
