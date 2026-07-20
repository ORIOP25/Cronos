from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.scheduler_fingerprint_service import SchedulerFingerprintService


@dataclass(frozen=True)
class ActiveDebtEntry:
    occurrence_id: int
    occurrence_revision: int
    source_planned_block_id: int | None
    class_id: int | None
    subject_id: int | None
    teacher_id: int | None
    original_planned_date: date
    original_timeslot_id: int | None
    declared_minutes: int
    delivered_recovery_minutes: int
    active_planned_recovery_minutes: int
    remaining_minutes: int


@dataclass(frozen=True)
class ActiveDebtLedger:
    organization_id: int
    school_year_id: int
    entries: tuple[ActiveDebtEntry, ...]
    total_remaining_minutes: int
    remaining_minutes_by_class_subject: dict[tuple[int | None, int | None], int]

    @property
    def is_empty(self) -> bool:
        return not self.entries


class SchedulerDebtService:
    def __init__(self, db: AsyncSession):
        self._fingerprints = SchedulerFingerprintService(db)

    async def active_debt_ledger(
        self,
        organization_id: int,
        school_year_id: int,
    ) -> ActiveDebtLedger:
        snapshot = await self._fingerprints.debt_basis_snapshot(
            organization_id,
            school_year_id,
        )
        entries = tuple(
            ActiveDebtEntry(
                occurrence_id=item["occurrence_id"],
                occurrence_revision=item["occurrence_revision"],
                source_planned_block_id=item["source_planned_block_id"],
                class_id=item["class_id"],
                subject_id=item["subject_id"],
                teacher_id=item["teacher_id"],
                original_planned_date=date.fromisoformat(item["original_planned_date"]),
                original_timeslot_id=item["original_timeslot_id"],
                declared_minutes=item["declared_debt_minutes"],
                delivered_recovery_minutes=item["delivered_recovery_minutes"],
                active_planned_recovery_minutes=item["active_planned_recovery_minutes"],
                remaining_minutes=item["unresolved_debt_minutes"],
            )
            for item in snapshot["items"]
            if item["unresolved_debt_minutes"] > 0
        )
        grouped: dict[tuple[int | None, int | None], int] = {}
        for entry in entries:
            key = (entry.class_id, entry.subject_id)
            grouped[key] = grouped.get(key, 0) + entry.remaining_minutes

        return ActiveDebtLedger(
            organization_id=organization_id,
            school_year_id=school_year_id,
            entries=entries,
            total_remaining_minutes=sum(entry.remaining_minutes for entry in entries),
            remaining_minutes_by_class_subject=grouped,
        )
