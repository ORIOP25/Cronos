from dataclasses import replace
from datetime import date, time, timedelta

from app.scheduler.domain.candidate import SchedulingStrategy
from app.scheduler.infrastructure.annual_model import (
    STATUS_FEASIBLE,
    STATUS_INFEASIBLE,
    QuotaDistribution,
    plan_annual_quotas,
)
from app.scheduler.lab.fixtures import AssignmentSpec, FixtureSpec, build_snapshot

TZ = "Europe/Lisbon"
ORIGIN = date(2026, 9, 21)
GRID = ((0, time(9), time(10)), (0, time(10), time(11)))
NEXT_WEEK = ORIGIN + timedelta(days=7)


def _snapshot(*, module_minutes=(100,), periods=None, assignments=None, rooms=(500,)):
    spec = FixtureSpec(
        strategy=SchedulingStrategy.COMPLETE_GENERATION,
        origin=ORIGIN,
        preferred_end_date=date(2026, 10, 30),
        hard_end_date=date(2026, 11, 30),
        timezone_name=TZ,
        grid_slots=GRID,
        periods=periods or ((ORIGIN, time(9), time(10)), (ORIGIN, time(10), time(11))),
        assignments=assignments or (AssignmentSpec(1, 7, module_minutes, rooms),),
    )
    return build_snapshot(spec)


def _periods(*rows):
    from app.scheduler.domain.calendar import normalize_period

    return tuple(normalize_period(day, start, end, TZ) for day, start, end in rows)


def test_annual_quotas_cover_the_exact_residual_with_partial_waste():
    snapshot = _snapshot(module_minutes=(100,))
    periods = _periods(
        (ORIGIN, time(9), time(10)),
        (ORIGIN, time(10), time(11)),
    )

    plan = plan_annual_quotas(snapshot, periods, time_limit_seconds=5)

    assert plan.status == STATUS_FEASIBLE
    assert plan.latest_week == 0
    assert plan.distribution.total_physical_minutes() == 120
    assert plan.distribution.total_physical_minutes() - plan.waste_minutes == 100
    assert all(week == 0 for _, week, _ in plan.distribution.counts)


def test_first_complete_annual_planning_skips_subsequent_waste_search(monkeypatch):
    from ortools.sat.python import cp_model

    original = cp_model.CpSolver.Solve
    calls = []

    def first_solve(solver, model, *args, **kwargs):
        assert solver.parameters.stop_after_first_solution
        calls.append(True)
        return original(solver, model, *args, **kwargs)

    monkeypatch.setattr(cp_model.CpSolver, "Solve", first_solve)
    snapshot = _snapshot(module_minutes=(100,))
    periods = _periods((ORIGIN, time(9), time(10)), (ORIGIN, time(10), time(11)))

    plan = plan_annual_quotas(snapshot, periods, stop_at_first_complete=True)

    assert plan.status == STATUS_FEASIBLE
    assert plan.distribution.total_physical_minutes() - plan.waste_minutes == 100
    assert calls == [True]


def test_no_quota_is_placed_after_the_final_week():
    snapshot = _snapshot(module_minutes=(120,))
    periods = _periods(
        (ORIGIN, time(9), time(10)),
        (ORIGIN, time(10), time(11)),
        (NEXT_WEEK, time(9), time(10)),
        (NEXT_WEEK, time(10), time(11)),
    )

    plan = plan_annual_quotas(snapshot, periods, time_limit_seconds=5)

    assert plan.status == STATUS_FEASIBLE
    assert plan.latest_week == 0
    assert all(week == 0 for _, week, _ in plan.distribution.counts)


def test_weekly_capacity_uses_the_joint_availability_of_the_class():
    assignments = (
        AssignmentSpec(1, 7, (60,), (500,)),
        AssignmentSpec(1, 8, (60,), (501,)),
    )
    snapshot = _snapshot(
        assignments=assignments,
        periods=((ORIGIN, time(9), time(10)),),
    )

    plan = plan_annual_quotas(snapshot, _periods((ORIGIN, time(9), time(10))), time_limit_seconds=5)

    assert plan.status == STATUS_INFEASIBLE
    assert plan.distribution is None


def test_excluded_distributions_are_not_planned_again():
    snapshot = _snapshot(module_minutes=(60,))
    periods = _periods(
        (ORIGIN, time(9), time(10)),
        (NEXT_WEEK, time(9), time(10)),
    )
    excluded = QuotaDistribution({(1, 0, 60): 1}, final_groups={1: (0, 60)})

    plan = plan_annual_quotas(
        snapshot,
        periods,
        excluded=(excluded,),
        time_limit_seconds=5,
    )

    assert plan.status == STATUS_FEASIBLE
    assert dict(plan.distribution.counts) == {(1, 1, 60): 1}
    assert dict(plan.distribution.final_groups) == {1: (1, 60)}


def test_excluding_every_distribution_proves_infeasibility():
    snapshot = _snapshot(module_minutes=(60,))
    periods = _periods(
        (ORIGIN, time(9), time(10)),
    )
    excluded = QuotaDistribution({(1, 0, 60): 1}, final_groups={1: (0, 60)})

    plan = plan_annual_quotas(
        snapshot,
        periods,
        excluded=(excluded,),
        time_limit_seconds=5,
    )

    assert plan.status == STATUS_INFEASIBLE


def test_a_successor_gets_no_quota_before_its_predecessor_week():
    week0 = (ORIGIN, time(9), time(10))
    week1 = (NEXT_WEEK, time(9), time(10))
    base = build_snapshot(
        FixtureSpec(
            strategy=SchedulingStrategy.COMPLETE_GENERATION,
            origin=ORIGIN,
            preferred_end_date=date(2026, 10, 30),
            hard_end_date=date(2026, 11, 30),
            timezone_name=TZ,
            grid_slots=((0, time(9), time(10)),),
            periods=(week0, week1),
            assignments=(
                AssignmentSpec(1, 7, (60,), (500,)),
                AssignmentSpec(2, 8, (60,), (501,)),
            ),
            unavailable=(("teacher", 7, week0),),
        )
    )
    snapshot = replace(base, precedences=((1, 2),))

    plan = plan_annual_quotas(snapshot, _periods(week0, week1), time_limit_seconds=5)

    assert plan.status == STATUS_FEASIBLE
    assert all(owner != 2 or week == 1 for owner, week, _duration in plan.distribution.counts)
