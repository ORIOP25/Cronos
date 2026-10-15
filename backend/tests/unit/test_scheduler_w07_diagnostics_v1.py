"""W07: honest diagnoses, proven minimum deficits and T26 evidence scopes."""

from dataclasses import replace

import pytest

from app.scheduler.domain.candidate import SchedulingStrategy
from app.scheduler.domain.diagnostics import (
    Diagnosis,
    DiagnosisCode,
    EvidenceKind,
    diagnose_capacity,
    diagnose_inconclusive,
    diagnose_joint_no_common_time,
)
from tests.unit.test_scheduler_w04_w05_regressions_v1 import period, snapshot


def test_a_proven_capacity_deficit_carries_a_minimum_only_when_demonstrated():
    periods = (period(0),)
    target = snapshot(periods, minutes=120)

    diagnoses = diagnose_capacity(target, periods)

    assert len(diagnoses) == 1
    diagnosis = diagnoses[0]
    assert diagnosis.code is DiagnosisCode.INSUFFICIENT_INTERSECTION
    assert diagnosis.evidence_kind is EvidenceKind.PROVEN_LOWER_BOUND
    assert diagnosis.minimum_missing_minutes == 60
    assert diagnosis.affected_class_ids == (1,)
    assert diagnosis.suggestions


def test_a_feasible_capacity_has_no_proven_diagnosis():
    periods = (period(0), period(1))
    target = snapshot(periods, minutes=120)

    assert diagnose_capacity(target, periods) == ()


def test_an_interruption_is_never_presented_as_impossibility():
    diagnosis = diagnose_inconclusive("The safety limit interrupted the search.")

    assert diagnosis.code is DiagnosisCode.SEARCH_INCONCLUSIVE
    assert diagnosis.evidence_kind is EvidenceKind.UNKNOWN
    assert diagnosis.minimum_missing_minutes is None
    assert "did not prove" in diagnosis.message
    assert "impossible" in diagnosis.message


def test_evidence_kind_guards_the_minimum_quantity():
    with pytest.raises(ValueError):
        Diagnosis(
            code=DiagnosisCode.SEARCH_INCONCLUSIVE,
            evidence_kind=EvidenceKind.ESTIMATE,
            message="An estimate cannot carry a proven minimum.",
            scope="GLOBAL",
            minimum_missing_minutes=30,
        )


def test_recovery_uses_the_hard_limit_and_flags_the_excess():
    periods = (period(0), period(21))
    target = replace(
        snapshot(periods, minutes=60),
        strategy=SchedulingStrategy.ADAPTIVE_RECOVERY,
        preferred_end_date=period(0).school_date,
    )

    diagnoses = diagnose_capacity(target, periods)

    assert diagnoses == ()


def test_joint_no_common_time_names_the_classes_and_discipline():
    diagnosis = diagnose_joint_no_common_time("Português", ("10.º MKT", "10.º MAS"))

    assert diagnosis.code is DiagnosisCode.JOINT_NO_COMMON_TIME
    assert diagnosis.evidence_kind is EvidenceKind.PROVEN_SCOPE
    assert "10.º MKT, 10.º MAS" in diagnosis.message
    assert "Português" in diagnosis.message
