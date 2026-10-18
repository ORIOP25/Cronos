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
from app.scheduler.domain.demand import (
    ExecutionEntry,
    ModuleCredit,
    frontier_credit,
    joint_frontier_credit,
)
from app.scheduler.domain.lesson_time import execution_allowed
from app.scheduler.domain.projection import ModuleRequirement
from app.scheduler.infrastructure.models import (
    CurricularAssignment,
    CurricularRequirement,
    SchedulerLessonLogV1,
    SchedulerLessonSliceV1,
    SchedulerLessonV1,
    SchedulerProposalV1,
    SchedulerVersionV1,
)
from app.scheduler.infrastructure.progress import (
    load_executed_minutes,
    load_execution_entries,
    load_open_debt,
    load_planning_requirements,
    reconcile_assignment_requirements,
    record_execution,
)

LESSON_LOG_ORIGIN = "lesson-log:{lesson_id}"
LESSON_OCCURRENCE_ORIGIN = "lesson-occurrence:{lesson_id}"
SUBSTITUTION_ORIGIN = "substitution:{occurrence_id}:{teacher_id}"
SUBSTITUTION_LIKE = "substitution:{occurrence_id}:%"
# Note stored on the occurrence of a class that missed a joint lesson (J12).
JOINT_ABSENT_NOTE = "Turma ausente"
# Block reason of every slot in a pending proposal preview (read-only).
PROPOSAL_PREVIEW_BLOCK = "proposal_preview"


class OperationsError(ValueError):
    """A school operation cannot be applied to the current v1 state."""

    def __init__(self, code: str, message: str, *, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class ProposalPreviewNotFound(LookupError):
    """The proposal cannot be previewed: unknown, not pending, or outside the active year."""


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


async def _proposal_preview_version_id(
    db: AsyncSession,
    organization_id: int,
    year: models.SchedulerSchoolYear | None,
    proposal_id: int,
) -> int:
    """Candidate version of a pending proposal in the active school year."""
    version_id = None
    if year is not None:
        version_id = await db.scalar(
            select(SchedulerProposalV1.version_id).where(
                SchedulerProposalV1.organization_id == organization_id,
                SchedulerProposalV1.school_year_id == year.id,
                SchedulerProposalV1.id == proposal_id,
                SchedulerProposalV1.status == "PENDING",
            )
        )
    if version_id is None:
        raise ProposalPreviewNotFound(proposal_id)
    return version_id


def _as_proposal_preview(slot: dict) -> dict:
    """A proposal slot is read-only: it cannot be completed or receive an occurrence."""
    return {
        **slot,
        "can_complete": False,
        "blocked_reason": PROPOSAL_PREVIEW_BLOCK,
        "can_create_occurrence": False,
    }


def local_times(lesson: SchedulerLessonV1, zone: ZoneInfo) -> tuple[time, time]:
    start = lesson.starts_at.astimezone(zone)
    end = lesson.ends_at.astimezone(zone)
    return time(start.hour, start.minute), time(end.hour, end.minute)


def _week_log_states(log: SchedulerLessonLogV1 | None) -> tuple[str | None, str | None]:
    if log is None:
        return None, None
    if log.status == "REVOKED":
        return "REVOKED", "PENDING"
    return log.decision or "PENDING", log.status


def _module_summary(
    module_id: int | None, required_minutes: int | None, name: str | None
) -> dict | None:
    if module_id is None or required_minutes is None or name is None:
        return None
    return {"id": module_id, "name": name, "hours_total": required_minutes / 60}


async def _joint_group_members(
    db: AsyncSession,
    organization_id: int,
    year_id: int,
    version_id: int,
    stable_keys: set[str],
) -> dict[str, list[dict]]:
    """Member classes of every joint lesson in the given stable keys (J17).

    A stable key with a single member is a plain lesson. A key with several
    members is a joint lesson; each member carries its class and its log so the
    weekly view can show the presence state of every class.
    """
    if not stable_keys:
        return {}
    result_rows = (
        await db.execute(
            select(SchedulerLessonV1, models.Class.id, models.Class.name, SchedulerLessonLogV1)
            .join(
                CurricularAssignment,
                and_(
                    CurricularAssignment.organization_id == SchedulerLessonV1.organization_id,
                    CurricularAssignment.school_year_id == SchedulerLessonV1.school_year_id,
                    CurricularAssignment.id == SchedulerLessonV1.assignment_id,
                ),
            )
            .join(
                models.Class,
                and_(
                    models.Class.organization_id == organization_id,
                    models.Class.id == CurricularAssignment.class_id,
                ),
            )
            .outerjoin(
                SchedulerLessonLogV1,
                and_(
                    SchedulerLessonLogV1.organization_id == organization_id,
                    SchedulerLessonLogV1.lesson_id == SchedulerLessonV1.id,
                ),
            )
            .where(
                SchedulerLessonV1.organization_id == organization_id,
                SchedulerLessonV1.school_year_id == year_id,
                SchedulerLessonV1.version_id == version_id,
                SchedulerLessonV1.stable_key.in_(stable_keys),
            )
            .order_by(SchedulerLessonV1.id)
        )
    ).all()
    groups: dict[str, list[dict]] = defaultdict(list)
    for lesson, class_id, class_name, log in result_rows:
        groups[lesson.stable_key].append(
            {
                "class_id": class_id,
                "class_name": class_name,
                "lesson_id": lesson.id,
                "log": log,
            }
        )
    return groups


async def week_schedule(
    db: AsyncSession,
    organization_id: int,
    *,
    week_start: date,
    class_id: int | None,
    teacher_id: int | None,
    today: date | None = None,
    now_utc: datetime | None = None,
    proposal_id: int | None = None,
) -> list[dict] | None:
    """Published v1 lessons of one week with their modular slices.

    With ``proposal_id`` the lessons come from that pending proposal's candidate
    version, read-only, and operational substitution blocks are left out.

    Returns ``None`` when no v1 version is active so the caller can keep the
    legacy operational view during the transition.
    """
    year, active_version = await _active_year_and_version(db, organization_id)
    is_preview = proposal_id is not None
    if is_preview:
        version_id = await _proposal_preview_version_id(db, organization_id, year, proposal_id)
    elif year is None or active_version is None:
        return None
    else:
        version_id = active_version.id
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
            SchedulerLessonV1.version_id == version_id,
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
    withdrawn = select(SchedulerLessonLogV1.lesson_id).where(
        SchedulerLessonLogV1.organization_id == organization_id,
        SchedulerLessonLogV1.withdrawn_at.is_not(None),
    )
    lessons_query = lessons_query.where(SchedulerLessonV1.id.not_in(withdrawn))
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
    block_models = [] if is_preview else (await db.scalars(block_query)).all()
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
    # Every member block of the displayed joint substitutions, including the
    # cancelled ones, so the weekly metadata carries each class's block (J18).
    member_block_by_class: dict[tuple[str, int], tuple] = {}
    if block_rows:
        member_block_rows = (
            await db.execute(
                select(models.OperationalScheduleBlock, SchedulerLessonV1, models.LessonLog)
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
                .outerjoin(
                    models.LessonLog,
                    and_(
                        models.LessonLog.organization_id == organization_id,
                        models.LessonLog.operational_block_id == models.OperationalScheduleBlock.id,
                    ),
                )
                .where(
                    models.OperationalScheduleBlock.organization_id == organization_id,
                    models.OperationalScheduleBlock.origin_kind == models.OperationalBlockOrigin.V1,
                    SchedulerLessonV1.version_id == version_id,
                    SchedulerLessonV1.stable_key.in_({row[1].stable_key for row in block_rows}),
                )
            )
        ).all()
        for member_block, member_lesson, member_log in member_block_rows:
            member_block_by_class[(member_lesson.stable_key, member_block.class_id)] = (
                member_block,
                member_log,
            )
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
    joint_members = await _joint_group_members(
        db,
        organization_id,
        year.id,
        version_id,
        {row[0].stable_key for row in rows} | {row[1].stable_key for row in block_rows},
    )
    joint_keys = {key for key, members in joint_members.items() if len(members) > 1}
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

    def _planned_week_slot(row):
        (lesson, _assignment, subject, teacher, class_model, room) = row
        start_local, end_local = local_times(lesson, zone)
        position = slices_by_lesson.get(lesson.id, [])
        module_id = position[0][1].id if position else None
        module_minutes = position[0][1].required_minutes if position else None
        log = logs.get(lesson.id)
        occurrence_status, lesson_log_status = _week_log_states(log)
        members = joint_members.get(lesson.stable_key, [])
        joint_classes: list[dict] = []
        class_infos: list[dict] = []
        if len(members) > 1:
            for member in members:
                if member["class_id"] != class_model.id:
                    joint_classes.append({"id": member["class_id"], "name": member["class_name"]})
                member_log = member["log"]
                class_infos.append(
                    {
                        "id": member["class_id"],
                        "name": member["class_name"],
                        "lesson_log_status": (
                            None
                            if member_log is None or member_log.status == "REVOKED"
                            else member_log.status
                        ),
                        "lesson_db_id": member["lesson_id"],
                    }
                )
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
        return {
            "scheduler_lesson_id": lesson.id,
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
            "occurrence_status": occurrence_status,
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
            "lesson_log_status": lesson_log_status,
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
            # WBS 5.7 (J17): joint view metadata.
            "joint_classes": joint_classes,
            "class_infos": class_infos,
            "_stable_key": lesson.stable_key,
        }

    slots.extend(_planned_week_slot(row) for row in rows if row[0].id not in hidden_lesson_ids)
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

        def _operational_week_slot(row):
            (block, source_lesson, source_log, subject, teacher, class_model, room, module) = row
            local_start, local_end = local_times(source_lesson, zone)
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
            members = joint_members.get(source_lesson.stable_key, [])
            joint_classes: list[dict] = []
            class_infos: list[dict] = []
            if len(members) > 1:
                for member in members:
                    if member["class_id"] != class_model.id:
                        joint_classes.append(
                            {"id": member["class_id"], "name": member["class_name"]}
                        )
                    member_entry = member_block_by_class.get(
                        (source_lesson.stable_key, member["class_id"])
                    )
                    member_block = member_entry[0] if member_entry is not None else None
                    member_log = member_entry[1] if member_entry is not None else None
                    class_infos.append(
                        {
                            "id": member["class_id"],
                            "name": member["class_name"],
                            "lesson_log_status": (
                                None
                                if member_log is None or member_log.status.value == "PENDING"
                                else member_log.status
                            ),
                            "lesson_db_id": member["lesson_id"],
                            "operational_block_id": member_block.id if member_block else None,
                            "substitute_execution_status": (
                                member_block.execution_status.value if member_block else None
                            ),
                        }
                    )
            return {
                "scheduler_lesson_id": None,
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
                # WBS 5.3.4/5.7: joint substitute metadata for the modal/teacher view.
                "joint_classes": joint_classes,
                "class_infos": class_infos,
                "_stable_key": source_lesson.stable_key,
            }

        slots.extend(_operational_week_slot(row) for row in block_rows)
        slots.sort(
            key=lambda row: (
                row["date"],
                row["timeslot"]["start_time"],
                row["operational_block_id"] or 0,
            )
        )
    # Teacher view: a joint lesson is one block, not one per member class (J17).
    if class_id is None and teacher_id is not None:
        seen: set[str] = set()
        deduped: list[dict] = []
        for slot in slots:
            key = slot.get("_stable_key")
            if key is not None and key in joint_keys:
                if key in seen:
                    continue
                seen.add(key)
            deduped.append(slot)
        slots = deduped
    for slot in slots:
        slot.pop("_stable_key", None)
    if is_preview:
        return [_as_proposal_preview(slot) for slot in slots]
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


async def _planning_slice_credits(
    db: AsyncSession,
    organization_id: int,
    assignment_id: int,
    slices: Sequence[SchedulerLessonSliceV1],
) -> tuple[ModuleCredit, ...]:
    """Credit a completed lesson, redirecting retired or removed modules.

    The lesson keeps its stored slices while every referenced module is still
    planned with capacity. When a slice points to a retired module, closed at
    its executed minutes, or to a module that left the selection, its minutes
    move to the planning frontier so the next selected module earns them.
    """
    planning, executed = await load_planning_requirements(db, organization_id, [assignment_id])
    modules = planning.get(assignment_id, ())
    completed = executed.get(assignment_id, {})
    by_module = {module.module_id: module for module in modules}
    stored_fit = True
    for row in slices:
        module = by_module.get(row.module_id)
        if (
            module is None
            or completed.get(row.module_id, 0) + row.minutes > module.required_minutes
        ):
            stored_fit = False
            break
    if stored_fit:
        return tuple(ModuleCredit(row.module_id, row.minutes) for row in slices)
    try:
        return frontier_credit(modules, completed, sum(row.minutes for row in slices))
    except ValueError as exc:
        raise OperationsError(
            "lesson_without_slices",
            "A aula não tem minutos curriculares disponíveis para creditar.",
        ) from exc


async def lock_school_year_state(
    db: AsyncSession, organization_id: int, school_year_id: int
) -> None:
    """Lock the school-year state row first, the repository-wide lock order.

    Every schedule mutator takes this lock before any mutable log or block row,
    so ``state -> logs`` holds for all of them. That single ordered lock is what
    keeps the operation transactions atomic without locking the immutable
    published lesson rows, which the runtime role may not update.
    """
    state = await db.scalar(
        select(models.SchedulerSchoolYearState)
        .where(
            models.SchedulerSchoolYearState.organization_id == organization_id,
            models.SchedulerSchoolYearState.school_year_id == school_year_id,
        )
        .with_for_update()
    )
    if state is None:
        raise OperationsError("scheduler_year_missing", "Ano letivo sem estado de planeamento.")


async def lesson_siblings(
    db: AsyncSession, organization_id: int, lesson: SchedulerLessonV1
) -> tuple[SchedulerLessonV1, ...]:
    """Every row of one logical lesson (the siblings of a joint lesson), by id.

    A lesson without a joint group returns just its own row. The rows share the
    stable key, date, teacher, room, interval, credit and slices (J12).

    The published lesson rows are immutable after publication and the runtime
    role holds only ``SELECT, INSERT`` on them, so this read is never locked.
    Concurrency is serialized by the school-year state lock and the mutable
    ``scheduler_lesson_log_v1`` rows, which are locked ``FOR UPDATE`` by ``id``.
    """
    rows = (
        await db.scalars(
            select(SchedulerLessonV1)
            .where(
                SchedulerLessonV1.organization_id == organization_id,
                SchedulerLessonV1.school_year_id == lesson.school_year_id,
                SchedulerLessonV1.version_id == lesson.version_id,
                SchedulerLessonV1.stable_key == lesson.stable_key,
            )
            .order_by(SchedulerLessonV1.id)
        )
    ).all()
    return tuple(rows)


async def _assignments_by_ids(
    db: AsyncSession, organization_id: int, assignment_ids: Sequence[int]
) -> dict[int, CurricularAssignment]:
    identifiers = sorted(set(assignment_ids))
    if not identifiers:
        return {}
    rows = (
        await db.scalars(
            select(CurricularAssignment).where(
                CurricularAssignment.organization_id == organization_id,
                CurricularAssignment.id.in_(identifiers),
            )
        )
    ).all()
    return {row.id: row for row in rows}


def _resolve_absent_classes(
    absent_class_ids: Sequence[int], class_ids: Sequence[int], *, joint: bool
) -> frozenset[int]:
    """Validate the present/absent split of a joint lesson registration (J12).

    An empty list keeps every class present. A non-empty list is only valid on
    a joint lesson, never names an unknown class, and never covers every class:
    registering that nobody attended is ``422`` and asks for an occurrence.
    """
    ordered = tuple(dict.fromkeys(absent_class_ids))
    if not ordered:
        return frozenset()
    if not joint:
        raise OperationsError(
            "absent_classes_not_joint",
            "Só uma aula conjunta pode ter turmas ausentes.",
        )
    known = set(class_ids)
    if any(class_id not in known for class_id in ordered):
        raise OperationsError("absent_class_unknown", "A turma ausente não pertence a esta aula.")
    if set(ordered) == known:
        raise OperationsError(
            "absent_classes_all",
            "Pelo menos uma turma tem de estar presente. Registe uma ocorrência.",
        )
    return frozenset(ordered)


def _ensure_log_writable(
    log: SchedulerLessonLogV1 | None, status: str, *, allow_decision_override: bool
) -> None:
    """Reject a conflicting active decision before any sibling ledger write."""
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


async def _completion_credits(
    db: AsyncSession,
    organization_id: int,
    *,
    siblings: Sequence[SchedulerLessonV1],
    sibling_contexts: dict[int, LessonContext],
    class_by_lesson: dict[int, int],
    present_classes: set[int],
) -> dict[int, tuple[ModuleCredit, ...]]:
    """Credits for the present classes when a lesson is completed (D07).

    The published slices are exact while every slice module is still in the
    planning view. When a module was deselected after publication, the credit
    follows the planning frontier instead: a joint lesson credits the joint
    progress once, identically for every present class, while a deficit (``D``)
    lesson keeps its per-class frontier. Already logged credits are untouched.
    """
    present_rows = [row for row in siblings if class_by_lesson[row.id] in present_classes]
    if not present_rows:
        return {}
    assignment_ids = [sibling_contexts[row.id].assignment.id for row in present_rows]
    planning, executed = await load_planning_requirements(db, organization_id, assignment_ids)
    outdated = False
    for row in present_rows:
        context = sibling_contexts[row.id]
        required = {
            module.module_id: module.required_minutes
            for module in planning.get(context.assignment.id, ())
        }
        if any(
            slice_.module_id not in required
            or slice_.offset_minutes + slice_.minutes > required[slice_.module_id]
            for slice_ in context.slices
        ):
            outdated = True
            break
    if not outdated:
        return {
            row.id: tuple(
                ModuleCredit(slice_.module_id, slice_.minutes)
                for slice_ in sibling_contexts[row.id].slices
            )
            for row in present_rows
        }
    credits: dict[int, tuple[ModuleCredit, ...]] = {}
    lesson = present_rows[0]
    deficit = (lesson.teaching_unit_key or "").startswith("D:")
    try:
        if len(siblings) > 1 and not deficit:
            modules: tuple[ModuleRequirement, ...] = ()
            for row in present_rows:
                modules = planning.get(sibling_contexts[row.id].assignment.id, ())
                if modules:
                    break
            completed_by_class = {
                sibling_contexts[row.id].assignment.id: executed.get(
                    sibling_contexts[row.id].assignment.id, {}
                )
                for row in siblings
            }
            joint_credits = joint_frontier_credit(
                modules, completed_by_class, lesson.credit_minutes
            )
            return {row.id: joint_credits for row in present_rows}
        for row in present_rows:
            context = sibling_contexts[row.id]
            credits[row.id] = frontier_credit(
                planning.get(context.assignment.id, ()),
                executed.get(context.assignment.id, {}),
                sum(slice_.minutes for slice_ in context.slices),
            )
    except ValueError as exc:
        raise OperationsError(
            "lesson_without_slices",
            "A aula não tem minutos curriculares disponíveis para creditar.",
        ) from exc
    return credits


async def _apply_lesson_log(
    db: AsyncSession,
    organization_id: int,
    *,
    context: LessonContext,
    log: SchedulerLessonLogV1 | None,
    membership_id: int,
    status: str,
    summary: str | None,
    notes: str | None,
    now_utc: datetime,
    planning_relevant: bool,
    allow_decision_override: bool,
    execution_credits: tuple[ModuleCredit, ...] | None = None,
) -> tuple[int, int]:
    """Apply one lesson log and move only that class's ledger.

    Returns ``(credited_minutes, revision)``. A correction reverses or credits
    only the class that changed, so the ledger stays append-only (J12).
    """
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
        return 0, log.revision
    if log is not None and previous_status == "REVOKED" and status == "OCCURRENCE":
        # A new occurrence cycle starts; the revocation audit stays on the row.
        log.decision = None
        log.decided_at = None
        log.decided_by_membership_id = None
    revision = (log.revision + 1) if log is not None else 1
    credited = 0
    if previous_status == "COMPLETED" and status != "COMPLETED":
        await reverse_lesson_execution(
            db, organization_id, context, membership_id=membership_id, now_utc=now_utc
        )
    if status == "COMPLETED" and previous_status != "COMPLETED":
        credits = (
            execution_credits
            if execution_credits is not None
            else await _planning_slice_credits(
                db, organization_id, context.assignment.id, context.slices
            )
        )
        if not credits:
            raise OperationsError(
                "lesson_without_slices",
                "A aula não tem minutos curriculares associados.",
            )
        entry = ExecutionEntry(
            LESSON_LOG_ORIGIN.format(lesson_id=context.lesson.id),
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
                lesson_id=context.lesson.id,
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
    return credited, revision


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
    absent_class_ids: Sequence[int] = (),
    include_siblings: bool = True,
) -> dict:
    """Register a lesson and move the v1 ledger of every sibling class.

    ``lesson_id`` may be any sibling of a joint lesson. ``absent_class_ids``
    marks the classes that did not attend when the lesson was given: they stay
    as pending occurrences without a summary, while the present classes share
    the same summary and notes. The full sibling set is locked by ``id`` and
    every write happens in one transaction (J12). ``include_siblings=False``
    applies the log to the given lesson only, which the occurrence decision
    uses to complete a single member class.
    """
    if status not in ("COMPLETED", "OCCURRENCE"):
        raise OperationsError("invalid_lesson_log_status", "Estado de aula inválido.")
    primary = await lesson_context(db, organization_id, lesson_id)
    # Repository lock order: the school-year state row first.
    await lock_school_year_state(db, organization_id, primary.year.id)
    siblings = (
        await lesson_siblings(db, organization_id, primary.lesson)
        if include_siblings
        else (primary.lesson,)
    )
    assignments = await _assignments_by_ids(
        db, organization_id, [row.assignment_id for row in siblings]
    )
    if any(row.assignment_id not in assignments for row in siblings):
        raise OperationsError("scheduler_lesson_not_found", "Aula não encontrada.", status_code=404)
    class_by_lesson = {row.id: assignments[row.assignment_id].class_id for row in siblings}
    class_ids = sorted(set(class_by_lesson.values()))
    absent = _resolve_absent_classes(absent_class_ids, class_ids, joint=len(siblings) > 1)
    if absent and status != "COMPLETED":
        raise OperationsError(
            "absent_classes_require_completed",
            "As turmas ausentes só se aplicam ao registo da aula dada.",
        )
    # Lock every sibling log by ``id`` and refresh their facts.
    logs = (
        await db.scalars(
            select(SchedulerLessonLogV1)
            .where(
                SchedulerLessonLogV1.organization_id == organization_id,
                SchedulerLessonLogV1.lesson_id.in_([row.id for row in siblings]),
            )
            .order_by(SchedulerLessonLogV1.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).all()
    logs_by_lesson = {row.lesson_id: row for row in logs}
    # Validate every sibling before any ledger write.
    if any(row.withdrawn_at is not None for row in logs):
        raise OperationsError(
            "lesson_withdrawn", "A aula foi retirada por fluxo de estágio.", status_code=409
        )
    if status == "COMPLETED":
        for row in siblings:
            if class_by_lesson[row.id] in absent:
                continue
            if not execution_allowed(now_utc, row.ends_at):
                raise OperationsError(
                    "lesson_not_finished",
                    "Só pode concluir esta aula depois do seu término.",
                )
    for teacher_id in sorted({assignments[row.assignment_id].teacher_id for row in siblings}):
        await assert_week_open(
            db,
            organization_id,
            teacher_id=teacher_id,
            lesson_date=primary.lesson.school_date,
        )
    for row in siblings:
        target_status = "OCCURRENCE" if class_by_lesson[row.id] in absent else status
        _ensure_log_writable(
            logs_by_lesson.get(row.id),
            target_status,
            allow_decision_override=allow_decision_override,
        )
    sibling_contexts: dict[int, LessonContext] = {}
    for row in siblings:
        sibling_contexts[row.id] = (
            primary
            if row.id == primary.lesson.id
            else await lesson_context(db, organization_id, row.id)
        )
    credits_by_lesson: dict[int, tuple[ModuleCredit, ...]] = {}
    if status == "COMPLETED":
        present_classes = {class_id for class_id in class_ids if class_id not in absent}
        needs_credit = any(
            class_by_lesson[row.id] in present_classes
            and (logs_by_lesson.get(row.id) is None or logs_by_lesson[row.id].status != "COMPLETED")
            for row in siblings
        )
        if needs_credit:
            credits_by_lesson = await _completion_credits(
                db,
                organization_id,
                siblings=siblings,
                sibling_contexts=sibling_contexts,
                class_by_lesson=class_by_lesson,
                present_classes=present_classes,
            )
    classes_payload: list[dict] = []
    revision = 1
    primary_credited = 0
    for row in siblings:
        class_id = class_by_lesson[row.id]
        if class_id in absent:
            target_status, target_summary, target_notes = "OCCURRENCE", None, JOINT_ABSENT_NOTE
        else:
            target_status, target_summary, target_notes = status, summary, notes
        credited, revision = await _apply_lesson_log(
            db,
            organization_id,
            context=sibling_contexts[row.id],
            log=logs_by_lesson.get(row.id),
            membership_id=membership_id,
            status=target_status,
            summary=target_summary,
            notes=target_notes,
            now_utc=now_utc,
            planning_relevant=planning_relevant or target_status == "OCCURRENCE",
            allow_decision_override=allow_decision_override,
            execution_credits=credits_by_lesson.get(row.id),
        )
        if row.id == primary.lesson.id:
            primary_credited = credited
        classes_payload.append(
            {
                "class_id": class_id,
                "status": target_status,
                "credited_minutes": credited,
            }
        )
    await db.flush()
    # The top-level total is the primary lesson's credited minutes; ``classes``
    # keeps the per-class ledger detail of a joint lesson.
    return {
        "lesson_id": lesson_id,
        "status": status,
        "credited_minutes": primary_credited,
        "debt_minutes": 0,
        "revision": revision,
        "classes": classes_payload,
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
    execution_credits = tuple(
        ModuleCredit(credit.module_id, -(credit.minutes - reversed_by_module[credit.module_id]))
        for credit in source.credits
        if credit.minutes - reversed_by_module[credit.module_id] > 0
    )
    if not execution_credits:
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
            execution_credits,
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
        execution_credits = tuple(
            ModuleCredit(
                credit.module_id,
                -(credit.minutes - reversed_by.get((entry.key, credit.module_id), 0)),
            )
            for credit in entry.credits
            if credit.minutes - reversed_by.get((entry.key, credit.module_id), 0) > 0
        )
        if not execution_credits:
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
                execution_credits,
                reversal_of=entry.key,
                recorded_at=now_utc,
            ),
            planning_relevant=True,
        )
        next_revision += 1


async def _joint_substitute_blocks(
    db: AsyncSession, organization_id: int, lesson: SchedulerLessonV1
) -> list[models.OperationalScheduleBlock]:
    """Active substitute blocks of every sibling of one logical lesson (J14)."""
    sibling_lesson_ids = select(SchedulerLessonV1.id).where(
        SchedulerLessonV1.organization_id == organization_id,
        SchedulerLessonV1.version_id == lesson.version_id,
        SchedulerLessonV1.stable_key == lesson.stable_key,
    )
    log_ids = list(
        await db.scalars(
            select(SchedulerLessonLogV1.id).where(
                SchedulerLessonLogV1.organization_id == organization_id,
                SchedulerLessonLogV1.lesson_id.in_(sibling_lesson_ids),
            )
        )
    )
    if not log_ids:
        return []
    rows = await db.scalars(
        select(models.OperationalScheduleBlock)
        .where(
            models.OperationalScheduleBlock.organization_id == organization_id,
            models.OperationalScheduleBlock.source_v1_lesson_log_id.in_(log_ids),
            models.OperationalScheduleBlock.status == models.OperationalBlockStatus.ACTIVE,
        )
        .order_by(models.OperationalScheduleBlock.class_id)
        .with_for_update()
    )
    return list(rows)


async def _upsert_block_log(
    db: AsyncSession,
    organization_id: int,
    block_id: int,
    payload: schemas.LessonLogCreate,
    membership_id: int,
    now_utc: datetime,
) -> models.LessonLog:
    log = await db.scalar(
        select(models.LessonLog)
        .where(models.LessonLog.operational_block_id == block_id)
        .with_for_update()
    )
    current = models.LessonLogStatus(
        payload.status.value if hasattr(payload.status, "value") else str(payload.status)
    )
    if log is None:
        log = models.LessonLog(
            organization_id=organization_id,
            operational_block_id=block_id,
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
    return log


async def _complete_joint_substitution(
    db: AsyncSession,
    organization_id: int,
    *,
    block: models.OperationalScheduleBlock,
    joint_blocks: list[models.OperationalScheduleBlock],
    payload: schemas.LessonLogCreate,
    membership_id: int,
    now_utc: datetime,
    lesson: SchedulerLessonV1,
) -> models.LessonLog:
    """Conclude a joint substitution: every present class shares the credit (J14).

    Completing any block concludes the whole joint substitution. An absent
    member class keeps its block cancelled and receives no credit. Every present
    class receives the same credit over the joint progress, never duplicated.
    """
    class_ids = [row.class_id for row in joint_blocks]
    absent = _resolve_absent_classes(payload.absent_class_ids, class_ids, joint=True)
    if block.class_id in absent:
        raise OperationsError(
            "absent_class_cannot_complete",
            "A turma do bloco indicado está ausente. Conclua a partir de uma turma presente.",
        )
    present = [row for row in joint_blocks if row.class_id not in absent]
    absent_blocks = [row for row in joint_blocks if row.class_id in absent]
    assignment_ids = [row.substitute_curricular_assignment_id for row in present]
    requirements, executed_by_assignment = await load_planning_requirements(
        db, organization_id, assignment_ids
    )
    modules = next(
        (
            requirements.get(assignment_id, ())
            for assignment_id in assignment_ids
            if requirements.get(assignment_id)
        ),
        (),
    )
    if not modules:
        raise OperationsError(
            "substitute_without_requirements",
            "A disciplina substituta não tem módulos configurados.",
        )
    completed_by_class = {
        assignment_id: executed_by_assignment.get(assignment_id, {})
        for assignment_id in assignment_ids
    }
    try:
        execution_credits = joint_frontier_credit(
            modules, completed_by_class, lesson.credit_minutes
        )
    except ValueError as exc:
        raise OperationsError(
            "substitute_without_capacity",
            "A disciplina substituta não tem minutos curriculares disponíveis.",
        ) from exc
    year_id = await db.scalar(
        select(CurricularAssignment.school_year_id).where(
            CurricularAssignment.id == assignment_ids[0],
            CurricularAssignment.organization_id == organization_id,
        )
    )
    result_log: models.LessonLog | None = None
    for row in present:
        assignment_id = row.substitute_curricular_assignment_id
        origin = SUBSTITUTION_ORIGIN.format(
            occurrence_id=row.source_v1_lesson_log_id, teacher_id=row.teacher_id
        )
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
                "Aula substituta conjunta concluída",
                execution_credits,
                recorded_at=now_utc,
            ),
            planning_relevant=True,
        )
        row.execution_status = models.OperationalBlockExecutionStatus.COMPLETED
        log = await _upsert_block_log(db, organization_id, row.id, payload, membership_id, now_utc)
        if row.id == block.id:
            result_log = log
    for row in absent_blocks:
        row.status = models.OperationalBlockStatus.CANCELLED
        row.execution_status = models.OperationalBlockExecutionStatus.CANCELLED
        row.cancelled_at = now_utc
    await db.flush()
    if result_log is None:
        result_log = await _upsert_block_log(
            db, organization_id, block.id, payload, membership_id, now_utc
        )
        await db.flush()
    await db.refresh(result_log)
    return result_log


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
    # Resolve the school year without locking, then take the state lock before
    # the mutable block and log rows (repository lock order: state -> logs).
    block = await db.scalar(
        select(models.OperationalScheduleBlock).where(
            models.OperationalScheduleBlock.id == operational_block_id,
            models.OperationalScheduleBlock.organization_id == organization_id,
            models.OperationalScheduleBlock.status == models.OperationalBlockStatus.ACTIVE,
        )
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
    await lock_school_year_state(db, organization_id, lesson.school_year_id)
    # Re-read the block under the state lock before touching its mutable rows.
    block = await db.scalar(
        select(models.OperationalScheduleBlock)
        .where(
            models.OperationalScheduleBlock.id == operational_block_id,
            models.OperationalScheduleBlock.organization_id == organization_id,
            models.OperationalScheduleBlock.status == models.OperationalBlockStatus.ACTIVE,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if block is None:
        raise OperationsError(
            "operational_block_not_found", "Bloco operacional não encontrado.", status_code=404
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
    joint_blocks = await _joint_substitute_blocks(db, organization_id, lesson)
    if len(joint_blocks) > 1:
        return await _complete_joint_substitution(
            db,
            organization_id,
            block=block,
            joint_blocks=joint_blocks,
            payload=payload,
            membership_id=membership_id,
            now_utc=now_utc,
            lesson=lesson,
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
            planning, executed = await load_planning_requirements(
                db, organization_id, [assignment_id]
            )
            requirements = planning.get(assignment_id, ())
            if not requirements:
                raise OperationsError(
                    "substitute_without_requirements",
                    "A disciplina substituta não tem módulos configurados.",
                )
            try:
                execution_credits = frontier_credit(
                    requirements, executed.get(assignment_id, {}), lesson.credit_minutes
                )
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
                    execution_credits,
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
    for assignment in assignments:
        await reconcile_assignment_requirements(db, organization_id, assignment.id)
    # Planning view: a retired module is closed and cannot receive manual
    # progress, so an unselected module is rejected as not assigned.
    requirements, executed = await load_planning_requirements(
        db, organization_id, [row.id for row in assignments]
    )
    module_owner: dict[int, int] = {}
    required_by_module: dict[int, int] = {}
    for assignment in assignments:
        for module in requirements.get(assignment.id, ()):
            module_owner[module.module_id] = assignment.id
            required_by_module[module.module_id] = module.required_minutes
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
    # Dashboard readers use the planning view: a retired module is closed and
    # receives no new debt or progress credit.
    requirements, executed = await load_planning_requirements(db, organization_id, assignment_ids)
    open_debt, claim_assignments = await load_open_debt(db, organization_id, assignment_ids)
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
