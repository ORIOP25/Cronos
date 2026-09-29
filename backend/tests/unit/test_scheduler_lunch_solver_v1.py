from dataclasses import replace
from datetime import date, time

from app.scheduler.composition import generate_schedule
from app.scheduler.domain.calendar import normalize_period
from app.scheduler.domain.candidate import (
    LunchRule,
    SchedulingStrategy,
    continuous_break_minutes,
)
from app.scheduler.domain.candidate_validation import validate_candidate
from app.scheduler.infrastructure.constructive import construct_schedule
from app.scheduler.infrastructure.placement_model import solve_placement
from app.scheduler.lab.fixtures import AssignmentSpec, FixtureSpec, build_snapshot

TZ = "Europe/Lisbon"
MONDAY = date(2026, 9, 21)
LUNCH = LunchRule(window_start=time(12), window_end=time(14), minimum_minutes=60)

GRID = ((0, time(12), time(13)), (0, time(13), time(14)), (0, time(14), time(15)))
PERIODS = ((MONDAY, time(12), time(13)), (MONDAY, time(13), time(14)), (MONDAY, time(14), time(15)))
NORMALIZED = tuple(normalize_period(day, start, end, TZ) for day, start, end in PERIODS)


def _snapshot(module_minutes: tuple[int, ...]):
    spec = FixtureSpec(
        strategy=SchedulingStrategy.COMPLETE_GENERATION,
        origin=MONDAY,
        preferred_end_date=date(2026, 10, 2),
        hard_end_date=date(2026, 10, 16),
        timezone_name=TZ,
        grid_slots=GRID,
        periods=PERIODS,
        assignments=(AssignmentSpec(1, 7, module_minutes, (500,)),),
    )
    return replace(build_snapshot(spec), lunch_rule=LUNCH)


def _breaks(candidate) -> int:
    intervals = [
        (
            lesson.period.start_local.hour * 60 + lesson.period.start_local.minute,
            lesson.period.end_local.hour * 60 + lesson.period.end_local.minute,
        )
        for lesson in candidate.lessons
    ]
    return continuous_break_minutes(intervals, LUNCH)


def test_constructive_preserves_a_continuous_lunch_break():
    snapshot = _snapshot((60, 60))

    candidate = construct_schedule(snapshot, NORMALIZED)

    assert candidate is not None
    assert _breaks(candidate) >= 60
    assert validate_candidate(snapshot, candidate).valid


def test_detailed_placement_respects_the_lunch_break():
    snapshot = _snapshot((60, 60))

    outcome = solve_placement(snapshot, NORMALIZED, time_limit_seconds=10)

    assert outcome.status == "COMPLETE"
    assert outcome.candidate is not None
    assert _breaks(outcome.candidate) >= 60
    assert validate_candidate(snapshot, outcome.candidate).valid


def test_generation_never_returns_a_candidate_without_the_lunch_break():
    snapshot = _snapshot((60, 60, 60))

    result = generate_schedule(
        snapshot, NORMALIZED, time_limit_seconds=10, num_workers=1, random_seed=1
    )

    assert result.candidate is None
    assert result.outcome in {"INFEASIBLE", "INCONCLUSIVE"}
