"""Joint lab family: units, precedences, witness and bounded performance.

The family follows the product typology: the general subjects of a course share
their first modules across the three classes, while the technical subjects stay
separate. ``build_teaching_units`` generates the units and precedences and the
independent constructor builds the witness, validated by the independent
validator. The pilot measures the constructive route against its no-joint peer
at the existing 48-class benchmark scale.
"""

from __future__ import annotations

from time import monotonic

import pytest

from app.scheduler.composition import generate_schedule
from app.scheduler.domain.candidate_validation import validate_candidate
from app.scheduler.lab.typology import (
    GENERAL_SUBJECT_COUNT,
    JOINT_MODULE_COUNT,
    build_joint_typology_fixture,
    build_typology_fixture,
)

PILOT_CLASSES = 48
CONSTRUCTIVE_LIMIT_SECONDS = 600


def _generate(fixture):
    started = monotonic()
    result = generate_schedule(
        fixture.snapshot,
        fixture.periods,
        time_limit_seconds=CONSTRUCTIVE_LIMIT_SECONDS,
        stop_at_first_complete=True,
        num_workers=1,
        random_seed=3,
    )
    return result, monotonic() - started


@pytest.fixture(scope="module")
def joint_pilot():
    return build_joint_typology_fixture(PILOT_CLASSES)


@pytest.fixture(scope="module")
def separate_pilot():
    return build_typology_fixture(PILOT_CLASSES)


def test_joint_family_units_and_precedences():
    fixture = build_joint_typology_fixture(12)
    snapshot = fixture.snapshot
    joint = [unit for unit in snapshot.assignments if len(unit.class_ids) > 1]

    assert len(joint) == fixture.courses * GENERAL_SUBJECT_COUNT
    for unit in joint:
        assert len(unit.class_ids) == 3
        assert unit.class_ids == tuple(sorted(unit.class_ids))
        assert [module.module_id for module in unit.modules] == list(
            range(1, JOINT_MODULE_COUNT + 1)
        )
    assert fixture.precedences > 0
    identifiers = {unit.assignment_id for unit in snapshot.assignments}
    assert all(
        source in identifiers and target in identifiers and source != target
        for source, target in snapshot.precedences
    )


def test_joint_family_witness_is_valid():
    fixture = build_joint_typology_fixture(12)

    report = validate_candidate(fixture.snapshot, fixture.witness)

    assert report.valid is True
    assert report.total_credit_minutes == sum(
        module.required_minutes for unit in fixture.snapshot.assignments for module in unit.modules
    )


def test_joint_family_is_deterministic():
    first = build_joint_typology_fixture(12)
    second = build_joint_typology_fixture(12)

    assert first.snapshot.precedences == second.snapshot.precedences
    assert [unit.assignment_id for unit in first.snapshot.assignments] == [
        unit.assignment_id for unit in second.snapshot.assignments
    ]
    assert len(first.witness.lessons) == len(second.witness.lessons)


def test_joint_pilot_measures_against_the_no_joint_peer(joint_pilot, separate_pilot):
    """One deterministic run per family at 48 classes (n=1, not a distribution)."""
    joint_result, joint_seconds = _generate(joint_pilot)
    separate_result, separate_seconds = _generate(separate_pilot)

    assert joint_result.outcome == "COMPLETE"
    assert joint_result.report is not None and joint_result.report.valid is True
    assert separate_result.outcome == "COMPLETE"
    assert separate_result.report is not None and separate_result.report.valid is True
    assert joint_result.evidence is not None and separate_result.evidence is not None
    assert joint_result.evidence.stop_reason == "CONSTRUCTIVE"
    assert separate_result.evidence.stop_reason == "CONSTRUCTIVE"
    assert joint_seconds < CONSTRUCTIVE_LIMIT_SECONDS
    assert separate_seconds < CONSTRUCTIVE_LIMIT_SECONDS
    # Recorded so a regression in either route is visible in the report.
    print(
        f"joint={joint_seconds:.2f}s (units={len(joint_pilot.snapshot.assignments)}, "
        f"precedences={joint_pilot.precedences}) separate={separate_seconds:.2f}s "
        f"(units={len(separate_pilot.snapshot.assignments)})"
    )
