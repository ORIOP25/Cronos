from datetime import UTC, date, datetime, time

from app.scheduler.domain.calendar import (
    grid_dates,
    is_physically_protected,
    normalize_period,
    protected_grid_dates,
)
from app.scheduler.domain.debt import (
    DebtBalance,
    DebtClaim,
    DebtSettlement,
    RecoveryAllocation,
    reconcile_debt,
)
from app.scheduler.domain.demand import (
    ExecutionEntry,
    ModuleCredit,
    append_execution,
    completed_by_module,
    remaining_minutes,
)
from app.scheduler.domain.projection import FutureLesson, ModuleRequirement, project_module_slices

RECORDED_AT = datetime(2026, 9, 23, 12, tzinfo=UTC)


def _entry(origin: str, revision: int, minutes: int, reversal_of=None) -> ExecutionEntry:
    return ExecutionEntry(
        origin,
        revision,
        7,
        "Confirmed by school",
        (ModuleCredit(1, minutes),),
        reversal_of,
        recorded_at=RECORDED_AT,
    )


def test_c01_domain_examples_for_clean_projection_and_empty_residual():
    modules = (ModuleRequirement(1, 1, 75), ModuleRequirement(2, 2, 75))
    lessons = tuple(FutureLesson(i, date(2026, 9, 21 + i), 9 * 60, 50, 50) for i in range(1, 4))

    x = project_module_slices(
        (ModuleRequirement(1, 1, 150),), completed_minutes={}, lessons=lessons
    )
    y = project_module_slices(modules, completed_minutes={}, lessons=lessons)
    z = project_module_slices(
        (ModuleRequirement(1, 1, 20), ModuleRequirement(2, 2, 15), ModuleRequirement(3, 3, 75)),
        completed_minutes={},
        lessons=(
            FutureLesson(1, date(2026, 9, 22), 9 * 60, 70, 70),
            FutureLesson(2, date(2026, 9, 23), 9 * 60, 50, 40),
        ),
    )
    recovered = project_module_slices(modules, completed_minutes={1: 75, 2: 75}, lessons=())

    assert [sum(part.credit_minutes for part in result) for result in (x, y, z, recovered)] == [
        150,
        150,
        110,
        0,
    ]
    assert [part.module_id for part in z if part.lesson_id == 1] == [1, 2, 3]
    assert recovered == ()


def test_c09_domain_examples_for_grid_protection():
    dates = grid_dates(date(2026, 9, 21), date(2026, 10, 16), {0, 2, 4})
    period = normalize_period(dates[3], time(9), time(9, 50), "Europe/Lisbon")
    now = datetime(2026, 9, 21, 8, tzinfo=UTC)

    x = is_physically_protected(period, now, protected_grid_dates(dates, dates[0], 0))
    y = is_physically_protected(period, now, protected_grid_dates(dates, dates[0], 1))
    z = is_physically_protected(period, now, protected_grid_dates(dates, dates[0], 9))
    recovered = is_physically_protected(period, now, protected_grid_dates(dates, dates[0], 0))

    assert (x, y, z, recovered) == (False, False, True, False)


def test_c13_domain_examples_for_accounting_transitions():
    modules = (ModuleRequirement(1, 1, 650),)
    claim = DebtClaim(1, date(2026, 9, 22), 50)
    recovery = RecoveryAllocation(7, 20, 1, 50)
    x = reconcile_debt(
        (claim,),
        residual_minutes=650,
        allocations=(recovery,),
        active_version_id=7,
        future_lesson_credits={20: 50},
    )

    cancelled = reconcile_debt((claim,), residual_minutes=650, active_version_id=7)
    executed = append_execution((), _entry("lesson:20", 1, 50), modules)
    executed = append_execution(executed, _entry("lesson:20", 1, 50), modules)
    y = reconcile_debt(
        (claim,),
        residual_minutes=remaining_minutes(modules, executed),
        settlements=(DebtSettlement(1, ("lesson:20", 1), 50),),
        executed_credit_by_event={("lesson:20", 1): 50},
    )

    adjusted = append_execution(executed, _entry("manual:8", 1, 600), modules)
    reversed_adjustment = append_execution(
        adjusted, _entry("manual:8", 2, -600, ("manual:8", 1)), modules
    )
    z = remaining_minutes(modules, reversed_adjustment)

    corrected = append_execution(
        reversed_adjustment, _entry("lesson:20", 2, -50, ("lesson:20", 1)), modules
    )
    reopened = reconcile_debt(
        (claim,),
        residual_minutes=remaining_minutes(modules, corrected),
        settlements=(
            DebtSettlement(1, ("lesson:20", 1), 50),
            DebtSettlement(1, ("lesson:20", 2), -50, ("lesson:20", 1)),
        ),
        allocations=(RecoveryAllocation(8, 30, 1, 50),),
        active_version_id=8,
        future_lesson_credits={30: 50},
        executed_credit_by_event={("lesson:20", 1): 50, ("lesson:20", 2): -50},
    )

    assert x == (DebtBalance(1, 50, 50),)
    assert cancelled == (DebtBalance(1, 50, 0),)
    assert y == (DebtBalance(1, 0, 0),)
    assert len(executed) == 1
    assert z == 600
    assert reopened == (DebtBalance(1, 50, 50),)


def test_c14_small_domain_replay_validates_each_transition():
    modules = (ModuleRequirement(1, 1, 75), ModuleRequirement(2, 2, 75))
    lessons = tuple(FutureLesson(i, date(2026, 9, 22 + i), 9 * 60, 50, 50) for i in range(1, 4))
    x = project_module_slices(modules, completed_minutes={}, lessons=lessons)

    executed = append_execution((), _entry("lesson:1", 1, 50), modules)
    y = project_module_slices(
        modules, completed_minutes=completed_by_module(modules, executed), lessons=lessons[1:]
    )

    replacement = FutureLesson(4, date(2026, 9, 26), 9 * 60, 50, 50)
    z = project_module_slices(
        modules,
        completed_minutes=completed_by_module(modules, executed),
        lessons=(lessons[2], replacement),
    )
    debt = DebtClaim(1, lessons[1].school_date, 50)
    reserved = reconcile_debt(
        (debt,),
        residual_minutes=100,
        allocations=(RecoveryAllocation(8, 4, 1, 50),),
        active_version_id=8,
        future_lesson_credits={4: 50},
    )

    executed = append_execution(
        executed,
        ExecutionEntry(
            "lesson:3",
            1,
            7,
            "Confirmed by school",
            (ModuleCredit(1, 25), ModuleCredit(2, 25)),
            recorded_at=RECORDED_AT,
        ),
        modules,
    )
    executed = append_execution(
        executed,
        ExecutionEntry(
            "lesson:4",
            1,
            7,
            "Confirmed by school",
            (ModuleCredit(2, 50),),
            recorded_at=RECORDED_AT,
        ),
        modules,
    )
    recovered = reconcile_debt(
        (debt,),
        residual_minutes=remaining_minutes(modules, executed),
        settlements=(DebtSettlement(1, ("lesson:4", 1), 50),),
        executed_credit_by_event={("lesson:4", 1): 50},
    )

    assert sum(part.credit_minutes for part in x) == 150
    assert sum(part.credit_minutes for part in y) == 100
    assert sum(part.credit_minutes for part in z) == 100
    assert reserved == (DebtBalance(1, 50, 50),)
    assert recovered == (DebtBalance(1, 0, 0),)
    assert remaining_minutes(modules, executed) == 0


def test_c13_substitution_credits_only_the_subject_actually_taught():
    planned_subject = (ModuleRequirement(1, 1, 50),)
    taught_subject = (ModuleRequirement(2, 1, 100),)
    substitution = ExecutionEntry(
        "substitution:42",
        1,
        7,
        "Subject 2 was taught",
        (ModuleCredit(2, 50),),
        recorded_at=RECORDED_AT,
    )

    taught_entries = append_execution((), substitution, taught_subject)
    planned_entries = ()
    planned_debt = reconcile_debt(
        (DebtClaim(1, date(2026, 9, 23), 50),),
        residual_minutes=remaining_minutes(planned_subject, planned_entries),
    )

    assert remaining_minutes(planned_subject, planned_entries) == 50
    assert remaining_minutes(taught_subject, taught_entries) == 50
    assert planned_debt == (DebtBalance(1, 50, 0),)
