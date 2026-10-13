from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.scheduler.domain.serialization import (
    SchedulerSerializationError,
    canonical_json_value,
)


class SchedulerStateError(RuntimeError):
    """Base error for scheduler lifecycle state operations."""


class SchedulerStateNotFoundError(SchedulerStateError):
    pass


class SchedulerStateIntegrityError(SchedulerStateError):
    pass


class SchedulerStateService:
    """Owns tenant/year scheduler lifecycle reads and transitions."""

    def __init__(self, db: AsyncSession):
        self._db = db

    async def get_active_school_year(
        self,
        organization_id: int,
        *,
        for_update: bool = False,
    ) -> models.SchedulerSchoolYear | None:
        query = select(models.SchedulerSchoolYear).where(
            models.SchedulerSchoolYear.organization_id == organization_id,
            models.SchedulerSchoolYear.is_active.is_(True),
        )
        if for_update:
            query = query.with_for_update()
        result = await self._db.execute(query)
        return result.scalar_one_or_none()

    async def get_or_create_active_school_year(
        self,
        organization_id: int,
        *,
        start_date: date,
        hard_end_date: date,
        timezone_name: str = "Europe/Lisbon",
    ) -> models.SchedulerSchoolYear:
        if hard_end_date < start_date:
            raise SchedulerStateIntegrityError("Hard end date cannot precede start date.")
        try:
            ZoneInfo(timezone_name)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise SchedulerStateIntegrityError(
                "Scheduler school year requires a valid IANA timezone."
            ) from exc

        existing = await self.get_active_school_year(organization_id)
        if existing is not None:
            return existing

        label = f"{start_date.year}/{hard_end_date.year}"
        statement = (
            pg_insert(models.SchedulerSchoolYear)
            .values(
                organization_id=organization_id,
                label=label,
                start_date=start_date,
                hard_end_date=hard_end_date,
                timezone=timezone_name,
                is_active=True,
            )
            .on_conflict_do_nothing(
                index_elements=["organization_id", "label"],
            )
        )
        await self._db.execute(statement)
        await self._db.flush()

        school_year = await self.get_active_school_year(organization_id, for_update=True)
        if school_year is None:
            raise SchedulerStateIntegrityError(
                "Could not create or load the active scheduler school year."
            )
        return school_year

    async def get_state(
        self,
        organization_id: int,
        school_year_id: int,
        *,
        for_update: bool = False,
    ) -> models.SchedulerSchoolYearState | None:
        query = select(models.SchedulerSchoolYearState).where(
            models.SchedulerSchoolYearState.organization_id == organization_id,
            models.SchedulerSchoolYearState.school_year_id == school_year_id,
        )
        if for_update:
            query = query.with_for_update()
        result = await self._db.execute(query)
        return result.scalar_one_or_none()

    async def get_or_create_state(
        self,
        organization_id: int,
        school_year_id: int,
    ) -> models.SchedulerSchoolYearState:
        existing = await self.get_state(organization_id, school_year_id)
        if existing is not None:
            return existing

        statement = (
            pg_insert(models.SchedulerSchoolYearState)
            .values(
                organization_id=organization_id,
                school_year_id=school_year_id,
                school_year_publication_state=(models.SchoolYearPublicationState.UNPUBLISHED),
                scheduler_state_version=0,
                lock_version=0,
            )
            .on_conflict_do_nothing(
                index_elements=["organization_id", "school_year_id"],
            )
        )
        await self._db.execute(statement)
        await self._db.flush()

        state = await self.get_state(organization_id, school_year_id, for_update=True)
        if state is None:
            raise SchedulerStateIntegrityError(
                "Could not create or load scheduler school-year state."
            )
        return state

    async def get_or_create_active_state(
        self,
        organization_id: int,
        *,
        start_date: date,
        hard_end_date: date,
        timezone_name: str = "Europe/Lisbon",
    ) -> tuple[models.SchedulerSchoolYear, models.SchedulerSchoolYearState]:
        school_year = await self.get_or_create_active_school_year(
            organization_id,
            start_date=start_date,
            hard_end_date=hard_end_date,
            timezone_name=timezone_name,
        )
        state = await self.get_or_create_state(organization_id, school_year.id)
        return school_year, state

    async def reset_year(
        self,
        organization_id: int,
        school_year_id: int,
        *,
        reset_by_membership_id: int,
        reset_at: datetime | None = None,
    ) -> models.SchedulerSchoolYearState:
        state = await self._require_locked_state(organization_id, school_year_id)
        state.school_year_publication_state = models.SchoolYearPublicationState.UNPUBLISHED
        state.active_schedule_version_id = None
        state.approved_scheduler_state_version = None
        state.reset_by_membership_id = reset_by_membership_id
        state.reset_at = reset_at or datetime.now(UTC)
        state.lock_version += 1
        await self._db.flush()
        return state

    async def record_change(
        self,
        organization_id: int,
        *,
        entity_type: str,
        entity_id: str | int | None,
        operation: models.SchedulerStateChangeOperation,
        before: Any,
        after: Any,
        changed_by_membership_id: int | None = None,
        future_impacting: bool = True,
        active_resource: bool = True,
        repair_policy_change: bool = False,
        metadata: Mapping[str, Any] | None = None,
    ) -> models.SchedulerStateVersionEvent | None:
        """Record one committed mutation decision and increment only when required."""
        if not entity_type.strip():
            raise SchedulerStateIntegrityError("Scheduler change entity type is required.")

        school_year = await self.get_active_school_year(
            organization_id,
            for_update=True,
        )
        if school_year is None:
            return None
        state = await self.get_or_create_state(organization_id, school_year.id)
        state = await self._require_locked_state(organization_id, school_year.id)

        try:
            canonical_before = canonical_json_value(before)
            canonical_after = canonical_json_value(after)
            canonical_metadata = canonical_json_value(metadata)
        except SchedulerSerializationError as exc:
            raise SchedulerStateIntegrityError(str(exc)) from exc

        if canonical_before == canonical_after:
            change_scope = models.SchedulerStateChangeScope.NO_OP
        elif repair_policy_change:
            change_scope = models.SchedulerStateChangeScope.NO_OP
            canonical_metadata = {
                **(canonical_metadata or {}),
                "repair_policy_change": True,
            }
        elif not active_resource:
            change_scope = models.SchedulerStateChangeScope.INACTIVE_RESOURCE
        elif not future_impacting:
            change_scope = models.SchedulerStateChangeScope.PAST_ONLY
        else:
            change_scope = models.SchedulerStateChangeScope.FUTURE_IMPACTING

        version_before = state.scheduler_state_version
        version_after = version_before
        if change_scope == models.SchedulerStateChangeScope.FUTURE_IMPACTING:
            version_after += 1
            state.scheduler_state_version = version_after
            state.lock_version += 1
            state.input_revision += 1
            state.planning_revision += 1
        elif change_scope == models.SchedulerStateChangeScope.PAST_ONLY:
            state.input_revision += 1

        event = models.SchedulerStateVersionEvent(
            organization_id=organization_id,
            school_year_id=school_year.id,
            version_before=version_before,
            version_after=version_after,
            entity_type=entity_type.strip(),
            entity_id=None if entity_id is None else str(entity_id),
            operation=operation,
            change_scope=change_scope,
            changed_by_membership_id=changed_by_membership_id,
            before_metadata_json=canonical_before,
            after_metadata_json=canonical_after,
            metadata_json=canonical_metadata,
        )
        self._db.add(event)
        await self._db.flush()
        return event

    async def _require_locked_state(
        self,
        organization_id: int,
        school_year_id: int,
    ) -> models.SchedulerSchoolYearState:
        state = await self.get_state(
            organization_id,
            school_year_id,
            for_update=True,
        )
        if state is None:
            raise SchedulerStateNotFoundError("Scheduler school-year state does not exist.")
        return state


async def record_scheduler_change(
    db: AsyncSession,
    organization_id: int,
    **change: Any,
) -> models.SchedulerStateVersionEvent | None:
    """Convenience entry point for mutation services."""
    return await SchedulerStateService(db).record_change(organization_id, **change)
