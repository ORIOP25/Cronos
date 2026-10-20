"""The product data typology must yield complete, valid schedules.

Each class has seven subjects with four 15-hour modules, every course has three
classes so the class count is a multiple of three, and each teacher covers two
classes. The school year runs 14 September to at most 30 July with the Christmas
and Easter breaks blocked. The generator must return a complete, independently
validated schedule for the 12-class and 48-class topologies.
"""

import hashlib
from dataclasses import replace
from datetime import date, time
from time import monotonic

import pytest

from app.scheduler.composition import generate_schedule
from app.scheduler.domain.candidate import (
    HomeRoom,
    LunchRule,
    SchedulingStrategy,
    TeacherPresenceRule,
    Unavailability,
    UnavailableResource,
)
from app.scheduler.domain.candidate_validation import validate_candidate
from app.scheduler.domain.priorities import CRITERION_KEYS, DEFAULT_LEVELS, PriorityWeights
from app.scheduler.domain.priority_metrics import measure_priority_metrics
from app.scheduler.infrastructure import search
from app.scheduler.infrastructure.constructive import construct_schedule
from app.scheduler.infrastructure.search import search_adaptive_schedule
from app.scheduler.lab.priority_bench import _scenario
from app.scheduler.lab.recovery import laboratory_policy
from app.scheduler.lab.typology import (
    CHRISTMAS_BREAK,
    EASTER_BREAK,
    MODULE_MINUTES,
    MODULES_PER_SUBJECT,
    PREFERRED_END,
    SCHOOL_YEAR_START,
    SUBJECT_COUNT,
    build_availability_typology_fixture,
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


# R14: the product typology without availability differences or Evitar keeps the
# construction output of main at 01a011e9 (tech spec I02, D11).
TWELVE_CLASS_CONSTRUCTION_DIGEST = (
    "eece1d47e0a03ace985f0582552ab033d39cb1fa8bdb117fb7563a20a368477d"
)


def test_the_typology_construction_output_is_unchanged_without_availability_rules():
    fixture = build_typology_fixture(12)

    candidate = construct_schedule(fixture.snapshot, fixture.periods)

    assert candidate is not None
    lessons = sorted(
        (lesson.assignment_id, lesson.period.start_utc.isoformat(), lesson.room_id)
        for lesson in candidate.lessons
    )
    assert hashlib.sha256(repr(lessons).encode()).hexdigest() == TWELVE_CLASS_CONSTRUCTION_DIGEST


@pytest.mark.parametrize("criterion", CRITERION_KEYS[:10])
def test_priority_level_four_strictly_improves_its_twelve_class_metric(criterion):
    fixture = build_typology_fixture(12, build_witness=False)
    snapshot = fixture.snapshot
    if criterion == "teacher_preferences":
        levels = dict(DEFAULT_LEVELS)
        levels[criterion] = 0
        baseline = construct_schedule(
            fixture.snapshot, fixture.periods, weights=PriorityWeights(levels)
        )
        assert baseline is not None
        teacher_of = {row.assignment_id: row.teacher_id for row in fixture.snapshot.assignments}
        teacher_id = teacher_of[baseline.lessons[0].assignment_id]
        teacher_periods = tuple(
            lesson.period
            for lesson in baseline.lessons
            if teacher_of[lesson.assignment_id] == teacher_id
        )
        assert teacher_periods
        snapshot = replace(
            snapshot,
            soft_unavailable=tuple(
                Unavailability(
                    UnavailableResource.TEACHER,
                    teacher_id,
                    blocked_period,
                )
                for blocked_period in teacher_periods
            ),
        )
    elif criterion == "class_preferences":
        levels = dict(DEFAULT_LEVELS)
        levels[criterion] = 0
        baseline = construct_schedule(
            fixture.snapshot, fixture.periods, weights=PriorityWeights(levels)
        )
        assert baseline is not None
        baseline_lesson = baseline.lessons[0]
        baseline_assignment = next(
            row
            for row in fixture.snapshot.assignments
            if row.assignment_id == baseline_lesson.assignment_id
        )
        snapshot = replace(
            snapshot,
            soft_unavailable=(
                Unavailability(
                    UnavailableResource.CLASS,
                    baseline_assignment.class_ids[0],
                    baseline_lesson.period,
                ),
            ),
        )
    elif criterion == "class_single_lessons":
        # With full teacher availability no class day holds a single lesson at level 0.
        # Teacher windows in the availability variant create such days to remove.
        fixture = build_availability_typology_fixture(12)
        snapshot = fixture.snapshot
    elif criterion == "class_gaps":
        # Full teacher availability never leaves a class gap in this fixture. The
        # availability variant gives each teacher a window, so class gaps appear.
        fixture = build_availability_typology_fixture(12)
        snapshot = fixture.snapshot
    elif criterion == "class_same_room":
        snapshot = replace(
            snapshot,
            home_rooms=tuple(
                HomeRoom(class_id, class_id) for class_id in range(1, fixture.class_count + 1)
            ),
        )
    metrics = []
    for level in (0, 4):
        levels = dict(DEFAULT_LEVELS)
        levels[criterion] = level
        candidate = construct_schedule(
            snapshot,
            fixture.periods,
            weights=PriorityWeights(levels),
        )
        assert candidate is not None
        metric = measure_priority_metrics(snapshot, candidate)[criterion]
        if criterion == "finish_early":
            metric = (metric - snapshot.origin).days
        metrics.append(metric)

    assert metrics[1] < metrics[0], f"{criterion}: level 4={metrics[1]}, level 0={metrics[0]}"


@pytest.mark.parametrize("resource", ["teacher", "class"])
def test_zero_evitar_weight_makes_evitar_blocks_invisible_to_the_construction(resource):
    """D01 and I05: a resource whose Evitar weight is 0 must not steer the schedule."""
    fixture = build_typology_fixture(12, build_witness=False)
    levels = dict(DEFAULT_LEVELS)
    levels[f"{resource}_preferences"] = 0
    weights = PriorityWeights(levels)
    baseline = construct_schedule(fixture.snapshot, fixture.periods, weights=weights)
    assert baseline is not None
    if resource == "teacher":
        owner_of = {row.assignment_id: (row.teacher_id,) for row in fixture.snapshot.assignments}
        kind = UnavailableResource.TEACHER
    else:
        owner_of = {row.assignment_id: row.class_ids for row in fixture.snapshot.assignments}
        kind = UnavailableResource.CLASS
    owner = owner_of[baseline.lessons[0].assignment_id][0]
    blocks = tuple(
        Unavailability(kind, owner, lesson.period)
        for lesson in baseline.lessons
        if owner in owner_of[lesson.assignment_id]
    )

    blocked = construct_schedule(
        replace(fixture.snapshot, soft_unavailable=blocks), fixture.periods, weights=weights
    )

    assert blocked is not None
    assert repr(blocked.lessons) == repr(baseline.lessons)


def assert_recommended_weights_keep_the_schedule_valid_and_not_later(snapshot, periods):
    """R24: the recommended weights stay complete and valid and do not finish later."""
    unweighted = construct_schedule(snapshot, periods)
    weighted = construct_schedule(snapshot, periods, weights=PriorityWeights(DEFAULT_LEVELS))

    assert unweighted is not None
    assert weighted is not None
    assert validate_candidate(snapshot, weighted).valid is True
    before = measure_priority_metrics(snapshot, unweighted)
    after = measure_priority_metrics(snapshot, weighted)
    assert after["finish_early"] <= before["finish_early"]
    assert after["teacher_preferences"] <= before["teacher_preferences"]


def test_recommended_weights_keep_twelve_classes_valid_and_not_later():
    fixture = build_typology_fixture(12, build_witness=False)

    assert_recommended_weights_keep_the_schedule_valid_and_not_later(
        fixture.snapshot, fixture.periods
    )


def test_recommended_weights_keep_the_twelve_class_availability_case_valid_and_not_later():
    fixture = build_availability_typology_fixture(12)

    assert_recommended_weights_keep_the_schedule_valid_and_not_later(
        fixture.snapshot, fixture.periods
    )


@pytest.mark.slow_solver
def test_recommended_weights_keep_forty_eight_classes_valid_and_not_later():
    fixture = build_typology_fixture(48, build_witness=False)

    assert_recommended_weights_keep_the_schedule_valid_and_not_later(
        fixture.snapshot, fixture.periods
    )


@pytest.mark.slow_solver
def test_recommended_weights_keep_the_pilot_forty_eight_valid_and_not_later():
    scenario = _scenario("pilot-48")

    assert_recommended_weights_keep_the_schedule_valid_and_not_later(
        scenario.snapshot, scenario.periods
    )


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


def test_the_availability_fixture_completes_twelve_classes_before_the_preferred_end():
    # R13: the pilot-school availability case (tech spec T13). Feasibility is shown
    # by the construction itself, because the fixture has no witness.
    fixture = build_availability_typology_fixture(12)

    candidate = construct_schedule(fixture.snapshot, fixture.periods)

    assert candidate is not None
    assert validate_candidate(fixture.snapshot, candidate).valid is True
    assert max(lesson.period.school_date for lesson in candidate.lessons) <= PREFERRED_END


@pytest.mark.slow_solver
def test_the_availability_fixture_completes_forty_eight_classes_before_the_preferred_end():
    fixture = build_availability_typology_fixture(48)

    started = monotonic()
    candidate = construct_schedule(fixture.snapshot, fixture.periods)
    elapsed = monotonic() - started

    # The slice proof records this construction time.
    print(f"availability48 construct_seconds={elapsed:.1f}")
    assert candidate is not None
    assert validate_candidate(fixture.snapshot, candidate).valid is True
    assert max(lesson.period.school_date for lesson in candidate.lessons) <= PREFERRED_END


@pytest.mark.slow_solver
def test_forty_eight_classes_repair_with_an_iris_presence_rule(monkeypatch):
    """The Íris presence rule repairs a 48-class schedule without the exact model (S2)."""
    fixture = build_typology_fixture(48)
    snapshot = replace(
        fixture.snapshot,
        strategy=SchedulingStrategy.ADAPTIVE_RECOVERY,
        baseline_lessons=fixture.witness.lessons,
        teacher_presence=(
            TeacherPresenceRule(
                teacher_id=1001, lunch_required=True, minimum_minutes=180, max_gap_minutes=60
            ),
        ),
        lunch_rule=LunchRule(time(12), time(14), 60),
    )

    def exact_model_must_not_run(*_args, **_kwargs):
        raise AssertionError("The exact placement model must not run.")

    monkeypatch.setattr(search, "solve_placement", exact_model_must_not_run)

    started = monotonic()
    outcome = search_adaptive_schedule(
        snapshot,
        fixture.periods,
        fixture.witness,
        laboratory_policy(snapshot),
        time_limit_seconds=900,
        stop_at_first_complete=True,
        num_workers=1,
        random_seed=3,
    )
    elapsed = monotonic() - started

    # The slice proof records the measured repair time.
    print(f"iris48 seconds={elapsed:.1f}")
    assert outcome.status == "COMPLETE"
    assert outcome.candidate is not None
    assert validate_candidate(snapshot, outcome.candidate).valid is True
    assert elapsed < 900
