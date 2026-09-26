from datetime import time

import pytest
from pydantic import ValidationError

from app import schemas
from app.services.foundation_service import (
    FoundationBreakOverrideError,
    assert_break_overrides_have_following_lesson,
    validate_foundation_snapshot,
)
from app.services.timeslot_service import build_timeslot_signatures


def _bulk(**changes) -> dict:
    payload = {
        "start_time": "09:00",
        "end_time": "11:45",
        "slot_duration_minutes": 50,
        "break_duration_minutes": 10,
        "break_overrides": [{"after_slot": 2, "duration_minutes": 5}],
        "days_of_week": [0],
    }
    payload.update(changes)
    return payload


def test_timeslot_contract_carries_overrides_and_keeps_legacy_payloads_uniform():
    with_overrides = schemas.TimeslotBulkCreate(**_bulk())
    signatures = build_timeslot_signatures(with_overrides)
    assert [(start.strftime("%H:%M"), end.strftime("%H:%M")) for _, start, end in signatures] == [
        ("09:00", "09:50"),
        ("10:00", "10:50"),
        ("10:55", "11:45"),
    ]

    legacy_payload = _bulk()
    legacy_payload.pop("break_overrides")
    legacy = schemas.TimeslotBulkCreate(**legacy_payload)
    assert legacy.break_overrides == []
    assert [
        (start.strftime("%H:%M"), end.strftime("%H:%M"))
        for _, start, end in build_timeslot_signatures(legacy)
    ] == [("09:00", "09:50"), ("10:00", "10:50")]


def test_timeslot_contract_rejects_unused_and_duplicate_overrides():
    with pytest.raises(ValidationError, match="não tem aula seguinte"):
        schemas.TimeslotBulkCreate(
            **_bulk(break_overrides=[{"after_slot": 4, "duration_minutes": 5}])
        )

    with pytest.raises(ValidationError, match="um ajuste de intervalo por aula"):
        schemas.TimeslotBulkCreate(
            **_bulk(
                break_overrides=[
                    {"after_slot": 1, "duration_minutes": 5},
                    {"after_slot": 1, "duration_minutes": 10},
                ]
            )
        )


def test_foundation_draft_accepts_overrides_and_rejects_duplicate_positions():
    draft = schemas.FoundationDraftData.model_validate(
        {
            "opening_time": "09:00",
            "closing_time": "11:45",
            "slot_duration_minutes": 50,
            "break_duration_minutes": 10,
            "break_overrides": [{"after_slot": 2, "duration_minutes": 5}],
        }
    )
    assert draft.break_overrides is not None
    assert draft.break_overrides[0].after_slot == 2

    with pytest.raises(ValidationError, match="um ajuste de intervalo por aula"):
        schemas.FoundationDraftData.model_validate(
            {
                "break_overrides": [
                    {"after_slot": 1, "duration_minutes": 5},
                    {"after_slot": 1, "duration_minutes": 10},
                ]
            }
        )


def test_assert_break_overrides_reports_the_position_that_lost_its_lesson():
    data = schemas.FoundationDraftData.model_validate(
        {
            "opening_time": "09:00",
            "closing_time": "09:50",
            "slot_duration_minutes": 50,
            "break_duration_minutes": 10,
            "break_overrides": [{"after_slot": 1, "duration_minutes": 5}],
        }
    )

    with pytest.raises(FoundationBreakOverrideError) as excinfo:
        assert_break_overrides_have_following_lesson(data)

    assert excinfo.value.position == 1


def test_assert_break_overrides_skips_references_without_a_full_window():
    data = schemas.FoundationDraftData.model_validate(
        {"break_overrides": [{"after_slot": 1, "duration_minutes": 5}]}
    )

    assert_break_overrides_have_following_lesson(data)


def test_foundation_snapshot_rejects_an_unused_override():
    data = schemas.FoundationDraftData.model_validate(
        {
            "school_start_date": "2025-09-15",
            "school_hard_end_date": "2026-07-31",
            "days_of_week": [0, 1],
            "opening_time": "09:00",
            "closing_time": "13:00",
            "slot_duration_minutes": 50,
            "break_duration_minutes": 10,
            "break_overrides": [{"after_slot": 4, "duration_minutes": 5}],
            "lunch_window_start": "12:00",
            "lunch_window_end": "12:50",
            "lunch_min_duration_minutes": 30,
        }
    )

    with pytest.raises(FoundationBreakOverrideError):
        validate_foundation_snapshot(data)


def test_domain_slots_are_consistent_with_the_contract_types():
    value = schemas.TimeslotBulkCreate(**_bulk(break_duration_minutes=0))
    signatures = build_timeslot_signatures(value)
    assert all(type(start) is time and type(end) is time for _, start, end in signatures)
