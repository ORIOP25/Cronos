from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from app.scheduler.domain.debt import DebtBalance, DebtClaim, reconcile_debt
from app.scheduler.domain.demand import (
    ExecutionEntry,
    ModuleCredit,
    append_execution,
    close_retired_modules,
    completed_by_module,
    frontier_credit,
    joint_frontier_credit,
    remaining_minutes,
)
from app.scheduler.domain.projection import ModuleRequirement

MODULES = (
    ModuleRequirement(1, 1, 600),
    ModuleRequirement(2, 2, 600),
)
RECORDED_AT = datetime(2026, 9, 23, 12, tzinfo=UTC)


def entry(origin, revision, *credits, reversal_of=None):
    return ExecutionEntry(
        origin,
        revision,
        7,
        "Confirmed by school",
        credits,
        reversal_of,
        recorded_at=RECORDED_AT,
    )


def test_t04_repeating_the_same_execution_does_not_credit_twice():
    execution = entry("lesson:31", 1, ModuleCredit(1, 300), ModuleCredit(2, 100))

    recorded = append_execution((), execution, MODULES)
    repeated = append_execution(recorded, execution, MODULES)

    assert repeated == recorded
    assert completed_by_module(MODULES, repeated) == {1: 300, 2: 100}
    assert remaining_minutes(MODULES, repeated) == 800


def test_t06_positive_adjustment_and_audited_reversal_restore_demand():
    adjustment = entry("manual:8", 1, ModuleCredit(1, 600))
    reversal = entry("manual:8", 2, ModuleCredit(1, -600), reversal_of=("manual:8", 1))

    recorded = append_execution((), adjustment, MODULES)
    recorded = append_execution(recorded, reversal, MODULES)

    assert completed_by_module(MODULES, recorded) == {1: 0, 2: 0}
    assert remaining_minutes(MODULES, recorded) == 1200
    assert len(recorded) == 2


def test_t30_all_required_minutes_executed_leave_no_future_demand():
    recorded = append_execution(
        (), entry("lesson:all", 1, ModuleCredit(1, 600), ModuleCredit(2, 600)), MODULES
    )

    assert remaining_minutes(MODULES, recorded) == 0


def test_conflicting_replay_and_out_of_bounds_adjustments_are_rejected():
    recorded = append_execution((), entry("manual:8", 1, ModuleCredit(1, 500)), MODULES)

    with pytest.raises(ValueError):
        append_execution(recorded, entry("manual:8", 1, ModuleCredit(1, 400)), MODULES)
    with pytest.raises(ValueError):
        append_execution(recorded, entry("manual:9", 1, ModuleCredit(1, 101)), MODULES)
    with pytest.raises(ValueError):
        append_execution(recorded, entry("manual:9", 1, ModuleCredit(1, -501)), MODULES)


def test_reversal_must_reference_an_existing_entry_and_its_minutes():
    recorded = append_execution((), entry("manual:8", 1, ModuleCredit(1, 500)), MODULES)

    with pytest.raises(ValueError):
        append_execution(
            recorded,
            entry("manual:8", 2, ModuleCredit(1, -500), reversal_of=("missing", 1)),
            MODULES,
        )
    with pytest.raises(ValueError):
        append_execution(
            recorded,
            entry("manual:8", 2, ModuleCredit(1, -501), reversal_of=("manual:8", 1)),
            MODULES,
        )


def test_repeated_entry_still_rejects_corrupt_existing_progress():
    excessive = entry("manual:8", 1, ModuleCredit(1, 601))

    with pytest.raises(ValueError):
        append_execution((excessive,), excessive, MODULES)


def test_execution_entry_cannot_hold_mutable_credit_slices():
    with pytest.raises(ValueError):
        ExecutionEntry(
            "lesson:1", 1, 7, "Confirmed", [ModuleCredit(1, 50)], recorded_at=RECORDED_AT
        )


def test_execution_audit_instant_must_be_explicit_utc():
    with pytest.raises(ValueError, match="UTC"):
        ExecutionEntry(
            "lesson:1",
            1,
            7,
            "Confirmed",
            (ModuleCredit(1, 50),),
            recorded_at=datetime(2026, 9, 23, 12),
        )
    with pytest.raises(ValueError, match="UTC"):
        ExecutionEntry(
            "lesson:1",
            1,
            7,
            "Confirmed",
            (ModuleCredit(1, 50),),
            recorded_at=datetime(2026, 9, 23, 12, tzinfo=timezone(timedelta(hours=1))),
        )


def test_close_retired_modules_keeps_planned_modules_unchanged():
    closed, completed = close_retired_modules(MODULES, frozenset(), {1: 100, 2: 0})

    assert closed == MODULES
    assert completed == {1: 100, 2: 0}


def test_close_retired_modules_closes_a_retired_module_at_its_executed_minutes():
    closed, completed = close_retired_modules(MODULES, frozenset({1}), {1: 250, 2: 0})

    assert closed == (ModuleRequirement(1, 1, 250), ModuleRequirement(2, 2, 600))
    assert completed == {1: 250, 2: 0}


def test_close_retired_modules_drops_a_retired_module_without_minutes():
    closed, completed = close_retired_modules(MODULES, frozenset({2}), {1: 100, 2: 0})

    assert closed == (ModuleRequirement(1, 1, 600),)
    assert completed == {1: 100}


def test_frontier_credit_on_the_planning_view_never_credits_a_retired_module():
    planning, completed = close_retired_modules(MODULES, frozenset({1}), {1: 250, 2: 0})

    assert frontier_credit(planning, completed, 100) == (ModuleCredit(2, 100),)


def test_t29_substitution_credits_taught_subject_and_leaves_original_demand():
    original = (ModuleRequirement(1, 1, 50),)
    substitute = (ModuleRequirement(2, 1, 50),)
    taught = append_execution((), entry("substitution:9", 1, ModuleCredit(2, 50)), substitute)

    assert remaining_minutes(original, ()) == 50
    assert remaining_minutes(substitute, taught) == 0
    assert reconcile_debt((DebtClaim(1, date(2026, 9, 22), 50),), residual_minutes=50) == (
        DebtBalance(1, open_minutes=50, reserved_minutes=0),
    )


def test_joint_frontier_credit_uses_the_highest_progress_and_never_exceeds_a_class():
    modules = (ModuleRequirement(1, 1, 100), ModuleRequirement(2, 2, 100))
    ahead = {1: {1: 80, 2: 0}, 2: {1: 30, 2: 0}}

    credit = joint_frontier_credit(modules, ahead, 50)

    assert credit == (ModuleCredit(1, 20), ModuleCredit(2, 30))
    for completed in ahead.values():
        assert all(
            item.minutes
            <= modules[item.module_id - 1].required_minutes - completed.get(item.module_id, 0)
            for item in credit
        )


def test_joint_frontier_credit_without_a_class_is_rejected():
    with pytest.raises(ValueError):
        joint_frontier_credit(MODULES, {}, 30)


def test_close_retired_modules_keeps_planned_requirements_and_minutes():
    completed = {1: 300, 2: 100}

    planning, minutes = close_retired_modules(MODULES, frozenset(), completed)

    assert planning == MODULES
    assert minutes == completed


def test_close_retired_module_with_execution_is_closed_at_those_minutes():
    modules = (
        ModuleRequirement(1, 1, 600),
        ModuleRequirement(2, 2, 600),
        ModuleRequirement(3, 3, 600),
    )

    planning, minutes = close_retired_modules(modules, frozenset({2}), {1: 100, 2: 250, 3: 0})

    assert planning == (
        ModuleRequirement(1, 1, 600),
        ModuleRequirement(2, 2, 250),
        ModuleRequirement(3, 3, 600),
    )
    assert minutes == {1: 100, 2: 250, 3: 0}


def test_close_retired_module_without_execution_leaves_the_planning_view():
    modules = (
        ModuleRequirement(1, 1, 600),
        ModuleRequirement(2, 2, 600),
        ModuleRequirement(3, 3, 600),
    )

    planning, minutes = close_retired_modules(modules, frozenset({2}), {1: 100, 2: 0, 3: 40})

    assert planning == (ModuleRequirement(1, 1, 600), ModuleRequirement(3, 3, 600))
    assert minutes == {1: 100, 3: 40}


def test_frontier_credit_never_credits_a_closed_retired_module():
    modules = (
        ModuleRequirement(1, 1, 100),
        ModuleRequirement(2, 2, 100),
        ModuleRequirement(3, 3, 100),
    )
    planning, minutes = close_retired_modules(modules, frozenset({1}), {1: 40, 2: 0, 3: 0})

    assert frontier_credit(planning, minutes, 120) == (
        ModuleCredit(2, 100),
        ModuleCredit(3, 20),
    )
