from datetime import date, time, timedelta

from app.scheduler.composition import generate_schedule
from app.scheduler.domain.candidate import SchedulingStrategy
from app.scheduler.domain.oracle import oracle_objective
from app.scheduler.lab.fixtures import AssignmentSpec, FixtureSpec, build_fixture

TZ = "Europe/Lisbon"
ORIGIN = date(2026, 9, 21)
LONG_PREFERENCE = date(2026, 10, 30)


def _spec(*, assignments, periods, grid, preferred=None, unavailable=()):
    return FixtureSpec(
        strategy=SchedulingStrategy.COMPLETE_GENERATION,
        origin=ORIGIN,
        preferred_end_date=preferred or LONG_PREFERENCE,
        hard_end_date=date(2026, 11, 30),
        timezone_name=TZ,
        grid_slots=grid,
        periods=periods,
        assignments=assignments,
        unavailable=unavailable,
    )


def _t19_spec(assignments):
    return _spec(
        assignments=assignments,
        grid=tuple((0, time(9 + hour), time(10 + hour)) for hour in range(4)),
        periods=tuple((ORIGIN, time(9 + hour), time(10 + hour)) for hour in range(4)),
        unavailable=(("class", 1, (ORIGIN, time(10), time(11))),),
    )


T19_ASSIGNMENTS = (
    AssignmentSpec(1, 7, (60,), (500,)),
    AssignmentSpec(1, 8, (60,), (500,)),
    AssignmentSpec(2, 7, (60,), (500,)),
    AssignmentSpec(3, 8, (60,), (500,)),
)


def test_t19_teacher_gaps_are_prioritized_over_class_gaps():
    fixture = build_fixture("t19-teacher-gaps", _t19_spec(T19_ASSIGNMENTS))

    result = generate_schedule(fixture.snapshot, fixture.periods, time_limit_seconds=10)

    assert result.outcome == "COMPLETE"
    assert result.quality is not None
    assert result.quality.teacher_gap_minutes == 0
    assert result.quality.class_gap_minutes == 60


def test_quality_priority_is_independent_of_assignment_order():
    ordered = build_fixture("t19-ordered", _t19_spec(T19_ASSIGNMENTS))
    shuffled = build_fixture(
        "t19-shuffled",
        _t19_spec(
            (
                T19_ASSIGNMENTS[2],
                T19_ASSIGNMENTS[0],
                T19_ASSIGNMENTS[3],
                T19_ASSIGNMENTS[1],
            )
        ),
    )

    left = generate_schedule(ordered.snapshot, ordered.periods, time_limit_seconds=10)
    right = generate_schedule(shuffled.snapshot, shuffled.periods, time_limit_seconds=10)

    assert left.outcome == right.outcome == "COMPLETE"
    assert left.quality.teacher_gap_minutes == right.quality.teacher_gap_minutes
    assert left.quality.class_gap_minutes == right.quality.class_gap_minutes
    assert left.quality.room_change_cost == right.quality.room_change_cost
    assert left.objective_days == right.objective_days


def test_generated_completion_vector_matches_the_enumerative_oracle():
    day_two = ORIGIN + timedelta(days=1)
    spec = _spec(
        assignments=(
            AssignmentSpec(1, 7, (120,), (500,)),
            AssignmentSpec(2, 8, (60,), (501,)),
        ),
        grid=((0, time(9), time(10)), (1, time(9), time(10))),
        periods=((ORIGIN, time(9), time(10)), (day_two, time(9), time(10))),
    )
    fixture = build_fixture("quality-oracle", spec)

    result = generate_schedule(fixture.snapshot, fixture.periods, time_limit_seconds=10)

    assert result.outcome == "COMPLETE"
    assert oracle_objective(fixture.snapshot, result.candidate) == (1, 0)
    assert oracle_objective(fixture.snapshot, result.candidate) == oracle_objective(
        fixture.snapshot, fixture.witness
    )
    vector = result.quality.vector(
        origin=fixture.snapshot.origin,
        preferred_end_date=fixture.snapshot.preferred_end_date,
    )
    assert vector.completion_days_desc == (1, 0)


def test_completion_report_exposes_margin_and_recoverability():
    early = build_fixture(
        "quality-early",
        _spec(
            assignments=(AssignmentSpec(1, 7, (60,), (500,)),),
            grid=((0, time(9), time(10)),),
            periods=((ORIGIN, time(9), time(10)),),
        ),
    )
    at_preference = build_fixture(
        "quality-at-preference",
        _spec(
            assignments=(AssignmentSpec(1, 7, (60,), (500,)),),
            grid=((1, time(9), time(10)),),
            periods=((ORIGIN + timedelta(days=1), time(9), time(10)),),
            preferred=ORIGIN + timedelta(days=1),
        ),
    )

    early_result = generate_schedule(early.snapshot, early.periods, time_limit_seconds=10)
    late_result = generate_schedule(
        at_preference.snapshot, at_preference.periods, time_limit_seconds=10
    )

    assert early_result.outcome == late_result.outcome == "COMPLETE"
    assert early_result.completion.margin_days > 0
    assert early_result.completion.recovery.status == "NOT_ASSESSED"
    assert late_result.completion.margin_days == 0
    assert late_result.completion.recovery.status == "NOT_ASSESSED"
    assert late_result.completion.classes_after_preferred == ()
