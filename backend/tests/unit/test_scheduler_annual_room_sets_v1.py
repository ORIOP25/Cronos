"""Annual master must bound each shared eligible room set.

Two or three classes can share the same two rooms. Each class and teacher has
enough weekly periods on its own, so only the physical capacity of the shared
room set can reject the demand. Before the fix the master ignored room capacity
whenever an assignment had more than one eligible room, so an impossible
distribution passed the relaxation.
"""

from datetime import date, time, timedelta

from app.scheduler.domain.calendar import normalize_period
from app.scheduler.domain.candidate import SchedulingStrategy
from app.scheduler.infrastructure.annual_model import (
    STATUS_FEASIBLE,
    STATUS_INFEASIBLE,
    plan_annual_quotas,
)
from app.scheduler.lab.fixtures import AssignmentSpec, FixtureSpec, build_snapshot

TZ = "Europe/Lisbon"
ORIGIN = date(2026, 9, 21)
DAYS = tuple(ORIGIN + timedelta(days=offset) for offset in range(5))
GRID = tuple(dict.fromkeys((day.weekday(), time(9), time(10)) for day in DAYS))
PERIODS = tuple((day, time(9), time(10)) for day in DAYS)
ROOMS = (100, 101)


def _spec(class_count: int) -> FixtureSpec:
    return FixtureSpec(
        strategy=SchedulingStrategy.COMPLETE_GENERATION,
        origin=ORIGIN,
        preferred_end_date=DAYS[-1],
        hard_end_date=DAYS[-1],
        timezone_name=TZ,
        grid_slots=GRID,
        periods=PERIODS,
        assignments=tuple(
            AssignmentSpec(
                class_id=index, teacher_id=index, module_minutes=(240,), eligible_rooms=ROOMS
            )
            for index in range(1, class_count + 1)
        ),
    )


def _periods():
    return tuple(normalize_period(day, start, end, TZ) for day, start, end in PERIODS)


def test_shared_room_set_capacity_rejects_an_impossible_distribution():
    # 3 classes x 240 min = 720 min. Two rooms x 5 periods x 60 min = 600 min.
    snapshot = build_snapshot(_spec(3))

    plan = plan_annual_quotas(snapshot, _periods(), time_limit_seconds=10, num_workers=2)

    assert plan.status == STATUS_INFEASIBLE
    assert plan.statistics["room_set_constraints"] >= 1


def test_shared_room_set_capacity_accepts_a_fitting_distribution():
    # 2 classes x 240 min = 480 min fits the 600 min shared room capacity.
    snapshot = build_snapshot(_spec(2))

    plan = plan_annual_quotas(snapshot, _periods(), time_limit_seconds=10, num_workers=2)

    assert plan.status == STATUS_FEASIBLE
    assert plan.distribution is not None
