from datetime import date

from app.scheduler.domain.contracts import DraftBlockSpec
from app.services.scheduler_recovery_validation import validate_recovery_identity


def _block(class_id=1, subject_id=2):
    return DraftBlockSpec(
        stable_block_key="recovery",
        class_id=class_id,
        subject_id=subject_id,
        teacher_id=3,
        room_id=4,
        room_type_id="normal",
        date=date(2026, 6, 1),
        timeslot_id=10,
        duration_minutes=60,
        is_recovery_block=True,
        recovery_source_occurrence_id=70,
        recovery_source_occurrence_revision=2,
        change_type="ADDED",
    )


def test_recovery_identity_rejects_cross_class_and_accepts_reassigned_teacher():
    debt = {
        "occurrence_id": 70,
        "occurrence_revision": 2,
        "class_id": 1,
        "subject_id": 2,
        "teacher_id": 8,
        "unresolved_debt_minutes": 60,
    }
    assignments = {(1, 2): 3}
    qualifications = {(3, 2)}

    assert validate_recovery_identity(_block(), debt, assignments, qualifications) == ()
    assert any(
        "class" in message
        for message in validate_recovery_identity(_block(2), debt, {(2, 2): 3}, qualifications)
    )


def test_recovery_identity_rejects_cross_subject_targets():
    debt = {
        "occurrence_id": 70,
        "occurrence_revision": 2,
        "class_id": 1,
        "subject_id": 2,
        "teacher_id": 8,
        "unresolved_debt_minutes": 60,
    }

    messages = validate_recovery_identity(
        _block(subject_id=9),
        debt,
        {(1, 9): 3},
        {(3, 9)},
    )

    assert any("subject" in message for message in messages)
