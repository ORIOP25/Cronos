"""V1 constraint policy: specific rooms and teacher (un)availability parsing."""

from datetime import date, datetime
from types import SimpleNamespace

import pytest

from app.scheduler.domain.constraint_policy import (
    ConfigurationViolationCode,
    SchoolConstraintPolicy,
)


def test_multiple_room_rows_are_a_value_union_and_teacher_preference_is_soft():
    parsed = SchoolConstraintPolicy.parse(
        [
            {
                "rule_type": "specific_room",
                "rule_payload": {"class_id": 1, "subject_id": 2, "room_id": 4},
            },
            {
                "rule_type": "specific_room",
                "rule_payload": {"class_id": 1, "subject_id": 2, "room_id": 9},
            },
            {
                "rule_type": "teacher_preferred",
                "rule_payload": {"teacher_id": 3, "timeslot_id": 10},
            },
        ]
    )

    assert parsed.is_valid is True
    assert parsed.policy.specific_rooms[(1, 2)] == frozenset({4, 9})
    assert parsed.policy.teacher_preferred_timeslots == {(3, 10)}


def test_lock_time_is_explicitly_unsupported_by_the_v1_policy():
    parsed = SchoolConstraintPolicy.parse(
        [
            {
                "id": 12,
                "rule_type": "lock_time",
                "rule_payload": {"class_id": 1, "subject_id": 2, "timeslot_id": 11},
            },
        ]
    )

    assert parsed.policy is None
    assert parsed.configuration_violations[0].code is (ConfigurationViolationCode.UNSUPPORTED_TYPE)
    assert parsed.configuration_violations[0].constraint_id == 12


def test_unsupported_and_unknown_types_have_no_policy():
    invalid = SchoolConstraintPolicy.parse(
        [
            {"id": 8, "rule_type": "min_gap", "rule_payload": {"class_id": 1, "minutes": 30}},
        ]
    )

    assert invalid.policy is None
    assert invalid.configuration_violations[0].constraint_id == 8


@pytest.mark.parametrize(
    "row",
    [
        {"id": 1, "rule_type": "specific_room", "rule_payload": None},
        {
            "rule_type": "specific_room",
            "rule_payload": {"class_id": True, "subject_id": 2, "room_id": 4},
        },
        {
            "rule_type": "specific_room",
            "rule_payload": {"class_id": 1, "subject_id": 2, "room_id": 0},
        },
        {
            "rule_type": "teacher_preferred",
            "rule_payload": {"teacher_id": 3, "timeslot_id": "10"},
        },
        {
            "rule_type": "teacher_unavailable",
            "rule_payload": {"teacher_id": 3, "date": "not-a-date"},
        },
        {
            "rule_type": "teacher_unavailable",
            "rule_payload": {"teacher_id": 3, "date": datetime(2026, 6, 1)},
        },
        {
            "rule_type": "teacher_unavailable",
            "rule_payload": {"teacher_id": 3, "date": 123},
        },
        {
            "rule_type": "teacher_unavailable",
            "rule_payload": {"teacher_id": 3, "day_of_week": 7},
        },
        {
            "rule_type": "teacher_unavailable",
            "rule_payload": {"teacher_id": 3, "date": "2026-06-01", "day_of_week": 0},
        },
    ],
)
def test_parser_rejects_every_malformed_legacy_shape(row):
    parsed = SchoolConstraintPolicy.parse([row])
    assert parsed.is_valid is False
    assert parsed.configuration_violations[0].code.value == "INVALID_PAYLOAD"


def test_parser_accepts_every_unavailable_selector_and_legacy_alias():
    parsed = SchoolConstraintPolicy.parse(
        [
            {
                "rule_type": "teacher_unavailable",
                "rule_payload": {"teacher_id": 3, "timeslot_id": 10},
            },
            {
                "rule_type": "teacher_unavailable",
                "rule_payload": {"teacher_id": 3, "weekday": 1},
            },
            {
                "rule_type": "teacher_unavailable",
                "rule_payload": {"teacher_id": 3, "output_date": date(2026, 6, 3)},
            },
            {
                "rule_type": "teacher_unavailable",
                "rule_payload": {
                    "teacher_id": 3,
                    "date": "2026-06-04",
                    "timeslot_id": 11,
                },
            },
        ]
    )

    assert parsed.is_valid is True
    assert parsed.policy.teacher_unavailable_timeslots == {(3, 10)}
    assert parsed.policy.teacher_unavailable_days == {(3, 1)}
    assert parsed.policy.teacher_unavailable_dates == {(3, date(2026, 6, 3))}
    assert parsed.policy.teacher_unavailable_date_slots == {(3, date(2026, 6, 4), 11)}


def test_object_rows_snapshot_and_deduplication():
    invalid_row = SimpleNamespace(
        id=9,
        rule_type=SimpleNamespace(value="unknown"),
        rule_payload={},
    )
    invalid = SchoolConstraintPolicy.parse([invalid_row, invalid_row])
    snapshot = SchoolConstraintPolicy.from_snapshot({})

    assert len(invalid.configuration_violations) == 1
    assert invalid.configuration_violations[0].code.value == "UNKNOWN_TYPE"
    assert snapshot.is_valid is True
