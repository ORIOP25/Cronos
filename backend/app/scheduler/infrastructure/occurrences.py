"""Occurrence consumer over the scheduler v1 ledger.

When a v1 version is active, this module is the single source of truth for the
administrative page: registration, consultation, decision and reversal.
An occurrence is a lesson log with status OCCURRENCE plus an audited debt
claim. Deciding GIVEN executes the lesson (settling debt), SUBSTITUTED credits
the subject actually taught, and reversal revises the debt and revokes the log.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models, schemas
from app.core.exceptions import AppError
from app.scheduler.domain.debt import DebtOrigin
from app.scheduler.domain.demand import ExecutionEntry, ModuleCredit, frontier_credit
from app.scheduler.domain.lesson_time import execution_allowed
from app.scheduler.domain.projection import ModuleRequirement
from app.scheduler.infrastructure.models import (
    CurricularAssignment,
    CurricularDebt,
    CurricularDebtRevision,
    CurricularDebtSettlement,
    CurricularExecution,
    CurricularExecutionCredit,
    SchedulerLessonLogV1,
    SchedulerLessonSliceV1,
    SchedulerLessonV1,
    SchedulerVersionV1,
)
from app.scheduler.infrastructure.operations import (
    LESSON_OCCURRENCE_ORIGIN,
    SUBSTITUTION_LIKE,
    OperationsError,
    assert_week_open,
    lesson_context,
    lesson_lineage_ids,
    local_times,
    lock_school_year_state,
    record_lesson_log,
    reverse_lesson_execution,
)
from app.scheduler.infrastructure.progress import (
    load_planning_requirements,
    record_debt,
    record_execution,
    revise_debt,
)

OCCURRENCE_NOT_FOUND = "Ocorrência não encontrada"
OCCURRENCE_WITHOUT_LESSON = "Ocorrência sem aula publicada."


DEBT_ORIGIN = "occurrence-debt:{occurrence_id}"
DEBT_LIKE = "occurrence-debt:%"

OP_STATE_OPEN = "OPEN_PENDING"
OP_STATE_GAP = "DECIDED_GAP"
OP_STATE_SUBSTITUTED = "DECIDED_SUBSTITUTED"
OP_STATE_REVOKED = "REVOKED"
OP_STATE_GIVEN = "DECIDED_GIVEN"


def _error(status_code: int, detail: str) -> AppError:
    kind = {400: "bad_request", 404: "not_found", 409: "conflict", 422: "validation"}.get(
        status_code, "unexpected_error"
    )
    code = {
        404: "resource_not_found",
        409: "conflict",
        422: "validation_error",
    }.get(status_code, "bad_request")
    return AppError(kind=kind, code=code, detail=detail)


async def _active_context(
    db: AsyncSession, organization_id: int
) -> tuple[models.SchedulerSchoolYear, SchedulerVersionV1, ZoneInfo] | None:
    year = await db.scalar(
        select(models.SchedulerSchoolYear).where(
            models.SchedulerSchoolYear.organization_id == organization_id,
            models.SchedulerSchoolYear.is_active.is_(True),
        )
    )
    if year is None:
        return None
    version = await db.scalar(
        select(SchedulerVersionV1).where(
            SchedulerVersionV1.organization_id == organization_id,
            SchedulerVersionV1.school_year_id == year.id,
            SchedulerVersionV1.status == "ACTIVE",
        )
    )
    if version is None:
        return None
    return year, version, ZoneInfo(year.timezone)


async def is_active(db: AsyncSession, organization_id: int) -> bool:
    return await _active_context(db, organization_id) is not None


async def _log_rows(
    db: AsyncSession,
    organization_id: int,
    context: tuple[models.SchedulerSchoolYear, SchedulerVersionV1, ZoneInfo],
    *,
    class_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
):
    year, version, _ = context
    query = (
        select(
            SchedulerLessonLogV1,
            SchedulerLessonV1,
            CurricularAssignment,
            models.Subject,
            models.Teacher,
            models.Class,
            models.Room,
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
            CurricularAssignment,
            and_(
                CurricularAssignment.organization_id == SchedulerLessonV1.organization_id,
                CurricularAssignment.school_year_id == SchedulerLessonV1.school_year_id,
                CurricularAssignment.id == SchedulerLessonV1.assignment_id,
            ),
        )
        .join(
            models.Subject,
            and_(
                models.Subject.organization_id == organization_id,
                models.Subject.id == CurricularAssignment.subject_id,
            ),
        )
        .join(
            models.Teacher,
            and_(
                models.Teacher.organization_id == organization_id,
                models.Teacher.id == CurricularAssignment.teacher_id,
            ),
        )
        .join(
            models.Class,
            and_(
                models.Class.organization_id == organization_id,
                models.Class.id == CurricularAssignment.class_id,
            ),
        )
        .join(
            models.Room,
            and_(
                models.Room.organization_id == organization_id,
                models.Room.id == SchedulerLessonV1.room_id,
            ),
        )
        .where(
            SchedulerLessonLogV1.organization_id == organization_id,
            SchedulerLessonLogV1.school_year_id == year.id,
            # Withdrawn lessons are never carried into a new version, so their
            # absence history stays on the version that withdrew them.
            or_(
                SchedulerLessonV1.version_id == version.id,
                SchedulerLessonLogV1.withdrawn_at.is_not(None),
            ),
            or_(
                SchedulerLessonLogV1.status.in_(("OCCURRENCE", "REVOKED")),
                SchedulerLessonLogV1.decision.is_not(None),
                and_(
                    SchedulerLessonLogV1.status == "COMPLETED",
                    SchedulerLessonLogV1.logged_at < SchedulerLessonV1.ends_at,
                ),
            ),
        )
        .order_by(
            SchedulerLessonV1.school_date,
            SchedulerLessonV1.starts_at,
            SchedulerLessonV1.id,
            SchedulerLessonLogV1.id,
        )
    )
    if class_id is not None:
        query = query.where(CurricularAssignment.class_id == class_id)
    if date_from is not None:
        query = query.where(SchedulerLessonV1.school_date >= date_from)
    if date_to is not None:
        query = query.where(SchedulerLessonV1.school_date <= date_to)
    return (await db.execute(query)).all()


async def _open_minutes_by_claim(
    db: AsyncSession, claims: Sequence[CurricularDebt]
) -> dict[int, int]:
    """Open minutes per claim, even when decision cycles share one origin."""
    if not claims:
        return {}
    claim_ids = [row.id for row in claims]
    revisions = dict(
        (
            await db.execute(
                select(
                    CurricularDebtRevision.debt_id,
                    func.coalesce(func.sum(CurricularDebtRevision.delta_minutes), 0),
                )
                .where(CurricularDebtRevision.debt_id.in_(claim_ids))
                .group_by(CurricularDebtRevision.debt_id)
            )
        ).all()
    )
    settlements = dict(
        (
            await db.execute(
                select(
                    CurricularDebtSettlement.debt_id,
                    func.coalesce(func.sum(CurricularDebtSettlement.minutes), 0),
                )
                .where(CurricularDebtSettlement.debt_id.in_(claim_ids))
                .group_by(CurricularDebtSettlement.debt_id)
            )
        ).all()
    )
    return {
        claim.id: max(
            0,
            claim.created_minutes
            + int(revisions.get(claim.id, 0))
            - int(settlements.get(claim.id, 0)),
        )
        for claim in claims
    }


async def _executions_for_occurrences(
    db: AsyncSession, organization_id: int, occurrence_ids: Sequence[int]
) -> tuple[list[CurricularExecution], dict[int, dict[int, int]]]:
    if not occurrence_ids:
        return [], {}
    conditions = [
        CurricularExecution.origin.like(SUBSTITUTION_LIKE.format(occurrence_id=occurrence_id))
        for occurrence_id in occurrence_ids
    ]
    executions = (
        await db.scalars(
            select(CurricularExecution).where(
                CurricularExecution.organization_id == organization_id,
                or_(*conditions),
            )
        )
    ).all()
    if not executions:
        return [], {}
    execution_credits = (
        await db.scalars(
            select(CurricularExecutionCredit).where(
                CurricularExecutionCredit.organization_id == organization_id,
                CurricularExecutionCredit.execution_id.in_([row.id for row in executions]),
            )
        )
    ).all()
    totals: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for row in execution_credits:
        totals[row.execution_id][row.module_id] += row.delta_minutes
    return list(executions), {key: dict(value) for key, value in totals.items()}


def _substitution_summary(
    executions: Sequence[CurricularExecution],
    credits_by_execution: Mapping[int, Mapping[int, int]],
) -> dict[int, dict]:
    """Net substitution credits per occurrence, keyed by the log identity."""
    net: dict[tuple[int, int], int] = defaultdict(int)
    teacher_by_occurrence: dict[int, int] = {}
    assignment_by_occurrence: dict[int, int] = {}
    for execution in executions:
        try:
            _, occurrence_token, teacher_token = execution.origin.split(":")
            occurrence_id = int(occurrence_token)
            teacher_id = int(teacher_token)
        except (TypeError, ValueError):
            continue
        teacher_by_occurrence[occurrence_id] = teacher_id
        execution_total = sum(credits_by_execution.get(execution.id, {}).values())
        if execution_total > 0:
            assignment_by_occurrence[occurrence_id] = execution.assignment_id
        net[(occurrence_id, execution.assignment_id)] += execution_total
    result: dict[int, dict] = {}
    for occurrence_id, teacher_id in teacher_by_occurrence.items():
        minutes = sum(
            value
            for (_occurrence, _assignment), value in net.items()
            if _occurrence == occurrence_id
        )
        if minutes <= 0:
            continue
        result[occurrence_id] = {
            "minutes": minutes,
            "teacher_id": teacher_id,
            "assignment_id": assignment_by_occurrence.get(occurrence_id),
        }
    return result


async def _timeslot_ids(
    db: AsyncSession, organization_id: int
) -> dict[tuple[int, time, time], int]:
    return {
        (row.day_of_week, row.start_time, row.end_time): row.id
        for row in (
            await db.scalars(
                select(models.Timeslot).where(models.Timeslot.organization_id == organization_id)
            )
        ).all()
    }


async def _first_modules(
    db: AsyncSession, organization_id: int, lesson_ids: Sequence[int]
) -> dict[int, int]:
    if not lesson_ids:
        return {}
    rows = (
        await db.execute(
            select(SchedulerLessonSliceV1.lesson_id, SchedulerLessonSliceV1.module_id)
            .where(
                SchedulerLessonSliceV1.organization_id == organization_id,
                SchedulerLessonSliceV1.lesson_id.in_(lesson_ids),
            )
            .order_by(SchedulerLessonSliceV1.lesson_id, SchedulerLessonSliceV1.offset_minutes)
        )
    ).all()
    result: dict[int, int] = {}
    for lesson_id, module_id in rows:
        result.setdefault(lesson_id, module_id)
    return result


async def _active_blocks_for_logs(
    db: AsyncSession, organization_id: int, log_ids: Sequence[int]
) -> dict[int, models.OperationalScheduleBlock]:
    if not log_ids:
        return {}
    rows = (
        await db.scalars(
            select(models.OperationalScheduleBlock).where(
                models.OperationalScheduleBlock.organization_id == organization_id,
                models.OperationalScheduleBlock.source_v1_lesson_log_id.in_(log_ids),
                models.OperationalScheduleBlock.status == models.OperationalBlockStatus.ACTIVE,
            )
        )
    ).all()
    return {row.source_v1_lesson_log_id: row for row in rows}


async def _lock_member_logs(
    db: AsyncSession, organization_id: int, log_ids: Iterable[int]
) -> dict[int, SchedulerLessonLogV1]:
    """Lock member logs by ``id`` and refresh their facts (tenant scoped)."""
    identifiers = sorted({log_id for log_id in log_ids})
    if not identifiers:
        return {}
    rows = (
        await db.scalars(
            select(SchedulerLessonLogV1)
            .where(
                SchedulerLessonLogV1.organization_id == organization_id,
                SchedulerLessonLogV1.id.in_(identifiers),
            )
            .order_by(SchedulerLessonLogV1.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).all()
    return {row.id: row for row in rows}


async def _require_open_week(
    db: AsyncSession,
    organization_id: int,
    *,
    teacher_id: int | None,
    lesson_date: date,
) -> None:
    """Translate the shared week guard into the occurrence API error."""
    try:
        await assert_week_open(db, organization_id, teacher_id=teacher_id, lesson_date=lesson_date)
    except OperationsError as exc:
        raise AppError(kind="conflict", code=exc.code, detail=str(exc)) from exc


async def _locked_weeks(
    db: AsyncSession,
    organization_id: int,
    pairs: set[tuple[int, date]],
) -> set[tuple[int, date]]:
    if not pairs:
        return set()
    teacher_ids = {teacher_id for teacher_id, _week in pairs}
    rows = (
        await db.scalars(
            select(models.TeacherWeeklyTimesheet).where(
                models.TeacherWeeklyTimesheet.organization_id == organization_id,
                models.TeacherWeeklyTimesheet.teacher_id.in_(teacher_ids),
                models.TeacherWeeklyTimesheet.status.in_(
                    (models.TimesheetStatus.SUBMITTED, models.TimesheetStatus.APPROVED)
                ),
            )
        )
    ).all()
    return {
        (row.teacher_id, row.week_start_date)
        for row in rows
        if (row.teacher_id, row.week_start_date) in pairs
    }


def _log_state(log) -> tuple[str, str]:
    """Public status and operational state of a lesson log, or a pending line."""
    if log is None:
        return "GAP", OP_STATE_OPEN
    if log.status == "REVOKED":
        return "REVOKED", OP_STATE_REVOKED
    if log.decision == "GIVEN" or log.status == "COMPLETED":
        return "GIVEN", OP_STATE_GIVEN
    if log.decision == "SUBSTITUTED":
        return "SUBSTITUTED", OP_STATE_SUBSTITUTED
    if log.decision == "GAP":
        return "GAP", OP_STATE_GAP
    return "GAP", OP_STATE_OPEN


async def _joint_members_for_keys(
    db: AsyncSession,
    organization_id: int,
    year_id: int,
    version_id: int,
    stable_keys: set[str],
) -> dict[str, list[dict]]:
    """Every member class of the given stable keys with its class and log (J13)."""
    if not stable_keys:
        return {}
    rows = (
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
    for lesson, class_id, class_name, log in rows:
        status_value, operational_state = _log_state(log)
        groups[lesson.stable_key].append(
            {
                "class_id": class_id,
                "class_name": class_name,
                "lesson_db_id": lesson.id,
                "log": log,
                "status": status_value,
                "operational_state": operational_state,
            }
        )
    return groups


async def _items(
    db: AsyncSession,
    organization_id: int,
    context: tuple[models.SchedulerSchoolYear, SchedulerVersionV1, ZoneInfo],
    *,
    class_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    now_utc: datetime | None = None,
) -> list[dict]:
    _, _, zone = context
    moment = now_utc or datetime.now(UTC)
    rows = await _log_rows(
        db, organization_id, context, class_id=class_id, date_from=date_from, date_to=date_to
    )
    if not rows:
        return []
    joint_members = await _joint_members_for_keys(
        db, organization_id, context[0].id, context[1].id, {row[1].stable_key for row in rows}
    )
    log_ids = [row[0].id for row in rows]
    blocks = await _active_blocks_for_logs(db, organization_id, log_ids)
    executions, credits_by_execution = await _executions_for_occurrences(
        db, organization_id, log_ids
    )
    substitutions = _substitution_summary(executions, credits_by_execution)
    first_modules = await _first_modules(db, organization_id, [row[1].id for row in rows])
    timeslots = await _timeslot_ids(db, organization_id)
    block_subjects = await _subject_names(
        db, organization_id, {block.subject_id for block in blocks.values()}
    )
    block_teachers = await _teacher_names(
        db, organization_id, {block.teacher_id for block in blocks.values()}
    )
    locked_weeks = await _locked_weeks(
        db,
        organization_id,
        {
            (block.teacher_id, block.date - timedelta(days=block.date.weekday()))
            for block in blocks.values()
        },
    )
    items: list[dict] = []
    for log, lesson, assignment, subject, teacher, class_model, _room in rows:
        local_start, local_end = local_times(lesson, zone)
        block = blocks.get(log.id)
        substitution = substitutions.get(log.id)
        lesson_finished = execution_allowed(moment, lesson.ends_at)
        status_value, operational_state = _log_state(log)
        members = joint_members.get(lesson.stable_key, [])
        joint_lesson = None
        if len(members) > 1:
            joint_lesson = {
                "classes": [
                    {
                        "class_id": member["class_id"],
                        "class_name": member["class_name"],
                        "operational_state": member["operational_state"],
                        "status": member["status"],
                        "version": member["log"].revision if member["log"] else None,
                        "id": member["log"].id if member["log"] else None,
                    }
                    for member in members
                ]
            }
        substitute_completed = (
            block is not None
            and block.execution_status == models.OperationalBlockExecutionStatus.COMPLETED
        )
        block_locked = (
            block is not None
            and (block.teacher_id, block.date - timedelta(days=block.date.weekday()))
            in locked_weeks
        )
        can_complete = (
            block is not None
            and block.execution_status == models.OperationalBlockExecutionStatus.PENDING_LOG
            and lesson_finished
            and not block_locked
        )
        if block is not None and not lesson_finished:
            blocked_reason = "lesson_not_finished"
        elif block_locked:
            blocked_reason = "week_locked"
        else:
            blocked_reason = None
        items.append(
            {
                "id": log.id,
                "organization_id": organization_id,
                "date": lesson.school_date,
                "status": status_value,
                "operational_state": operational_state,
                "revision": 1,
                "is_active": log.status != "REVOKED",
                "version": log.revision,
                "class_id": class_model.id,
                "class_name": class_model.name,
                "subject_id": subject.id,
                "subject_name": subject.name,
                "timeslot_id": timeslots.get(
                    (lesson.school_date.weekday(), local_start, local_end), 0
                ),
                "timeslot_start_time": local_start,
                "timeslot_end_time": local_end,
                "planned_hours": lesson.credit_minutes / 60,
                "planned_teacher_id": teacher.id,
                "planned_teacher_name": teacher.name,
                "executed_teacher_id": block.teacher_id if substitute_completed else None,
                "executed_teacher_name": (
                    block_teachers.get(block.teacher_id) if substitute_completed else None
                ),
                "planned_module_id": first_modules.get(lesson.id),
                "executed_module_id": block.module_id if substitute_completed else None,
                "substitute_teacher_id": block.teacher_id if block is not None else None,
                "substitute_subject_id": block.subject_id if block is not None else None,
                "substitute_subject_name": (
                    block_subjects.get(block.subject_id) if block is not None else None
                ),
                "substitute_block_id": block.id if block is not None else None,
                "substitute_execution_status": (
                    block.execution_status.value if block is not None else None
                ),
                "hours_given": (
                    substitution["minutes"] / 60
                    if substitute_completed and substitution is not None
                    else 0.0
                ),
                "decided_by_membership_id": log.decided_by_membership_id,
                "decided_by_membership_name": None,
                "decided_at": (
                    log.decided_at
                    if log.decided_at is not None
                    else (log.logged_at if log.decision is not None else None)
                ),
                "revoked_at": log.revoked_at
                or (log.updated_at if log.status == "REVOKED" else None),
                "revoked_by_membership_id": (
                    log.revoked_by_membership_id if log.status == "REVOKED" else None
                ),
                "revoked_reason": log.revoked_reason,
                "lesson_log_summary": log.summary,
                "lesson_log_notes": log.notes,
                "reason": None,
                "creation_source": "scheduler_v1",
                "created_at": log.created_at,
                "ends_at": lesson.ends_at,
                "can_complete": can_complete,
                "blocked_reason": blocked_reason,
                # WBS 5.2 (J13): joint lesson grouping for the occurrences page.
                "joint_lesson": joint_lesson,
                "_group_key": lesson.stable_key,
                # Internal context used by the commands; the response model drops it.
                "lesson_db_id": lesson.id,
                "assignment_db_id": assignment.id,
            }
        )
    return items


async def _subject_names(
    db: AsyncSession, organization_id: int, subject_ids: set[int]
) -> dict[int, str]:
    if not subject_ids:
        return {}
    return dict(
        (
            await db.execute(
                select(models.Subject.id, models.Subject.name).where(
                    models.Subject.organization_id == organization_id,
                    models.Subject.id.in_(subject_ids),
                )
            )
        ).all()
    )


async def _teacher_names(
    db: AsyncSession, organization_id: int, teacher_ids: set[int]
) -> dict[int, str]:
    if not teacher_ids:
        return {}
    return dict(
        (
            await db.execute(
                select(models.Teacher.id, models.Teacher.name).where(
                    models.Teacher.organization_id == organization_id,
                    models.Teacher.id.in_(teacher_ids),
                )
            )
        ).all()
    )


def _matches_status(item: Mapping, status_filter: str | None) -> bool:
    if not status_filter:
        return True
    normalized = status_filter.upper()
    if normalized in ("OPEN", OP_STATE_OPEN):
        return item["operational_state"] == OP_STATE_OPEN
    if normalized == "GIVEN":
        return item["operational_state"] == OP_STATE_GIVEN
    if normalized == "GAP":
        return item["operational_state"] == OP_STATE_GAP
    if normalized == "SUBSTITUTED":
        return item["operational_state"] == OP_STATE_SUBSTITUTED
    if normalized == "REVOKED":
        return item["operational_state"] == OP_STATE_REVOKED
    raise _error(422, f"Estado de ocorrência inválido: {status_filter}")


async def list_occurrences(
    db: AsyncSession,
    organization_id: int,
    *,
    class_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    status_filter: str | None = None,
    skip: int = 0,
    limit: int = 100,
) -> dict:
    context = await _active_context(db, organization_id)
    if context is None:
        return {"items": [], "total": 0, "limit": limit, "offset": skip}
    if date_from is not None and date_to is not None and date_from > date_to:
        raise _error(422, "O intervalo de datas é inválido.")
    items = await _items(
        db, organization_id, context, class_id=class_id, date_from=date_from, date_to=date_to
    )
    # A joint lesson is one card. Filter first, then collapse the sibling logs to
    # the stable first line (min lesson id) so any matching class keeps the
    # card, while the per-class state travels inside ``joint_lesson`` (J13).
    seen_groups: set[str] = set()
    grouped: list[dict] = []
    for item in items:
        if not _matches_status(item, status_filter):
            continue
        group_key = item.pop("_group_key", None)
        if group_key is not None:
            if group_key in seen_groups:
                continue
            seen_groups.add(group_key)
        grouped.append(item)
    return {
        "items": grouped[skip : skip + limit],
        "total": len(grouped),
        "limit": limit,
        "offset": skip,
    }


async def _find_item(
    db: AsyncSession,
    organization_id: int,
    occurrence_id: int,
    now_utc: datetime | None = None,
) -> tuple[dict, models.SchedulerSchoolYear, SchedulerVersionV1] | None:
    context = await _active_context(db, organization_id)
    if context is None:
        return None
    items = await _items(db, organization_id, context, now_utc=now_utc)
    match = next((item for item in items if item["id"] == occurrence_id), None)
    if match is None:
        return None
    match.pop("_group_key", None)
    return match, context[0], context[1]


async def get_occurrence(
    db: AsyncSession,
    organization_id: int,
    occurrence_id: int,
    now_utc: datetime | None = None,
):
    found = await _find_item(db, organization_id, occurrence_id, now_utc)
    if found is None:
        raise _error(404, OCCURRENCE_NOT_FOUND)
    return found[0]


async def get_debts(db: AsyncSession, organization_id: int, *, class_id: int | None = None) -> dict:
    moment = datetime.now(UTC)
    today = moment.date()
    context = await _active_context(db, organization_id)
    if context is None:
        return {
            "total_gaps": 0,
            "total_hours_owed": 0.0,
            "total_gaps_overdue": 0,
            "total_hours_owed_overdue": 0.0,
            "as_of_date": today,
            "items": [],
        }
    year, _, tz = context
    today = moment.astimezone(tz).date()
    claims = (
        await db.scalars(
            select(CurricularDebt).where(
                CurricularDebt.organization_id == organization_id,
                or_(
                    CurricularDebt.origin.like("lesson-occurrence:%"),
                    CurricularDebt.origin.like(DEBT_LIKE),
                ),
            )
        )
    ).all()
    open_by_claim = await _open_minutes_by_claim(db, claims)
    assignments = {
        row.id: row
        for row in (
            await db.scalars(
                select(CurricularAssignment).where(
                    CurricularAssignment.organization_id == organization_id,
                    CurricularAssignment.school_year_id == year.id,
                )
            )
        ).all()
    }
    grouped: dict[tuple[int, int, int], dict] = {}
    for claim in claims:
        minutes = open_by_claim.get(claim.id, 0)
        assignment = assignments.get(claim.assignment_id)
        if minutes <= 0 or assignment is None:
            continue
        if class_id is not None and assignment.class_id != class_id:
            continue
        key = (assignment.class_id, assignment.subject_id, assignment.teacher_id)
        entry = grouped.setdefault(
            key,
            {
                "class_id": assignment.class_id,
                "subject_id": assignment.subject_id,
                "teacher_id": assignment.teacher_id,
                "gap_occurrences": 0,
                "minutes": 0,
                "overdue_minutes": 0,
                "overdue_gaps": 0,
            },
        )
        entry["gap_occurrences"] += 1
        entry["minutes"] += minutes
        if claim.origin_date <= today:
            entry["overdue_gaps"] += 1
            entry["overdue_minutes"] += minutes
    classes = {
        row.id: row.name
        for row in (
            await db.scalars(
                select(models.Class).where(models.Class.organization_id == organization_id)
            )
        ).all()
    }
    subjects = {
        row.id: row.name
        for row in (
            await db.scalars(
                select(models.Subject).where(models.Subject.organization_id == organization_id)
            )
        ).all()
    }
    teachers = {
        row.id: row.name
        for row in (
            await db.scalars(
                select(models.Teacher).where(models.Teacher.organization_id == organization_id)
            )
        ).all()
    }
    items = [
        {
            "class_id": entry["class_id"],
            "class_name": classes.get(entry["class_id"], ""),
            "subject_id": entry["subject_id"],
            "subject_name": subjects.get(entry["subject_id"], ""),
            "teacher_id": entry["teacher_id"],
            "teacher_name": teachers.get(entry["teacher_id"]),
            "gap_occurrences": entry["gap_occurrences"],
            "hours_owed": entry["minutes"] / 60,
            "gap_occurrences_overdue": entry["overdue_gaps"],
            "hours_owed_overdue": entry["overdue_minutes"] / 60,
        }
        for entry in grouped.values()
    ]
    return {
        "total_gaps": sum(entry["gap_occurrences"] for entry in grouped.values()),
        "total_hours_owed": sum(entry["minutes"] for entry in grouped.values()) / 60,
        "total_gaps_overdue": sum(entry["overdue_gaps"] for entry in grouped.values()),
        "total_hours_owed_overdue": (
            sum(entry["overdue_minutes"] for entry in grouped.values()) / 60
        ),
        "as_of_date": today,
        "items": items,
    }


def _reversal_credits(
    executions: Sequence[CurricularExecution],
    credits_by_execution: Mapping[int, Mapping[int, int]],
) -> list[tuple[CurricularExecution, tuple[ModuleCredit, ...]]]:
    """Remaining positive balance per execution, oldest first."""
    key_by_db_id = {row.id: (row.origin, row.revision) for row in executions}
    reversed_by_source: dict[tuple[tuple[str, int], int], int] = defaultdict(int)
    for execution in executions:
        if execution.reversal_of_id is None:
            continue
        source_key = key_by_db_id.get(execution.reversal_of_id)
        if source_key is None:
            continue
        for module_id, minutes in credits_by_execution.get(execution.id, {}).items():
            reversed_by_source[(source_key, module_id)] += abs(minutes)
    pending: list[tuple[CurricularExecution, tuple[ModuleCredit, ...]]] = []
    for execution in sorted(executions, key=lambda row: row.id):
        if execution.reversal_of_id is not None:
            continue
        key = (execution.origin, execution.revision)
        execution_credits = tuple(
            ModuleCredit(
                module_id,
                -(minutes - reversed_by_source.get((key, module_id), 0)),
            )
            for module_id, minutes in sorted(credits_by_execution.get(execution.id, {}).items())
            if minutes - reversed_by_source.get((key, module_id), 0) > 0
        )
        if execution_credits:
            pending.append((execution, execution_credits))
    return pending


async def _reverse_substitutions(
    db: AsyncSession,
    organization_id: int,
    *,
    occurrence_id: int,
    membership_id: int,
    now_utc: datetime,
) -> None:
    executions, credits_by_execution = await _executions_for_occurrences(
        db, organization_id, [occurrence_id]
    )
    if not executions:
        return
    next_revisions: dict[str, int] = defaultdict(int)
    for execution in executions:
        next_revisions[execution.origin] = max(next_revisions[execution.origin], execution.revision)
    for execution, execution_credits in _reversal_credits(executions, credits_by_execution):
        next_revisions[execution.origin] += 1
        await record_execution(
            db,
            organization_id,
            await _year_id_for_assignment(db, organization_id, execution.assignment_id),
            execution.assignment_id,
            ExecutionEntry(
                execution.origin,
                next_revisions[execution.origin],
                membership_id,
                "Substituição revertida",
                execution_credits,
                reversal_of=(execution.origin, execution.revision),
                recorded_at=now_utc,
            ),
            planning_relevant=True,
        )


async def _year_id_for_assignment(
    db: AsyncSession, organization_id: int, assignment_id: int
) -> int:
    year_id = await db.scalar(
        select(CurricularAssignment.school_year_id).where(
            CurricularAssignment.id == assignment_id,
            CurricularAssignment.organization_id == organization_id,
        )
    )
    if year_id is None:
        raise _error(422, "Disciplina sem ano letivo válido.")
    return year_id


async def _requirements(
    db: AsyncSession, organization_id: int, assignment_id: int
) -> tuple[ModuleRequirement, ...]:
    planning, _ = await load_planning_requirements(db, organization_id, [assignment_id])
    return planning.get(assignment_id, ())


def _substitution_exclusion(code: str, message: str, setup: str) -> dict:
    return {"code": code, "message": message, "setup": setup}


async def _class_ids_for_item(
    db: AsyncSession,
    organization_id: int,
    context: tuple[models.SchedulerSchoolYear, SchedulerVersionV1, ZoneInfo],
    item: Mapping,
) -> tuple[int, ...]:
    """Member classes of the item's logical lesson, ``item`` class for plain ones."""
    lesson = await db.get(SchedulerLessonV1, item["lesson_db_id"])
    if lesson is None:
        return (item["class_id"],)
    year, version, _ = context
    members = (
        await _joint_members_for_keys(db, organization_id, year.id, version.id, {lesson.stable_key})
    ).get(lesson.stable_key, [])
    class_ids = tuple(sorted(member["class_id"] for member in members))
    return class_ids or (item["class_id"],)


async def _link_class_rows(
    db: AsyncSession, organization_id: int, subject_id: int, class_ids: Sequence[int]
) -> list:
    rows = await db.execute(
        select(models.ClassSubjectLink.id, models.ClassSubjectLink.class_id)
        .join(
            models.Class,
            and_(
                models.Class.organization_id == organization_id,
                models.Class.id == models.ClassSubjectLink.class_id,
            ),
        )
        .where(
            models.ClassSubjectLink.organization_id == organization_id,
            models.ClassSubjectLink.subject_id == subject_id,
            models.ClassSubjectLink.class_id.in_(sorted(set(class_ids))),
            models.ClassSubjectLink.grade_level == models.Class.grade_level,
        )
    )
    return rows.all()


async def _joint_group_modules(db: AsyncSession, organization_id: int, group_id: int) -> set[int]:
    rows = await db.scalars(
        select(models.joint_lesson_group_module.c.module_id).where(
            models.joint_lesson_group_module.c.organization_id == organization_id,
            models.joint_lesson_group_module.c.group_id == group_id,
        )
    )
    return set(rows.all())


async def _joint_group_for_classes(
    db: AsyncSession, organization_id: int, subject_id: int, class_ids: Sequence[int]
) -> int | None:
    """A joint group of the subject with exactly these member classes (J14)."""
    link_rows = await _link_class_rows(db, organization_id, subject_id, class_ids)
    link_class = {row.id: row.class_id for row in link_rows}
    if not link_class:
        return None
    member_rows = (
        await db.execute(
            select(
                models.joint_lesson_group_member.c.group_id,
                models.joint_lesson_group_member.c.class_subject_link_id,
            ).where(
                models.joint_lesson_group_member.c.organization_id == organization_id,
                models.joint_lesson_group_member.c.class_subject_link_id.in_(list(link_class)),
            )
        )
    ).all()
    groups: dict[int, set[int]] = defaultdict(set)
    for group_id, link_id in member_rows:
        groups[group_id].add(link_class[link_id])
    target = set(class_ids)
    for group_id, classes in groups.items():
        if classes != target:
            continue
        group = await db.get(models.JointLessonGroup, group_id)
        if (
            group is not None
            and group.organization_id == organization_id
            and group.subject_id == subject_id
        ):
            return group_id
    return None


async def _joint_group_containing_class(
    db: AsyncSession, organization_id: int, subject_id: int, class_id: int
) -> int | None:
    """A joint group of the subject that contains this class (J15)."""
    link_rows = await _link_class_rows(db, organization_id, subject_id, (class_id,))
    link_class = {row.id: row.class_id for row in link_rows}
    if not link_class:
        return None
    member_rows = (
        await db.execute(
            select(models.joint_lesson_group_member.c.group_id).where(
                models.joint_lesson_group_member.c.organization_id == organization_id,
                models.joint_lesson_group_member.c.class_subject_link_id.in_(list(link_class)),
            )
        )
    ).all()
    for (group_id,) in member_rows:
        group = await db.get(models.JointLessonGroup, group_id)
        if (
            group is not None
            and group.organization_id == organization_id
            and group.subject_id == subject_id
        ):
            return group_id
    return None


async def _next_residual_is_joint(
    db: AsyncSession,
    organization_id: int,
    year_id: int,
    subject_id: int,
    class_id: int,
    joint_module_ids: set[int],
) -> bool:
    """True when the class's next unit with missing minutes is a joint module."""
    assignment = await db.scalar(
        select(CurricularAssignment).where(
            CurricularAssignment.organization_id == organization_id,
            CurricularAssignment.school_year_id == year_id,
            CurricularAssignment.class_id == class_id,
            CurricularAssignment.subject_id == subject_id,
        )
    )
    if assignment is None:
        return False
    planning, executed = await load_planning_requirements(db, organization_id, [assignment.id])
    modules = planning.get(assignment.id, ())
    completed = executed.get(assignment.id, {})
    target = next(
        (
            module.module_id
            for module in modules
            if completed.get(module.module_id, 0) < module.required_minutes
        ),
        None,
    )
    return target is not None and target in joint_module_ids


async def _joint_residual_minutes(
    db: AsyncSession,
    organization_id: int,
    year_id: int,
    subject_id: int,
    class_ids: Sequence[int],
    joint_module_ids: set[int],
) -> int:
    """Joint residual of the group: requirement minus the joint progress (J14)."""
    assignments = (
        await db.scalars(
            select(CurricularAssignment).where(
                CurricularAssignment.organization_id == organization_id,
                CurricularAssignment.school_year_id == year_id,
                CurricularAssignment.class_id.in_(sorted(set(class_ids))),
                CurricularAssignment.subject_id == subject_id,
            )
        )
    ).all()
    if not assignments:
        return 0
    planning, executed = await load_planning_requirements(
        db, organization_id, [assignment.id for assignment in assignments]
    )
    required: dict[int, int] = {}
    for assignment in assignments:
        for module in planning.get(assignment.id, ()):
            if module.module_id in joint_module_ids:
                required.setdefault(module.module_id, module.required_minutes)
    progress = {
        module_id: max(
            (executed.get(assignment.id, {}).get(module_id, 0) for assignment in assignments),
            default=0,
        )
        for module_id in joint_module_ids
    }
    return sum(
        max(0, required.get(module_id, 0) - progress.get(module_id, 0))
        for module_id in joint_module_ids
    )


async def _substitute_exclusions(
    db: AsyncSession,
    organization_id: int,
    context: tuple[models.SchedulerSchoolYear, SchedulerVersionV1, ZoneInfo],
    item: Mapping,
    *,
    teacher_id: int,
    subject_id: int,
) -> list[dict]:
    """Every reason the candidate cannot replace this lesson, possibly empty."""
    year, version, _ = context
    if teacher_id == item["planned_teacher_id"]:
        return [
            _substitution_exclusion(
                "same_teacher",
                "O docente previsto não pode ser confirmado como substituto.",
                "teacher",
            )
        ]
    if subject_id == item["subject_id"]:
        return [
            _substitution_exclusion(
                "same_subject",
                "A disciplina substituta não pode ser igual à planeada.",
                "assignment",
            )
        ]
    lesson = await db.get(SchedulerLessonV1, item["lesson_db_id"])
    if lesson is None:
        return [_substitution_exclusion("lesson_missing", OCCURRENCE_WITHOUT_LESSON, "assignment")]
    teacher = await db.scalar(
        select(models.Teacher).where(
            models.Teacher.organization_id == organization_id,
            models.Teacher.id == teacher_id,
        )
    )
    if teacher is None:
        return [
            _substitution_exclusion(
                "teacher_unknown", "O docente não pertence a esta organização.", "teacher"
            )
        ]
    class_ids = await _class_ids_for_item(db, organization_id, context, item)
    if len(class_ids) == 1:
        assignment = await db.scalar(
            select(CurricularAssignment).where(
                CurricularAssignment.organization_id == organization_id,
                CurricularAssignment.school_year_id == year.id,
                CurricularAssignment.class_id == item["class_id"],
                CurricularAssignment.subject_id == subject_id,
            )
        )
        if assignment is None or assignment.teacher_id != teacher_id:
            return [
                _substitution_exclusion(
                    "not_assigned",
                    "O docente não está associado a esta turma e disciplina no ano letivo.",
                    "assignment",
                )
            ]
    else:
        member_assignments = (
            await db.scalars(
                select(CurricularAssignment).where(
                    CurricularAssignment.organization_id == organization_id,
                    CurricularAssignment.school_year_id == year.id,
                    CurricularAssignment.class_id.in_(class_ids),
                    CurricularAssignment.subject_id == subject_id,
                )
            )
        ).all()
        by_class = {row.class_id: row for row in member_assignments}
        if len(by_class) != len(class_ids) or any(
            row.teacher_id != teacher_id for row in by_class.values()
        ):
            return [
                _substitution_exclusion(
                    "not_assigned",
                    "O docente não está associado a estas turmas e disciplina no ano letivo.",
                    "assignment",
                )
            ]
        assignment = by_class[class_ids[0]]
    exclusions: list[dict] = []
    availability = await db.scalar(
        select(models.Availability.score).where(
            models.Availability.organization_id == organization_id,
            models.Availability.teacher_id == teacher_id,
            models.Availability.timeslot_id == item["timeslot_id"],
        )
    )
    if availability is not None and availability < 0:
        exclusions.append(
            _substitution_exclusion(
                "unavailable", "Candidato indisponível para o período.", "availability"
            )
        )
    schedule_conflict = await db.scalar(
        select(SchedulerLessonV1.id)
        .join(
            CurricularAssignment,
            and_(
                CurricularAssignment.organization_id == SchedulerLessonV1.organization_id,
                CurricularAssignment.school_year_id == SchedulerLessonV1.school_year_id,
                CurricularAssignment.id == SchedulerLessonV1.assignment_id,
            ),
        )
        .where(
            SchedulerLessonV1.organization_id == organization_id,
            SchedulerLessonV1.school_year_id == year.id,
            SchedulerLessonV1.version_id == version.id,
            CurricularAssignment.teacher_id == teacher_id,
            SchedulerLessonV1.school_date == lesson.school_date,
            SchedulerLessonV1.starts_at < lesson.ends_at,
            lesson.starts_at < SchedulerLessonV1.ends_at,
        )
        .limit(1)
    )
    if schedule_conflict is not None:
        exclusions.append(
            _substitution_exclusion(
                "schedule_conflict",
                "Candidato em conflito de horário com aulas publicadas.",
                "availability",
            )
        )
    member_log_ids = [
        member["log"].id
        for member in (
            await _joint_members_for_keys(
                db, organization_id, year.id, version.id, {lesson.stable_key}
            )
        ).get(lesson.stable_key, [])
        if member["log"] is not None
    ]
    if item["id"] not in member_log_ids:
        member_log_ids.append(item["id"])
    block_conflict = await db.scalar(
        select(models.OperationalScheduleBlock.id)
        .where(
            models.OperationalScheduleBlock.organization_id == organization_id,
            models.OperationalScheduleBlock.status == models.OperationalBlockStatus.ACTIVE,
            models.OperationalScheduleBlock.date == lesson.school_date,
            models.OperationalScheduleBlock.timeslot_id == item["timeslot_id"],
            or_(
                models.OperationalScheduleBlock.source_v1_lesson_log_id.is_(None),
                models.OperationalScheduleBlock.source_v1_lesson_log_id.not_in(member_log_ids),
            ),
            or_(
                models.OperationalScheduleBlock.teacher_id == teacher_id,
                models.OperationalScheduleBlock.room_id == lesson.room_id,
                models.OperationalScheduleBlock.class_id.in_(class_ids),
            ),
        )
        .limit(1)
    )
    if block_conflict is not None:
        exclusions.append(
            _substitution_exclusion(
                "operational_conflict",
                "Candidato em conflito com uma substituição já planeada.",
                "availability",
            )
        )
    room = await db.get(models.Room, lesson.room_id)
    subject = await db.get(models.Subject, subject_id)
    if room is not None and subject is not None and room.type != subject.required_room_type:
        exclusions.append(
            _substitution_exclusion(
                "room_mismatch",
                "A sala da aula não é compatível com a disciplina substituta.",
                "room",
            )
        )
    if len(class_ids) == 1:
        # J15: a single-class substitute cannot give a subject the class is
        # taking jointly, or the other classes would fall behind.
        joint_group_id = await _joint_group_containing_class(
            db, organization_id, subject_id, item["class_id"]
        )
        if joint_group_id is not None:
            joint_modules = await _joint_group_modules(db, organization_id, joint_group_id)
            if await _next_residual_is_joint(
                db, organization_id, year.id, subject_id, item["class_id"], joint_modules
            ):
                exclusions.append(
                    _substitution_exclusion(
                        "joint_in_progress",
                        "A turma tem esta disciplina em conjunto. "
                        "A substituição deixaria as outras turmas para trás.",
                        "assignment",
                    )
                )
        # Planning view: a retired module is closed, so it never counts as
        # substitute capacity.
        requirements, executed_by_assignment = await load_planning_requirements(
            db, organization_id, [assignment.id]
        )
        modules = requirements.get(assignment.id, ())
        if not modules:
            exclusions.append(
                _substitution_exclusion(
                    "no_modules",
                    "A disciplina substituta não tem módulos configurados.",
                    "capacity",
                )
            )
        else:
            executed = executed_by_assignment.get(assignment.id, {})
            try:
                frontier_credit(modules, executed, lesson.credit_minutes)
            except ValueError:
                exclusions.append(
                    _substitution_exclusion(
                        "no_capacity",
                        "A disciplina substituta não tem minutos curriculares disponíveis.",
                        "capacity",
                    )
                )
        return exclusions
    # J14: a joint substitute gives another subject jointly to the same classes.
    joint_group_id = await _joint_group_for_classes(db, organization_id, subject_id, class_ids)
    if joint_group_id is None:
        exclusions.append(
            _substitution_exclusion(
                "joint_classes_mismatch",
                "O docente não dá esta disciplina em conjunto a estas turmas.",
                "assignment",
            )
        )
        return exclusions
    joint_modules = await _joint_group_modules(db, organization_id, joint_group_id)
    next_flags = [
        await _next_residual_is_joint(
            db, organization_id, year.id, subject_id, class_id, joint_modules
        )
        for class_id in class_ids
    ]
    if not next_flags or not all(next_flags):
        exclusions.append(
            _substitution_exclusion(
                "joint_not_in_progress",
                "As turmas não estão na parte conjunta desta disciplina.",
                "assignment",
            )
        )
        return exclusions
    residual = await _joint_residual_minutes(
        db, organization_id, year.id, subject_id, class_ids, joint_modules
    )
    if residual < lesson.credit_minutes:
        exclusions.append(
            _substitution_exclusion(
                "no_capacity",
                "A disciplina substituta não tem minutos curriculares disponíveis.",
                "capacity",
            )
        )
    return exclusions


def _lesson_not_finished_error() -> AppError:
    return AppError(
        kind="validation",
        code="lesson_not_finished",
        detail="Só pode concluir esta aula depois do seu término.",
    )


async def _claims_for_log(
    db: AsyncSession, organization_id: int, log: SchedulerLessonLogV1
) -> list[CurricularDebt]:
    context = await lesson_context(db, organization_id, log.lesson_id)
    origins = {
        DEBT_ORIGIN.format(occurrence_id=log.id),
        *(
            LESSON_OCCURRENCE_ORIGIN.format(lesson_id=lesson_id)
            for lesson_id in await lesson_lineage_ids(db, organization_id, context)
        ),
    }
    rows = (
        await db.scalars(
            select(CurricularDebt).where(
                CurricularDebt.organization_id == organization_id,
                CurricularDebt.origin.in_(origins),
            )
        )
    ).all()
    return list(rows)


async def _ensure_debt_claim(
    db: AsyncSession,
    organization_id: int,
    school_year_id: int,
    item: Mapping,
    log: SchedulerLessonLogV1,
    *,
    membership_id: int,
    reason: str,
    now_utc: datetime,
) -> None:
    """Create the audited debt claim once per decision cycle."""
    claims = await _claims_for_log(db, organization_id, log)
    open_by_claim = await _open_minutes_by_claim(db, claims)
    if any(minutes > 0 for minutes in open_by_claim.values()):
        return
    lesson = await db.get(SchedulerLessonV1, log.lesson_id)
    if lesson is None:
        raise _error(404, OCCURRENCE_WITHOUT_LESSON)
    await record_debt(
        db,
        organization_id,
        school_year_id,
        item["assignment_db_id"],
        DebtOrigin(
            origin=DEBT_ORIGIN.format(occurrence_id=log.id),
            revision=log.revision,
            origin_date=lesson.school_date,
            minutes=lesson.credit_minutes,
            author_id=membership_id,
            reason=reason,
            recorded_at=now_utc,
        ),
    )


async def _cancel_debt_claim(
    db: AsyncSession,
    organization_id: int,
    school_year_id: int,
    log: SchedulerLessonLogV1,
    *,
    membership_id: int,
    reason: str,
    now_utc: datetime,
) -> None:
    claims = await _claims_for_log(db, organization_id, log)
    open_by_claim = await _open_minutes_by_claim(db, claims)
    for claim in claims:
        open_minutes = open_by_claim.get(claim.id, 0)
        if open_minutes <= 0:
            continue
        await revise_debt(
            db,
            organization_id,
            school_year_id,
            claim.id,
            origin=f"occurrence-reverse:{log.id}:{claim.id}",
            revision=log.revision + 1,
            delta_minutes=-open_minutes,
            author_id=membership_id,
            reason=reason,
            recorded_at=now_utc,
        )


async def _cancel_blocks_for_log(
    db: AsyncSession,
    organization_id: int,
    *,
    occurrence_id: int,
    membership_id: int | None = None,
    now_utc: datetime | None = None,
) -> None:
    """Cancel every active substitute block of one occurrence log."""
    del membership_id
    moment = now_utc or datetime.now(UTC)
    blocks = (
        await db.scalars(
            select(models.OperationalScheduleBlock)
            .where(
                models.OperationalScheduleBlock.organization_id == organization_id,
                models.OperationalScheduleBlock.source_v1_lesson_log_id == occurrence_id,
                models.OperationalScheduleBlock.status == models.OperationalBlockStatus.ACTIVE,
            )
            .with_for_update()
        )
    ).all()
    for block in blocks:
        block.status = models.OperationalBlockStatus.CANCELLED
        block.execution_status = models.OperationalBlockExecutionStatus.CANCELLED
        block.cancelled_at = moment


def _is_repeated_v1_decision(
    item: Mapping, log: SchedulerLessonLogV1, payload: schemas.LessonOccurrenceUpdate
) -> bool:
    if payload.version + 1 != log.revision:
        return False
    if payload.status.value != (log.decision or ""):
        return False
    if payload.status is schemas.LessonOccurrenceStatus.SUBSTITUTED:
        return (
            payload.substitute_teacher_id == item["substitute_teacher_id"]
            and payload.substitute_subject_id == item["substitute_subject_id"]
        )
    return True


async def _plan_substitution(
    db: AsyncSession,
    organization_id: int,
    context: tuple[models.SchedulerSchoolYear, SchedulerVersionV1, ZoneInfo],
    item: Mapping,
    payload: schemas.LessonOccurrenceUpdate,
    *,
    membership_id: int,
    now_utc: datetime,
    revision: int,
) -> models.OperationalScheduleBlock:
    """Plan the substitute lesson without crediting execution."""
    if payload.substitute_teacher_id is None or payload.substitute_subject_id is None:
        raise _error(422, "substitute_teacher_id e substitute_subject_id são obrigatórios.")
    exclusions = await _substitute_exclusions(
        db,
        organization_id,
        context,
        item,
        teacher_id=payload.substitute_teacher_id,
        subject_id=payload.substitute_subject_id,
    )
    if exclusions:
        first = exclusions[0]
        status_by_code = {
            "lesson_missing": 404,
            "not_assigned": 422,
            "teacher_unknown": 422,
            "no_modules": 422,
            "no_capacity": 422,
        }
        raise _error(status_by_code.get(first["code"], 409), first["message"])
    _, _, zone = context
    assignment = await db.scalar(
        select(CurricularAssignment).where(
            CurricularAssignment.organization_id == organization_id,
            CurricularAssignment.class_id == item["class_id"],
            CurricularAssignment.subject_id == payload.substitute_subject_id,
        )
    )
    if assignment is None:
        raise _error(422, "Disciplina substituta inválida para esta turma.")
    planning, _ = await load_planning_requirements(db, organization_id, [assignment.id])
    modules = planning.get(assignment.id, ())
    if not modules:
        raise _error(422, "A disciplina substituta não tem módulos configurados.")
    lesson = await db.get(SchedulerLessonV1, item["lesson_db_id"])
    if lesson is None:
        raise _error(404, OCCURRENCE_WITHOUT_LESSON)
    timeslots = await _timeslot_ids(db, organization_id)
    local_start, local_end = local_times(lesson, zone)
    timeslot_id = timeslots.get((lesson.school_date.weekday(), local_start, local_end))
    if not timeslot_id:
        raise _error(422, "A aula substituta não tem um período compatível.")
    await _cancel_blocks_for_log(
        db,
        organization_id,
        occurrence_id=item["id"],
        membership_id=membership_id,
        now_utc=now_utc,
    )
    block = models.OperationalScheduleBlock(
        organization_id=organization_id,
        source_occurrence_id=None,
        source_occurrence_revision=revision,
        origin_kind=models.OperationalBlockOrigin.V1,
        source_v1_lesson_log_id=item["id"],
        substitute_curricular_assignment_id=assignment.id,
        date=lesson.school_date,
        timeslot_id=timeslot_id,
        room_id=lesson.room_id,
        class_id=item["class_id"],
        teacher_id=payload.substitute_teacher_id,
        subject_id=payload.substitute_subject_id,
        module_id=modules[0].module_id,
        status=models.OperationalBlockStatus.ACTIVE,
        execution_status=models.OperationalBlockExecutionStatus.PENDING_LOG,
        created_by_membership_id=membership_id,
        created_at=now_utc,
    )
    db.add(block)
    await db.flush()
    return block


async def update_occurrence(
    db: AsyncSession,
    organization_id: int,
    occurrence_id: int,
    payload: schemas.LessonOccurrenceUpdate,
    *,
    decided_by_membership_id: int | None = None,
    now_utc: datetime | None = None,
) -> dict:
    """Register an occurrence decision, optionally across member classes (J13)."""
    moment = now_utc or datetime.now(UTC)
    found = await _find_item(db, organization_id, occurrence_id, moment)
    if found is None:
        raise _error(404, OCCURRENCE_NOT_FOUND)
    item, year, version = found
    # Lock the school-year state row before any mutable log row (state -> logs).
    await lock_school_year_state(db, organization_id, year.id)
    target = payload.status.value
    if target == "SUBSTITUTED" and not payload.class_ids:
        # A joint substitution always covers every member class (J13): auto the
        # group instead of silently planning a single class.
        lesson = await db.get(SchedulerLessonV1, item["lesson_db_id"])
        if lesson is not None:
            members = (
                await _joint_members_for_keys(
                    db, organization_id, year.id, version.id, {lesson.stable_key}
                )
            ).get(lesson.stable_key, [])
            if len(members) > 1:
                payload = payload.model_copy(
                    update={"class_ids": [member["class_id"] for member in members]}
                )
    if payload.class_ids:
        return await _decide_joint(
            db,
            organization_id,
            occurrence_id,
            payload,
            item,
            year,
            version,
            moment,
            decided_by_membership_id,
        )
    return await _decide_line(
        db,
        organization_id,
        occurrence_id,
        payload,
        item,
        year,
        version,
        moment,
        decided_by_membership_id,
    )


async def _decide_joint(
    db: AsyncSession,
    organization_id: int,
    occurrence_id: int,
    payload: schemas.LessonOccurrenceUpdate,
    item: Mapping,
    year: models.SchedulerSchoolYear,
    version: SchedulerVersionV1,
    moment: datetime,
    decided_by_membership_id: int | None,
) -> dict:
    """Apply one decision to the selected member classes of a joint lesson.

    ``class_ids`` must name member classes and the payload version references
    the clicked line. ``SUBSTITUTED`` applies to every member and requires every
    member to be a pending occurrence, matching an absent teacher (J13). The
    sibling logs are locked by ``id`` before any decision, so a failure never
    leaves a partial set of decisions.
    """
    target = payload.status.value
    if target == "REVOKED":
        raise _error(422, "Use o cancelamento para reverter a ocorrência.")
    lesson = await db.get(SchedulerLessonV1, item["lesson_db_id"])
    if lesson is None:
        raise _error(404, OCCURRENCE_WITHOUT_LESSON)
    members = (
        await _joint_members_for_keys(db, organization_id, year.id, version.id, {lesson.stable_key})
    ).get(lesson.stable_key, [])
    if len(members) <= 1:
        raise _error(422, "A aula indicada não é conjunta.")
    member_class_ids = {member["class_id"] for member in members}
    selected = list(dict.fromkeys(payload.class_ids or []))
    if any(class_id not in member_class_ids for class_id in selected):
        raise _error(422, "Uma turma indicada não pertence a esta aula conjunta.")
    # Lock every sibling log by ``id`` and refresh its facts before validating.
    locked_logs = await _lock_member_logs(
        db, organization_id, (member["log"].id for member in members if member["log"] is not None)
    )
    clicked = locked_logs.get(item["id"])
    if clicked is None or clicked.revision != payload.version:
        raise _error(409, "OCCURRENCE_STALE_VERSION")
    for member in members:
        member["log"] = locked_logs.get(member["log"].id) if member["log"] is not None else None
    if target == "SUBSTITUTED":
        if set(selected) != member_class_ids:
            raise _error(422, "Uma substituição conjunta aplica-se a todas as turmas.")
        for member in members:
            member_log = member["log"]
            if member_log is None or member_log.status != "OCCURRENCE" or member_log.decision:
                raise _error(
                    409,
                    "Todas as turmas têm de estar com ocorrência pendente para substituir.",
                )
    for member in members:
        if member["class_id"] in selected and member["log"] is None:
            raise _error(409, "A turma indicada não tem ocorrência para decidir.")
    for member in members:
        if member["class_id"] not in selected:
            continue
        member_log = member["log"]
        if member_log is None:
            raise _error(409, "A turma indicada não tem ocorrência para decidir.")
        line_found = await _find_item(db, organization_id, member_log.id, moment)
        if line_found is None:
            raise _error(404, OCCURRENCE_NOT_FOUND)
        line_item, line_year, line_version = line_found
        await _decide_line(
            db,
            organization_id,
            member_log.id,
            payload.model_copy(update={"class_ids": None, "version": member_log.revision}),
            line_item,
            line_year,
            line_version,
            moment,
            decided_by_membership_id,
        )
    return await get_occurrence(db, organization_id, occurrence_id, moment)


async def _decide_line(
    db: AsyncSession,
    organization_id: int,
    occurrence_id: int,
    payload: schemas.LessonOccurrenceUpdate,
    item: Mapping,
    year: models.SchedulerSchoolYear,
    version: SchedulerVersionV1,
    moment: datetime,
    decided_by_membership_id: int | None,
) -> dict:
    if item["status"] == "REVOKED":
        raise _error(409, "Ocorrência já revertida")
    log = await db.scalar(
        select(SchedulerLessonLogV1)
        .where(
            SchedulerLessonLogV1.id == occurrence_id,
            SchedulerLessonLogV1.organization_id == organization_id,
        )
        .with_for_update()
    )
    if log is None:
        raise _error(404, OCCURRENCE_NOT_FOUND)
    if log.withdrawn_at is not None and payload.status != models.LessonOccurrenceStatus.GAP:
        raise _error(409, "A aula foi retirada por fluxo de estágio.")
    membership_id = decided_by_membership_id or log.logged_by_membership_id
    if _is_repeated_v1_decision(item, log, payload):
        return item
    if payload.version != log.revision:
        raise _error(409, "OCCURRENCE_STALE_VERSION")
    target = payload.status.value
    if target == "REVOKED":
        raise _error(422, "Use o cancelamento para reverter a ocorrência.")
    block = (await _active_blocks_for_logs(db, organization_id, [occurrence_id])).get(occurrence_id)
    context = (year, version, ZoneInfo(year.timezone))
    await _require_open_week(
        db,
        organization_id,
        teacher_id=item["planned_teacher_id"],
        lesson_date=item["date"],
    )
    if target == "GIVEN":
        if log.decision == "SUBSTITUTED" or block is not None:
            raise _error(422, "Uma substituição registada não pode passar a aula dada.")
        if not execution_allowed(moment, item["ends_at"]):
            raise _lesson_not_finished_error()
        if log.decision == "GAP":
            await _cancel_debt_claim(
                db,
                organization_id,
                year.id,
                log,
                membership_id=membership_id,
                reason="Aula dada depois de furo",
                now_utc=moment,
            )
        await record_lesson_log(
            db,
            organization_id,
            membership_id=membership_id,
            lesson_id=log.lesson_id,
            status="COMPLETED",
            summary=log.summary,
            notes=log.notes,
            now_utc=moment,
            planning_relevant=True,
            allow_decision_override=True,
            include_siblings=False,
        )
        # record_lesson_log already advanced the revision.
        log.decision = "GIVEN"
    else:
        if target == "SUBSTITUTED":
            await _require_open_week(
                db,
                organization_id,
                teacher_id=payload.substitute_teacher_id,
                lesson_date=item["date"],
            )
        if (
            log.decision == "SUBSTITUTED"
            and block is not None
            and block.execution_status == models.OperationalBlockExecutionStatus.COMPLETED
        ):
            raise _error(
                409,
                "A substituição já tem execução concluída. "
                "Reverta a ocorrência com confirmação explícita.",
            )
        if log.decision == "GIVEN" or log.status == "COMPLETED":
            lesson_ctx = await lesson_context(db, organization_id, log.lesson_id)
            await reverse_lesson_execution(
                db,
                organization_id,
                lesson_ctx,
                membership_id=membership_id,
                now_utc=moment,
            )
            log.status = "OCCURRENCE"
        if log.decision == "SUBSTITUTED" or block is not None:
            await _cancel_blocks_for_log(
                db,
                organization_id,
                occurrence_id=occurrence_id,
                membership_id=membership_id,
                now_utc=moment,
            )
        await _reverse_substitutions(
            db,
            organization_id,
            occurrence_id=occurrence_id,
            membership_id=membership_id,
            now_utc=moment,
        )
        if target == "SUBSTITUTED":
            await _plan_substitution(
                db,
                organization_id,
                context,
                item,
                payload,
                membership_id=membership_id,
                now_utc=moment,
                revision=log.revision,
            )
            claim_reason = "Substituição planeada"
        else:
            claim_reason = "Furo decidido"
        await _ensure_debt_claim(
            db,
            organization_id,
            year.id,
            item,
            log,
            membership_id=membership_id,
            reason=claim_reason,
            now_utc=moment,
        )
        log.decision = target
        log.revision += 1
    log.decided_at = moment
    log.decided_by_membership_id = membership_id
    log.updated_at = moment
    await db.flush()
    return await get_occurrence(db, organization_id, occurrence_id, moment)


async def cancel_occurrence(
    db: AsyncSession,
    organization_id: int,
    occurrence_id: int,
    *,
    version: int,
    reason: str,
    cancelled_by_membership_id: int | None = None,
    cancel_completed_substitute_log: bool = False,
    now_utc: datetime | None = None,
) -> dict:
    moment = now_utc or datetime.now(UTC)
    found = await _find_item(db, organization_id, occurrence_id, moment)
    if found is None:
        raise _error(404, OCCURRENCE_NOT_FOUND)
    item, year, _ = found
    # Lock the school-year state row before any mutable log row (state -> logs).
    await lock_school_year_state(db, organization_id, year.id)
    log = await db.scalar(
        select(SchedulerLessonLogV1)
        .where(
            SchedulerLessonLogV1.id == occurrence_id,
            SchedulerLessonLogV1.organization_id == organization_id,
        )
        .with_for_update()
    )
    if log is None:
        raise _error(404, OCCURRENCE_NOT_FOUND)
    if log.status == "REVOKED":
        await _require_open_week(
            db,
            organization_id,
            teacher_id=item["planned_teacher_id"],
            lesson_date=item["date"],
        )
        await _cancel_debt_claim(
            db,
            organization_id,
            year.id,
            log,
            membership_id=cancelled_by_membership_id or log.logged_by_membership_id,
            reason="Reconciliação de dívida de ocorrência revertida",
            now_utc=moment,
        )
        return {"cancelled": True, "revision": log.revision}
    if version != log.revision:
        raise _error(409, "OCCURRENCE_STALE_VERSION")
    membership_id = cancelled_by_membership_id or log.logged_by_membership_id
    block = (await _active_blocks_for_logs(db, organization_id, [occurrence_id])).get(occurrence_id)
    await _require_open_week(
        db,
        organization_id,
        teacher_id=item["planned_teacher_id"],
        lesson_date=item["date"],
    )
    if block is not None:
        await _require_open_week(
            db,
            organization_id,
            teacher_id=block.teacher_id,
            lesson_date=block.date,
        )
    completed = (
        block is not None
        and block.execution_status == models.OperationalBlockExecutionStatus.COMPLETED
    )
    if completed and not cancel_completed_substitute_log:
        raise _error(
            409,
            "SUBSTITUTE_LOG_LOCKED",
        )
    await _cancel_blocks_for_log(
        db,
        organization_id,
        occurrence_id=occurrence_id,
        membership_id=membership_id,
        now_utc=moment,
    )
    if block is not None or log.decision == "SUBSTITUTED":
        await _reverse_substitutions(
            db,
            organization_id,
            occurrence_id=occurrence_id,
            membership_id=membership_id,
            now_utc=moment,
        )
    if log.decision == "GIVEN" or log.status == "COMPLETED":
        context = await lesson_context(db, organization_id, log.lesson_id)
        await reverse_lesson_execution(
            db,
            organization_id,
            context,
            membership_id=membership_id,
            now_utc=moment,
        )
    # Reversing execution can reopen settlements. Cancel the resulting balance last.
    await _cancel_debt_claim(
        db,
        organization_id,
        year.id,
        log,
        membership_id=membership_id,
        reason="Ocorrência revertida",
        now_utc=moment,
    )
    log.status = "REVOKED"
    log.revoked_at = moment
    log.revoked_by_membership_id = membership_id
    log.revoked_reason = (reason or "Reversão administrativa")[:250]
    log.revision += 1
    log.updated_at = moment
    await db.flush()
    return {
        "cancelled": True,
        "revision": log.revision,
    }


async def get_substitute_recommendations(
    db: AsyncSession, organization_id: int, occurrence_id: int
) -> list[dict]:
    found = await _find_item(db, organization_id, occurrence_id)
    if found is None:
        raise _error(404, OCCURRENCE_NOT_FOUND)
    item, year, version = found
    context = (year, version, ZoneInfo(year.timezone))
    rows = (
        await db.execute(
            select(models.Teacher, models.Subject, CurricularAssignment)
            .join(
                models.Teacher,
                and_(
                    models.Teacher.organization_id == organization_id,
                    models.Teacher.id == CurricularAssignment.teacher_id,
                ),
            )
            .join(
                models.Subject,
                and_(
                    models.Subject.organization_id == organization_id,
                    models.Subject.id == CurricularAssignment.subject_id,
                ),
            )
            .where(
                CurricularAssignment.organization_id == organization_id,
                CurricularAssignment.school_year_id == year.id,
                CurricularAssignment.class_id == item["class_id"],
                CurricularAssignment.teacher_id != item["planned_teacher_id"],
                CurricularAssignment.subject_id != item["subject_id"],
            )
        )
    ).all()
    recommendations: list[dict] = []
    for teacher, subject, _assignment in rows:
        exclusions = await _substitute_exclusions(
            db,
            organization_id,
            context,
            item,
            teacher_id=teacher.id,
            subject_id=subject.id,
        )
        if exclusions:
            continue
        recommendations.append(
            {
                "rank": len(recommendations) + 1,
                "teacher_id": teacher.id,
                "teacher_name": teacher.name,
                "subject_id": subject.id,
                "subject_name": subject.name,
                "class_id": item["class_id"],
                "class_name": item["class_name"],
                "substitutions_in_period": 0,
                "daily_load_hours": 0.0,
                "days_since_last_substitution": None,
                "justification": "Disponível para o período da aula.",
            }
        )
    return recommendations


async def get_substitute_diagnostics(
    db: AsyncSession, organization_id: int, occurrence_id: int
) -> dict:
    """Every candidate with the structured reasons that exclude them."""
    found = await _find_item(db, organization_id, occurrence_id)
    if found is None:
        raise _error(404, OCCURRENCE_NOT_FOUND)
    item, year, version = found
    context = (year, version, ZoneInfo(year.timezone))
    rows = (
        await db.execute(
            select(models.Teacher, models.Subject, CurricularAssignment)
            .join(
                models.Teacher,
                and_(
                    models.Teacher.organization_id == organization_id,
                    models.Teacher.id == CurricularAssignment.teacher_id,
                ),
            )
            .join(
                models.Subject,
                and_(
                    models.Subject.organization_id == organization_id,
                    models.Subject.id == CurricularAssignment.subject_id,
                ),
            )
            .where(
                CurricularAssignment.organization_id == organization_id,
                CurricularAssignment.school_year_id == year.id,
                CurricularAssignment.class_id == item["class_id"],
                CurricularAssignment.teacher_id != item["planned_teacher_id"],
                CurricularAssignment.subject_id != item["subject_id"],
            )
        )
    ).all()
    candidates: list[dict] = []
    for teacher, subject, _assignment in rows:
        exclusions = await _substitute_exclusions(
            db,
            organization_id,
            context,
            item,
            teacher_id=teacher.id,
            subject_id=subject.id,
        )
        candidates.append(
            {
                "teacher_id": teacher.id,
                "teacher_name": teacher.name,
                "subject_id": subject.id,
                "subject_name": subject.name,
                "eligible": not exclusions,
                "exclusions": exclusions,
            }
        )
    eligible = [candidate for candidate in candidates if candidate["eligible"]]
    return {
        "occurrence_id": occurrence_id,
        "eligible_count": len(eligible),
        "candidates": candidates,
        "setup_actions": sorted(
            {
                exclusion["setup"]
                for candidate in candidates
                for exclusion in candidate["exclusions"]
            }
        ),
    }
