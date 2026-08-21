"""Availability matrix inspection (pure read-only) and repair (explicit transactional mutation)."""

from __future__ import annotations

from dataclasses import dataclass

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Availability,
    MembershipLifecycleStatus,
    OrganizationMembership,
    PreferenceLevel,
    Teacher,
    Timeslot,
)

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class AvailabilityAnomaly:
    teacher_id: int
    timeslot_id: int


@dataclass(frozen=True)
class AvailabilityMatrixInspection:
    matrix: dict[tuple[int, int], int]  # (teacher_id, timeslot_id) -> score
    anomalies: list[AvailabilityAnomaly]

    def get_score(self, teacher_id: int, timeslot_id: int) -> int:
        return self.matrix.get((teacher_id, timeslot_id), PreferenceLevel.NEUTRAL.value)

    def is_impossible(self, teacher_id: int, timeslot_id: int) -> bool:
        return self.get_score(teacher_id, timeslot_id) == PreferenceLevel.IMPOSSIBLE.value


class AvailabilityMatrixInspector:
    """
    Pure read-only inspector for teacher-timeslot availability.
    Missing database rows are synthesized in-memory as PreferenceLevel.NEUTRAL (1).
    ZERO database writes, flushes, or commits.
    """

    @classmethod
    async def inspect(
        cls,
        db: AsyncSession,
        *,
        organization_id: int,
        teacher_ids: list[int] | set[int] | None = None,
        timeslot_ids: list[int] | set[int] | None = None,
    ) -> AvailabilityMatrixInspection:
        # 1. Fetch active teachers of the org
        t_stmt = (
            select(Teacher.id)
            .join(
                OrganizationMembership,
                OrganizationMembership.id == Teacher.organization_membership_id,
            )
            .where(
                Teacher.organization_id == organization_id,
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.lifecycle_status == MembershipLifecycleStatus.active,
                OrganizationMembership.can_teach.is_(True),
            )
        )
        if teacher_ids is not None:
            t_stmt = t_stmt.where(Teacher.id.in_(teacher_ids))
        t_result = await db.execute(t_stmt)
        valid_teacher_ids = set(t_result.scalars().all())

        # 2. Fetch active timeslots of the org
        ts_stmt = select(Timeslot.id).where(Timeslot.organization_id == organization_id)
        if timeslot_ids is not None:
            ts_stmt = ts_stmt.where(Timeslot.id.in_(timeslot_ids))
        ts_result = await db.execute(ts_stmt)
        valid_timeslot_ids = set(ts_result.scalars().all())

        if not valid_teacher_ids or not valid_timeslot_ids:
            return AvailabilityMatrixInspection(matrix={}, anomalies=[])

        # 3. Fetch persisted availability rows
        av_stmt = select(
            Availability.teacher_id, Availability.timeslot_id, Availability.score
        ).where(
            Availability.organization_id == organization_id,
            Availability.teacher_id.in_(valid_teacher_ids),
            Availability.timeslot_id.in_(valid_timeslot_ids),
        )
        av_result = await db.execute(av_stmt)
        persisted = {(r.teacher_id, r.timeslot_id): r.score for r in av_result.all()}

        # 4. Build full matrix and track missing cells as anomalies
        matrix: dict[tuple[int, int], int] = {}
        anomalies: list[AvailabilityAnomaly] = []

        for tid in valid_teacher_ids:
            for tsid in valid_timeslot_ids:
                if (tid, tsid) in persisted:
                    matrix[(tid, tsid)] = persisted[(tid, tsid)]
                else:
                    matrix[(tid, tsid)] = PreferenceLevel.NEUTRAL.value
                    anomalies.append(AvailabilityAnomaly(teacher_id=tid, timeslot_id=tsid))

        if anomalies:
            logger.info(
                "availability_matrix_missing_cells_synthesized",
                organization_id=organization_id,
                anomalies_count=len(anomalies),
            )

        return AvailabilityMatrixInspection(matrix=matrix, anomalies=anomalies)


class AvailabilityMatrixRepairService:
    """
    Explicit transactional repair for missing availability rows.
    Inserts missing (teacher, timeslot) cells as NEUTRAL with ON CONFLICT DO NOTHING.
    Never commits; only flushes.
    """

    @classmethod
    async def repair(
        cls,
        db: AsyncSession,
        *,
        organization_id: int,
        teacher_ids: list[int] | set[int] | None = None,
        timeslot_ids: list[int] | set[int] | None = None,
    ) -> int:
        inspection = await AvailabilityMatrixInspector.inspect(
            db,
            organization_id=organization_id,
            teacher_ids=teacher_ids,
            timeslot_ids=timeslot_ids,
        )
        if not inspection.anomalies:
            return 0

        values = [
            {
                "organization_id": organization_id,
                "teacher_id": a.teacher_id,
                "timeslot_id": a.timeslot_id,
                "score": PreferenceLevel.NEUTRAL.value,
            }
            for a in inspection.anomalies
        ]

        stmt = (
            pg_insert(Availability)
            .values(values)
            .on_conflict_do_nothing(index_elements=["organization_id", "teacher_id", "timeslot_id"])
        )
        result = await db.execute(stmt)
        await db.flush()
        inserted_count = (
            result.rowcount if result.rowcount is not None and result.rowcount >= 0 else len(values)
        )

        logger.error(
            "availability_matrix_integrity_repaired",
            organization_id=organization_id,
            repaired_count=inserted_count,
            anomalies_count=len(inspection.anomalies),
        )
        return inserted_count
