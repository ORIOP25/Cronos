"""Internship flows are calendar events that block only their classes.

A flow change previews the published lessons it would remove. The confirmed
change removes the affected lessons in the same transaction and records the
scheduler state change that makes pending proposals stale.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, aliased

from app import models, schemas
from app.services.scheduler_serialization import sha256_json
from app.services.scheduler_state_service import (
    SchedulerStateService,
    record_scheduler_change,
)

CONFIRMATION_REQUIRED_MESSAGE = (
    "O fluxo de estágio remove aulas do horário. Pré-visualize e confirme a alteração."
)
STALE_MESSAGE = "As aulas afetadas mudaram desde a pré-visualização. Repita a pré-visualização."
BLOCKED_LESSON_MESSAGE = (
    "Este dia de estágio não permite criar aulas para a turma. Ajuste ou remova o fluxo primeiro."
)
MISSING_SCHOOL_YEAR_MESSAGE = "Configure o ano letivo antes de criar fluxos de estágio."


class InternshipFlowError(RuntimeError):
    code = "INTERNSHIP_FLOW_INVALID"


class InternshipFlowConfirmationRequired(InternshipFlowError):
    code = "CALENDAR_EVENT_CONFIRMATION_REQUIRED"


class InternshipFlowStale(InternshipFlowError):
    code = "CALENDAR_EVENT_STALE"


class InternshipFlowBlockedLesson(InternshipFlowError):
    code = "INTERNSHIP_FLOW_BLOCKS_LESSON"


@dataclass(frozen=True)
class AffectedLesson:
    active_schedule_block_id: int
    class_id: int
    class_name: str | None
    subject_id: int
    subject_name: str | None
    date: date
    timeslot_id: int
    duration_minutes: int
    log_id: int | None
    log_status: str | None
    occurrence_id: int | None
    occurrence_status: str | None

    def fingerprint_payload(self) -> dict[str, Any]:
        return {
            "id": self.active_schedule_block_id,
            "date": self.date,
            "class_id": self.class_id,
            "timeslot_id": self.timeslot_id,
            "duration_minutes": self.duration_minutes,
            "log_id": self.log_id,
            "log_status": self.log_status,
            "occurrence_id": self.occurrence_id,
            "occurrence_status": self.occurrence_status,
        }


@dataclass(frozen=True)
class FlowImpact:
    lessons: tuple[AffectedLesson, ...]
    fingerprint: str | None

    @property
    def requires_confirmation(self) -> bool:
        return bool(self.lessons)


def flow_snapshot(event: models.SchoolCalendarEvent, class_ids: list[int]) -> dict[str, Any]:
    return {
        "name": event.name,
        "start_date": event.start_date,
        "end_date": event.end_date,
        "event_type": event.event_type,
        "source": event.source,
        "school_year_start_year": event.school_year_start_year,
        "class_ids": sorted(class_ids),
    }


def flow_blocking_snapshot(
    event: models.SchoolCalendarEvent, class_ids: list[int]
) -> dict[str, Any]:
    """Only the blocking scope decides whether proposals become stale."""
    return {
        "start_date": event.start_date,
        "end_date": event.end_date,
        "school_year_start_year": event.school_year_start_year,
        "class_ids": sorted(class_ids),
    }


async def resolve_school_start_year(
    db: AsyncSession,
    organization_id: int,
) -> int:
    settings = await db.scalar(
        select(models.OrganizationSettings).where(
            models.OrganizationSettings.organization_id == organization_id
        )
    )
    if settings is None or settings.school_start_date is None:
        raise InternshipFlowError(MISSING_SCHOOL_YEAR_MESSAGE)
    return settings.school_start_date.year


def class_blocked_on_sync(
    db: Session,
    organization_id: int,
    class_id: int,
    target_date: date,
) -> bool:
    """Sync guard for operational decisions that would create lessons in a flow."""
    active_start_year = db.scalar(
        select(models.OrganizationSettings.school_start_date).where(
            models.OrganizationSettings.organization_id == organization_id
        )
    )
    active_start_year = None if active_start_year is None else active_start_year.year
    if active_start_year is None:
        return False
    blocked = db.scalar(
        select(models.SchoolCalendarEventClass.id)
        .join(
            models.SchoolCalendarEvent,
            and_(
                models.SchoolCalendarEvent.id == models.SchoolCalendarEventClass.calendar_event_id,
                models.SchoolCalendarEvent.organization_id
                == models.SchoolCalendarEventClass.organization_id,
            ),
        )
        .where(
            models.SchoolCalendarEventClass.organization_id == organization_id,
            models.SchoolCalendarEventClass.class_id == class_id,
            models.SchoolCalendarEvent.event_type == models.CalendarEventType.internship_flow,
            models.SchoolCalendarEvent.school_year_start_year == active_start_year,
            models.SchoolCalendarEvent.start_date <= target_date,
            models.SchoolCalendarEvent.end_date >= target_date,
        )
        .limit(1)
    )
    return blocked is not None


async def validate_flow_input(
    db: AsyncSession,
    organization_id: int,
    start_date: date,
    end_date: date,
    class_ids: list[int],
) -> None:
    settings = await db.scalar(
        select(models.OrganizationSettings).where(
            models.OrganizationSettings.organization_id == organization_id
        )
    )
    if settings is not None:
        min_date = settings.school_start_date
        max_date = settings.school_hard_end_date
        if min_date and (start_date < min_date or end_date < min_date):
            raise InternshipFlowError(
                "Fluxo fora do intervalo permitido. O calendário escolar começa a "
                f"{min_date.isoformat()}."
            )
        if max_date and (start_date > max_date or end_date > max_date):
            raise InternshipFlowError(
                "Fluxo fora do intervalo permitido. O calendário escolar termina a "
                f"{max_date.isoformat()}."
            )
    if not class_ids:
        return
    found = set(
        (
            await db.scalars(
                select(models.Class.id).where(
                    models.Class.organization_id == organization_id,
                    models.Class.id.in_(class_ids),
                    models.Class.is_archived.is_(False),
                )
            )
        ).all()
    )
    missing = sorted(set(class_ids) - found)
    if missing:
        raise InternshipFlowError(
            "Turmas inválidas para esta organização: " + ", ".join(str(item) for item in missing)
        )


async def compute_impact(
    db: AsyncSession,
    organization_id: int,
    class_ids: list[int],
    start_date: date,
    end_date: date,
) -> FlowImpact:
    if not class_ids:
        return FlowImpact(lessons=(), fingerprint=None)
    given_log = (
        select(models.LessonLog.id)
        .where(
            models.LessonLog.organization_id == organization_id,
            models.LessonLog.active_schedule_block_id == models.ActiveScheduleBlock.id,
            models.LessonLog.status == models.LessonLogStatus.COMPLETED,
        )
        .exists()
    )
    given_occurrence = (
        select(models.LessonOccurrence.id)
        .where(
            models.LessonOccurrence.organization_id == organization_id,
            models.LessonOccurrence.active_schedule_block_id == models.ActiveScheduleBlock.id,
            models.LessonOccurrence.is_active.is_(True),
            models.LessonOccurrence.status == models.LessonOccurrenceStatus.GIVEN,
        )
        .exists()
    )
    class_alias = aliased(models.Class)
    subject_alias = aliased(models.Subject)
    block_rows = (
        await db.execute(
            select(
                models.ActiveScheduleBlock,
                class_alias.name,
                subject_alias.name,
            )
            .outerjoin(
                class_alias,
                and_(
                    class_alias.id == models.ActiveScheduleBlock.class_id,
                    class_alias.organization_id == organization_id,
                ),
            )
            .outerjoin(
                subject_alias,
                and_(
                    subject_alias.id == models.ActiveScheduleBlock.subject_id,
                    subject_alias.organization_id == organization_id,
                ),
            )
            .where(
                models.ActiveScheduleBlock.organization_id == organization_id,
                models.ActiveScheduleBlock.status == models.ActiveScheduleBlockStatus.ACTIVE,
                models.ActiveScheduleBlock.class_id.in_(class_ids),
                models.ActiveScheduleBlock.date >= start_date,
                models.ActiveScheduleBlock.date <= end_date,
                ~given_log,
                ~given_occurrence,
            )
            .order_by(
                models.ActiveScheduleBlock.date,
                models.ActiveScheduleBlock.timeslot_id,
                models.ActiveScheduleBlock.id,
            )
        )
    ).all()
    if not block_rows:
        return FlowImpact(lessons=(), fingerprint=None)

    block_ids = [row[0].id for row in block_rows]
    logs = {
        log.active_schedule_block_id: log
        for log in (
            await db.scalars(
                select(models.LessonLog).where(
                    models.LessonLog.organization_id == organization_id,
                    models.LessonLog.active_schedule_block_id.in_(block_ids),
                )
            )
        ).all()
    }
    occurrences = {
        occurrence.active_schedule_block_id: occurrence
        for occurrence in (
            await db.scalars(
                select(models.LessonOccurrence)
                .where(
                    models.LessonOccurrence.organization_id == organization_id,
                    models.LessonOccurrence.active_schedule_block_id.in_(block_ids),
                    models.LessonOccurrence.is_active.is_(True),
                )
                .order_by(models.LessonOccurrence.id)
            )
        ).all()
    }

    lessons = tuple(
        AffectedLesson(
            active_schedule_block_id=block.id,
            class_id=block.class_id,
            class_name=class_name,
            subject_id=block.subject_id,
            subject_name=subject_name,
            date=block.date,
            timeslot_id=block.timeslot_id,
            duration_minutes=block.duration_minutes,
            log_id=logs[block.id].id if block.id in logs else None,
            log_status=_value(logs[block.id].status) if block.id in logs else None,
            occurrence_id=occurrences[block.id].id if block.id in occurrences else None,
            occurrence_status=(
                _value(occurrences[block.id].status) if block.id in occurrences else None
            ),
        )
        for block, class_name, subject_name in block_rows
    )
    fingerprint = sha256_json({"lessons": [lesson.fingerprint_payload() for lesson in lessons]})
    return FlowImpact(lessons=lessons, fingerprint=fingerprint)


def require_confirmation(impact: FlowImpact, fingerprint: str | None) -> None:
    if fingerprint is not None:
        if fingerprint != impact.fingerprint:
            raise InternshipFlowStale(STALE_MESSAGE)
        return
    if impact.requires_confirmation:
        raise InternshipFlowConfirmationRequired(CONFIRMATION_REQUIRED_MESSAGE)


async def remove_affected_blocks(
    db: AsyncSession,
    organization_id: int,
    lessons: tuple[AffectedLesson, ...],
) -> None:
    if not lessons:
        return
    await db.execute(
        update(models.ActiveScheduleBlock)
        .where(
            models.ActiveScheduleBlock.organization_id == organization_id,
            models.ActiveScheduleBlock.status == models.ActiveScheduleBlockStatus.ACTIVE,
            models.ActiveScheduleBlock.id.in_(
                [lesson.active_schedule_block_id for lesson in lessons]
            ),
        )
        .values(status=models.ActiveScheduleBlockStatus.REMOVED)
    )


async def _lock_scheduler_state(db: AsyncSession, organization_id: int) -> None:
    """Serialize confirmed flow changes with schedule approval and publication."""
    state_service = SchedulerStateService(db)
    school_year = await state_service.get_active_school_year(organization_id, for_update=True)
    if school_year is None:
        return
    await state_service.get_or_create_state(organization_id, school_year.id)
    await state_service.get_state(organization_id, school_year.id, for_update=True)


async def _lock_affected_blocks(
    db: AsyncSession,
    organization_id: int,
    block_ids: list[int],
) -> None:
    ids = sorted(set(block_ids))
    if not ids:
        return
    await db.execute(
        select(models.ActiveScheduleBlock.id)
        .where(
            models.ActiveScheduleBlock.organization_id == organization_id,
            models.ActiveScheduleBlock.id.in_(ids),
        )
        .order_by(models.ActiveScheduleBlock.id)
        .with_for_update()
    )


async def _stable_impact(
    db: AsyncSession,
    organization_id: int,
    class_ids: list[int],
    start_date: date,
    end_date: date,
) -> FlowImpact:
    """Recompute the impact while holding the affected rows so confirmation stays exact."""
    impact = await compute_impact(db, organization_id, class_ids, start_date, end_date)
    for _ in range(3):
        ids = [lesson.active_schedule_block_id for lesson in impact.lessons]
        await _lock_affected_blocks(db, organization_id, ids)
        refreshed = await compute_impact(db, organization_id, class_ids, start_date, end_date)
        if [lesson.active_schedule_block_id for lesson in refreshed.lessons] == ids:
            return refreshed
        impact = refreshed
    raise InternshipFlowStale(STALE_MESSAGE)


async def _cancel_pending_operational_blocks(
    db: AsyncSession,
    organization_id: int,
    class_ids: list[int],
    start_date: date,
    end_date: date,
) -> None:
    """Withdraw substitutions that were not taught; taught ones stay visible."""
    if not class_ids:
        return
    taught_log = (
        select(models.LessonLog.id)
        .where(
            models.LessonLog.organization_id == organization_id,
            models.LessonLog.operational_block_id == models.OperationalScheduleBlock.id,
            models.LessonLog.status == models.LessonLogStatus.COMPLETED,
        )
        .exists()
    )
    await db.execute(
        update(models.OperationalScheduleBlock)
        .where(
            models.OperationalScheduleBlock.organization_id == organization_id,
            models.OperationalScheduleBlock.class_id.in_(class_ids),
            models.OperationalScheduleBlock.date >= start_date,
            models.OperationalScheduleBlock.date <= end_date,
            models.OperationalScheduleBlock.status == models.OperationalBlockStatus.ACTIVE,
            models.OperationalScheduleBlock.execution_status
            != models.OperationalBlockExecutionStatus.COMPLETED,
            ~taught_log,
        )
        .values(
            status=models.OperationalBlockStatus.CANCELLED,
            execution_status=models.OperationalBlockExecutionStatus.CANCELLED,
            cancelled_at=datetime.now(UTC),
        )
    )


async def preview_change(
    db: AsyncSession,
    organization_id: int,
    data: schemas.CalendarEventChangePreviewRequest,
) -> schemas.CalendarEventChangePreviewRead:
    if data.operation == "delete":
        await _load_flow(db, organization_id, data.event_id)
        return schemas.CalendarEventChangePreviewRead(
            requires_confirmation=False,
            affected_lessons=[],
            message="Eliminar um fluxo não repõe aulas. Nenhuma aula será retirada do horário.",
        )
    await validate_flow_input(
        db,
        organization_id,
        data.start_date,
        data.end_date,
        data.class_ids,
    )
    impact = await compute_impact(
        db,
        organization_id,
        data.class_ids,
        data.start_date,
        data.end_date,
    )
    return _preview_response(impact)


async def create_flow(
    db: AsyncSession,
    organization_id: int,
    data: schemas.SchoolCalendarEventCreate,
    changed_by_membership_id: int | None = None,
) -> models.SchoolCalendarEvent:
    await validate_flow_input(db, organization_id, data.start_date, data.end_date, data.class_ids)
    await _lock_scheduler_state(db, organization_id)
    impact = await _stable_impact(
        db, organization_id, data.class_ids, data.start_date, data.end_date
    )
    require_confirmation(impact, data.confirmation_fingerprint)
    school_year_start_year = await resolve_school_start_year(db, organization_id)

    event = models.SchoolCalendarEvent(
        organization_id=organization_id,
        school_year_start_year=school_year_start_year,
        name=data.name,
        start_date=data.start_date,
        end_date=data.end_date,
        event_type=models.CalendarEventType.internship_flow,
        source=models.CalendarEventSource.manual,
        class_links=[
            models.SchoolCalendarEventClass(organization_id=organization_id, class_id=class_id)
            for class_id in data.class_ids
        ],
    )
    db.add(event)
    await db.flush()
    await remove_affected_blocks(db, organization_id, impact.lessons)
    await _cancel_pending_operational_blocks(
        db, organization_id, data.class_ids, data.start_date, data.end_date
    )
    await record_scheduler_change(
        db,
        organization_id,
        entity_type="INTERNSHIP_FLOW",
        entity_id=event.id,
        operation=models.SchedulerStateChangeOperation.CREATE,
        before=None,
        after=flow_blocking_snapshot(event, data.class_ids),
        changed_by_membership_id=changed_by_membership_id,
        future_impacting=bool(data.class_ids),
        metadata={"removed_lesson_count": len(impact.lessons), "name": event.name},
    )
    await db.flush()
    await db.refresh(event)
    return event


async def update_flow(
    db: AsyncSession,
    organization_id: int,
    event_id: int,
    data: schemas.SchoolCalendarEventUpdate,
    changed_by_membership_id: int | None = None,
) -> models.SchoolCalendarEvent:
    await _lock_scheduler_state(db, organization_id)
    event = await _load_flow(db, organization_id, event_id, for_update=True)
    current_start_year = await resolve_school_start_year(db, organization_id)
    if event.school_year_start_year != current_start_year:
        raise InternshipFlowError(
            "Fluxos de anos anteriores são apenas para consulta. Crie um novo fluxo para o ano atual."
        )
    before_scope = flow_blocking_snapshot(event, event.class_ids)
    await validate_flow_input(db, organization_id, data.start_date, data.end_date, data.class_ids)
    impact = await _stable_impact(
        db, organization_id, data.class_ids, data.start_date, data.end_date
    )
    require_confirmation(impact, data.confirmation_fingerprint)

    event.name = data.name
    event.start_date = data.start_date
    event.end_date = data.end_date
    after_scope = flow_blocking_snapshot(event, data.class_ids)
    await _replace_class_links(db, event, organization_id, data.class_ids)
    await remove_affected_blocks(db, organization_id, impact.lessons)
    await _cancel_pending_operational_blocks(
        db, organization_id, data.class_ids, data.start_date, data.end_date
    )
    await db.flush()
    blocking_changed = before_scope != after_scope
    await record_scheduler_change(
        db,
        organization_id,
        entity_type="INTERNSHIP_FLOW",
        entity_id=event.id,
        operation=models.SchedulerStateChangeOperation.UPDATE,
        before=before_scope,
        after=after_scope,
        changed_by_membership_id=changed_by_membership_id,
        future_impacting=blocking_changed,
        metadata={
            "removed_lesson_count": len(impact.lessons),
            "name": event.name,
            "blocking_changed": blocking_changed,
        },
    )
    await db.flush()
    await db.refresh(event)
    return event


async def delete_flow(
    db: AsyncSession,
    organization_id: int,
    event_id: int,
    changed_by_membership_id: int | None = None,
) -> None:
    event = await _load_flow(db, organization_id, event_id, for_update=True)
    before_scope = flow_blocking_snapshot(event, event.class_ids)
    blocked_classes = bool(event.class_ids)
    name = event.name
    await db.delete(event)
    await record_scheduler_change(
        db,
        organization_id,
        entity_type="INTERNSHIP_FLOW",
        entity_id=event_id,
        operation=models.SchedulerStateChangeOperation.DELETE,
        before=before_scope,
        after=None,
        changed_by_membership_id=changed_by_membership_id,
        future_impacting=blocked_classes,
        metadata={"removed_lesson_count": 0, "name": name},
    )
    await db.flush()


async def _replace_class_links(
    db: AsyncSession,
    event: models.SchoolCalendarEvent,
    organization_id: int,
    class_ids: list[int],
) -> None:
    await db.refresh(event, attribute_names=["class_links"])
    for link in list(event.class_links):
        await db.delete(link)
    await db.flush()
    db.add_all(
        [
            models.SchoolCalendarEventClass(
                organization_id=organization_id,
                calendar_event_id=event.id,
                class_id=class_id,
            )
            for class_id in class_ids
        ]
    )
    await db.flush()
    await db.refresh(event, attribute_names=["class_links"])


async def _load_flow(
    db: AsyncSession,
    organization_id: int,
    event_id: int | None,
    *,
    for_update: bool = False,
) -> models.SchoolCalendarEvent:
    if event_id is None:
        raise InternshipFlowError("Indique o fluxo de estágio.")
    query = select(models.SchoolCalendarEvent).where(
        models.SchoolCalendarEvent.id == event_id,
        models.SchoolCalendarEvent.organization_id == organization_id,
    )
    if for_update:
        query = query.with_for_update()
    event = await db.scalar(query)
    if event is None or event.event_type != models.CalendarEventType.internship_flow:
        raise InternshipFlowError("Fluxo de estágio não encontrado.")
    return event


def _preview_response(impact: FlowImpact) -> schemas.CalendarEventChangePreviewRead:
    lessons = [
        schemas.AffectedLessonRead(
            active_schedule_block_id=lesson.active_schedule_block_id,
            class_id=lesson.class_id,
            class_name=lesson.class_name,
            subject_id=lesson.subject_id,
            subject_name=lesson.subject_name,
            date=lesson.date,
            timeslot_id=lesson.timeslot_id,
            duration_minutes=lesson.duration_minutes,
        )
        for lesson in impact.lessons
    ]
    if not lessons:
        message = "Sem aulas afetadas: o horário publicado não muda."
    else:
        message = (
            f"{len(lessons)} aula(s) serão retiradas do horário ativo. "
            "As aulas já dadas e os registos existentes são preservados."
        )
    return schemas.CalendarEventChangePreviewRead(
        requires_confirmation=impact.requires_confirmation,
        confirmation_fingerprint=impact.fingerprint,
        affected_lessons=lessons,
        message=message,
    )


def _value(value: Any) -> str | None:
    if value is None:
        return None
    return str(getattr(value, "value", value))
