from dataclasses import replace
from datetime import UTC, date, datetime, time

import pytest

from app.scheduler.domain.calendar import normalize_period
from app.scheduler.domain.candidate import (
    Assignment,
    GridSlot,
    PlanningSnapshot,
    ScheduledLesson,
    SchedulingStrategy,
    TeacherPresenceRule,
)
from app.scheduler.domain.projection import ModuleRequirement, ModuleSlice

TZ = "Europe/Lisbon"
ORIGIN = date(2026, 9, 21)


def _period(day=ORIGIN, start=time(9), end=time(10)):
    return normalize_period(day, start, end, TZ)


def _assignment(**overrides) -> Assignment:
    values = {
        "assignment_id": 1,
        "class_ids": (1,),
        "subject_id": 10,
        "teacher_id": 100,
        "eligible_room_ids": frozenset({500}),
        "modules": (ModuleRequirement(1, 1, 60),),
    }
    values.update(overrides)
    return Assignment(**values)


def _snapshot(**overrides) -> PlanningSnapshot:
    values = {
        "strategy": SchedulingStrategy.COMPLETE_GENERATION,
        "origin": ORIGIN,
        "preferred_end_date": date(2026, 10, 30),
        "hard_end_date": date(2026, 11, 30),
        "timezone_name": TZ,
        "grid_slots": (GridSlot(0, time(9), time(10)),),
        "assignments": (_assignment(),),
        "executed_minutes": {},
        "blocked_dates": frozenset(),
        "unavailable": (),
    }
    values.update(overrides)
    return PlanningSnapshot(**values)


def test_snapshot_deep_copies_executed_minutes_so_aliases_cannot_mutate_it():
    executed = {1: {1: 0}}
    snapshot = _snapshot(executed_minutes=executed)

    executed[1][1] = 60

    assert snapshot.executed_minutes[1][1] == 0


def test_snapshot_refuses_unknown_timezone_and_date_order():
    with pytest.raises(ValueError):
        _snapshot(timezone_name="Mars/Olympus")
    with pytest.raises(ValueError):
        _snapshot(preferred_end_date=date(2026, 12, 1))


def test_snapshot_requires_unique_assignments_and_matching_debt_claims():
    with pytest.raises(ValueError):
        _snapshot(assignments=(_assignment(), _assignment()))
    with pytest.raises(ValueError):
        _snapshot(open_debt_minutes={7: 30})


def test_assignment_rejects_duplicate_modules_and_ids():
    with pytest.raises(ValueError):
        _assignment(modules=(ModuleRequirement(1, 1, 60), ModuleRequirement(1, 2, 30)))
    with pytest.raises(ValueError):
        _assignment(assignment_id=0)


def test_incoherent_period_instants_are_rejected_at_construction():
    period = _period()

    with pytest.raises(ValueError):
        replace(period, start_utc=datetime(2026, 9, 21, 6, 0, tzinfo=UTC))


def test_lesson_rejects_credit_above_physical_duration():
    with pytest.raises(ValueError):
        ScheduledLesson(
            lesson_id=1,
            assignment_id=1,
            period=_period(),
            room_id=500,
            credit_minutes=61,
            slices=(ModuleSlice(1, 1, 0, 61),),
        )


def test_grid_slot_rejects_invalid_weekday_and_duration():
    with pytest.raises(ValueError):
        GridSlot(7, time(9), time(10))
    with pytest.raises(ValueError):
        GridSlot(0, time(10), time(9))


def test_grid_weekdays_are_derived_from_concrete_slots():
    snapshot = _snapshot(
        grid_slots=(GridSlot(0, time(9), time(10)), GridSlot(2, time(9), time(10)))
    )

    assert snapshot.grid_weekdays == frozenset({0, 2})


def test_assignment_accepts_sorted_classes_and_rejects_empty():
    assignment = _assignment(class_ids=(1, 2))

    assert assignment.class_ids == (1, 2)
    with pytest.raises(ValueError):
        _assignment(class_ids=())
    with pytest.raises(ValueError):
        _assignment(class_ids=(2, 1))
    with pytest.raises(ValueError):
        _assignment(class_ids=(1, 1))


def test_snapshot_rejects_unknown_self_and_cyclic_precedences():
    with pytest.raises(ValueError):
        _snapshot(precedences=((1, 99),))
    with pytest.raises(ValueError):
        _snapshot(precedences=((1, 1),))
    with pytest.raises(ValueError):
        _snapshot(
            assignments=(_assignment(), _assignment(assignment_id=2, class_ids=(2,))),
            precedences=((1, 2), (2, 1)),
        )


def test_snapshot_claim_classes_must_belong_to_their_unit():
    with pytest.raises(ValueError):
        _snapshot(
            open_debt_minutes={7: 30},
            claim_assignments={7: 1},
            claim_classes={7: 2},
        )
    snapshot = _snapshot(
        open_debt_minutes={7: 30},
        claim_assignments={7: 1},
        claim_classes={7: 1},
    )

    assert snapshot.claim_classes[7] == 1


def test_snapshot_without_joint_fields_keeps_the_legacy_defaults():
    snapshot = _snapshot()

    assert snapshot.precedences == ()
    assert dict(snapshot.claim_classes) == {}


def test_jointless_snapshot_serializes_the_legacy_shape_and_digest():
    from app.scheduler.domain.serialization import payload_digest, snapshot_to_dict

    payload = snapshot_to_dict(_snapshot())
    assignment = payload["assignments"][0]

    assert assignment["class_id"] == 1
    assert "class_ids" not in assignment
    assert "precedences" not in payload
    assert "claim_classes" not in payload
    assert "teacher_presence" not in payload
    assert payload_digest(payload) == (
        "2bca0796d98ace3edbd7c2ed3529f27c2d083b511a62f382c07d2983ab6269f1"
    )


def test_teacher_presence_rules_serialize_sorted_and_only_when_non_default():
    from app.scheduler.domain.serialization import (
        payload_digest,
        snapshot_from_dict,
        snapshot_to_dict,
    )

    snapshot = _snapshot(
        teacher_presence=(
            TeacherPresenceRule(teacher_id=50, minimum_minutes=180, max_gap_minutes=60),
            TeacherPresenceRule(teacher_id=100, lunch_required=False),
        )
    )
    payload = snapshot_to_dict(snapshot)

    assert payload["teacher_presence"] == [[50, True, 180, 60], [100, False, None, None]]
    assert snapshot_from_dict(payload).teacher_presence == snapshot.teacher_presence
    assert payload_digest(payload) != payload_digest(snapshot_to_dict(_snapshot()))


def test_snapshot_rejects_default_duplicate_or_unsorted_presence_rules():
    with pytest.raises(ValueError):
        _snapshot(teacher_presence=(TeacherPresenceRule(teacher_id=100),))
    with pytest.raises(ValueError):
        _snapshot(
            teacher_presence=(
                TeacherPresenceRule(teacher_id=100, lunch_required=False),
                TeacherPresenceRule(teacher_id=100, lunch_required=False),
            )
        )
    with pytest.raises(ValueError):
        _snapshot(
            teacher_presence=(
                TeacherPresenceRule(teacher_id=100, lunch_required=False),
                TeacherPresenceRule(teacher_id=50, lunch_required=False),
            )
        )


def test_joint_snapshot_roundtrip_keeps_classes_precedences_and_claims():
    from app.scheduler.domain.serialization import snapshot_from_dict, snapshot_to_dict

    snapshot = _snapshot(
        assignments=(_assignment(), _assignment(assignment_id=2, class_ids=(1, 2))),
        precedences=((1, 2),),
        open_debt_minutes={7: 30},
        claim_assignments={7: 2},
        claim_classes={7: 2},
    )

    payload = snapshot_to_dict(snapshot)
    restored = snapshot_from_dict(payload)

    assert payload["assignments"][1]["class_ids"] == [1, 2]
    assert payload["precedences"] == [[1, 2]]
    assert payload["claim_classes"] == [[7, 2]]
    assert restored.assignments[1].class_ids == (1, 2)
    assert restored.precedences == ((1, 2),)
    assert restored.claim_classes[7] == 2
