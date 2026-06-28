import pytest

from app import models
from app.services.scheduler_repair_trigger import RepairTriggerClassifier


def _generation(current=4, approved=4):
    return {
        "scheduler_state_version": current,
        "approved_scheduler_state_version": approved,
    }


def _debt(minutes=60):
    return {"items": [{"unresolved_debt_minutes": minutes}]}


@pytest.mark.parametrize(
    ("generation", "debt", "expected"),
    [
        (_generation(), _debt(), models.ScheduleGenerationTrigger.EXPLICIT_DEBT),
        (_generation(5, 4), None, models.ScheduleGenerationTrigger.SCHEDULER_CHANGE),
        (_generation(5, 4), _debt(), models.ScheduleGenerationTrigger.MIXED),
    ],
)
def test_repair_trigger_classification(generation, debt, expected):
    result = RepairTriggerClassifier().classify(generation, debt)

    assert result.trigger_type == expected
    assert result.use_recovery_ladder is (expected != models.ScheduleGenerationTrigger.SCHEDULER_CHANGE)
    assert result.use_adaptation_ladder is (expected != models.ScheduleGenerationTrigger.EXPLICIT_DEBT)
    assert "Adaptive repair" in result.summary


def test_repair_trigger_rejects_no_trigger_and_declared_mismatch():
    classifier = RepairTriggerClassifier()
    with pytest.raises(ValueError, match="No unresolved"):
        classifier.classify(_generation(), None)
    with pytest.raises(ValueError, match="does not match"):
        classifier.classify(
            _generation(5, 4),
            None,
            declared_trigger=models.ScheduleGenerationTrigger.EXPLICIT_DEBT,
        )
