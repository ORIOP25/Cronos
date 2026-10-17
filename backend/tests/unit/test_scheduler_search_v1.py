from dataclasses import replace
from datetime import date, time, timedelta

import app.scheduler.infrastructure.search as search_module
from app.scheduler.composition import generate_schedule
from app.scheduler.domain.candidate import CandidateSchedule, HomeRoom, SchedulingStrategy
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
from tests.unit.test_scheduler_recovery_solver_v1 import POLICY
from tests.unit.test_scheduler_resource_exclusivity_v1 import assignment, lesson, plan
from tests.unit.test_scheduler_w04_w05_regressions_v1 import period

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


def test_r21_the_exact_path_published_incumbent_takes_the_new_home_room():
    """❌ R21: no caminho exato, o incumbente publicado também recebe a sala nova da turma.

    No protected lesson shares A's day here: a protected lesson in the old room would add
    a room change to the certified room cost, and the guard would refuse the move (T12).
    """
    periods = (period(0, 9, 10), period(0, 10, 11))
    assignments = [assignment(1, 1, 1, {1, 2, 3}, 120), assignment(2, 2, 2, {1, 2, 3}, 120)]
    baseline = CandidateSchedule(
        (
            lesson(1, 1, periods[0], 1),
            lesson(2, 1, periods[1], 1, offset=60),
            lesson(3, 2, periods[0], 2),
            lesson(4, 2, periods[1], 2, offset=60),
        )
    )
    target = replace(
        plan(periods, assignments),
        strategy=SchedulingStrategy.ADAPTIVE_RECOVERY,
        baseline_lessons=baseline.lessons,
        home_rooms=(HomeRoom(class_id=1, room_id=3),),
    )
    profile = search_module._SearchProfile(
        baseline, replace(POLICY, daily_slopes=tuple(range(1, 21)))
    )

    incumbent = search_module._baseline_incumbent(target, profile)

    assert incumbent is not None
    outcome, _vector = incumbent
    assert {
        (row.assignment_id, row.period.start_local.hour): row.room_id
        for row in outcome.candidate.lessons
    } == {(1, 9): 3, (1, 10): 3, (2, 9): 2, (2, 10): 2}
