"""W07: honest diagnoses, proven minimum deficits and T26 evidence scopes."""

from dataclasses import replace
from datetime import time

import pytest

from app.scheduler.domain.candidate import LunchRule, SchedulingStrategy, TeacherPresenceRule
from app.scheduler.domain.capacity import aggregate_capacity_check
from app.scheduler.domain.diagnostics import (
    Diagnosis,
    DiagnosisCode,
    EvidenceKind,
    diagnose_capacity,
    diagnose_inconclusive,
    diagnose_joint_no_common_time,
    diagnose_teacher_presence_rules,
)
from app.scheduler.domain.teacher_presence import PresenceSlot, teacher_can_have_presence
from tests.unit.test_scheduler_w04_w05_regressions_v1 import period, snapshot


def test_a_proven_capacity_deficit_carries_a_minimum_only_when_demonstrated():
    periods = (period(0),)
    target = snapshot(periods, minutes=120)

    diagnoses = diagnose_capacity(target, aggregate_capacity_check(target, periods))

    assert len(diagnoses) == 2
    assert {(row.code, row.minimum_missing_minutes) for row in diagnoses} == {
        (DiagnosisCode.INSUFFICIENT_INTERSECTION, 60),
        (DiagnosisCode.INSUFFICIENT_CLASS_TIME, 60),
    }
    assert all(row.evidence_kind is EvidenceKind.PROVEN_LOWER_BOUND for row in diagnoses)
    intersection = next(
        row for row in diagnoses if row.code is DiagnosisCode.INSUFFICIENT_INTERSECTION
    )
    assert intersection.scope == "ASSIGNMENT:1"
    assert intersection.affected_class_ids == (1,)
    assert intersection.affected_subject_id == 1
    assert intersection.suggestions
    class_time = next(row for row in diagnoses if row.code is DiagnosisCode.INSUFFICIENT_CLASS_TIME)
    assert class_time.scope == "CLASS:1"
    assert class_time.affected_class_ids == (1,)
    assert class_time.suggestions


def test_a_feasible_capacity_has_no_proven_diagnosis():
    periods = (period(0), period(1))
    target = snapshot(periods, minutes=120)

    assert diagnose_capacity(target, aggregate_capacity_check(target, periods)) == ()


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

    diagnoses = diagnose_capacity(target, aggregate_capacity_check(target, periods))

    assert diagnoses == ()


def test_joint_no_common_time_names_the_classes_and_discipline():
    diagnosis = diagnose_joint_no_common_time("Português", ("10.º MKT", "10.º MAS"))

    assert diagnosis.code is DiagnosisCode.JOINT_NO_COMMON_TIME
    assert diagnosis.evidence_kind is EvidenceKind.PROVEN_SCOPE
    assert "10.º MKT, 10.º MAS" in diagnosis.message
    assert "Português" in diagnosis.message


def _slot(start_hour, end_hour, possible=True):
    return PresenceSlot(start_hour * 60, end_hour * 60, possible)


def test_capacity_finds_a_presence_when_possible_blocks_reach_the_minimum():
    rule = TeacherPresenceRule(1, True, 120, 0)
    slots = {0: (_slot(9, 10), _slot(10, 11))}

    assert teacher_can_have_presence(rule, slots, lunch_rule=None) is True


def test_capacity_rejects_when_possible_minutes_stay_below_the_minimum():
    rule = TeacherPresenceRule(1, True, 180, 0)
    slots = {0: (_slot(9, 10), _slot(10, 11))}

    assert teacher_can_have_presence(rule, slots, lunch_rule=None) is False


def test_capacity_counts_impossible_blocks_as_holes_bounded_by_the_gap():
    slots = {0: (_slot(9, 10), _slot(10, 11, possible=False), _slot(11, 12))}

    assert (
        teacher_can_have_presence(TeacherPresenceRule(1, True, 120, 0), slots, lunch_rule=None)
        is False
    )
    assert (
        teacher_can_have_presence(TeacherPresenceRule(1, True, 120, 60), slots, lunch_rule=None)
        is True
    )


def test_capacity_keeps_a_required_lunch_on_one_side_of_the_break():
    # 9h-10h and 11h-12h possible, lunch window 10h-11h: with a required lunch the
    # day splits into a 60-minute morning and a 60-minute afternoon, so a 120-minute
    # presence is impossible; without the lunch rule the same day fits.
    slots = {0: (_slot(9, 10), _slot(11, 12))}
    lunch = LunchRule(time(10, 0), time(11, 0), 60)

    assert (
        teacher_can_have_presence(TeacherPresenceRule(1, True, 120, 0), slots, lunch_rule=lunch)
        is False
    )
    assert (
        teacher_can_have_presence(TeacherPresenceRule(1, False, 120, 0), slots, lunch_rule=lunch)
        is True
    )


def test_diagnose_teacher_presence_rules_lists_only_minimum_teachers():
    target = replace(
        snapshot((period(0),)),
        teacher_presence=(
            TeacherPresenceRule(1, False),
            TeacherPresenceRule(2, True, 180, 60),
        ),
    )

    diagnosis = diagnose_teacher_presence_rules(target)

    assert diagnosis is not None
    assert diagnosis.code is DiagnosisCode.TEACHER_PRESENCE_RULES
    assert diagnosis.evidence_kind is EvidenceKind.ESTIMATE
    assert diagnosis.minimum_missing_minutes is None
    assert diagnosis.affected_teacher_ids == (2,)


def test_diagnose_teacher_presence_rules_is_absent_without_a_minimum():
    target = replace(
        snapshot((period(0),)),
        teacher_presence=(TeacherPresenceRule(1, False),),
    )

    assert diagnose_teacher_presence_rules(target) is None


def test_capacity_accepts_a_required_lunch_when_a_side_reaches_the_minimum():
    # 09:00-12:00 possible (3 h) with lunch at 13:00-14:00: the morning presence
    # reaches the minimum without overlapping the break, so no false blocker.
    slots = {0: (_slot(9, 10), _slot(10, 11), _slot(11, 12))}
    lunch = LunchRule(time(13, 0), time(14, 0), 60)

    assert (
        teacher_can_have_presence(TeacherPresenceRule(1, True, 180, 0), slots, lunch_rule=lunch)
        is True
    )


def test_capacity_accepts_a_d19_grid_with_variable_durations():
    # D19 default grid shape: 60-minute lessons with 5-minute breaks from 09:00
    # and lunch 12:00-14:00 with a 60-minute minimum. A 3-hour minimum still fits
    # on one side of the break, so the pre-check never blocks it falsely.
    slots = {
        0: (
            PresenceSlot(9 * 60, 10 * 60, True),
            PresenceSlot(10 * 60 + 5, 11 * 60 + 5, True),
            PresenceSlot(11 * 60 + 10, 12 * 60 + 10, True),
            PresenceSlot(12 * 60 + 15, 13 * 60 + 15, True),
        )
    }
    lunch = LunchRule(time(12, 0), time(14, 0), 60)

    assert (
        teacher_can_have_presence(TeacherPresenceRule(1, True, 180, 0), slots, lunch_rule=lunch)
        is True
    )
