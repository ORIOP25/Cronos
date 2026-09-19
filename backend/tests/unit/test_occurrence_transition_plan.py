from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app import models, schemas
from app.core.exceptions import AppError
from app.services.occurrence_service import build_occurrence_transition_plan


def _occurrence(*, status=None, decided=False, is_active=True):
    return SimpleNamespace(
        status=status,
        decided_at=datetime.now(UTC) if decided else None,
        is_active=is_active,
    )


def _payload(status, version=1, **kwargs):
    return schemas.LessonOccurrenceUpdate(status=status, version=version, **kwargs)


def test_open_occurrence_can_be_decided_as_given_without_reversal():
    plan = build_occurrence_transition_plan(
        _occurrence(), _payload(models.LessonOccurrenceStatus.GIVEN)
    )

    assert plan.previous_status is None
    assert plan.next_status == models.LessonOccurrenceStatus.GIVEN
    assert not plan.is_redecision
    assert not plan.reverses_accounting
    assert not plan.requires_substitute


def test_given_occurrence_allows_only_idempotent_given_redecision():
    plan = build_occurrence_transition_plan(
        _occurrence(status=models.LessonOccurrenceStatus.GIVEN, decided=True),
        _payload(models.LessonOccurrenceStatus.GIVEN),
    )

    assert plan.is_redecision
    assert plan.reverses_accounting


def test_gap_can_be_redecided_as_substituted():
    plan = build_occurrence_transition_plan(
        _occurrence(status=models.LessonOccurrenceStatus.GAP, decided=True),
        _payload(
            models.LessonOccurrenceStatus.SUBSTITUTED,
            substitute_teacher_id=10,
            substitute_subject_id=20,
        ),
    )

    assert plan.previous_status == models.LessonOccurrenceStatus.GAP
    assert plan.requires_substitute


def test_decided_given_cannot_be_changed_to_gap():
    with pytest.raises(AppError) as raised:
        build_occurrence_transition_plan(
            _occurrence(status=models.LessonOccurrenceStatus.GIVEN, decided=True),
            _payload(models.LessonOccurrenceStatus.GAP),
        )

    assert raised.value.kind == "validation"
    assert raised.value.code == "validation_error"


@pytest.mark.parametrize(
    "occurrence",
    [
        _occurrence(status=models.LessonOccurrenceStatus.REVOKED, decided=True),
        _occurrence(status=models.LessonOccurrenceStatus.GAP, decided=True, is_active=False),
    ],
)
def test_terminal_or_inactive_occurrence_is_not_transitionable(occurrence):
    with pytest.raises(AppError) as raised:
        build_occurrence_transition_plan(
            occurrence,
            _payload(models.LessonOccurrenceStatus.GIVEN),
        )

    assert raised.value.kind == "conflict"
