from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.services.scheduler_state_service import SchedulerStateService


class SchedulerDraftError(RuntimeError):
    pass


class SchedulerDraftNotFoundError(SchedulerDraftError):
    pass


@dataclass(frozen=True)
class DraftSummary:
    draft_id: int
    strategy: str
    draft_state: str
    result_category: str
    trigger_type: str
    recovery_escalation_level: str | None
    adaptation_level: str | None
    projected_completion_date: date
    hard_end_date: date
    debt_hours_before: float
    debt_hours_recovered: float
    debt_hours_remaining: float
    partial_recovery_blocker_type: str | None
    main_blocker_message: str | None
    recommended_actions: tuple[str, ...]
    changed_blocks: int
    affected_classes: int
    affected_teachers: int
    affected_days: int
    disruption_score: float
    warnings: tuple[str, ...]
    can_approve: bool


class SchedulerDraftService:
    def __init__(self, db: AsyncSession):
        self._db = db
        self._state = SchedulerStateService(db)

    async def current_summary(self, organization_id: int) -> DraftSummary:
        school_year = await self._state.get_active_school_year(organization_id)
        if school_year is None:
            raise SchedulerDraftNotFoundError("No active scheduler school year exists.")
        draft = await self._state.get_pending_draft(
            organization_id,
            school_year.id,
        )
        if draft is None:
            raise SchedulerDraftNotFoundError("No pending schedule draft exists.")
        return await self.summary(organization_id, draft.id)

    async def summary(self, organization_id: int, draft_id: int) -> DraftSummary:
        draft = await self._db.scalar(
            select(models.ScheduleDraft).where(
                models.ScheduleDraft.id == draft_id,
                models.ScheduleDraft.organization_id == organization_id,
            )
        )
        if draft is None:
            raise SchedulerDraftNotFoundError("Schedule draft was not found.")
        blocks = (
            await self._db.scalars(
                select(models.ScheduleDraftBlock).where(
                    models.ScheduleDraftBlock.organization_id == organization_id,
                    models.ScheduleDraftBlock.school_year_id == draft.school_year_id,
                    models.ScheduleDraftBlock.draft_id == draft.id,
                )
            )
        ).all()
        changed = [
            row
            for row in blocks
            if row.change_type != models.ScheduleDraftBlockChangeType.UNCHANGED
        ]
        summary = draft.summary_json or {}
        recovered = int(summary.get("recovered_minutes", 0))
        remaining = int(summary.get("remaining_unscheduled_minutes", 0))
        state = await self._state.get_state(
            organization_id,
            draft.school_year_id,
        )
        can_approve = bool(
            draft.draft_state == models.ScheduleDraftState.PENDING
            and state is not None
            and state.pending_draft_id == draft.id
        )
        return DraftSummary(
            draft_id=draft.id,
            strategy=draft.strategy.value,
            draft_state=draft.draft_state.value,
            result_category=draft.result_category.value,
            trigger_type=draft.trigger_type.value,
            recovery_escalation_level=draft.recovery_escalation_level,
            adaptation_level=draft.adaptation_level,
            projected_completion_date=draft.projected_completion_date,
            hard_end_date=draft.hard_end_date,
            debt_hours_before=(recovered + remaining) / 60,
            debt_hours_recovered=recovered / 60,
            debt_hours_remaining=remaining / 60,
            partial_recovery_blocker_type=draft.partial_recovery_blocker_type,
            main_blocker_message=draft.main_blocker_message,
            recommended_actions=tuple(draft.recommended_actions_json or ()),
            changed_blocks=len(changed),
            affected_classes=len({row.class_id for row in changed}),
            affected_teachers=len({row.teacher_id for row in changed}),
            affected_days=len({row.date for row in changed}),
            disruption_score=float(summary.get("disruption_score", 0)),
            warnings=tuple(draft.warnings_json or ()),
            can_approve=can_approve,
        )
