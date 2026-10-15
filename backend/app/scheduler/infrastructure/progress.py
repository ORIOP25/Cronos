"""Persist audited curricular execution under the school-year state lock."""

from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
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
from app.scheduler.domain.demand import (
    ExecutionEntry,
    ModuleCredit,
    append_execution,
    close_retired_modules,
    completed_by_module,
    remaining_minutes,
)
from app.scheduler.domain.projection import ModuleRequirement
from app.scheduler.infrastructure.models import (
    CurricularAssignment,
    CurricularDebt,
    CurricularDebtRevision,
    CurricularDebtSettlement,
    CurricularExecution,
    CurricularExecutionCredit,
    CurricularRequirement,
    SchedulerLessonV1,
    SchedulerRecoveryReservationV1,
    SchedulerVersionV1,
)

ERR_MISSING_STATE = "Scheduler school-year state does not exist."


async def _locked_assignment(
    db: AsyncSession, organization_id: int, school_year_id: int, assignment_id: int
) -> tuple[models.SchedulerSchoolYearState, CurricularAssignment]:
    state = await db.scalar(
        select(models.SchedulerSchoolYearState)
        .where(
            models.SchedulerSchoolYearState.organization_id == organization_id,
            models.SchedulerSchoolYearState.school_year_id == school_year_id,
        )
        .with_for_update()
    )
    if state is None:
        raise ValueError(ERR_MISSING_STATE)
    assignment = await db.scalar(
        select(CurricularAssignment).where(
            CurricularAssignment.id == assignment_id,
            CurricularAssignment.organization_id == organization_id,
            CurricularAssignment.school_year_id == school_year_id,
        )
    )
    if assignment is None:
        raise ValueError("Curricular assignment does not belong to this school year.")
    return state, assignment


async def _requirements(
    db: AsyncSession, organization_id: int, assignment: CurricularAssignment
) -> tuple[ModuleRequirement, ...]:
    rows = (
        await db.execute(
            select(CurricularRequirement, models.Module.subject_id)
            .join(models.Module, models.Module.id == CurricularRequirement.module_id)
            .where(
                CurricularRequirement.organization_id == organization_id,
                CurricularRequirement.assignment_id == assignment.id,
            )
            .order_by(CurricularRequirement.sequence)
        )
    ).all()
    if not rows or any(subject_id != assignment.subject_id for _, subject_id in rows):
        raise ValueError("Assignment requirements must belong to its subject.")
    return tuple(
        ModuleRequirement(requirement.module_id, requirement.sequence, requirement.required_minutes)
        for requirement, _ in rows
    )


def _entries_from_rows(
    stored: Sequence[CurricularExecution],
    credits_by_execution: Mapping[int, Sequence[CurricularExecutionCredit]],
) -> tuple[ExecutionEntry, ...]:
    stored_by_id = {row.id: row for row in stored}
    if any(
        row.reversal_of_id is not None and row.reversal_of_id not in stored_by_id for row in stored
    ):
        raise ValueError("Execution reversal references another assignment.")
    return tuple(
        ExecutionEntry(
            row.origin,
            row.revision,
            row.author_membership_id,
            row.reason,
            tuple(
                ModuleCredit(credit.module_id, credit.delta_minutes)
                for credit in credits_by_execution[row.id]
            ),
            (
                stored_by_id[row.reversal_of_id].origin,
                stored_by_id[row.reversal_of_id].revision,
            )
            if row.reversal_of_id in stored_by_id
            else None,
            recorded_at=row.recorded_at,
        )
        for row in stored
    )


async def _execution_history(
    db: AsyncSession, organization_id: int, assignment_id: int
) -> tuple[
    list[CurricularExecution],
    dict[int, list[CurricularExecutionCredit]],
    tuple[ExecutionEntry, ...],
]:
    stored = (
        await db.scalars(
            select(CurricularExecution)
            .where(
                CurricularExecution.organization_id == organization_id,
                CurricularExecution.assignment_id == assignment_id,
            )
            .order_by(CurricularExecution.id)
        )
    ).all()
    credits_by_execution: dict[int, list[CurricularExecutionCredit]] = defaultdict(list)
    if stored:
        credits = (
            await db.scalars(
                select(CurricularExecutionCredit)
                .where(CurricularExecutionCredit.execution_id.in_([row.id for row in stored]))
                .order_by(CurricularExecutionCredit.id)
            )
        ).all()
        for credit in credits:
            credits_by_execution[credit.execution_id].append(credit)
    return stored, credits_by_execution, _entries_from_rows(stored, credits_by_execution)


async def _debt_history(
    db: AsyncSession,
    organization_id: int,
    assignment_id: int,
    stored: Sequence[CurricularExecution],
) -> tuple[
    list[CurricularDebt],
    list[CurricularDebtRevision],
    list[CurricularDebtSettlement],
    tuple[DebtSettlement, ...],
]:
    debts = (
        await db.scalars(
            select(CurricularDebt).where(
                CurricularDebt.organization_id == organization_id,
                CurricularDebt.assignment_id == assignment_id,
            )
        )
    ).all()
    debt_ids = [debt.id for debt in debts]
    if not debt_ids:
        return [], [], [], ()
    revisions = (
        await db.scalars(
            select(CurricularDebtRevision)
            .where(CurricularDebtRevision.debt_id.in_(debt_ids))
            .order_by(CurricularDebtRevision.id)
        )
    ).all()
    recorded = (
        await db.scalars(
            select(CurricularDebtSettlement)
            .where(CurricularDebtSettlement.debt_id.in_(debt_ids))
            .order_by(CurricularDebtSettlement.id)
        )
    ).all()
    stored_by_id = {row.id: row for row in stored}
    settlement_by_id = {row.id: row for row in recorded}
    if any(
        row.execution_id not in stored_by_id
        or (row.reversal_of_id is not None and row.reversal_of_id not in settlement_by_id)
        for row in recorded
    ):
        raise ValueError("Debt settlement references execution outside its assignment.")
    prior = tuple(
        DebtSettlement(
            row.debt_id,
            (stored_by_id[row.execution_id].origin, stored_by_id[row.execution_id].revision),
            row.minutes,
            (
                stored_by_id[settlement_by_id[row.reversal_of_id].execution_id].origin,
                stored_by_id[settlement_by_id[row.reversal_of_id].execution_id].revision,
            )
            if row.reversal_of_id is not None
            else None,
        )
        for row in recorded
    )
    return debts, revisions, recorded, prior


def _validate_debt_state(
    modules: Sequence[ModuleRequirement],
    entries: Sequence[ExecutionEntry],
    debts: Sequence[CurricularDebt],
    revisions: Sequence[CurricularDebtRevision],
    settlements: Sequence[DebtSettlement],
    *,
    allocations: Sequence[RecoveryAllocation] = (),
    active_version_id: int | None = None,
    future_lesson_credits: Mapping[int, int] | None = None,
) -> tuple[DebtBalance, ...]:
    return reconcile_debt(
        tuple(DebtClaim(debt.id, debt.origin_date, debt.created_minutes) for debt in debts),
        residual_minutes=remaining_minutes(modules, entries),
        revisions=tuple(
            DebtRevision(row.debt_id, row.origin, row.revision, row.delta_minutes)
            for row in revisions
        ),
        settlements=settlements,
        allocations=allocations,
        active_version_id=active_version_id,
        future_lesson_credits=future_lesson_credits,
        executed_credit_by_event={
            entry.key: sum(credit.minutes for credit in entry.credits) for entry in entries
        },
    )


async def load_active_version_id(
    db: AsyncSession, organization_id: int, school_year_id: int
) -> int | None:
    return await db.scalar(
        select(SchedulerVersionV1.id).where(
            SchedulerVersionV1.organization_id == organization_id,
            SchedulerVersionV1.school_year_id == school_year_id,
            SchedulerVersionV1.status == "ACTIVE",
        )
    )


async def _active_reservations(
    db: AsyncSession,
    organization_id: int,
    school_year_id: int,
    assignment_id: int,
    active_version_id: int | None,
) -> list[SchedulerRecoveryReservationV1]:
    if active_version_id is None:
        return []
    return list(
        (
            await db.scalars(
                select(SchedulerRecoveryReservationV1)
                .where(
                    SchedulerRecoveryReservationV1.organization_id == organization_id,
                    SchedulerRecoveryReservationV1.school_year_id == school_year_id,
                    SchedulerRecoveryReservationV1.assignment_id == assignment_id,
                    SchedulerRecoveryReservationV1.version_id == active_version_id,
                )
                .order_by(SchedulerRecoveryReservationV1.id)
            )
        ).all()
    )


async def _future_lesson_credits(
    db: AsyncSession,
    organization_id: int,
    school_year_id: int,
    assignment_id: int,
    version_id: int,
) -> dict[int, int]:
    rows = (
        await db.execute(
            select(SchedulerLessonV1.id, SchedulerLessonV1.credit_minutes).where(
                SchedulerLessonV1.organization_id == organization_id,
                SchedulerLessonV1.school_year_id == school_year_id,
                SchedulerLessonV1.assignment_id == assignment_id,
                SchedulerLessonV1.version_id == version_id,
            )
        )
    ).all()
    return dict(rows)


async def _release_excess_reservations(
    db: AsyncSession,
    organization_id: int,
    school_year_id: int,
    assignment_id: int,
    active_version_id: int | None,
    open_by_claim: Mapping[int, int],
) -> None:
    """Release active reservations so they never exceed the open debt."""
    reservations = await _active_reservations(
        db, organization_id, school_year_id, assignment_id, active_version_id
    )
    reserved: dict[int, int] = defaultdict(int)
    for reservation in reservations:
        reserved[reservation.debt_id] += reservation.minutes
    for claim_id in sorted(reserved):
        excess = reserved[claim_id] - open_by_claim.get(claim_id, 0)
        if excess <= 0:
            continue
        for reservation in reservations:
            if reservation.debt_id != claim_id or excess <= 0:
                continue
            if reservation.minutes <= excess:
                excess -= reservation.minutes
                await db.delete(reservation)
            else:
                reservation.minutes -= excess
                excess = 0
    await db.flush()


def _subtract_interval(
    intervals: list[tuple[int, int]], start: int, end: int
) -> list[tuple[int, int]]:
    remaining = []
    for low, high in intervals:
        if high <= start or low >= end:
            remaining.append((low, high))
            continue
        if low < start:
            remaining.append((low, start))
        if high > end:
            remaining.append((end, high))
    return remaining


def _effective_intervals(
    module_id: int,
    stored: Sequence[CurricularExecution],
    credits_by_execution: dict[int, list[CurricularExecutionCredit]],
) -> list[tuple[int, int]]:
    intervals: list[tuple[int, int]] = []
    for execution in stored:
        for credit in credits_by_execution[execution.id]:
            if credit.module_id != module_id:
                continue
            start = credit.offset_minutes
            end = start + abs(credit.delta_minutes)
            if credit.delta_minutes > 0:
                intervals.append((start, end))
            else:
                intervals = _subtract_interval(intervals, start, end)
    return intervals


def _next_free_offset(
    intervals: Sequence[tuple[int, int]], required_minutes: int, credit_minutes: int
) -> int:
    cursor = 0
    for low, high in sorted(intervals):
        if low - cursor >= credit_minutes:
            return cursor
        cursor = max(cursor, high)
    if required_minutes - cursor >= credit_minutes:
        return cursor
    raise ValueError("No free curricular interval can hold the new credit.")


def _reversal_offset(
    credit: ModuleCredit,
    reversal_id: int,
    stored: Sequence[CurricularExecution],
    credits_by_execution: dict[int, list[CurricularExecutionCredit]],
) -> int:
    original = next(
        row for row in credits_by_execution[reversal_id] if row.module_id == credit.module_id
    )
    reversed_before = sum(
        abs(row.delta_minutes)
        for event in stored
        if event.reversal_of_id == reversal_id
        for row in credits_by_execution[event.id]
        if row.module_id == credit.module_id
    )
    return (
        original.offset_minutes + original.delta_minutes - reversed_before - abs(credit.minutes)
        if original.delta_minutes > 0
        else original.offset_minutes + reversed_before
    )


def _credit_offset(
    credit: ModuleCredit,
    reversal_id: int | None,
    required_minutes: int,
    stored: Sequence[CurricularExecution],
    credits_by_execution: dict[int, list[CurricularExecutionCredit]],
) -> int:
    if reversal_id is None:
        return _next_free_offset(
            _effective_intervals(credit.module_id, stored, credits_by_execution),
            required_minutes,
            credit.minutes,
        )
    return _reversal_offset(credit, reversal_id, stored, credits_by_execution)


def _reversed_settlements(
    entry: ExecutionEntry,
    prior: Sequence[DebtSettlement],
    minutes: int,
) -> tuple[DebtSettlement, ...]:
    if entry.reversal_of is None:
        return ()
    already_reversed: dict[int, int] = defaultdict(int)
    for settlement in prior:
        if settlement.reversal_of == entry.reversal_of:
            already_reversed[settlement.claim_id] += abs(settlement.minutes)
    selected = []
    remaining = minutes
    for original in reversed(prior):
        if original.execution_key != entry.reversal_of or original.minutes <= 0:
            continue
        available = original.minutes - already_reversed[original.claim_id]
        reversed_minutes = min(remaining, max(0, available))
        if reversed_minutes:
            selected.append(
                DebtSettlement(original.claim_id, entry.key, -reversed_minutes, entry.reversal_of)
            )
            remaining -= reversed_minutes
        if not remaining:
            break
    return tuple(selected)


def _execution_settlements(
    modules, earlier, debts, revisions, prior_settlements, entry, settlements
):
    if settlements is None:
        balances = _validate_debt_state(modules, earlier, debts, revisions, prior_settlements)
        positive_credit = sum(credit.minutes for credit in entry.credits)
        if positive_credit > 0 and debts:
            settlements = settlements_for_positive_credit(
                tuple(DebtClaim(debt.id, debt.origin_date, debt.created_minutes) for debt in debts),
                balances,
                entry.key,
                positive_credit,
            )
        elif positive_credit < 0:
            settlements = _reversed_settlements(entry, prior_settlements, abs(positive_credit))
        else:
            settlements = ()
    return settlements


async def record_execution(
    db: AsyncSession,
    organization_id: int,
    school_year_id: int,
    assignment_id: int,
    entry: ExecutionEntry,
    *,
    planning_relevant: bool,
    settlements: Sequence[DebtSettlement] | None = None,
) -> int:
    """Append one execution and bump revisions in the caller's transaction."""
    state, assignment = await _locked_assignment(db, organization_id, school_year_id, assignment_id)

    await reconcile_assignment_requirements(db, organization_id, assignment.id)
    modules = await _requirements(db, organization_id, assignment)

    stored, credits_by_execution, earlier = await _execution_history(
        db, organization_id, assignment_id
    )
    required_by_module = {module.module_id: module.required_minutes for module in modules}
    updated = append_execution(earlier, entry, modules)
    debts, revisions, recorded_settlements, prior_settlements = await _debt_history(
        db, organization_id, assignment_id, stored
    )
    active_version_id = await load_active_version_id(db, organization_id, school_year_id)
    reservations = await _active_reservations(
        db, organization_id, school_year_id, assignment_id, active_version_id
    )
    allocations = tuple(
        RecoveryAllocation(row.version_id, row.lesson_id, row.debt_id, row.minutes)
        for row in reservations
    )
    future_credits = (
        await _future_lesson_credits(
            db, organization_id, school_year_id, assignment_id, active_version_id
        )
        if active_version_id is not None
        else {}
    )
    if updated == earlier:
        _validate_debt_state(
            modules,
            earlier,
            debts,
            revisions,
            prior_settlements,
            allocations=allocations,
            active_version_id=active_version_id,
            future_lesson_credits=future_credits,
        )
        previous = next(row for row in stored if (row.origin, row.revision) == entry.key)
        if previous.planning_relevant != planning_relevant:
            raise ValueError("Conflicting replay of execution planning relevance.")
        previous_settlements = tuple(
            settlement
            for row, settlement in zip(recorded_settlements, prior_settlements, strict=True)
            if row.execution_id == previous.id
        )
        if settlements is not None and (
            len(previous_settlements) != len(settlements)
            or set(previous_settlements) != set(settlements)
        ):
            raise ValueError("Conflicting replay of execution debt settlements.")
        return previous.id

    settlements = _execution_settlements(
        modules, earlier, debts, revisions, prior_settlements, entry, settlements
    )
    if any(settlement.execution_key != entry.key for settlement in settlements):
        raise ValueError("New debt settlements must belong to this execution event.")
    balances_after = _validate_debt_state(
        modules, updated, debts, revisions, (*prior_settlements, *settlements)
    )
    await _release_excess_reservations(
        db,
        organization_id,
        school_year_id,
        assignment_id,
        active_version_id,
        {balance.claim_id: balance.open_minutes for balance in balances_after},
    )
    reservations = await _active_reservations(
        db, organization_id, school_year_id, assignment_id, active_version_id
    )
    allocations = tuple(
        RecoveryAllocation(row.version_id, row.lesson_id, row.debt_id, row.minutes)
        for row in reservations
    )
    _validate_debt_state(
        modules,
        updated,
        debts,
        revisions,
        (*prior_settlements, *settlements),
        allocations=allocations,
        active_version_id=active_version_id,
        future_lesson_credits=future_credits,
    )

    reversal_id = next(
        (row.id for row in stored if (row.origin, row.revision) == entry.reversal_of), None
    )
    record = CurricularExecution(
        organization_id=organization_id,
        assignment_id=assignment_id,
        origin=entry.origin,
        revision=entry.revision,
        author_membership_id=entry.author_id,
        reason=entry.reason,
        recorded_at=entry.recorded_at,
        planning_relevant=planning_relevant,
        reversal_of_id=reversal_id,
    )
    db.add(record)
    await db.flush()
    for credit in entry.credits:
        db.add(
            CurricularExecutionCredit(
                organization_id=organization_id,
                execution_id=record.id,
                module_id=credit.module_id,
                offset_minutes=_credit_offset(
                    credit,
                    reversal_id,
                    required_by_module[credit.module_id],
                    stored,
                    credits_by_execution,
                ),
                delta_minutes=credit.minutes,
            )
        )
    for settlement in settlements:
        original_settlement_id = next(
            (
                row.id
                for row, prior in zip(recorded_settlements, prior_settlements, strict=True)
                if prior.claim_id == settlement.claim_id
                and prior.execution_key == settlement.reversal_of
            ),
            None,
        )
        db.add(
            CurricularDebtSettlement(
                organization_id=organization_id,
                debt_id=settlement.claim_id,
                execution_id=record.id,
                minutes=settlement.minutes,
                reversal_of_id=original_settlement_id,
            )
        )
    state.input_revision += 1
    if planning_relevant:
        state.planning_revision += 1
    await db.flush()
    return record.id


async def reverse_outstanding_credits(
    db: AsyncSession,
    organization_id: int,
    school_year_id: int,
    assignment_id: int,
    *,
    membership_id: int,
    reason: str,
    now_utc: datetime,
) -> int:
    """Append one audited reversal per execution with remaining credit.

    The append-only ledger stays intact: every reversal references its source
    execution and opposes only the credit that is still effective, so a replayed
    balance returns to zero. Returns the number of reversal events written.
    """
    stored, credits_by_execution, entries = await _execution_history(
        db, organization_id, assignment_id
    )
    source_id_by_key = {(row.origin, row.revision): row.id for row in stored}
    reversed_by_source: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for row, entry in zip(stored, entries, strict=True):
        if entry.reversal_of is None:
            continue
        source_id = source_id_by_key.get(entry.reversal_of)
        if source_id is None:
            raise ValueError("Execution reversal references an unknown entry.")
        for credit in credits_by_execution.get(row.id, ()):
            reversed_by_source[source_id][credit.module_id] += abs(credit.delta_minutes)

    written = 0
    for row, entry in zip(stored, entries, strict=True):
        if entry.reversal_of is not None:
            continue
        credits = tuple(
            ModuleCredit(
                credit.module_id,
                -(credit.minutes - reversed_by_source[row.id].get(credit.module_id, 0)),
            )
            for credit in entry.credits
            if credit.minutes - reversed_by_source[row.id].get(credit.module_id, 0) > 0
        )
        if not credits:
            continue
        revision = (
            max(
                (candidate.revision for candidate in entries if candidate.origin == entry.origin),
                default=0,
            )
            + 1
        )
        await record_execution(
            db,
            organization_id,
            school_year_id,
            assignment_id,
            ExecutionEntry(
                entry.origin,
                revision,
                membership_id,
                reason,
                credits,
                reversal_of=entry.key,
                recorded_at=now_utc,
            ),
            planning_relevant=True,
            # Settlements stay untouched: the debt they already closed must not
            # reopen for a reset that later settles the remaining open balance.
            settlements=(),
        )
        written += 1
    return written


async def settle_open_debt(
    db: AsyncSession,
    organization_id: int,
    school_year_id: int,
    assignment_id: int,
    *,
    membership_id: int,
    reason: str,
    now_utc: datetime,
) -> int:
    """Close every open claim of one assignment with one audited credit.

    A negative debt revision cannot close a claim whose older settlements were
    reversed, so the open balance is settled with recorded execution credit.
    The caller annuls that credit in the same transaction; the executed balance
    then returns to zero while the debt stays closed. Returns settled minutes.
    """
    open_debt, _ = await load_open_debt(db, organization_id, [assignment_id])
    total = sum(open_debt.values())
    if total == 0:
        return 0
    planning, executed_by_assignment = await load_planning_requirements(
        db, organization_id, [assignment_id]
    )
    executed = executed_by_assignment.get(assignment_id, {})
    credits: list[ModuleCredit] = []
    remaining = total
    for module in planning.get(assignment_id, ()):
        available = module.required_minutes - int(executed.get(module.module_id, 0))
        if available <= 0:
            continue
        taken = min(remaining, available)
        credits.append(ModuleCredit(module.module_id, taken))
        remaining -= taken
        if remaining == 0:
            break
    if remaining > 0:
        raise ValueError("Open debt exceeds the remaining curricular demand.")
    await record_execution(
        db,
        organization_id,
        school_year_id,
        assignment_id,
        ExecutionEntry(
            f"school-year-reset-settlement:{school_year_id}:{uuid4().hex}",
            1,
            membership_id,
            reason,
            tuple(credits),
            recorded_at=now_utc,
        ),
        planning_relevant=True,
    )
    return total


async def configure_school_year(
    db: AsyncSession,
    organization_id: int,
    school_year_id: int,
    *,
    preferred_end_date: date,
) -> bool:
    """Set the annual preferred end date under the state lock.

    Returns ``True`` only when the value changed; a no-op does not consume a
    revision. The caller owns the transaction, so a rollback preserves the
    previous configuration.
    """
    if type(preferred_end_date) is not date:
        raise ValueError("Preferred end date must be a date.")
    state = await db.scalar(
        select(models.SchedulerSchoolYearState)
        .where(
            models.SchedulerSchoolYearState.organization_id == organization_id,
            models.SchedulerSchoolYearState.school_year_id == school_year_id,
        )
        .with_for_update()
    )
    if state is None:
        raise ValueError(ERR_MISSING_STATE)
    year = await db.scalar(
        select(models.SchedulerSchoolYear).where(
            models.SchedulerSchoolYear.id == school_year_id,
            models.SchedulerSchoolYear.organization_id == organization_id,
        )
    )
    if year is None:
        raise ValueError("The school year does not belong to this organization.")
    if not year.start_date <= preferred_end_date <= year.hard_end_date:
        raise ValueError("Dates must satisfy start <= preferred <= hard end.")
    if year.preferred_end_date == preferred_end_date:
        return False
    year.preferred_end_date = preferred_end_date
    state.input_revision += 1
    state.planning_revision += 1
    await db.flush()
    return True


async def record_debt(
    db: AsyncSession,
    organization_id: int,
    school_year_id: int,
    assignment_id: int,
    origin: DebtOrigin,
) -> int:
    """Create one audited debt origin under the school-year state lock."""
    state, assignment = await _locked_assignment(db, organization_id, school_year_id, assignment_id)

    await reconcile_assignment_requirements(db, organization_id, assignment.id)
    modules = await _requirements(db, organization_id, assignment)
    stored, _, entries = await _execution_history(db, organization_id, assignment_id)
    debts, revisions, _, settlements = await _debt_history(
        db, organization_id, assignment_id, stored
    )
    balances = _validate_debt_state(modules, entries, debts, revisions, settlements)
    previous = next(
        (
            debt
            for debt in debts
            if (debt.origin, debt.origin_revision) == (origin.origin, origin.revision)
        ),
        None,
    )
    if previous is not None:
        if (
            previous.origin_date != origin.origin_date
            or previous.created_minutes != origin.minutes
            or previous.author_membership_id != origin.author_id
            or previous.reason != origin.reason
            or previous.recorded_at != origin.recorded_at
        ):
            raise ValueError("Conflicting replay of a debt origin and revision.")
        return previous.id

    if sum(balance.open_minutes for balance in balances) + origin.minutes > remaining_minutes(
        modules, entries
    ):
        raise ValueError("Open debt exceeds residual curricular demand.")
    debt = CurricularDebt(
        organization_id=organization_id,
        assignment_id=assignment_id,
        origin=origin.origin,
        origin_revision=origin.revision,
        origin_date=origin.origin_date,
        created_minutes=origin.minutes,
        author_membership_id=origin.author_id,
        reason=origin.reason,
        recorded_at=origin.recorded_at,
    )
    db.add(debt)
    state.input_revision += 1
    state.planning_revision += 1
    await db.flush()
    return debt.id


async def revise_debt(
    db: AsyncSession,
    organization_id: int,
    school_year_id: int,
    debt_id: int,
    *,
    origin: str,
    revision: int,
    delta_minutes: int,
    author_id: int,
    reason: str,
    recorded_at,
) -> int:
    """Append one audited debt revision under the school-year state lock."""
    state = await db.scalar(
        select(models.SchedulerSchoolYearState)
        .where(
            models.SchedulerSchoolYearState.organization_id == organization_id,
            models.SchedulerSchoolYearState.school_year_id == school_year_id,
        )
        .with_for_update()
    )
    if state is None:
        raise ValueError(ERR_MISSING_STATE)
    debt = await db.scalar(
        select(CurricularDebt).where(
            CurricularDebt.id == debt_id,
            CurricularDebt.organization_id == organization_id,
        )
    )
    if debt is None:
        raise ValueError("Debt does not belong to this school year.")
    if (
        not origin
        or type(revision) is not int
        or revision <= 0
        or type(delta_minutes) is not int
        or delta_minutes == 0
        or not reason
        or type(author_id) is not int
        or author_id <= 0
    ):
        raise ValueError("A debt revision needs an origin, revision, delta, author and reason.")
    existing = await db.scalar(
        select(CurricularDebtRevision).where(
            CurricularDebtRevision.debt_id == debt_id,
            CurricularDebtRevision.origin == origin,
            CurricularDebtRevision.revision == revision,
        )
    )
    if existing is not None:
        if (
            existing.delta_minutes != delta_minutes
            or existing.author_membership_id != author_id
            or existing.reason != reason
            or existing.recorded_at != recorded_at
        ):
            raise ValueError("Conflicting replay of a debt revision.")
        return existing.id
    row = CurricularDebtRevision(
        organization_id=organization_id,
        debt_id=debt_id,
        origin=origin,
        revision=revision,
        delta_minutes=delta_minutes,
        author_membership_id=author_id,
        reason=reason,
        recorded_at=recorded_at,
    )
    db.add(row)
    await db.flush()
    assignment = await db.scalar(
        select(CurricularAssignment).where(
            CurricularAssignment.id == debt.assignment_id,
            CurricularAssignment.organization_id == organization_id,
            CurricularAssignment.school_year_id == school_year_id,
        )
    )
    if assignment is None:
        raise ValueError("Debt does not belong to this school year.")
    await reconcile_assignment_requirements(db, organization_id, assignment.id)
    modules = await _requirements(db, organization_id, assignment)
    stored, _, entries = await _execution_history(db, organization_id, assignment.id)
    debts, revisions, _, settlements = await _debt_history(
        db, organization_id, assignment.id, stored
    )
    _validate_debt_state(modules, entries, debts, revisions, settlements)
    state.input_revision += 1
    state.planning_revision += 1
    await db.flush()
    return row.id


async def load_execution_entries(
    db: AsyncSession, organization_id: int, assignment_id: int
) -> tuple[ExecutionEntry, ...]:
    """Full append-only history of one assignment, oldest first."""
    _, _, entries = await _execution_history(db, organization_id, assignment_id)
    return entries


async def _load_assignment_requirements(db, organization_id, identifiers):
    requirements: dict[int, list[ModuleRequirement]] = defaultdict(list)
    requirement_rows = (
        await db.execute(
            select(
                CurricularRequirement.assignment_id,
                CurricularRequirement.module_id,
                CurricularRequirement.sequence,
                CurricularRequirement.required_minutes,
            )
            .where(
                CurricularRequirement.organization_id == organization_id,
                CurricularRequirement.assignment_id.in_(identifiers),
            )
            .order_by(CurricularRequirement.assignment_id, CurricularRequirement.sequence)
        )
    ).all()
    for assignment_id, module_id, sequence, required_minutes in requirement_rows:
        requirements[assignment_id].append(ModuleRequirement(module_id, sequence, required_minutes))
    return requirements


async def load_executed_minutes(
    db: AsyncSession,
    organization_id: int,
    assignment_ids: Sequence[int],
    *,
    requirements: Mapping[int, Sequence[ModuleRequirement]] | None = None,
) -> dict[int, dict[int, int]]:
    """Executed minutes per assignment and module, batched for reading snapshots.

    The append-only ledger is replayed exactly like the write path: reversals
    subtract credit, so a correction never counts the same minute twice. Callers
    that already loaded the requirement rows pass them to avoid a second query.
    """
    identifiers = sorted(set(assignment_ids))
    if not identifiers:
        return {}
    if requirements is None:
        requirements = await _load_assignment_requirements(db, organization_id, identifiers)
    stored = (
        await db.scalars(
            select(CurricularExecution)
            .where(
                CurricularExecution.organization_id == organization_id,
                CurricularExecution.assignment_id.in_(identifiers),
            )
            .order_by(CurricularExecution.id)
        )
    ).all()
    credits_by_execution: dict[int, list[CurricularExecutionCredit]] = defaultdict(list)
    if stored:
        credits = (
            await db.scalars(
                select(CurricularExecutionCredit)
                .where(
                    CurricularExecutionCredit.organization_id == organization_id,
                    CurricularExecutionCredit.execution_id.in_([row.id for row in stored]),
                )
                .order_by(CurricularExecutionCredit.id)
            )
        ).all()
        for credit in credits:
            credits_by_execution[credit.execution_id].append(credit)
    by_assignment: dict[int, list[CurricularExecution]] = defaultdict(list)
    for row in stored:
        by_assignment[row.assignment_id].append(row)
    executed: dict[int, dict[int, int]] = {}
    for assignment_id in identifiers:
        modules = requirements.get(assignment_id, [])
        if not modules and not by_assignment.get(assignment_id):
            executed[assignment_id] = {}
            continue
        entries = _entries_from_rows(by_assignment.get(assignment_id, []), credits_by_execution)
        executed[assignment_id] = completed_by_module(modules, entries)
    return executed


async def _load_retired_modules(
    db: AsyncSession, organization_id: int, identifiers: Sequence[int]
) -> dict[int, frozenset[int]]:
    rows = (
        await db.execute(
            select(CurricularRequirement.assignment_id, CurricularRequirement.module_id).where(
                CurricularRequirement.organization_id == organization_id,
                CurricularRequirement.assignment_id.in_(identifiers),
                CurricularRequirement.planned.is_(False),
            )
        )
    ).all()
    retired: dict[int, set[int]] = defaultdict(set)
    for assignment_id, module_id in rows:
        retired[assignment_id].add(module_id)
    return {key: frozenset(value) for key, value in retired.items()}


async def _planning_targets(
    db: AsyncSession, organization_id: int, identifiers: Sequence[int]
) -> dict[int, tuple[int, int]]:
    """Class and subject of each assignment, tenant scoped."""
    rows = (
        await db.execute(
            select(
                CurricularAssignment.id,
                CurricularAssignment.class_id,
                CurricularAssignment.subject_id,
            ).where(
                CurricularAssignment.organization_id == organization_id,
                CurricularAssignment.id.in_(identifiers),
            )
        )
    ).all()
    return {assignment_id: (class_id, subject_id) for assignment_id, class_id, subject_id in rows}


async def _live_module_selection(
    db: AsyncSession,
    organization_id: int,
    targets: Mapping[int, tuple[int, int]],
) -> dict[tuple[int, int], frozenset[int]]:
    """Selected module ids per live class/subject link at the current grade.

    A key is present exactly when a live link exists, so an empty selection is
    distinct from an absent link. The selection is authoritative between
    generations: the projection flag is stale until the next sync.
    """
    class_ids = {class_id for class_id, _ in targets.values()}
    subject_ids = {subject_id for _, subject_id in targets.values()}
    if not class_ids or not subject_ids:
        return {}
    rows = (
        await db.execute(
            select(
                models.ClassSubjectLink.class_id,
                models.ClassSubjectLink.subject_id,
                models.class_subject_module.c.module_id,
            )
            .join(
                models.Class,
                (models.Class.organization_id == models.ClassSubjectLink.organization_id)
                & (models.Class.id == models.ClassSubjectLink.class_id),
            )
            .outerjoin(
                models.class_subject_module,
                (models.class_subject_module.c.organization_id == organization_id)
                & (
                    models.class_subject_module.c.class_subject_link_id
                    == models.ClassSubjectLink.id
                ),
            )
            .where(
                models.ClassSubjectLink.organization_id == organization_id,
                models.ClassSubjectLink.class_id.in_(class_ids),
                models.ClassSubjectLink.subject_id.in_(subject_ids),
                models.ClassSubjectLink.grade_level == models.Class.grade_level,
                models.Class.is_archived.is_(False),
            )
        )
    ).all()
    selection: dict[tuple[int, int], set[int]] = {}
    for class_id, subject_id, module_id in rows:
        selected = selection.setdefault((class_id, subject_id), set())
        if module_id is not None:
            selected.add(module_id)
    return {key: frozenset(value) for key, value in selection.items()}


async def _catalogue_modules(
    db: AsyncSession, organization_id: int, subject_ids: Sequence[int]
) -> dict[int, tuple[models.Module, ...]]:
    if not subject_ids:
        return {}
    modules = (
        await db.scalars(
            select(models.Module)
            .where(
                models.Module.organization_id == organization_id,
                models.Module.subject_id.in_(subject_ids),
            )
            .order_by(models.Module.subject_id, models.Module.order, models.Module.id)
        )
    ).all()
    catalogue: dict[int, list[models.Module]] = defaultdict(list)
    for module in modules:
        catalogue[module.subject_id].append(module)
    return {key: tuple(value) for key, value in catalogue.items()}


def _catalogue_requirements(
    catalogue: Mapping[int, Sequence[models.Module]], subject_id: int
) -> tuple[ModuleRequirement, ...]:
    return tuple(
        ModuleRequirement(module.id, module.order + 1, module.required_minutes)
        for module in catalogue.get(subject_id, ())
    )


async def load_planning_requirements(
    db: AsyncSession, organization_id: int, assignment_ids: Sequence[int]
) -> tuple[dict[int, tuple[ModuleRequirement, ...]], dict[int, dict[int, int]]]:
    """Planning view of the requirements plus the executed minutes.

    For a live class/subject link the current selection is authoritative: a
    catalogue module that is not selected is retired and a reselected module
    overrides a stale projection flag. An assignment without a live link keeps
    the projection flag, so removed-assignment and year-reset semantics stay.
    Every row is replayed with the catalogue minutes, then each retired module
    is closed at its executed minutes. A retired module without execution leaves
    the planning view; its history stays in the ledger for the callers that
    reproduce it.
    """
    identifiers = sorted(set(assignment_ids))
    if not identifiers:
        return {}, {}
    requirements = await _load_assignment_requirements(db, organization_id, identifiers)
    executed = await load_executed_minutes(
        db, organization_id, identifiers, requirements=requirements
    )
    targets = await _planning_targets(db, organization_id, identifiers)
    selection = await _live_module_selection(db, organization_id, targets)
    catalogue = await _catalogue_modules(
        db, organization_id, [subject_id for _, subject_id in targets.values()]
    )
    fallback = [
        assignment_id
        for assignment_id in identifiers
        if targets.get(assignment_id) not in selection
    ]
    retired = await _load_retired_modules(db, organization_id, fallback) if fallback else {}
    planning: dict[int, tuple[ModuleRequirement, ...]] = {}
    for assignment_id in identifiers:
        completed = executed.get(assignment_id, {})
        target = targets.get(assignment_id)
        if target is not None and target in selection:
            modules = _catalogue_requirements(catalogue, target[1])
            selected = selection[target]
            retired_ids = frozenset(
                module.module_id for module in modules if module.module_id not in selected
            )
        else:
            modules = tuple(requirements.get(assignment_id, ()))
            retired_ids = retired.get(assignment_id, frozenset())
        closed, minutes = close_retired_modules(modules, retired_ids, completed)
        planning[assignment_id] = closed
        executed[assignment_id] = minutes
    return planning, executed


async def _credited_module_ids(
    db: AsyncSession, organization_id: int, assignment_id: int
) -> frozenset[int]:
    rows = (
        await db.execute(
            select(CurricularExecutionCredit.module_id)
            .join(
                CurricularExecution,
                CurricularExecutionCredit.execution_id == CurricularExecution.id,
            )
            .where(
                CurricularExecution.organization_id == organization_id,
                CurricularExecution.assignment_id == assignment_id,
                CurricularExecutionCredit.organization_id == organization_id,
            )
            .distinct()
        )
    ).all()
    return frozenset(module_id for (module_id,) in rows)


async def _requirement_rows_by_module(
    db: AsyncSession, organization_id: int, assignment_id: int
) -> dict[int, CurricularRequirement]:
    rows = (
        await db.scalars(
            select(CurricularRequirement).where(
                CurricularRequirement.organization_id == organization_id,
                CurricularRequirement.assignment_id == assignment_id,
            )
        )
    ).all()
    return {row.module_id: row for row in rows}


async def reconcile_assignment_requirements(
    db: AsyncSession, organization_id: int, assignment_id: int
) -> None:
    """Persist the current selection as canonical requirement rows for one assignment.

    The write path validates credits against persisted rows, but the live
    selection can be newer than the last projection: a newly selected catalogue
    module or a reselected module whose uncredited row a prior sync deleted. This
    applies the projection rules to that one assignment (selected modules become
    planned catalogue requirements; unselected modules keep execution credit and
    are dropped otherwise) without a whole-school sync, so an empty link
    elsewhere never blocks a summary. Assignments without a live link keep their
    persisted rows untouched.
    """
    # Sessions run with autoflush off, so pending rows must reach the database
    # before the reads below or they are invisible and inserted twice.
    await db.flush()
    targets = await _planning_targets(db, organization_id, [assignment_id])
    target = targets.get(assignment_id)
    if target is None:
        return
    selection = await _live_module_selection(db, organization_id, {assignment_id: target})
    if target not in selection:
        return
    modules = _catalogue_requirements(
        await _catalogue_modules(db, organization_id, [target[1]]), target[1]
    )
    selected = selection[target]
    credited = await _credited_module_ids(db, organization_id, assignment_id)
    rows = await _requirement_rows_by_module(db, organization_id, assignment_id)
    changed = False
    for module in modules:
        row = rows.pop(module.module_id, None)
        if module.module_id in selected:
            if row is None:
                db.add(
                    CurricularRequirement(
                        organization_id=organization_id,
                        assignment_id=assignment_id,
                        module_id=module.module_id,
                        sequence=module.sequence,
                        required_minutes=module.required_minutes,
                        planned=True,
                    )
                )
                changed = True
            elif (
                row.sequence != module.sequence
                or row.required_minutes != module.required_minutes
                or not row.planned
            ):
                row.sequence = module.sequence
                row.required_minutes = module.required_minutes
                row.planned = True
                changed = True
        elif row is not None and module.module_id in credited:
            if (
                row.sequence != module.sequence
                or row.required_minutes != module.required_minutes
                or row.planned
            ):
                row.sequence = module.sequence
                row.required_minutes = module.required_minutes
                row.planned = False
                changed = True
        elif row is not None:
            await db.delete(row)
            changed = True
    if changed:
        await db.flush()


async def load_open_debt(
    db: AsyncSession,
    organization_id: int,
    assignment_ids: Sequence[int],
) -> tuple[dict[int, int], dict[int, int]]:
    """Open minutes and assignment per debt claim, without counting reservations."""
    identifiers = sorted(set(assignment_ids))
    if not identifiers:
        return {}, {}
    debts = (
        await db.scalars(
            select(CurricularDebt).where(
                CurricularDebt.organization_id == organization_id,
                CurricularDebt.assignment_id.in_(identifiers),
            )
        )
    ).all()
    if not debts:
        return {}, {}
    debt_ids = [row.id for row in debts]
    revisions = (
        await db.execute(
            select(
                CurricularDebtRevision.debt_id,
                func.coalesce(func.sum(CurricularDebtRevision.delta_minutes), 0),
            )
            .where(CurricularDebtRevision.debt_id.in_(debt_ids))
            .group_by(CurricularDebtRevision.debt_id)
        )
    ).all()
    settlements = (
        await db.execute(
            select(
                CurricularDebtSettlement.debt_id,
                func.coalesce(func.sum(CurricularDebtSettlement.minutes), 0),
            )
            .where(CurricularDebtSettlement.debt_id.in_(debt_ids))
            .group_by(CurricularDebtSettlement.debt_id)
        )
    ).all()
    revision_by_claim = {debt_id: int(minutes) for debt_id, minutes in revisions}
    settlement_by_claim = {debt_id: int(minutes) for debt_id, minutes in settlements}
    open_by_claim: dict[int, int] = {}
    claim_assignments: dict[int, int] = {}
    for debt in debts:
        opened = (
            debt.created_minutes
            + revision_by_claim.get(debt.id, 0)
            - settlement_by_claim.get(debt.id, 0)
        )
        if opened < 0:
            raise ValueError("Open debt is negative for a debt claim.")
        if opened:
            open_by_claim[debt.id] = opened
            claim_assignments[debt.id] = debt.assignment_id
    return open_by_claim, claim_assignments
