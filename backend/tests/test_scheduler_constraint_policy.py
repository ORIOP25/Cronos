from datetime import date, datetime
from types import SimpleNamespace

import pytest

from app.scheduler.domain.constraints import (
    ConstraintViolationCode,
    ConstraintEvaluation,
    PlacementFacts,
    RepairDimension,
    SchedulerConstraintPolicy,
    placement_facts,
)


pytestmark = pytest.mark.unit


def test_policy_returns_all_hard_violations_and_broadest_dimension():
    parsed = SchedulerConstraintPolicy.parse([
        {"rule_type": "specific_room", "rule_payload": {"class_id": 1, "subject_id": 2, "room_id": 9}},
        {"rule_type": "lock_time", "rule_payload": {"class_id": 1, "subject_id": 2, "timeslot_id": 11}},
        {"rule_type": "teacher_unavailable", "rule_payload": {"teacher_id": 3, "date": "2026-06-01", "timeslot_id": 10}},
    ])

    evaluation = parsed.policy.evaluate(PlacementFacts(1, 2, 3, 4, date(2026, 6, 1), 10))

    assert [row.code for row in evaluation.hard_violations] == [
        ConstraintViolationCode.SPECIFIC_ROOM,
        ConstraintViolationCode.LOCK_TIME,
        ConstraintViolationCode.TEACHER_UNAVAILABLE,
    ]
    assert evaluation.required_repair_dimension is RepairDimension.TIME


def test_multiple_room_and_time_rows_are_allowed_value_unions():
    parsed = SchedulerConstraintPolicy.parse([
        {"rule_type": "specific_room", "rule_payload": {"class_id": 1, "subject_id": 2, "room_id": 4}},
        {"rule_type": "specific_room", "rule_payload": {"class_id": 1, "subject_id": 2, "room_id": 9}},
        {"rule_type": "lock_time", "rule_payload": {"class_id": 1, "subject_id": 2, "timeslot_id": 10}},
        {"rule_type": "lock_time", "rule_payload": {"class_id": 1, "subject_id": 2, "timeslot_id": 11}},
    ])

    assert parsed.policy.evaluate(PlacementFacts(1, 2, 3, 9, date(2026, 6, 1), 11)).hard_violations == ()


def test_preference_adjustment_is_soft_and_invalid_configuration_has_no_policy():
    preferred = SchedulerConstraintPolicy.parse([
        {"rule_type": "teacher_preferred", "rule_payload": {"teacher_id": 3, "timeslot_id": 10}},
    ]).policy.evaluate(PlacementFacts(1, 2, 3, 4, date(2026, 6, 1), 10))
    invalid = SchedulerConstraintPolicy.parse([
        {"id": 8, "rule_type": "min_gap", "rule_payload": {"class_id": 1, "minutes": 30}},
    ])

    assert preferred.hard_violations == ()
    assert preferred.preference_tier_adjustment == 1
    assert invalid.policy is None
    assert invalid.configuration_violations[0].constraint_id == 8


def test_parse_result_and_repair_dimension_cover_empty_and_resource_only_policies():
    empty = SchedulerConstraintPolicy.parse([])
    resource = SchedulerConstraintPolicy.parse([
        {
            "rule_type": "specific_room",
            "rule_payload": {"class_id": 1, "subject_id": 2, "room_id": 9},
        }
    ]).policy.evaluate(PlacementFacts(1, 2, 3, 4, date(2026, 6, 1), 10))

    assert empty.is_valid is True
    assert ConstraintEvaluation().required_repair_dimension is None
    assert resource.required_repair_dimension is RepairDimension.RESOURCE


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
            "rule_type": "lock_time",
            "rule_payload": {"class_id": 1, "subject_id": 2},
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
    parsed = SchedulerConstraintPolicy.parse([row])
    assert parsed.is_valid is False
    assert parsed.configuration_violations[0].code.value == "INVALID_PAYLOAD"


def test_parser_accepts_every_unavailable_selector_and_legacy_alias():
    parsed = SchedulerConstraintPolicy.parse([
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
    ])

    assert parsed.is_valid is True
    assert parsed.policy.teacher_unavailable_timeslots == {(3, 10)}
    assert parsed.policy.teacher_unavailable_days == {(3, 1)}
    assert parsed.policy.teacher_unavailable_dates == {(3, date(2026, 6, 3))}
    assert parsed.policy.teacher_unavailable_date_slots == {
        (3, date(2026, 6, 4), 11)
    }


def test_object_rows_mapping_helpers_snapshot_and_deduplication():
    invalid_row = SimpleNamespace(
        id=9,
        rule_type=SimpleNamespace(value="unknown"),
        rule_payload={},
    )
    invalid = SchedulerConstraintPolicy.parse([invalid_row, invalid_row])
    snapshot = SchedulerConstraintPolicy.from_snapshot({})
    facts_from_mapping = placement_facts({
        "class_id": 1,
        "subject_id": 2,
        "teacher_id": 3,
        "room_id": 4,
        "output_date": "2026-06-01",
        "timeslot_id": 10,
    })
    facts_from_object = placement_facts(SimpleNamespace(
        class_id=1,
        subject_id=2,
        teacher_id=3,
        room_id=4,
        date=date(2026, 6, 1),
        timeslot_id=10,
    ))

    assert len(invalid.configuration_violations) == 1
    assert invalid.configuration_violations[0].code.value == "UNKNOWN_TYPE"
    assert snapshot.is_valid is True
    assert facts_from_mapping == facts_from_object
