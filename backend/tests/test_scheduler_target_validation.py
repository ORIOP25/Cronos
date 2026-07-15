from dataclasses import replace
from copy import deepcopy
from datetime import date, time
from types import SimpleNamespace

import pytest

from app.scheduler.domain.contracts import DraftBlockSpec
from app.scheduler.domain.validation import (
    GenerationEnvelopeValidator,
    LunchBreakValidator,
    TargetHardConstraintValidator,
    TargetViolationCode,
)


pytestmark = pytest.mark.unit


def _block(key: str, class_id: int, teacher_id: int, timeslot_id: int) -> DraftBlockSpec:
    return DraftBlockSpec(
        stable_block_key=key,
        class_id=class_id,
        subject_id=2,
        teacher_id=teacher_id,
        room_id=4,
        room_type_id="normal",
        date=date(2026, 6, 1),
        timeslot_id=timeslot_id,
        duration_minutes=60,
        change_type="ADDED",
    )


GRID = {
    10: (0, 12 * 60, 13 * 60),
    11: (0, 13 * 60, 14 * 60),
}
RULE = {
    "window_start": "12:00:00",
    "window_end": "14:00:00",
    "minimum_minutes": 60,
}


def test_no_configured_lunch_policy_has_no_violations():
    assert LunchBreakValidator.validate(None, (_block("a", 1, 3, 10),), GRID) == ()


def test_lunch_validator_reports_class_and_teacher_separately():
    violations = LunchBreakValidator.validate(
        RULE,
        (_block("a", 1, 3, 10), _block("b", 1, 3, 11)),
        GRID,
    )
    assert [(row.code, row.resource_type) for row in violations] == [
        (TargetViolationCode.LUNCH_BREAK_VIOLATION, "class"),
        (TargetViolationCode.LUNCH_BREAK_VIOLATION, "teacher"),
    ]


def test_lunch_validator_distinguishes_class_only_and_teacher_only_violations():
    class_only = LunchBreakValidator.validate(
        RULE,
        (_block("a", 1, 3, 10), _block("b", 1, 4, 11)),
        GRID,
    )
    teacher_only = LunchBreakValidator.validate(
        RULE,
        (_block("a", 1, 3, 10), _block("b", 5, 3, 11)),
        GRID,
    )
    assert [(row.resource_type, row.resource_id) for row in class_only] == [("class", 1)]
    assert [(row.resource_type, row.resource_id) for row in teacher_only] == [("teacher", 3)]


def test_exact_minimum_lunch_boundary_is_valid():
    block = replace(_block("a", 1, 3, 10), duration_minutes=60)
    assert LunchBreakValidator.validate(RULE, (block,), GRID) == ()


def test_generation_envelope_reports_deterministic_contract_violations():
    result = SimpleNamespace(
        result_category="PARTIAL_RECOVERY",
        blocks=(),
        projected_completion_date=date(2026, 7, 2),
        hard_end_date=date(2026, 7, 1),
    )

    violations = GenerationEnvelopeValidator.validate(
        "COMPLETE_GENERATION",
        result,
        date(2026, 6, 30),
    )

    assert [row.code for row in violations] == [
        TargetViolationCode.GENERATION_ENVELOPE_INVALID,
    ] * 4


def test_generation_envelope_accepts_valid_adaptive_result():
    result = SimpleNamespace(
        result_category="COMPLETE_SUCCESS",
        blocks=(_block("a", 1, 3, 10),),
        projected_completion_date=date(2026, 6, 1),
        hard_end_date=date(2026, 7, 1),
    )

    assert GenerationEnvelopeValidator.validate(
        "ADAPTIVE_REPAIR",
        result,
        date(2026, 7, 1),
    ) == ()


def _hard_snapshot():
    return {
        "start_date": "2026-06-01",
        "hard_end_date": "2026-06-30",
        "timetable_grid": [
            {
                "id": 10,
                "day_of_week": 0,
                "start_time": "09:00:00",
                "end_time": "10:00:00",
            }
        ],
        "calendar_events": [],
        "class_subject_requirements": [
            {"class_id": 1, "subject_id": 2, "teacher_id": 3}
        ],
        "classes": [{"id": 1, "size": 20}],
        "subjects": [{"id": 2, "required_room_type": "normal"}],
        "rooms": [{"id": 4, "capacity": 30, "type": "normal"}],
        "teacher_subject_eligibility": [{"teacher_id": 3, "subject_id": 2}],
        "teacher_availability": [],
        "constraints": [],
        "lunch_rules": None,
    }


def _valid_hard_block(key="valid"):
    return replace(
        _block(key, 1, 3, 10),
        date=date(2026, 6, 1),
        duration_minutes=60,
    )


def test_shared_hard_validator_accepts_valid_target_and_time_values():
    snapshot = _hard_snapshot()
    snapshot["timetable_grid"][0]["start_time"] = time(9)
    snapshot["timetable_grid"][0]["end_time"] = time(10)
    snapshot["subjects"][0]["required_room_type"] = SimpleNamespace(value="normal")
    snapshot["rooms"][0]["type"] = SimpleNamespace(value="normal")

    assert TargetHardConstraintValidator.validate(snapshot, (_valid_hard_block(),)) == ()


@pytest.mark.parametrize(
    ("mutate_snapshot", "mutate_block"),
    [
        (lambda row: row["timetable_grid"].clear(), lambda block: block),
        (lambda row: row["timetable_grid"][0].update(day_of_week=1), lambda block: block),
        (lambda row: None, lambda block: replace(block, date=date(2026, 5, 31))),
        (lambda row: None, lambda block: replace(block, date=date(2026, 7, 1))),
        (lambda row: None, lambda block: replace(block, duration_minutes=0)),
        (lambda row: None, lambda block: replace(block, duration_minutes=61)),
        (
            lambda row: row["calendar_events"].append(
                {"start_date": "2026-05-31", "end_date": "2026-06-01"}
            ),
            lambda block: block,
        ),
        (lambda row: None, lambda block: replace(block, stable_block_key=" ")),
        (lambda row: row["classes"].clear(), lambda block: block),
        (lambda row: row["subjects"].clear(), lambda block: block),
        (lambda row: row["rooms"].clear(), lambda block: block),
        (
            lambda row: row["class_subject_requirements"][0].update(teacher_id=9),
            lambda block: block,
        ),
        (lambda row: row["teacher_subject_eligibility"].clear(), lambda block: block),
        (lambda row: row["rooms"][0].update(capacity=19), lambda block: block),
        (lambda row: row["rooms"][0].update(type="lab"), lambda block: block),
        (
            lambda row: row["teacher_availability"].append(
                {"teacher_id": 3, "timeslot_id": 10, "score": -1}
            ),
            lambda block: block,
        ),
        (lambda row: None, lambda block: replace(block, is_recovery_block=True)),
        (
            lambda row: None,
            lambda block: replace(
                block,
                recovery_source_occurrence_id=1,
                recovery_source_occurrence_revision=1,
            ),
        ),
    ],
)
def test_shared_hard_validator_reports_each_hard_invalid_shape(
    mutate_snapshot,
    mutate_block,
):
    snapshot = _hard_snapshot()
    mutate_snapshot(snapshot)
    violations = TargetHardConstraintValidator.validate(
        snapshot,
        (mutate_block(_valid_hard_block()),),
    )
    assert violations[0].code is TargetViolationCode.HARD_CONSTRAINT_VIOLATION


def test_shared_hard_validator_reports_duplicate_conflicts_custom_and_configuration():
    snapshot = _hard_snapshot()
    duplicate = TargetHardConstraintValidator.validate(
        snapshot,
        (_valid_hard_block("same"), _valid_hard_block("same")),
    )
    conflict = TargetHardConstraintValidator.validate(
        snapshot,
        (_valid_hard_block("one"), _valid_hard_block("two")),
    )
    constrained = deepcopy(snapshot)
    constrained["constraints"] = [
        {
            "rule_type": "specific_room",
            "rule_payload": {"class_id": 1, "subject_id": 2, "room_id": 9},
        }
    ]
    custom = TargetHardConstraintValidator.validate(
        constrained,
        (_valid_hard_block(),),
    )
    invalid_policy = deepcopy(snapshot)
    invalid_policy["constraints"] = [
        {"rule_type": "min_gap", "rule_payload": {"class_id": 1}}
    ]
    configuration = TargetHardConstraintValidator.validate(
        invalid_policy,
        (_valid_hard_block(),),
    )

    assert duplicate[0].code is TargetViolationCode.HARD_CONSTRAINT_VIOLATION
    assert {row.resource_type for row in conflict} == {"class", "teacher", "room"}
    assert custom[0].code is TargetViolationCode.CUSTOM_CONSTRAINT_VIOLATION
    assert configuration[0].code is TargetViolationCode.CONSTRAINT_CONFIGURATION_INVALID


def test_lunch_validator_ignores_unknown_slots_and_merges_adjacent_intervals():
    missing = replace(_valid_hard_block(), timeslot_id=999)
    spanning_grid = {
        10: (0, 11 * 60, 12 * 60 + 30),
        11: (0, 12 * 60 + 30, 14 * 60),
    }
    violations = LunchBreakValidator.validate(
        RULE,
        (missing, _block("a", 1, 3, 10), _block("b", 1, 3, 11)),
        spanning_grid,
    )
    assert len(violations) == 2
