"""Debt balances, future reservations, and executed settlements."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta


def _positive(value: int, name: str) -> None:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer.")


@dataclass(frozen=True)
class DebtOrigin:
    origin: str
    revision: int
    origin_date: date
    minutes: int
    author_id: int
    reason: str
    recorded_at: datetime

    def __post_init__(self) -> None:
        if (
            type(self.origin) is not str
            or not self.origin.strip()
            or type(self.reason) is not str
            or not self.reason.strip()
        ):
            raise ValueError("Debt origin and reason are required.")
        for name in ("revision", "minutes", "author_id"):
            _positive(getattr(self, name), name)
        if type(self.origin_date) is not date:
            raise ValueError("Debt origin date must be a date.")
        if type(self.recorded_at) is not datetime or self.recorded_at.utcoffset() != timedelta(0):
            raise ValueError("Debt audit instant must be UTC with timezone.")


@dataclass(frozen=True)
class DebtClaim:
    claim_id: int
    origin_date: date
    created_minutes: int

    def __post_init__(self) -> None:
        _positive(self.claim_id, "claim_id")
        if type(self.origin_date) is not date:
            raise ValueError("origin_date must be a date.")
        _positive(self.created_minutes, "created_minutes")


@dataclass(frozen=True)
class DebtRevision:
    claim_id: int
    origin: str
    revision: int
    delta_minutes: int

    def __post_init__(self) -> None:
        _positive(self.claim_id, "claim_id")
        _positive(self.revision, "revision")
        if not self.origin or type(self.delta_minutes) is not int or self.delta_minutes == 0:
            raise ValueError("Debt revision needs an origin and nonzero minute delta.")


@dataclass(frozen=True)
class DebtSettlement:
    claim_id: int
    execution_key: tuple[str, int]
    minutes: int
    reversal_of: tuple[str, int] | None = None

    def __post_init__(self) -> None:
        _positive(self.claim_id, "claim_id")
        if type(self.minutes) is not int or self.minutes == 0:
            raise ValueError("Settlement minutes must be a nonzero integer.")
        if (self.minutes < 0) != (self.reversal_of is not None):
            raise ValueError("A negative settlement must reference the settlement it reverses.")


@dataclass(frozen=True)
class RecoveryAllocation:
    version_id: int
    lesson_id: int
    claim_id: int
    minutes: int

    def __post_init__(self) -> None:
        for name in ("version_id", "lesson_id", "claim_id", "minutes"):
            _positive(getattr(self, name), name)


@dataclass(frozen=True)
class DebtBalance:
    claim_id: int
    open_minutes: int
    reserved_minutes: int


def settlements_for_positive_credit(
    claims: Sequence[DebtClaim],
    balances: Sequence[DebtBalance],
    execution_key: tuple[str, int],
    credit_minutes: int,
    *,
    claim_id: int | None = None,
) -> tuple[DebtSettlement, ...]:
    """Select open debt for an audited positive credit, oldest origin first."""
    _positive(credit_minutes, "credit_minutes")
    open_by_claim = {balance.claim_id: balance.open_minutes for balance in balances}
    if (
        len(open_by_claim) != len(balances)
        or len(open_by_claim) != len(claims)
        or set(open_by_claim) != {claim.claim_id for claim in claims}
    ):
        raise ValueError("Debt balances must match distinct claims.")
    if claim_id is not None and claim_id not in open_by_claim:
        raise ValueError("Explicit debt origin is unknown.")
    if any(type(minutes) is not int or minutes < 0 for minutes in open_by_claim.values()):
        raise ValueError("Open debt must be nonnegative minutes.")

    ordered = sorted(claims, key=lambda claim: (claim.origin_date, claim.claim_id))
    if claim_id is not None:
        ordered = [claim for claim in ordered if claim.claim_id == claim_id]
    remaining = credit_minutes
    selected = []
    for claim in ordered:
        minutes = min(remaining, open_by_claim[claim.claim_id])
        if minutes:
            selected.append(DebtSettlement(claim.claim_id, execution_key, minutes))
            remaining -= minutes
        if not remaining:
            break
    return tuple(selected)


def reconcile_debt(
    claims: Sequence[DebtClaim],
    *,
    residual_minutes: int,
    revisions: Sequence[DebtRevision] = (),
    settlements: Sequence[DebtSettlement] = (),
    allocations: Sequence[RecoveryAllocation] = (),
    active_version_id: int | None = None,
    future_lesson_credits: Mapping[int, int] | None = None,
    executed_credit_by_event: Mapping[tuple[str, int], int] | None = None,
) -> tuple[DebtBalance, ...]:
    if type(residual_minutes) is not int or residual_minutes < 0:
        raise ValueError("Residual demand must be nonnegative minutes.")
    open_by_claim = {claim.claim_id: claim.created_minutes for claim in claims}
    if len(open_by_claim) != len(claims):
        raise ValueError("Debt claim IDs must be unique.")
    seen_revisions = set()
    for revision in revisions:
        key = revision.claim_id, revision.origin, revision.revision
        if revision.claim_id not in open_by_claim or key in seen_revisions:
            raise ValueError("Debt revision has an unknown claim or duplicate origin.")
        seen_revisions.add(key)
        open_by_claim[revision.claim_id] += revision.delta_minutes
        if open_by_claim[revision.claim_id] < 0:
            raise ValueError("Debt revision exceeds the open claim.")

    executed_credit_by_event = executed_credit_by_event or {}
    settled_by_event: dict[tuple[str, int], int] = {}
    settlement_by_key = {}
    reversed_by_settlement: dict[tuple[int, tuple[str, int]], int] = {}
    for settlement in settlements:
        key = settlement.claim_id, settlement.execution_key
        if settlement.claim_id not in open_by_claim or key in settlement_by_key:
            raise ValueError("Debt settlement has an unknown claim or duplicate execution.")
        executed_credit = executed_credit_by_event.get(settlement.execution_key)
        if executed_credit is None or settlement.minutes * executed_credit <= 0:
            raise ValueError("Debt can only be settled by recorded execution.")
        if settlement.reversal_of is not None:
            original_key = settlement.claim_id, settlement.reversal_of
            original = settlement_by_key.get(original_key)
            if original is None or original.minutes <= 0:
                raise ValueError("Reversed debt must reference an earlier settlement.")
            reversed_by_settlement[original_key] = reversed_by_settlement.get(
                original_key, 0
            ) + abs(settlement.minutes)
            if reversed_by_settlement[original_key] > original.minutes:
                raise ValueError("Debt reversal exceeds the referenced settlement.")
        settled_by_event[settlement.execution_key] = (
            settled_by_event.get(settlement.execution_key, 0) + settlement.minutes
        )
        if abs(settled_by_event[settlement.execution_key]) > abs(executed_credit):
            raise ValueError("Debt settlement exceeds executed curricular credit.")
        open_by_claim[settlement.claim_id] -= settlement.minutes
        if open_by_claim[settlement.claim_id] < 0:
            raise ValueError("Debt settlement exceeds the open claim.")
        settlement_by_key[key] = settlement

    if sum(open_by_claim.values()) > residual_minutes:
        raise ValueError("Open debt exceeds residual curricular demand.")

    future_lesson_credits = future_lesson_credits or {}
    reserved_by_claim = dict.fromkeys(open_by_claim, 0)
    reserved_by_lesson: dict[int, int] = {}
    seen_allocations = set()
    for allocation in allocations:
        if allocation.claim_id not in open_by_claim:
            raise ValueError("Recovery allocation references an unknown claim.")
        if allocation.version_id != active_version_id:
            continue
        key = allocation.lesson_id, allocation.claim_id
        if key in seen_allocations:
            raise ValueError("Recovery allocation is duplicated within its version.")
        seen_allocations.add(key)
        if allocation.lesson_id not in future_lesson_credits:
            raise ValueError("Recovery allocation references an unknown future lesson.")
        reserved_by_claim[allocation.claim_id] += allocation.minutes
        reserved_by_lesson[allocation.lesson_id] = (
            reserved_by_lesson.get(allocation.lesson_id, 0) + allocation.minutes
        )
        if reserved_by_claim[allocation.claim_id] > open_by_claim[allocation.claim_id]:
            raise ValueError("Reserved recovery exceeds open debt.")
        if reserved_by_lesson[allocation.lesson_id] > future_lesson_credits[allocation.lesson_id]:
            raise ValueError("Recovery reservations exceed future lesson credit.")

    return tuple(
        DebtBalance(
            claim.claim_id, open_by_claim[claim.claim_id], reserved_by_claim[claim.claim_id]
        )
        for claim in claims
    )
