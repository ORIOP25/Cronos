import pytest
from pydantic import TypeAdapter, ValidationError

from app import schemas
from app.scheduler.domain.constraints import SchedulerConstraintPolicy

adapter = TypeAdapter(schemas.ConstraintCreate)


@pytest.mark.parametrize(
    "payload",
    [
        {
            "rule_type": "specific_room",
            "rule_payload": {"class_id": 1, "subject_id": 2, "room_id": 3},
        },
        {
            "rule_type": "lock_time",
            "rule_payload": {"class_id": 1, "subject_id": 2, "timeslot_id": 3},
        },
        {"rule_type": "teacher_preferred", "rule_payload": {"teacher_id": 1, "timeslot_id": 2}},
        {"rule_type": "teacher_unavailable", "rule_payload": {"teacher_id": 1, "timeslot_id": 2}},
        {"rule_type": "teacher_unavailable", "rule_payload": {"teacher_id": 1, "day_of_week": 0}},
        {
            "rule_type": "teacher_unavailable",
            "rule_payload": {"teacher_id": 1, "date": "2026-06-01"},
        },
        {
            "rule_type": "teacher_unavailable",
            "rule_payload": {"teacher_id": 1, "date": "2026-06-01", "timeslot_id": 2},
        },
    ],
)
def test_supported_constraint_payloads_are_typed(payload):
    result = adapter.validate_python(payload)
    stored = result.model_dump(mode="json", exclude_none=True)

    assert result.rule_payload.model_dump()
    assert SchedulerConstraintPolicy.parse([stored]).is_valid is True


def test_unavailable_date_slot_storage_omits_inactive_selectors():
    result = adapter.validate_python(
        {
            "rule_type": "teacher_unavailable",
            "rule_payload": {
                "teacher_id": 3,
                "date": "2026-06-01",
                "timeslot_id": 10,
            },
        }
    )

    assert result.model_dump(mode="json", exclude_none=True)["rule_payload"] == {
        "teacher_id": 3,
        "date": "2026-06-01",
        "timeslot_id": 10,
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"rule_type": "min_gap", "rule_payload": {"class_id": 1}},
        {"rule_type": "max_days", "rule_payload": {"class_id": 1}},
        {
            "rule_type": "specific_room",
            "rule_payload": {"class_id": True, "subject_id": 2, "room_id": 3},
        },
        {
            "rule_type": "specific_room",
            "rule_payload": {"class_id": "1", "subject_id": 2, "room_id": 3},
        },
        {"rule_type": "teacher_unavailable", "rule_payload": {"teacher_id": 1}},
        {
            "rule_type": "teacher_unavailable",
            "rule_payload": {"teacher_id": 1, "date": "2026-06-01", "day_of_week": 0},
        },
        {
            "rule_type": "teacher_unavailable",
            "rule_payload": {"teacher_id": 1, "date": "2026-06-01T10:00:00"},
        },
        {
            "rule_type": "teacher_preferred",
            "rule_payload": {"teacher_id": 1, "timeslot_id": 2, "extra": 3},
        },
    ],
)
def test_unsupported_or_noncanonical_constraint_payloads_are_rejected(payload):
    with pytest.raises(ValidationError):
        adapter.validate_python(payload)
