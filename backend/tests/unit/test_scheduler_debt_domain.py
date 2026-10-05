from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from app.scheduler.domain.debt import (
    DebtBalance,
    DebtClaim,
    DebtOrigin,
    DebtRevision,
    DebtSettlement,
    RecoveryAllocation,
    reconcile_debt,
    settlements_for_positive_credit,
)


def claim(claim_id: int, minutes: int) -> DebtClaim:
    return DebtClaim(claim_id, date(2026, 9, 22), minutes)


def test_debt_origin_requires_audited_utc_minutes_and_reason():
    recorded_at = datetime(2026, 9, 23, 10, tzinfo=UTC)
    valid = DebtOrigin("occurrence:1", 1, date(2026, 9, 22), 50, 3, "Missed lesson", recorded_at)
    assert valid.minutes == 50
    with pytest.raises(ValueError, match="positive integer"):
        DebtOrigin("occurrence:1", 1, date(2026, 9, 22), 0, 3, "Missed", recorded_at)
    with pytest.raises(ValueError, match="reason"):
        DebtOrigin("occurrence:1", 1, date(2026, 9, 22), 50, 3, "", recorded_at)
    with pytest.raises(ValueError, match="UTC"):
        DebtOrigin(
            "occurrence:1",
            1,
            date(2026, 9, 22),
            50,
            3,
            "Missed",
            recorded_at.astimezone(timezone(timedelta(hours=1))),
        )


def test_t05_cancelling_a_planned_recovery_releases_reservation_without_new_debt():
    claims = (claim(1, 50),)
    reserved = reconcile_debt(
        claims,
        allocations=(RecoveryAllocation(7, 20, 1, 50),),
        active_version_id=7,
        future_lesson_credits={20: 50},
        residual_minutes=50,
    )
    cancelled = reconcile_debt(claims, active_version_id=7, residual_minutes=50)

    assert reserved == (DebtBalance(1, open_minutes=50, reserved_minutes=50),)
    assert cancelled == (DebtBalance(1, open_minutes=50, reserved_minutes=0),)


def test_t05_revising_original_occurrence_after_cancellation_changes_same_claim():
    revised = reconcile_debt(
        (claim(1, 50),),
        revisions=(DebtRevision(1, "occurrence:4", 2, -20),),
        active_version_id=7,
        residual_minutes=30,
    )

    assert revised == (DebtBalance(1, open_minutes=30, reserved_minutes=0),)


def test_many_to_many_allocations_conserve_claim_and_lesson_credit():
    balances = reconcile_debt(
        (claim(1, 50), claim(2, 30)),
        allocations=(
            RecoveryAllocation(7, 20, 1, 20),
            RecoveryAllocation(7, 21, 1, 30),
            RecoveryAllocation(7, 20, 2, 30),
            RecoveryAllocation(8, 20, 1, 50),  # pending proposal is separate
        ),
        active_version_id=7,
        future_lesson_credits={20: 50, 21: 30},
        residual_minutes=80,
    )

    assert balances == (
        DebtBalance(1, open_minutes=50, reserved_minutes=50),
        DebtBalance(2, open_minutes=30, reserved_minutes=30),
    )


def test_execution_settles_debt_once_and_revisions_change_only_its_origin():
    balances = reconcile_debt(
        (claim(1, 50),),
        revisions=(DebtRevision(1, "occurrence:4", 2, -20),),
        settlements=(DebtSettlement(1, ("lesson:20", 1), 30),),
        executed_credit_by_event={("lesson:20", 1): 50},
        residual_minutes=20,
    )

    assert balances == (DebtBalance(1, open_minutes=0, reserved_minutes=0),)


def test_reversing_recorded_execution_reopens_its_settled_debt():
    balances = reconcile_debt(
        (claim(1, 30),),
        settlements=(
            DebtSettlement(1, ("lesson:20", 1), 30),
            DebtSettlement(1, ("lesson:20", 2), -30, reversal_of=("lesson:20", 1)),
        ),
        executed_credit_by_event={("lesson:20", 1): 30, ("lesson:20", 2): -30},
        residual_minutes=30,
    )

    assert balances == (DebtBalance(1, open_minutes=30, reserved_minutes=0),)


def test_cancelled_debt_reconciles_reversed_settlements_without_erasing_history():
    settlements = (
        DebtSettlement(1, ("lesson:20", 1), 50),
        DebtSettlement(1, ("lesson:20", 2), -50, reversal_of=("lesson:20", 1)),
    )
    arguments = dict(
        revisions=(DebtRevision(1, "revoke:20", 1, -50),),
        executed_credit_by_event={("lesson:20", 1): 50, ("lesson:20", 2): -50},
        residual_minutes=50,
    )
    assert reconcile_debt((claim(1, 50),), settlements=settlements, **arguments) == (
        DebtBalance(1, open_minutes=0, reserved_minutes=0),
    )
    with pytest.raises(ValueError, match="exceeds the open claim"):
        reconcile_debt((claim(1, 50),), settlements=settlements[:1], **arguments)


def test_reservations_and_settlements_cannot_exceed_real_credit_or_open_debt():
    with pytest.raises(ValueError):
        reconcile_debt((claim(1, 50),), residual_minutes=49)
    with pytest.raises(ValueError):
        reconcile_debt(
            (claim(1, 50),),
            allocations=(RecoveryAllocation(7, 20, 1, 51),),
            active_version_id=7,
            future_lesson_credits={20: 100},
            residual_minutes=50,
        )
    with pytest.raises(ValueError):
        reconcile_debt(
            (claim(1, 50),),
            settlements=(DebtSettlement(1, ("lesson:20", 1), 50),),
            executed_credit_by_event={("lesson:20", 1): 49},
            residual_minutes=0,
        )
    with pytest.raises(ValueError):
        DebtSettlement(1, ("lesson:20", 2), -30)


def test_positive_adjustment_reconciles_oldest_open_debt_then_stable_id():
    claims = (
        DebtClaim(4, date(2026, 9, 24), 40),
        DebtClaim(3, date(2026, 9, 22), 25),
        DebtClaim(2, date(2026, 9, 22), 30),
    )
    balances = reconcile_debt(claims, residual_minutes=95)

    selected = settlements_for_positive_credit(claims, balances, ("adjustment:7", 1), 60)

    assert selected == (
        DebtSettlement(2, ("adjustment:7", 1), 30),
        DebtSettlement(3, ("adjustment:7", 1), 25),
        DebtSettlement(4, ("adjustment:7", 1), 5),
    )
    assert reconcile_debt(
        claims,
        residual_minutes=35,
        settlements=selected,
        executed_credit_by_event={("adjustment:7", 1): 60},
    ) == (
        DebtBalance(4, 35, 0),
        DebtBalance(3, 0, 0),
        DebtBalance(2, 0, 0),
    )


def test_positive_adjustment_with_explicit_origin_only_settles_that_claim():
    claims = (claim(1, 40), claim(2, 30))
    balances = reconcile_debt(claims, residual_minutes=70)

    selected = settlements_for_positive_credit(
        claims, balances, ("adjustment:8", 1), 50, claim_id=2
    )

    assert selected == (DebtSettlement(2, ("adjustment:8", 1), 30),)
    with pytest.raises(ValueError):
        settlements_for_positive_credit(claims, balances, ("adjustment:8", 1), 50, claim_id=3)
