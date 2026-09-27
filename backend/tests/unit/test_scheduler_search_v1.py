from datetime import date, time, timedelta

from app.scheduler.composition import generate_schedule
from app.scheduler.domain.candidate import SchedulingStrategy
from app.scheduler.infrastructure.placement_model import (
    STATUS_COMPLETE,
    STATUS_INCONCLUSIVE,
    STATUS_INFEASIBLE,
)
from app.scheduler.infrastructure.search import feedback_cut
from app.scheduler.lab.fixtures import (
    AssignmentSpec,
    CaseExpectation,
    FixtureSpec,
    build_fixture,
)

TZ = "Europe/Lisbon"
ORIGIN = date(2026, 9, 21)
NEXT_WEEK = ORIGIN + timedelta(days=7)
OVERLAPPING_GRID = ((0, time(9), time(10)), (0, time(9, 30), time(10, 30)))


def _shared_teacher_spec(*, periods, grid, unavailable=()):
    return FixtureSpec(
        strategy=SchedulingStrategy.COMPLETE_GENERATION,
        origin=ORIGIN,
        preferred_end_date=date(2026, 10, 30),
        hard_end_date=date(2026, 11, 30),
        timezone_name=TZ,
        grid_slots=grid,
        periods=periods,
        assignments=(
            AssignmentSpec(1, 7, (60,), (500,)),
            AssignmentSpec(2, 7, (60,), (501,)),
        ),
        unavailable=unavailable,
    )


def test_t11_a_proven_conflict_reopens_the_weeks_and_finds_the_witness():
    spec = _shared_teacher_spec(
        grid=((0, time(9), time(10)), (0, time(9, 30), time(10, 30))),
        periods=(
            (ORIGIN, time(9), time(10)),
            (ORIGIN, time(9, 30), time(10, 30)),
            (NEXT_WEEK, time(9), time(10)),
        ),
    )
    fixture = build_fixture("search-reopens-weeks", spec)

    result = generate_schedule(fixture.snapshot, fixture.periods, time_limit_seconds=10)

    assert result.outcome == "COMPLETE"
    assert result.report is not None and result.report.valid
    assert result.evidence is not None
    assert result.evidence.rounds >= 2
    assert result.evidence.relaxation_bound == 0
    weeks = {
        (lesson.period.school_date - fixture.snapshot.origin).days // 7
        for lesson in result.candidate.lessons
    }
    assert weeks == {0, 1}


def test_t10_sufficient_weekly_sums_do_not_replace_the_detailed_proof():
    spec = _shared_teacher_spec(
        grid=OVERLAPPING_GRID,
        periods=(
            (ORIGIN, time(9), time(10)),
            (ORIGIN, time(9, 30), time(10, 30)),
        ),
    )
    fixture = build_fixture("search-exhausted", spec, expectation=CaseExpectation.INFEASIBLE_PROVEN)

    result = generate_schedule(fixture.snapshot, fixture.periods, time_limit_seconds=10)

    assert result.outcome == "INFEASIBLE"
    assert result.evidence is not None
    assert result.evidence.stop_reason == "INFEASIBLE"


def test_only_a_proven_infeasibility_becomes_a_cut():
    assert feedback_cut(STATUS_INFEASIBLE) is True
    assert feedback_cut(STATUS_INCONCLUSIVE) is False
    assert feedback_cut(STATUS_COMPLETE) is False
