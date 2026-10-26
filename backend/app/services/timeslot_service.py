from dataclasses import dataclass
from datetime import date, time

import structlog
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models, schemas
from app.core.exceptions import AppError
from app.scheduler.domain.timetable import BreakOverride, build_daily_slots
from app.scheduler.infrastructure.models import SchedulerProposalV1
from app.services import grid_version_service
from app.services.scheduler_state_service import record_scheduler_change

logger = structlog.get_logger(__name__)

PENDING_PROPOSAL_MESSAGE = (
    "Existe uma proposta de alteração da grelha pendente. Conclua ou cancele "
    "a proposta antes de regenerar a grelha."
)


@dataclass(frozen=True)
class GridRegenerationPlan:
    organization_id: int
    desired_signatures: tuple[tuple[int, time, time], ...]
    before_grid: tuple[dict, ...]
    changed: bool
    configuration: dict | None = None
    configuration_changed: bool = False
    replaceable_slot_ids: tuple[int, ...] = ()


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
    timeslot_ids: set[int],
) -> dict[tuple[int, int, time, time], int]:
    """Snapshot preferences by (teacher, day, start, end) before timeslot reset."""
    if not timeslot_ids:
        return {}
    result = await db.execute(
        select(
            models.Availability.teacher_id,
            models.Timeslot.day_of_week,
            models.Timeslot.start_time,
            models.Timeslot.end_time,
            models.Availability.score,
        )
        .join(models.Timeslot, models.Timeslot.id == models.Availability.timeslot_id)
        .where(
            models.Timeslot.organization_id == organization_id,
            models.Timeslot.id.in_(timeslot_ids),
        )
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


async def _get_class_availability_by_time(
    db: AsyncSession,
    organization_id: int,
    timeslot_ids: set[int],
) -> dict[tuple[int, int, time, time], int]:
    """Snapshot class availability by (class, day, start, end) before reset.

    Only non-NEUTRAL rows exist, so a missing key means NEUTRAL in the new grid.
    """
    if not timeslot_ids:
        return {}
    result = await db.execute(
        select(
            models.ClassAvailability.class_id,
            models.Timeslot.day_of_week,
            models.Timeslot.start_time,
            models.Timeslot.end_time,
            models.ClassAvailability.score,
        )
        .join(models.Timeslot, models.Timeslot.id == models.ClassAvailability.timeslot_id)
        .where(
            models.ClassAvailability.organization_id == organization_id,
            models.Timeslot.organization_id == organization_id,
            models.Timeslot.id.in_(timeslot_ids),
        )
    )
    return {
        (class_id, day_of_week, start_time, end_time): score
        for class_id, day_of_week, start_time, end_time, score in result.all()
    }


def _restore_class_availability_for_new_grid(
    db: AsyncSession,
    organization_id: int,
    timeslots: list[models.Timeslot],
    previous_preferences: dict[tuple[int, int, time, time], int],
) -> None:
    """Recreate class rows on the blocks that keep the same signature.

    A block without a matching signature stays NEUTRAL because no row is stored.
    """
    signature_to_slot = {
        (slot.day_of_week, slot.start_time, slot.end_time): slot for slot in timeslots
    }
    restored: dict[tuple[int, int], int] = {}
    for (class_id, day_of_week, start_time, end_time), score in previous_preferences.items():
        slot = signature_to_slot.get((day_of_week, start_time, end_time))
        if slot is None:
            continue
        restored[(class_id, slot.id)] = score
    for (class_id, timeslot_id), score in restored.items():
        db.add(
            models.ClassAvailability(
                organization_id=organization_id,
                class_id=class_id,
                timeslot_id=timeslot_id,
                score=score,
            )
        )


async def get_timeslots_by_org(
    db: AsyncSession,
    organization_id: int,
    on_date: date | None = None,
):
    """Return the blocks of the grid version valid on a school date."""
    target = on_date or await grid_version_service.school_today(db, organization_id)
    resolved = await grid_version_service.resolve_grid(db, organization_id, target)
    return list(resolved.blocks)


async def create_timeslot(
    db: AsyncSession,
    item: schemas.TimeslotCreate,
    organization_id: int,
    changed_by_membership_id: int | None = None,
):
    version = await grid_version_service.ensure_active_grid_version(db, organization_id)
    db_item = models.Timeslot(
        **item.model_dump(),
        organization_id=organization_id,
        grid_version_id=version.id,
    )
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


# --- GERAÇÃO EM MASSA (RESET ESTRUTURAL) ---


def build_timeslot_signatures(
    settings: schemas.TimeslotBulkCreate,
) -> list[tuple[int, time, time]]:
    """Pure, canonical implementation of the grid generation math."""
    slots = build_daily_slots(
        opening_time=settings.start_time,
        closing_time=settings.end_time,
        slot_duration_minutes=settings.slot_duration_minutes,
        break_duration_minutes=settings.break_duration_minutes,
        break_overrides=tuple(
            BreakOverride(
                after_slot=override.after_slot,
                duration_minutes=override.duration_minutes,
            )
            for override in settings.break_overrides
        ),
    )
    return sorted(
        (day, slot.start, slot.end) for day in sorted(settings.days_of_week) for slot in slots
    )


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
        "pending_proposals": await _count_for_org(
            db, SchedulerProposalV1, organization_id, SchedulerProposalV1.status == "PENDING"
        ),
        "operational_blocks": await _count_for_org(
            db, models.OperationalScheduleBlock, organization_id
        ),
        "lesson_occurrences": await _count_for_org(
            db,
            models.LessonOccurrence,
            organization_id,
            models.LessonOccurrence.planned_timeslot_id.in_(current_slot_ids),
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

    all_slots = list(
        await db.scalars(
            select(models.Timeslot)
            .where(models.Timeslot.organization_id == organization_id)
            .order_by(models.Timeslot.day_of_week, models.Timeslot.start_time)
            .with_for_update()
        )
    )
    active_version = await grid_version_service.get_active_grid_version(db, organization_id)
    replaceable_slots = [
        slot
        for slot in all_slots
        if slot.grid_version_id is None
        or (active_version is not None and slot.grid_version_id == active_version.id)
    ]
    desired = tuple(build_timeslot_signatures(settings))
    current = tuple(
        (slot.day_of_week, slot.start_time, slot.end_time) for slot in replaceable_slots
    )
    configuration = grid_version_service.configuration_from_bulk(settings)
    configuration_changed = (
        active_version is None or active_version.configuration_json != configuration
    )
    plan = GridRegenerationPlan(
        organization_id=organization_id,
        desired_signatures=desired,
        before_grid=tuple(_timeslot_snapshot(slot) for slot in replaceable_slots),
        changed=current != desired,
        configuration=configuration,
        configuration_changed=configuration_changed,
        replaceable_slot_ids=tuple(slot.id for slot in replaceable_slots),
    )
    if not plan.changed:
        # Configuration-only edits are safe to persist without touching blocks.
        return plan

    pending_version = next(
        (
            version
            for version in await grid_version_service.list_grid_versions(db, organization_id)
            if version.state == models.GridVersionState.PENDING
        ),
        None,
    )
    if pending_version is not None:
        raise AppError(
            kind="conflict",
            code="conflict",
            detail=PENDING_PROPOSAL_MESSAGE,
        )

    blockers = await _protected_dependency_counts(
        db,
        organization_id,
        {slot.id for slot in all_slots},
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
        code = (
            "grid_slot_rules_blocked"
            if set(blockers) == {"slot_rules"}
            else "grid_regeneration_blocked"
        )
        raise AppError(kind="conflict", code=code, detail=code)
    return plan


async def apply_grid_regeneration(
    db: AsyncSession,
    plan: GridRegenerationPlan,
    changed_by_membership_id: int | None = None,
) -> int:
    # Regeneration is only reachable without schedule dependencies, so the
    # active version can still replace its blocks in place.
    version = await grid_version_service.ensure_active_grid_version(db, plan.organization_id)
    if plan.configuration is not None and version.configuration_json != plan.configuration:
        version.configuration_json = plan.configuration

    if not plan.changed:
        await db.flush()
        return len(plan.desired_signatures)

    teacher_ids = await _get_org_teacher_ids(db, plan.organization_id)
    previous_preferences = await _get_availability_preferences_by_time(
        db, plan.organization_id, set(plan.replaceable_slot_ids)
    )
    previous_class_preferences = await _get_class_availability_by_time(
        db, plan.organization_id, set(plan.replaceable_slot_ids)
    )
    if plan.replaceable_slot_ids:
        await db.execute(
            delete(models.Availability).where(
                models.Availability.organization_id == plan.organization_id,
                models.Availability.timeslot_id.in_(plan.replaceable_slot_ids),
            )
        )
        await db.execute(
            delete(models.Timeslot).where(
                models.Timeslot.organization_id == plan.organization_id,
                models.Timeslot.id.in_(plan.replaceable_slot_ids),
            )
        )
    await db.flush()

    new_timeslots = [
        models.Timeslot(
            organization_id=plan.organization_id,
            grid_version_id=version.id,
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
    _restore_class_availability_for_new_grid(
        db,
        plan.organization_id,
        new_timeslots,
        previous_class_preferences,
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
