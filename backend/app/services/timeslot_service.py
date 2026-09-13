from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

import structlog
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models, schemas
from app.core.exceptions import ConflictError
from app.services.scheduler_state_service import record_scheduler_change

logger = structlog.get_logger(__name__)

PROTECTED_GRID_MESSAGE = (
    "Não é possível regenerar a grelha enquanto existirem horários, rascunhos "
    "ou registos operacionais. Se pretende apagar esses dados, use “Período "
    "Letivo > Recomeçar Ano Letivo” e confirme a operação antes de tentar novamente."
)
SLOT_RULES_MESSAGE = (
    "Existem regras associadas aos blocos horários atuais. Remova ou recrie "
    "essas regras antes de substituir a grelha."
)

TIMESLOT_DEPENDENCY_POLICIES = {
    ("availability", "timeslot_id"): "recreate",
    ("schedule_draft_blocks", "timeslot_id"): "protect",
    ("active_schedule_blocks", "timeslot_id"): "protect",
    ("operational_schedule_block", "timeslot_id"): "protect",
    ("schedule_output", "timeslot_id"): "protect",
    ("substitutions", "timeslot_id"): "protect",
    ("lesson_occurrence", "planned_timeslot_id"): "protect",
    ("schedule_diff_entries", "before_timeslot_id"): "protect",
    ("schedule_diff_entries", "after_timeslot_id"): "protect",
}


@dataclass(frozen=True)
class GridRegenerationPlan:
    organization_id: int
    desired_signatures: tuple[tuple[int, time, time], ...]
    before_grid: tuple[dict, ...]
    changed: bool


def _timeslot_snapshot(slot: models.Timeslot) -> dict:
    return {
        "day_of_week": slot.day_of_week,
        "start_time": slot.start_time,
        "end_time": slot.end_time,
    }


async def _get_org_teacher_ids(db: AsyncSession, organization_id: int) -> list[int]:
    result = await db.execute(
        select(models.Teacher.id).where(models.Teacher.organization_id == organization_id)
    )
    return list(result.scalars().all())


async def _get_availability_preferences_by_time(
    db: AsyncSession,
    organization_id: int,
) -> dict[tuple[int, int, time, time], int]:
    """Snapshot preferences by (teacher, day, start, end) before timeslot reset."""
    result = await db.execute(
        select(
            models.Availability.teacher_id,
            models.Timeslot.day_of_week,
            models.Timeslot.start_time,
            models.Timeslot.end_time,
            models.Availability.score,
        )
        .join(models.Timeslot, models.Timeslot.id == models.Availability.timeslot_id)
        .where(models.Timeslot.organization_id == organization_id)
    )
    return {
        (teacher_id, day_of_week, start_time, end_time): score
        for teacher_id, day_of_week, start_time, end_time, score in result.all()
    }


def _restore_availabilities_for_new_grid(
    db: AsyncSession,
    organization_id: int,
    teacher_ids: list[int],
    timeslots: list[models.Timeslot],
    previous_preferences: dict[tuple[int, int, time, time], int],
) -> None:
    """Recreate availability matrix for all teachers in the new grid.

    If a new slot matches a previous slot by day/start/end, reuse that score.
    Otherwise default to NEUTRAL so schedule generation remains feasible.
    """
    neutral_score = models.PreferenceLevel.NEUTRAL.value
    for teacher_id in teacher_ids:
        for slot in timeslots:
            score = previous_preferences.get(
                (teacher_id, slot.day_of_week, slot.start_time, slot.end_time),
                neutral_score,
            )
            db.add(
                models.Availability(
                    organization_id=organization_id,
                    teacher_id=teacher_id,
                    timeslot_id=slot.id,
                    score=score,
                )
            )


async def get_timeslots_by_org(db: AsyncSession, organization_id: int):
    # Ordenar por Dia da Semana e depois Hora de Início
    stmt = (
        select(models.Timeslot)
        .where(models.Timeslot.organization_id == organization_id)
        .order_by(models.Timeslot.day_of_week, models.Timeslot.start_time)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


async def create_timeslot(
    db: AsyncSession,
    item: schemas.TimeslotCreate,
    organization_id: int,
    changed_by_membership_id: int | None = None,
):
    db_item = models.Timeslot(**item.model_dump(), organization_id=organization_id)
    db.add(db_item)
    await db.flush()
    await record_scheduler_change(
        db,
        organization_id,
        entity_type="TIMESLOT",
        entity_id=db_item.id,
        operation=models.SchedulerStateChangeOperation.CREATE,
        before=None,
        after=_timeslot_snapshot(db_item),
        changed_by_membership_id=changed_by_membership_id,
    )
    await db.flush()
    await db.refresh(db_item)
    return db_item


async def update_timeslot(
    db: AsyncSession,
    timeslot_id: int,
    item: schemas.TimeslotUpdate,
    organization_id: int,
    changed_by_membership_id: int | None = None,
):
    query = select(models.Timeslot).where(
        models.Timeslot.id == timeslot_id, models.Timeslot.organization_id == organization_id
    )
    result = await db.execute(query)
    db_item = result.scalars().first()

    if not db_item:
        return None

    before = _timeslot_snapshot(db_item)
    update_data = item.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_item, field, value)

    db.add(db_item)
    await record_scheduler_change(
        db,
        organization_id,
        entity_type="TIMESLOT",
        entity_id=db_item.id,
        operation=models.SchedulerStateChangeOperation.UPDATE,
        before=before,
        after=_timeslot_snapshot(db_item),
        changed_by_membership_id=changed_by_membership_id,
    )
    await db.flush()
    await db.refresh(db_item)
    return db_item


async def delete_timeslot(
    db: AsyncSession,
    timeslot_id: int,
    organization_id: int,
    changed_by_membership_id: int | None = None,
):
    """
    Remove um bloco horário individual.
    Lógica 'Soft': Limpa dependências fracas (Availability) mas bloqueia se houver dados críticos.
    """
    result = await db.execute(
        select(models.Timeslot).where(
            models.Timeslot.id == timeslot_id, models.Timeslot.organization_id == organization_id
        )
    )
    item = result.scalars().first()

    if not item:
        return "NOT_FOUND"

    # Verificações de Integridade (Firewall para delete individual)

    for model in (
        models.ActiveScheduleBlock,
        models.ScheduleDraftBlock,
        models.OperationalScheduleBlock,
    ):
        query = select(model.id).where(model.timeslot_id == timeslot_id)
        if (await db.execute(query)).first():
            return "DEPENDENCY_ERROR_SCHEDULE"

    # Limpeza de dependências fracas (Availability)
    await db.execute(
        delete(models.Availability).where(models.Availability.timeslot_id == timeslot_id)
    )

    before = _timeslot_snapshot(item)
    await db.delete(item)
    await record_scheduler_change(
        db,
        organization_id,
        entity_type="TIMESLOT",
        entity_id=item.id,
        operation=models.SchedulerStateChangeOperation.DELETE,
        before=before,
        after=None,
        changed_by_membership_id=changed_by_membership_id,
    )
    await db.flush()
    return "SUCCESS"


# --- GERAÇÃO EM MASSA (RESET ESTRUTURAL) ---


def build_timeslot_signatures(
    settings: schemas.TimeslotBulkCreate,
) -> list[tuple[int, time, time]]:
    """Pure, canonical implementation of the grid generation math."""
    signatures: list[tuple[int, time, time]] = []
    current = datetime.combine(date.min, settings.start_time)
    limit = datetime.combine(date.min, settings.end_time)
    while current + timedelta(minutes=settings.slot_duration_minutes) <= limit:
        end = current + timedelta(minutes=settings.slot_duration_minutes)
        signatures.extend(
            (day, current.time(), end.time()) for day in sorted(settings.days_of_week)
        )
        current = end + timedelta(minutes=settings.break_duration_minutes)
    return sorted(signatures)


async def _count_for_org(
    db: AsyncSession,
    model,
    organization_id: int,
    *conditions,
) -> int:
    return (
        await db.scalar(
            select(func.count())
            .select_from(model)
            .where(model.organization_id == organization_id, *conditions)
        )
        or 0
    )


async def _protected_dependency_counts(
    db: AsyncSession,
    organization_id: int,
    current_slot_ids: set[int],
    published: bool,
) -> dict[str, int]:
    counts = {
        "published_state": int(published),
        "draft_blocks": await _count_for_org(db, models.ScheduleDraftBlock, organization_id),
        "active_blocks": await _count_for_org(db, models.ActiveScheduleBlock, organization_id),
        "operational_blocks": await _count_for_org(
            db, models.OperationalScheduleBlock, organization_id
        ),
        "lesson_occurrences": await _count_for_org(
            db,
            models.LessonOccurrence,
            organization_id,
            models.LessonOccurrence.planned_timeslot_id.in_(current_slot_ids),
        ),
        "schedule_diffs": await _count_for_org(
            db,
            models.ScheduleDiffEntry,
            organization_id,
            or_(
                models.ScheduleDiffEntry.before_timeslot_id.in_(current_slot_ids),
                models.ScheduleDiffEntry.after_timeslot_id.in_(current_slot_ids),
            ),
        ),
    }
    constraints = list(
        await db.scalars(
            select(models.Constraint).where(models.Constraint.organization_id == organization_id)
        )
    )
    counts["slot_rules"] = sum(
        1
        for constraint in constraints
        if isinstance(constraint.rule_payload, dict)
        and constraint.rule_payload.get("timeslot_id") in current_slot_ids
    )
    return {category: count for category, count in counts.items() if count}


async def preflight_grid_regeneration(
    db: AsyncSession,
    settings: schemas.TimeslotBulkCreate,
    organization_id: int,
    changed_by_membership_id: int | None = None,
) -> GridRegenerationPlan:
    organization = await db.scalar(
        select(models.Organization)
        .where(models.Organization.id == organization_id)
        .with_for_update()
    )
    if organization is None:
        raise ValueError("Organization does not exist.")

    active_year = await db.scalar(
        select(models.SchedulerSchoolYear)
        .where(
            models.SchedulerSchoolYear.organization_id == organization_id,
            models.SchedulerSchoolYear.is_active.is_(True),
        )
        .with_for_update()
    )
    state = None
    if active_year is not None:
        state = await db.scalar(
            select(models.SchedulerSchoolYearState)
            .where(
                models.SchedulerSchoolYearState.organization_id == organization_id,
                models.SchedulerSchoolYearState.school_year_id == active_year.id,
            )
            .with_for_update()
        )

    current_slots = list(
        await db.scalars(
            select(models.Timeslot)
            .where(models.Timeslot.organization_id == organization_id)
            .order_by(models.Timeslot.day_of_week, models.Timeslot.start_time)
            .with_for_update()
        )
    )
    desired = tuple(build_timeslot_signatures(settings))
    current = tuple((slot.day_of_week, slot.start_time, slot.end_time) for slot in current_slots)
    plan = GridRegenerationPlan(
        organization_id=organization_id,
        desired_signatures=desired,
        before_grid=tuple(_timeslot_snapshot(slot) for slot in current_slots),
        changed=current != desired,
    )
    if not plan.changed:
        return plan

    blockers = await _protected_dependency_counts(
        db,
        organization_id,
        {slot.id for slot in current_slots},
        state is not None
        and state.school_year_publication_state == models.SchoolYearPublicationState.PUBLISHED,
    )
    if blockers:
        logger.info(
            "grid_regeneration_blocked",
            organization_id=organization_id,
            actor_membership_id=changed_by_membership_id,
            blockers=blockers,
        )
        message = SLOT_RULES_MESSAGE if set(blockers) == {"slot_rules"} else PROTECTED_GRID_MESSAGE
        raise ConflictError(message)
    return plan


async def apply_grid_regeneration(
    db: AsyncSession,
    plan: GridRegenerationPlan,
    changed_by_membership_id: int | None = None,
) -> int:
    if not plan.changed:
        return len(plan.desired_signatures)

    teacher_ids = await _get_org_teacher_ids(db, plan.organization_id)
    previous_preferences = await _get_availability_preferences_by_time(db, plan.organization_id)
    await db.execute(
        delete(models.Availability).where(
            models.Availability.organization_id == plan.organization_id
        )
    )
    await db.execute(
        delete(models.Timeslot).where(models.Timeslot.organization_id == plan.organization_id)
    )
    await db.flush()

    new_timeslots = [
        models.Timeslot(
            organization_id=plan.organization_id,
            day_of_week=day,
            start_time=start,
            end_time=end,
        )
        for day, start, end in plan.desired_signatures
    ]
    db.add_all(new_timeslots)
    await db.flush()
    _restore_availabilities_for_new_grid(
        db,
        plan.organization_id,
        teacher_ids,
        new_timeslots,
        previous_preferences,
    )
    await record_scheduler_change(
        db,
        plan.organization_id,
        entity_type="TIMETABLE_GRID",
        entity_id=None,
        operation=models.SchedulerStateChangeOperation.BULK_IMPORT,
        before=plan.before_grid,
        after=[_timeslot_snapshot(slot) for slot in new_timeslots],
        changed_by_membership_id=changed_by_membership_id,
        metadata={"created_count": len(new_timeslots)},
    )
    await db.flush()
    return len(new_timeslots)


