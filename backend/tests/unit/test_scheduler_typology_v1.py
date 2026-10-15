"""The product data typology must yield complete, valid schedules.

Each class has seven subjects with four 15-hour modules, every course has three
classes so the class count is a multiple of three, and each teacher covers two
classes. The school year runs 14 September to at most 30 July with the Christmas
and Easter breaks blocked. The generator must return a complete, independently
validated schedule for the 12-class and 48-class topologies.
"""

from datetime import date
from time import monotonic

import pytest

from app.scheduler.composition import generate_schedule
from app.scheduler.domain.candidate import TeacherPresenceRule
from app.scheduler.domain.candidate_validation import validate_candidate
from app.scheduler.lab.typology import (
    CHRISTMAS_BREAK,
    EASTER_BREAK,
    MODULE_MINUTES,
    MODULES_PER_SUBJECT,
    PREFERRED_END,
    SCHOOL_YEAR_START,
    SUBJECT_COUNT,
    build_typology_fixture,
)


def test_the_fixture_follows_the_product_typology():
    fixture = build_typology_fixture(12)

    assert fixture.class_count % 3 == 0
    assert fixture.class_count == fixture.courses * 3
    assert len(fixture.snapshot.assignments) == fixture.class_count * SUBJECT_COUNT
    assert fixture.teachers == SUBJECT_COUNT * 6
    for assignment in fixture.snapshot.assignments:
        assert len(assignment.modules) == MODULES_PER_SUBJECT
        assert all(module.required_minutes == MODULE_MINUTES for module in assignment.modules)
    assert fixture.snapshot.origin == SCHOOL_YEAR_START
    assert fixture.snapshot.preferred_end_date == PREFERRED_END
    for day in CHRISTMAS_BREAK[0], EASTER_BREAK[0]:
        assert day in fixture.snapshot.blocked_dates


def test_classes_are_always_multiples_of_three():
    with pytest.raises(ValueError, match="multiples of three"):
        build_typology_fixture(4)


def test_the_independent_witness_is_valid():
    fixture = build_typology_fixture(12)

    report = validate_candidate(fixture.snapshot, fixture.witness)

    assert report.valid is True
    assert report.total_credit_minutes == (
        fixture.class_count * SUBJECT_COUNT * MODULES_PER_SUBJECT * MODULE_MINUTES
    )


def test_twelve_classes_generate_a_complete_valid_schedule():
    fixture = build_typology_fixture(12)

    result = generate_schedule(
        fixture.snapshot,
        fixture.periods,
        # Verify complete generation with the same production policy as 48 classes.
        # An eight-second deadline makes this correctness check depend on host load.
        time_limit_seconds=900,
        stop_at_first_complete=True,
        num_workers=1,
        random_seed=3,
    )

    assert result.outcome == "COMPLETE"
    assert result.report is not None and result.report.valid is True
    assert result.completion is not None
    assert result.completion.classes_after_preferred == ()
    assert result.completion.latest_completion_date <= PREFERRED_END


@pytest.mark.slow_solver
def test_forty_eight_classes_generate_a_complete_valid_schedule():
    fixture = build_typology_fixture(48)

    result = generate_schedule(
        fixture.snapshot,
        fixture.periods,
        # Use the production safety budget and constructive stopping policy.
        # A short optimization deadline makes correctness depend on host load.
        time_limit_seconds=900,
        stop_at_first_complete=True,
        num_workers=1,
        random_seed=3,
    )

    assert result.outcome == "COMPLETE"
    assert result.report is not None and result.report.valid is True
    assert result.completion is not None
    assert result.completion.latest_completion_date <= PREFERRED_END
    assert result.wall_time_seconds < 900


def test_typology_fixture_accepts_optional_presence_rules():
    rule = TeacherPresenceRule(
        teacher_id=1001, lunch_required=False, minimum_minutes=180, max_gap_minutes=120
    )

    fixture = build_typology_fixture(12, teacher_presence=(rule,), build_witness=False)

    assert fixture.snapshot.teacher_presence == (rule,)
    assert fixture.witness is None
    legacy = build_typology_fixture(12)
    assert legacy.snapshot.teacher_presence == ()
    assert legacy.witness is not None
    assert validate_candidate(legacy.snapshot, legacy.witness).valid


@pytest.mark.slow_solver
def test_forty_eight_classes_with_presence_rules_measure_the_route():
    """Measure the 48-class case under meaningful presence rules (T10/S6)."""
    from app.scheduler.infrastructure.constructive import construct_schedule
    from app.scheduler.infrastructure.search import search_complete_schedule

    rule = TeacherPresenceRule(
        teacher_id=1001, lunch_required=False, minimum_minutes=180, max_gap_minutes=120
    )
    fixture = build_typology_fixture(48, teacher_presence=(rule,), build_witness=False)
    assert fixture.snapshot.teacher_presence == (rule,)

    started = monotonic()
    constructed = construct_schedule(fixture.snapshot, fixture.periods)
    constructive_seconds = monotonic() - started
    assert constructed is None or validate_candidate(fixture.snapshot, constructed).valid

    if constructed is not None:
        route = "constructive"
        outcome, candidate, elapsed = "COMPLETE", constructed, constructive_seconds
    else:
        started = monotonic()
        search_outcome = search_complete_schedule(
            fixture.snapshot, fixture.periods, time_limit_seconds=900, num_workers=1, random_seed=3
        )
        elapsed = monotonic() - started
        route, outcome, candidate = "exact", search_outcome.status, search_outcome.candidate

    # The slice proof records the measured route and time.
    print(
        f"presence48 route={route} outcome={outcome} seconds={elapsed:.1f} "
        f"constructive_seconds={constructive_seconds:.1f}"
    )
    assert outcome == "COMPLETE"
    assert candidate is not None
    assert validate_candidate(fixture.snapshot, candidate).valid


def test_the_school_year_break_dates_are_within_the_calendar():
    fixture = build_typology_fixture(12)

    for day in (date(2026, 12, 21), date(2027, 1, 1), date(2027, 4, 12), date(2027, 4, 23)):
        assert day not in {period.school_date for period in fixture.periods}
