"""School operations over scheduler v1 lessons: weekly map, logs and adjustments.

These consumers read and write only the v1 curricular ledger. A lesson can hold
several module slices, execution is credited once, an occurrence creates an
audited debt origin, and manual adjustments append signed corrections instead
of overwriting history.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models, schemas
from app.scheduler.domain.demand import ExecutionEntry, ModuleCredit, frontier_credit
from app.scheduler.domain.lesson_time import execution_allowed
from app.scheduler.domain.projection import ModuleRequirement
from app.scheduler.infrastructure.models import (
    CurricularAssignment,
    CurricularRequirement,
    SchedulerLessonLogV1,
    SchedulerLessonSliceV1,
    SchedulerLessonV1,
    SchedulerVersionV1,
)
from app.scheduler.infrastructure.progress import (
    load_executed_minutes,
    load_execution_entries,
    load_open_debt,
    record_execution,
)

LESSON_LOG_ORIGIN = "lesson-log:{lesson_id}"
LESSON_OCCURRENCE_ORIGIN = "lesson-occurrence:{lesson_id}"
SUBSTITUTION_ORIGIN = "substitution:{occurrence_id}:{teacher_id}"
SUBSTITUTION_LIKE = "substitution:{occurrence_id}:%"


class OperationsError(ValueError):
    """A school operation cannot be applied to the current v1 state."""

    def __init__(self, code: str, message: str, *, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


async def _active_year_and_version(db: AsyncSession, organization_id: int):
    year = await db.scalar(
        select(models.SchedulerSchoolYear).where(
            models.SchedulerSchoolYear.organization_id == organization_id,
            models.SchedulerSchoolYear.is_active.is_(True),
        )
    )
    if year is None:
        return None, None
    version = await db.scalar(
        select(SchedulerVersionV1).where(
            SchedulerVersionV1.organization_id == organization_id,
            SchedulerVersionV1.school_year_id == year.id,
            SchedulerVersionV1.status == "ACTIVE",
        )
    )
    return year, version


def _local_times(lesson: SchedulerLessonV1, zone: ZoneInfo) -> tuple[time, time]:
    start = lesson.starts_at.astimezone(zone)
    end = lesson.ends_at.astimezone(zone)
    return time(start.hour, start.minute), time(end.hour, end.minute)


def _module_summary(
    module_id: int | None, required_minutes: int | None, name: str | None
) -> dict | None:
    if module_id is None or required_minutes is None or name is None:
        return None
    return {"id": module_id, "name": name, "hours_total": required_minutes / 60}


async def week_schedule(
    db: AsyncSession,
    organization_id: int,
    *,
    week_start: date,
    class_id: int | None,
    teacher_id: int | None,
    today: date | None = None,
    now_utc: datetime | None = None,
) -> list[dict] | None:
    """Published v1 lessons of one week with their modular slices.

    Returns ``None`` when no v1 version is active so the caller can keep the
    legacy operational view during the transition.
    """
    year, version = await _active_year_and_version(db, organization_id)
    if year is None or version is None:
        return None
    zone = ZoneInfo(year.timezone)
    reference_today = today if today is not None else date.today()
    moment = now_utc or datetime.now(UTC)
    week_end = week_start + timedelta(days=6)
    lessons_query = (
        select(
            SchedulerLessonV1,
            CurricularAssignment,
            models.Subject,
            models.Teacher,
            models.Class,
            models.Room,
        )
        .join(
            CurricularAssignment,
            (CurricularAssignment.organization_id == SchedulerLessonV1.organization_id)
            & (CurricularAssignment.school_year_id == SchedulerLessonV1.school_year_id)
            & (CurricularAssignment.id == SchedulerLessonV1.assignment_id),
        )
        .join(
            models.Subject,
            (models.Subject.organization_id == SchedulerLessonV1.organization_id)
            & (models.Subject.id == CurricularAssignment.subject_id),
        )
        .join(
            models.Teacher,
            (models.Teacher.organization_id == SchedulerLessonV1.organization_id)
            & (models.Teacher.id == CurricularAssignment.teacher_id),
        )
        .join(
            models.Class,
            (models.Class.organization_id == SchedulerLessonV1.organization_id)
            & (models.Class.id == CurricularAssignment.class_id),
        )
        .join(
            models.Room,
            (models.Room.organization_id == SchedulerLessonV1.organization_id)
            & (models.Room.id == SchedulerLessonV1.room_id),
        )
        .where(
            SchedulerLessonV1.organization_id == organization_id,
            SchedulerLessonV1.school_year_id == year.id,
            SchedulerLessonV1.version_id == version.id,
            SchedulerLessonV1.school_date.between(week_start, week_end),
        )
        .order_by(
            SchedulerLessonV1.school_date,
            SchedulerLessonV1.starts_at,
            SchedulerLessonV1.id,
        )
    )
    if class_id is not None:
        lessons_query = lessons_query.where(CurricularAssignment.class_id == class_id)
    if teacher_id is not None:
        lessons_query = lessons_query.where(CurricularAssignment.teacher_id == teacher_id)
    rows = (await db.execute(lessons_query)).all()
    block_query = (
        select(models.OperationalScheduleBlock)
        .where(
            models.OperationalScheduleBlock.organization_id == organization_id,
            models.OperationalScheduleBlock.status == models.OperationalBlockStatus.ACTIVE,
            models.OperationalScheduleBlock.origin_kind == models.OperationalBlockOrigin.V1,
            models.OperationalScheduleBlock.date.between(week_start, week_end),
        )
        .order_by(models.OperationalScheduleBlock.date, models.OperationalScheduleBlock.id)
    )
    if class_id is not None:
        block_query = block_query.where(models.OperationalScheduleBlock.class_id == class_id)
    block_models = (await db.scalars(block_query)).all()
    if not rows and not block_models:
        return []
    all_block_rows: list = []
    if block_models:
        # The heavy detail join only runs when a substitution exists this week.
        all_block_rows = (
            await db.execute(
                select(
                    models.OperationalScheduleBlock,
                    SchedulerLessonV1,
                    SchedulerLessonLogV1,
                    models.Subject,
                    models.Teacher,
                    models.Class,
                    models.Room,
                    models.Module,
                )
                .join(
                    SchedulerLessonLogV1,
                    and_(
                        SchedulerLessonLogV1.organization_id
                        == models.OperationalScheduleBlock.organization_id,
                        SchedulerLessonLogV1.id
                        == models.OperationalScheduleBlock.source_v1_lesson_log_id,
                    ),
                )
                .join(
                    SchedulerLessonV1,
                    and_(
                        SchedulerLessonV1.organization_id == SchedulerLessonLogV1.organization_id,
                        SchedulerLessonV1.school_year_id == SchedulerLessonLogV1.school_year_id,
                        SchedulerLessonV1.id == SchedulerLessonLogV1.lesson_id,
                    ),
                )
                .join(
                    models.Subject,
                    and_(
                        models.Subject.organization_id
                        == models.OperationalScheduleBlock.organization_id,
                        models.Subject.id == models.OperationalScheduleBlock.subject_id,
                    ),
                )
                .join(
                    models.Teacher,
                    and_(
                        models.Teacher.organization_id
                        == models.OperationalScheduleBlock.organization_id,
                        models.Teacher.id == models.OperationalScheduleBlock.teacher_id,
                    ),
                )
                .join(
                    models.Class,
                    and_(
                        models.Class.organization_id
                        == models.OperationalScheduleBlock.organization_id,
                        models.Class.id == models.OperationalScheduleBlock.class_id,
                    ),
                )
                .outerjoin(
                    models.Room,
                    and_(
                        models.Room.organization_id
                        == models.OperationalScheduleBlock.organization_id,
                        models.Room.id == models.OperationalScheduleBlock.room_id,
                    ),
                )
                .outerjoin(
                    models.Module,
                    and_(
                        models.Module.organization_id
                        == models.OperationalScheduleBlock.organization_id,
                        models.Module.id == models.OperationalScheduleBlock.module_id,
                    ),
                )
                .where(models.OperationalScheduleBlock.id.in_([row.id for row in block_models]))
            )
        ).all()
    # The original lesson leaves every active view, not only the substitute's.
    hidden_lesson_ids = {lesson.id for _block, lesson, *_rest in all_block_rows}
    block_rows = [
        row for row in all_block_rows if teacher_id is None or row[0].teacher_id == teacher_id
    ]
    lesson_ids = [row[0].id for row in rows]
    assignment_ids = sorted({row[0].assignment_id for row in rows})
    executed = await load_executed_minutes(db, organization_id, assignment_ids)
    requirements = await _requirements_for_assignments(db, organization_id, assignment_ids)
    module_names = dict(
        (
            await db.execute(
                select(models.Module.id, models.Module.name).where(
                    models.Module.organization_id == organization_id,
                    models.Module.id.in_(
                        {row.module_id for reqs in requirements.values() for row in reqs}
                    ),
                )
            )
        ).all()
    )
    slices_by_lesson: dict[int, list] = defaultdict(list)
    slice_rows = (
        await db.execute(
            select(SchedulerLessonSliceV1, models.Module)
            .join(
                models.Module,
                (models.Module.organization_id == SchedulerLessonSliceV1.organization_id)
                & (models.Module.id == SchedulerLessonSliceV1.module_id),
            )
            .where(
                SchedulerLessonSliceV1.organization_id == organization_id,
                SchedulerLessonSliceV1.school_year_id == year.id,
                SchedulerLessonSliceV1.lesson_id.in_(lesson_ids),
            )
            .order_by(SchedulerLessonSliceV1.lesson_id, SchedulerLessonSliceV1.offset_minutes)
        )
    ).all()
    for slice_row, module in slice_rows:
        slices_by_lesson[slice_row.lesson_id].append((slice_row, module))
    logs = {
        row.lesson_id: row
        for row in (
            await db.scalars(
                select(SchedulerLessonLogV1).where(
                    SchedulerLessonLogV1.organization_id == organization_id,
                    SchedulerLessonLogV1.lesson_id.in_(lesson_ids),
                )
            )
        ).all()
    }
    timeslots = {
        (row.day_of_week, row.start_time, row.end_time): row.id
        for row in (
            await db.scalars(
                select(models.Timeslot).where(models.Timeslot.organization_id == organization_id)
            )
        ).all()
    }
    timesheet_status = {
        row.teacher_id: row
        for row in (
            await db.scalars(
                select(models.TeacherWeeklyTimesheet).where(
                    models.TeacherWeeklyTimesheet.organization_id == organization_id,
                    models.TeacherWeeklyTimesheet.week_start_date == week_start,
                )
            )
        ).all()
    }
    slots: list[dict] = []
    for lesson, _assignment, subject, teacher, class_model, room in rows:
        if lesson.id in hidden_lesson_ids:
            continue
        start_local, end_local = _local_times(lesson, zone)
        position = slices_by_lesson.get(lesson.id, [])
        module_id = position[0][1].id if position else None
        module_minutes = position[0][1].required_minutes if position else None
        log = logs.get(lesson.id)
        timesheet = timesheet_status.get(teacher.id)
        lesson_finished = execution_allowed(moment, lesson.ends_at)
        timesheet_locked = timesheet is not None and timesheet.status in (
            models.TimesheetStatus.SUBMITTED,
            models.TimesheetStatus.APPROVED,
        )
        can_complete = (
            lesson_finished and not timesheet_locked and (log is None or log.status != "COMPLETED")
        )
        if not lesson_finished:
            blocked_reason = "lesson_not_finished"
        elif timesheet_locked:
            blocked_reason = "week_locked"
        else:
            blocked_reason = None
        slots.append(
            {
                "scheduler_lesson_id": lesson.id,
                "active_schedule_block_id": None,
                "operational_block_id": None,
                "block_source": "planned",
                "date": lesson.school_date.isoformat(),
                "timeslot": {
                    "id": timeslots.get((lesson.school_date.weekday(), start_local, end_local), 0),
                    "day_of_week": lesson.school_date.weekday(),
                    "start_time": start_local.strftime("%H:%M"),
                    "end_time": end_local.strftime("%H:%M"),
                },
                "subject": {"id": subject.id, "name": subject.name},
                "teacher": {"id": teacher.id, "name": teacher.name},
                "room": {"id": room.id, "name": room.name},
                "class_info": {"id": class_model.id, "name": class_model.name},
                "module": _module_summary(module_id, module_minutes, module_names.get(module_id)),
                "is_past": lesson.school_date < reference_today,
                "occurrence_status": (
                    None
                    if log is None
                    else ("REVOKED" if log.status == "REVOKED" else log.decision or "PENDING")
                ),
                "hours_given": None,
                "occurrence_id": (
                    log.id
                    if log is not None
                    and (log.status in ("OCCURRENCE", "REVOKED") or log.decision is not None)
                    else None
                ),
                "occurrence_decided_at": log.decided_at if log is not None else None,
                "can_create_occurrence": log is None or log.status == "REVOKED",
                "can_decide_occurrence": False,
                "lesson_log_id": log.id if log else None,
                "lesson_log_status": (
                    "PENDING"
                    if log is not None and log.status == "REVOKED"
                    else log.status
                    if log
                    else None
                ),
                "lesson_log_summary": log.summary if log else None,
                "lesson_log_notes": log.notes if log else None,
                "lesson_log_logged_at": log.logged_at if log else None,
                "week_timesheet_status": timesheet.status.value if timesheet else "OPEN",
                "timesheet_id": timesheet.id if timesheet else None,
                "is_substituted_block": False,
                "credit_minutes": lesson.credit_minutes,
                "slices": [
                    _slice_payload(
                        slice_row,
                        module,
                        executed.get(lesson.assignment_id, {}).get(module.id, 0),
                    )
                    for slice_row, module in position
                ],
                "substitute_execution_status": None,
                "ends_at": lesson.ends_at,
                "can_complete": can_complete,
                "blocked_reason": blocked_reason,
            }
        )
    if block_rows:
        block_logs = {
            row.operational_block_id: row
            for row in (
                await db.scalars(
                    select(models.LessonLog).where(
                        models.LessonLog.organization_id == organization_id,
                        models.LessonLog.operational_block_id.in_(
                            [block.id for block, *_rest in block_rows]
                        ),
                    )
                )
            ).all()
        }
        for (
            block,
            source_lesson,
            source_log,
            subject,
            teacher,
            class_model,
            room,
            module,
        ) in block_rows:
            local_start, local_end = _local_times(source_lesson, zone)
            timesheet = timesheet_status.get(block.teacher_id)
            timesheet_locked = timesheet is not None and timesheet.status in (
                models.TimesheetStatus.SUBMITTED,
                models.TimesheetStatus.APPROVED,
            )
            lesson_finished = execution_allowed(moment, source_lesson.ends_at)
            pending = block.execution_status == models.OperationalBlockExecutionStatus.PENDING_LOG
            can_complete = pending and lesson_finished and not timesheet_locked
            if not pending:
                blocked_reason = None
            elif not lesson_finished:
                blocked_reason = "lesson_not_finished"
            elif timesheet_locked:
                blocked_reason = "week_locked"
            else:
                blocked_reason = None
            block_log = block_logs.get(block.id)
            slots.append(
                {
                    "scheduler_lesson_id": None,
                    "active_schedule_block_id": None,
                    "operational_block_id": block.id,
                    "block_source": "operational",
                    "date": block.date.isoformat(),
                    "timeslot": {
                        "id": block.timeslot_id,
                        "day_of_week": block.date.weekday(),
                        "start_time": local_start.strftime("%H:%M"),
                        "end_time": local_end.strftime("%H:%M"),
                    },
                    "subject": {"id": subject.id, "name": subject.name},
                    "teacher": {"id": teacher.id, "name": teacher.name},
                    "room": {"id": room.id, "name": room.name} if room is not None else None,
                    "class_info": {"id": class_model.id, "name": class_model.name},
                    "module": _module_summary(
                        block.module_id,
                        module.required_minutes if module else None,
                        module.name if module else None,
                    ),
                    "is_past": block.date < reference_today,
                    "occurrence_status": "SUBSTITUTED",
                    "hours_given": None,
                    "occurrence_id": block.source_v1_lesson_log_id,
                    "occurrence_decided_at": source_log.decided_at,
                    "can_create_occurrence": False,
                    "can_decide_occurrence": False,
                    "lesson_log_id": block_log.id if block_log else None,
                    "lesson_log_status": block_log.status if block_log else None,
                    "lesson_log_summary": block_log.summary if block_log else None,
                    "lesson_log_notes": block_log.notes if block_log else None,
                    "lesson_log_logged_at": block_log.logged_at if block_log else None,
                    "week_timesheet_status": timesheet.status.value if timesheet else "OPEN",
                    "timesheet_id": timesheet.id if timesheet else None,
                    "is_substituted_block": True,
                    "credit_minutes": source_lesson.credit_minutes,
                    "slices": [],
                    "substitute_execution_status": block.execution_status.value,
                    "ends_at": source_lesson.ends_at,
                    "can_complete": can_complete,
                    "blocked_reason": blocked_reason,
                }
            )
        slots.sort(
            key=lambda row: (
                row["date"],
                row["timeslot"]["start_time"],
                row["operational_block_id"] or 0,
            )
        )
    return slots


def _slice_payload(
    slice_row: SchedulerLessonSliceV1, module: models.Module, completed: int
) -> dict:
    return {
        "module_id": module.id,
        "module_name": module.name,
        "offset_minutes": slice_row.offset_minutes,
        "minutes": slice_row.minutes,
        "completed_minutes": max(0, completed),
        "remaining_minutes": max(0, module.required_minutes - completed),
    }


async def _requirements_for_assignments(
    db: AsyncSession, organization_id: int, assignment_ids: Sequence[int]
) -> dict[int, list[ModuleRequirement]]:
    rows = (
        await db.execute(
            select(CurricularRequirement).where(
                CurricularRequirement.organization_id == organization_id,
                CurricularRequirement.assignment_id.in_(assignment_ids),
            )
        )
    ).scalars()
    requirements: dict[int, list[ModuleRequirement]] = defaultdict(list)
    for row in rows:
        requirements[row.assignment_id].append(
            ModuleRequirement(row.module_id, row.sequence, row.required_minutes)
        )
    for values in requirements.values():
        values.sort(key=lambda module: module.sequence)
    return requirements


@dataclass(frozen=True)
class LessonContext:
    lesson: SchedulerLessonV1
    year: models.SchedulerSchoolYear
    assignment: CurricularAssignment
    slices: tuple[SchedulerLessonSliceV1, ...]
    modules: dict[int, models.Module]


async def lesson_context(db: AsyncSession, organization_id: int, lesson_id: int) -> LessonContext:
    year, version = await _active_year_and_version(db, organization_id)
    if year is None or version is None:
        raise OperationsError(
            "scheduler_not_published",
            "Ainda não existe um horário publicado para registar aulas.",
            status_code=409,
        )
    lesson = await db.scalar(
        select(SchedulerLessonV1).where(
            SchedulerLessonV1.id == lesson_id,
            SchedulerLessonV1.organization_id == organization_id,
            SchedulerLessonV1.school_year_id == year.id,
            SchedulerLessonV1.version_id == version.id,
        )
    )
    if lesson is None:
        raise OperationsError("scheduler_lesson_not_found", "Aula não encontrada.", status_code=404)
    assignment = await db.scalar(
        select(CurricularAssignment).where(
            CurricularAssignment.id == lesson.assignment_id,
            CurricularAssignment.organization_id == organization_id,
        )
    )
    if assignment is None:
        raise OperationsError("scheduler_lesson_not_found", "Aula não encontrada.", status_code=404)
    slices = tuple(
        (
            await db.scalars(
                select(SchedulerLessonSliceV1)
                .where(
                    SchedulerLessonSliceV1.organization_id == organization_id,
                    SchedulerLessonSliceV1.lesson_id == lesson.id,
                )
                .order_by(SchedulerLessonSliceV1.offset_minutes)
            )
        ).all()
    )
    module_ids = {row.module_id for row in slices}
    modules = {
        row.id: row
        for row in (
            await db.scalars(
                select(models.Module).where(
                    models.Module.organization_id == organization_id,
                    models.Module.id.in_(module_ids),
                )
            )
        ).all()
    }
    return LessonContext(
        lesson=lesson, year=year, assignment=assignment, slices=slices, modules=modules
    )


async def assert_week_open(
    db: AsyncSession,
    organization_id: int,
    *,
    teacher_id: int | None,
    lesson_date: date,
) -> None:
    """Reject operations that would change a submitted or approved week."""
    if teacher_id is None:
        return
    week_start = lesson_date - timedelta(days=lesson_date.weekday())
    status = await db.scalar(
        select(models.TeacherWeeklyTimesheet.status).where(
            models.TeacherWeeklyTimesheet.organization_id == organization_id,
            models.TeacherWeeklyTimesheet.teacher_id == teacher_id,
            models.TeacherWeeklyTimesheet.week_start_date == week_start,
        )
    )
    if status in (models.TimesheetStatus.SUBMITTED, models.TimesheetStatus.APPROVED):
        raise OperationsError(
            "week_locked",
            "Esta semana já foi submetida ou aprovada. Não é possível alterar registos.",
            status_code=409,
        )


async def record_lesson_log(
    db: AsyncSession,
    organization_id: int,
    *,
    membership_id: int,
    lesson_id: int,
    status: str,
    summary: str | None,
    notes: str | None,
    now_utc: datetime,
    planning_relevant: bool = False,
    allow_decision_override: bool = False,
) -> dict:
    """Register or update one lesson log and move the v1 ledger accordingly."""
    if status not in ("COMPLETED", "OCCURRENCE"):
        raise OperationsError("invalid_lesson_log_status", "Estado de aula inválido.")
    context = await lesson_context(db, organization_id, lesson_id)
    if status == "COMPLETED" and not execution_allowed(now_utc, context.lesson.ends_at):
        raise OperationsError(
            "lesson_not_finished",
            "Só pode concluir esta aula depois do seu término.",
        )
    await assert_week_open(
        db,
        organization_id,
        teacher_id=context.assignment.teacher_id,
        lesson_date=context.lesson.school_date,
    )
    state = await db.scalar(
        select(models.SchedulerSchoolYearState)
        .where(
            models.SchedulerSchoolYearState.organization_id == organization_id,
            models.SchedulerSchoolYearState.school_year_id == context.year.id,
        )
        .with_for_update()
    )
    if state is None:
        raise OperationsError("scheduler_year_missing", "Ano letivo sem estado de planeamento.")
    log = await db.scalar(
        select(SchedulerLessonLogV1)
        .where(
            SchedulerLessonLogV1.organization_id == organization_id,
            SchedulerLessonLogV1.lesson_id == lesson_id,
        )
        .with_for_update()
    )
    previous_status = log.status if log is not None else None
    if (
        log is not None
        and log.status != "REVOKED"
        and log.decision is not None
        and status != log.status
        and not allow_decision_override
    ):
        raise OperationsError(
            "occurrence_active",
            "Esta aula tem uma ocorrência ativa. Gira a decisão em Faltas e Ocorrências.",
            status_code=409,
        )
    if (
        log is not None
        and log.status == status
        and (log.summary or None) == (summary or None)
        and (log.notes or None) == (notes or None)
    ):
        return {
            "lesson_id": lesson_id,
            "status": status,
            "credited_minutes": 0,
            "debt_minutes": 0,
            "revision": log.revision,
        }
    if log is not None and previous_status == "REVOKED" and status == "OCCURRENCE":
        # A new occurrence cycle starts; the revocation audit stays on the row.
        log.decision = None
        log.decided_at = None
        log.decided_by_membership_id = None
    revision = (log.revision + 1) if log is not None else 1
    credited = 0
    debt_minutes = 0
    if previous_status == "COMPLETED" and status != "COMPLETED":
        await reverse_lesson_execution(
            db, organization_id, context, membership_id=membership_id, now_utc=now_utc
        )
    if status == "COMPLETED" and previous_status != "COMPLETED":
        credits = tuple(ModuleCredit(row.module_id, row.minutes) for row in context.slices)
        if not credits:
            raise OperationsError(
                "lesson_without_slices",
                "A aula não tem minutos curriculares associados.",
            )
        entry = ExecutionEntry(
            LESSON_LOG_ORIGIN.format(lesson_id=lesson_id),
            revision,
            membership_id,
            (summary or "Aula registada").strip() or "Aula registada",
            credits,
            recorded_at=now_utc,
        )
        await record_execution(
            db,
            organization_id,
            context.year.id,
            context.assignment.id,
            entry,
            planning_relevant=planning_relevant,
        )
        credited = sum(credit.minutes for credit in credits)
    # A pending occurrence only signals a problem. Debt is created by the
    # direction decision, never by the registration itself.
    if log is None:
        db.add(
            SchedulerLessonLogV1(
                organization_id=organization_id,
                school_year_id=context.year.id,
                lesson_id=lesson_id,
                status=status,
                summary=summary,
                notes=notes,
                revision=revision,
                logged_by_membership_id=membership_id,
                logged_at=now_utc,
                created_at=now_utc,
                updated_at=now_utc,
            )
        )
    else:
        log.status = status
        log.summary = summary
        log.notes = notes
        log.revision = revision
        log.logged_by_membership_id = membership_id
        log.logged_at = now_utc
        log.updated_at = now_utc
    await db.flush()
    return {
        "lesson_id": lesson_id,
        "status": status,
        "credited_minutes": credited,
        "debt_minutes": debt_minutes,
        "revision": revision,
    }


async def lesson_lineage_ids(
    db: AsyncSession,
    organization_id: int,
    context: LessonContext,
) -> set[int]:
    # Publication moves the log while ledger entries retain their original lesson ID.
    # Older copies lost source links. Match only the same stable and physical
    # identity within this tenant, school year and curricular assignment.
    lineage = (
        select(SchedulerLessonV1.id, SchedulerLessonV1.source_lesson_id)
        .where(
            SchedulerLessonV1.organization_id == organization_id,
            SchedulerLessonV1.school_year_id == context.year.id,
            SchedulerLessonV1.assignment_id == context.assignment.id,
            SchedulerLessonV1.stable_key == context.lesson.stable_key,
            SchedulerLessonV1.starts_at == context.lesson.starts_at,
            SchedulerLessonV1.ends_at == context.lesson.ends_at,
        )
        .cte("lesson_lineage", recursive=True)
    )
    lineage = lineage.union(
        select(SchedulerLessonV1.id, SchedulerLessonV1.source_lesson_id)
        .join(lineage, SchedulerLessonV1.id == lineage.c.source_lesson_id)
        .where(
            SchedulerLessonV1.organization_id == organization_id,
            SchedulerLessonV1.school_year_id == context.year.id,
            SchedulerLessonV1.assignment_id == context.assignment.id,
        )
    )
    return set(await db.scalars(select(lineage.c.id)))


async def reverse_lesson_execution(
    db: AsyncSession,
    organization_id: int,
    context: LessonContext,
    *,
    membership_id: int,
    now_utc: datetime,
) -> None:
    entries = await load_execution_entries(db, organization_id, context.assignment.id)
    origins = {
        LESSON_LOG_ORIGIN.format(lesson_id=lesson_id)
        for lesson_id in await lesson_lineage_ids(db, organization_id, context)
    }
    source = next(
        (
            entry
            for entry in reversed(entries)
            if entry.origin in origins and entry.reversal_of is None
        ),
        None,
    )
    if source is None:
        return
    origin = source.origin
    # Reverse only the balance that is still credited per module. A partial
    # manual reduction must not hide the remaining credit of another module.
    reversed_by_module: dict[int, int] = defaultdict(int)
    for entry in entries:
        if entry.reversal_of != source.key:
            continue
        for credit in entry.credits:
            reversed_by_module[credit.module_id] += abs(credit.minutes)
    credits = tuple(
        ModuleCredit(credit.module_id, -(credit.minutes - reversed_by_module[credit.module_id]))
        for credit in source.credits
        if credit.minutes - reversed_by_module[credit.module_id] > 0
    )
    if not credits:
        return
    next_revision = (
        max((entry.revision for entry in entries if entry.origin == origin), default=0) + 1
    )
    await record_execution(
        db,
        organization_id,
        context.year.id,
        context.assignment.id,
        ExecutionEntry(
            origin,
            next_revision,
            membership_id,
            "Registo de aula revertido",
            credits,
            reversal_of=source.key,
            recorded_at=now_utc,
        ),
        planning_relevant=True,
    )


async def _reverse_origin_executions(
    db: AsyncSession,
    organization_id: int,
    school_year_id: int,
    assignment_id: int,
    *,
    origin: str,
    membership_id: int,
    reason: str,
    now_utc: datetime,
) -> None:
    """Append reversals for the remaining credit of one execution origin."""
    entries = await load_execution_entries(db, organization_id, assignment_id)
    reversed_by: dict[tuple[tuple[str, int], int], int] = defaultdict(int)
    for entry in entries:
        if entry.reversal_of is None:
            continue
        for credit in entry.credits:
            reversed_by[(entry.reversal_of, credit.module_id)] += abs(credit.minutes)
    next_revision = (
        max((entry.revision for entry in entries if entry.origin == origin), default=0) + 1
    )
    for entry in entries:
        if entry.origin != origin or entry.reversal_of is not None:
            continue
        credits = tuple(
            ModuleCredit(
                credit.module_id,
                -(credit.minutes - reversed_by.get((entry.key, credit.module_id), 0)),
            )
            for credit in entry.credits
            if credit.minutes - reversed_by.get((entry.key, credit.module_id), 0) > 0
        )
        if not credits:
            continue
        await record_execution(
            db,
            organization_id,
            school_year_id,
            assignment_id,
            ExecutionEntry(
                origin,
                next_revision,
                membership_id,
                reason,
                credits,
                reversal_of=entry.key,
                recorded_at=now_utc,
            ),
            planning_relevant=True,
        )
        next_revision += 1


async def record_operational_lesson_log(
    db: AsyncSession,
    organization_id: int,
    *,
    membership_id: int,
    operational_block_id: int,
    payload: schemas.LessonLogCreate,
    now_utc: datetime,
) -> models.LessonLog:
    """Register execution of a v1-origin substitute block in the v1 ledger."""
    block = await db.scalar(
        select(models.OperationalScheduleBlock)
        .where(
            models.OperationalScheduleBlock.id == operational_block_id,
            models.OperationalScheduleBlock.organization_id == organization_id,
            models.OperationalScheduleBlock.status == models.OperationalBlockStatus.ACTIVE,
        )
        .with_for_update()
    )
    if block is None:
        raise OperationsError(
            "operational_block_not_found", "Bloco operacional não encontrado.", status_code=404
        )
    if (
        block.origin_kind != models.OperationalBlockOrigin.V1
        or block.source_v1_lesson_log_id is None
        or block.substitute_curricular_assignment_id is None
    ):
        raise OperationsError(
            "operational_block_not_v1", "Bloco operacional não pertence ao horário v1."
        )
    status = payload.status.value if hasattr(payload.status, "value") else str(payload.status)
    if status == "OCCURRENCE":
        raise OperationsError(
            "operational_occurrence_unsupported",
            "Blocos operacionais não podem originar novas ocorrências.",
        )
    source_log = await db.scalar(
        select(SchedulerLessonLogV1).where(
            SchedulerLessonLogV1.id == block.source_v1_lesson_log_id,
            SchedulerLessonLogV1.organization_id == organization_id,
        )
    )
    lesson = (
        await db.get(SchedulerLessonV1, source_log.lesson_id) if source_log is not None else None
    )
    if lesson is None:
        raise OperationsError(
            "scheduler_lesson_not_found", "Aula de origem não encontrada.", status_code=404
        )
    if status == "COMPLETED" and not execution_allowed(now_utc, lesson.ends_at):
        raise OperationsError(
            "lesson_not_finished",
            "Só pode concluir esta aula depois do seu término.",
        )
    week_start = block.date - timedelta(days=block.date.weekday())
    timesheet = await db.scalar(
        select(models.TeacherWeeklyTimesheet).where(
            models.TeacherWeeklyTimesheet.organization_id == organization_id,
            models.TeacherWeeklyTimesheet.teacher_id == block.teacher_id,
            models.TeacherWeeklyTimesheet.week_start_date == week_start,
        )
    )
    if timesheet is not None and timesheet.status in (
        models.TimesheetStatus.SUBMITTED,
        models.TimesheetStatus.APPROVED,
    ):
        raise OperationsError(
            "week_locked",
            "Esta semana já foi submetida ou aprovada. Não é possível alterar registos.",
        )
    log = await db.scalar(
        select(models.LessonLog)
        .where(models.LessonLog.operational_block_id == operational_block_id)
        .with_for_update()
    )
    previous = log.status if log is not None else models.LessonLogStatus.PENDING
    current = models.LessonLogStatus(status)
    if log is None:
        log = models.LessonLog(
            organization_id=organization_id,
            operational_block_id=operational_block_id,
            status=current,
            summary=payload.summary,
            notes=payload.notes,
            logged_by_membership_id=membership_id,
            logged_at=now_utc,
            version=1,
        )
        db.add(log)
    else:
        log.version = int(log.version or 1) + 1
        log.status = current
        log.summary = payload.summary
        log.notes = payload.notes
        log.logged_by_membership_id = membership_id
        log.logged_at = now_utc
    await db.flush()
    if previous != current:
        assignment_id = block.substitute_curricular_assignment_id
        year_id = await db.scalar(
            select(CurricularAssignment.school_year_id).where(
                CurricularAssignment.id == assignment_id,
                CurricularAssignment.organization_id == organization_id,
            )
        )
        if year_id is None:
            raise OperationsError(
                "substitute_assignment_missing",
                "A disciplina substituta não tem ano letivo válido.",
            )
        origin = SUBSTITUTION_ORIGIN.format(
            occurrence_id=block.source_v1_lesson_log_id, teacher_id=block.teacher_id
        )
        if current == models.LessonLogStatus.COMPLETED:
            requirements = (
                await _requirements_for_assignments(db, organization_id, [assignment_id])
            ).get(assignment_id, [])
            if not requirements:
                raise OperationsError(
                    "substitute_without_requirements",
                    "A disciplina substituta não tem módulos configurados.",
                )
            executed = (await load_executed_minutes(db, organization_id, [assignment_id])).get(
                assignment_id, {}
            )
            try:
                credits = frontier_credit(requirements, executed, lesson.credit_minutes)
            except ValueError as exc:
                raise OperationsError(
                    "substitute_without_capacity",
                    "A disciplina substituta não tem minutos curriculares disponíveis.",
                ) from exc
            entries = await load_execution_entries(db, organization_id, assignment_id)
            revision = (
                max((entry.revision for entry in entries if entry.origin == origin), default=0) + 1
            )
            await record_execution(
                db,
                organization_id,
                year_id,
                assignment_id,
                ExecutionEntry(
                    origin,
                    revision,
                    membership_id,
                    "Aula substituta concluída",
                    credits,
                    recorded_at=now_utc,
                ),
                planning_relevant=True,
            )
            block.execution_status = models.OperationalBlockExecutionStatus.COMPLETED
        else:
            await _reverse_origin_executions(
                db,
                organization_id,
                year_id,
                assignment_id,
                origin=origin,
                membership_id=membership_id,
                reason="Aula substituta revertida",
                now_utc=now_utc,
            )
            block.execution_status = models.OperationalBlockExecutionStatus.PENDING_LOG
    await db.flush()
    await db.refresh(log)
    return log


async def adjust_class_progress(
    db: AsyncSession,
    organization_id: int,
    class_id: int,
    updates: Sequence[schemas.ClassProgressUpdate],
    *,
    membership_id: int,
    now_utc: datetime,
) -> bool:
    """Apply manual progress targets to the v1 ledger; ``False`` means no v1 data."""
    assignments = (
        await db.scalars(
            select(CurricularAssignment).where(
                CurricularAssignment.organization_id == organization_id,
                CurricularAssignment.class_id == class_id,
            )
        )
    ).all()
    if not assignments:
        return False
    year = await db.scalar(
        select(models.SchedulerSchoolYear).where(
            models.SchedulerSchoolYear.organization_id == organization_id,
            models.SchedulerSchoolYear.is_active.is_(True),
        )
    )
    if year is None:
        return False
    requirements = await _requirements_for_assignments(
        db, organization_id, [row.id for row in assignments]
    )
    module_owner: dict[int, int] = {}
    required_by_module: dict[int, int] = {}
    for assignment in assignments:
        for module in requirements.get(assignment.id, ()):
            module_owner[module.module_id] = assignment.id
            required_by_module[module.module_id] = module.required_minutes
    executed = await load_executed_minutes(db, organization_id, [row.id for row in assignments])
    for update in updates:
        assignment_id = module_owner.get(update.module_id)
        if assignment_id is None:
            raise OperationsError(
                "module_not_assigned",
                f"O módulo {update.module_id} não pertence a esta turma.",
                status_code=400,
            )
        required_minutes = required_by_module[update.module_id]
        target = int(round(min(max(update.hours_completed, 0.0), required_minutes / 60) * 60))
        current = int(executed.get(assignment_id, {}).get(update.module_id, 0))
        delta = target - current
        if delta == 0:
            continue
        if delta > 0:
            await record_execution(
                db,
                organization_id,
                year.id,
                assignment_id,
                ExecutionEntry(
                    f"manual-adjust:{uuid4()}",
                    1,
                    membership_id,
                    "Acerto manual de progresso",
                    (ModuleCredit(update.module_id, delta),),
                    recorded_at=now_utc,
                ),
                planning_relevant=True,
            )
        else:
            await _record_manual_reduction(
                db,
                organization_id,
                year.id,
                assignment_id,
                update.module_id,
                -delta,
                membership_id=membership_id,
                now_utc=now_utc,
            )
    return True


async def _record_manual_reduction(
    db: AsyncSession,
    organization_id: int,
    school_year_id: int,
    assignment_id: int,
    module_id: int,
    minutes: int,
    *,
    membership_id: int,
    now_utc: datetime,
) -> None:
    """Reverse the newest positive credits for one module, never inventing offsets."""
    entries = await load_execution_entries(db, organization_id, assignment_id)
    reversed_by_module: dict[tuple[tuple[str, int], int], int] = defaultdict(int)
    for entry in entries:
        if entry.reversal_of is not None:
            for credit in entry.credits:
                reversed_by_module[(entry.reversal_of, credit.module_id)] += abs(credit.minutes)
    remaining = minutes
    origin = f"manual-adjust:{uuid4()}"
    revision = 1
    for entry in reversed(entries):
        if remaining <= 0:
            break
        if entry.reversal_of is not None:
            continue
        credit = next(
            (
                row.minutes
                for row in entry.credits
                if row.module_id == module_id and row.minutes > 0
            ),
            None,
        )
        if credit is None:
            continue
        available = credit - reversed_by_module.get((entry.key, module_id), 0)
        if available <= 0:
            continue
        taken = min(remaining, available)
        await record_execution(
            db,
            organization_id,
            school_year_id,
            assignment_id,
            ExecutionEntry(
                origin,
                revision,
                membership_id,
                "Acerto manual de progresso",
                (ModuleCredit(module_id, -taken),),
                reversal_of=entry.key,
                recorded_at=now_utc,
            ),
            planning_relevant=True,
        )
        remaining -= taken
        revision += 1
    if remaining > 0:
        raise OperationsError(
            "progress_below_recorded",
            "Não é possível reduzir progresso abaixo do que está registado.",
        )


async def class_progress_map(
    db: AsyncSession,
    organization_id: int,
    class_id: int,
) -> dict[int, tuple[int, int]] | None:
    """Completed and open-debt minutes per module for one class, or ``None``."""
    assignments = (
        await db.scalars(
            select(CurricularAssignment).where(
                CurricularAssignment.organization_id == organization_id,
                CurricularAssignment.class_id == class_id,
            )
        )
    ).all()
    if not assignments:
        return None
    assignment_ids = [row.id for row in assignments]
    executed = await load_executed_minutes(db, organization_id, assignment_ids)
    open_debt, claim_assignments = await load_open_debt(db, organization_id, assignment_ids)
    requirements = await _requirements_for_assignments(db, organization_id, assignment_ids)
    assignment_for_claim = claim_assignments
    debt_by_module: dict[int, int] = defaultdict(int)
    for claim_id, minutes in open_debt.items():
        assignment_id = assignment_for_claim.get(claim_id)
        if assignment_id is None:
            continue
        modules = requirements.get(assignment_id, [])
        completed = executed.get(assignment_id, {})
        target = next(
            (
                module
                for module in modules
                if completed.get(module.module_id, 0) < module.required_minutes
            ),
            modules[-1] if modules else None,
        )
        if target is not None:
            debt_by_module[target.module_id] += minutes
    progress: dict[int, tuple[int, int]] = {}
    for assignment_id, modules in requirements.items():
        completed = executed.get(assignment_id, {})
        for module in modules:
            progress[module.module_id] = (
                int(completed.get(module.module_id, 0)),
                int(debt_by_module.get(module.module_id, 0)),
            )
    return progress
