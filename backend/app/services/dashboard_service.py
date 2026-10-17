"""Serviço de Dashboard V1 — agrega métricas chave para o painel do diretor."""

from collections import defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app import models, schemas
from app.scheduler.infrastructure import occurrences as occurrences_v1
from app.scheduler.infrastructure.models import (
    CurricularAssignment,
    CurricularExecution,
    CurricularExecutionCredit,
    SchedulerLessonLogV1,
    SchedulerLessonV1,
    SchedulerProposalV1,
    SchedulerVersionV1,
)
from app.services.preflight_service import PreflightService
from app.services.school_readiness_service import SchoolReadinessService


async def get_dashboard_summary(
    db: AsyncSession,
    organization_id: int,
) -> schemas.DashboardResponse:
    """Resolve o modo do dashboard e agrega os dados da organização autenticada."""
    organization = await db.get(models.Organization, organization_id)
    if organization is None:
        raise RuntimeError(f"Organization {organization_id} not found")

    bases = None
    prevalidation = None
    debt_summary = None
    if organization.first_real_schedule_approved_at is None:
        bases = await SchoolReadinessService(db).evaluate_bases(
            organization_id,
            resolve_fingerprint=False,
        )
        prevalidation = await PreflightService(db).evaluate(
            organization_id=organization_id,
            resolve_fingerprint=False,
        )
    else:
        debt_list = await occurrences_v1.get_debts(db, organization_id)
        debt_summary = schemas.DebtSummary(
            **{key: value for key, value in debt_list.items() if key != "items"},
            affected_classes_count=len({item["class_id"] for item in debt_list["items"]}),
        )

    def _run(sync_db):
        snapshot = (
            organization.name,
            organization.foundation_status,
            organization.foundation_completed_at,
            organization.first_real_schedule_approved_at,
        )
        return get_dashboard_summary_sync(
            sync_db,
            organization_id,
            bases=bases,
            prevalidation=prevalidation,
            organization_snapshot=snapshot,
            debt_summary=debt_summary,
        )

    return await db.run_sync(_run)


def get_dashboard_summary_sync(
    db: Session,
    organization_id: int,
    *,
    bases: schemas.BasesReadinessResponse | None = None,
    prevalidation: schemas.PreflightReport | None = None,
    debt_summary: schemas.DebtSummary | None = None,
    organization_snapshot: tuple[
        str,
        models.OrganizationFoundationStatus,
        datetime | None,
        datetime | None,
    ]
    | None = None,
) -> schemas.DashboardResponse:
    """Retorna estatísticas agregadas para o dashboard principal (PREPARATION vs OPERATIONAL discriminada)."""
    today = date.today()

    if organization_snapshot is None:
        org = db.scalar(
            select(models.Organization).where(models.Organization.id == organization_id)
        )
        organization_snapshot = (
            org.name if org else "Escola",
            org.foundation_status if org else models.OrganizationFoundationStatus.NOT_STARTED,
            org.foundation_completed_at if org else None,
            org.first_real_schedule_approved_at if org else None,
        )
    org_name, foundation_status, foundation_completed_at, first_real_approved_at = (
        organization_snapshot
    )

    if first_real_approved_at is None:
        if bases is None:
            raise ValueError("Preparation dashboard requires canonical readiness bases")
        if prevalidation is None:
            raise ValueError("Preparation dashboard requires canonical prevalidation")
        return schemas.PreparationDashboardResponse(
            mode="PREPARATION",
            organization_name=org_name,
            foundation_status=foundation_status,
            foundation_completed_at=foundation_completed_at,
            bases=bases,
            prevalidation=prevalidation,
        )

    # Modo Operacional
    alerts, resources, _, _ = _get_overview(db, organization_id, today)
    schedule_health = _get_schedule_health(db, organization_id, today)
    class_progress = _get_class_progress(db, organization_id)
    if debt_summary is None:
        raise ValueError("Operational dashboard requires canonical v1 debt summary")
    debts = debt_summary

    return schemas.OperationalDashboardResponse(
        mode="OPERATIONAL",
        organization_name=org_name,
        first_real_schedule_approved_at=first_real_approved_at,
        alerts=alerts,
        resources=resources,
        schedule_health=schedule_health,
        class_progress=class_progress,
        debts=debts,
    )


def _count(model, *criteria):
    return select(func.count(model.id)).where(*criteria).scalar_subquery()


def _get_overview(
    db: Session,
    organization_id: int,
    today: date,
) -> tuple[schemas.AlertCounts, schemas.ResourceCounts, str, datetime | None]:
    active_lessons = (
        select(SchedulerLessonV1.id)
        .join(
            SchedulerVersionV1,
            (SchedulerVersionV1.id == SchedulerLessonV1.version_id)
            & (SchedulerVersionV1.organization_id == organization_id),
        )
        .where(
            SchedulerLessonV1.organization_id == organization_id,
            SchedulerVersionV1.status == "ACTIVE",
        )
    )
    today_lessons = active_lessons.where(SchedulerLessonV1.school_date == today)
    room_counts = (
        select(
            models.SchoolRoomType.name.label("room_type"),
            func.count(models.Room.id).label("room_count"),
        )
        .join(
            models.SchoolRoomType,
            and_(
                models.SchoolRoomType.organization_id == models.Room.organization_id,
                models.SchoolRoomType.id == models.Room.room_type_id,
            ),
        )
        .where(
            models.Room.organization_id == organization_id,
            models.Room.is_archived.is_(False),
        )
        .group_by(models.SchoolRoomType.name)
        .subquery()
    )
    rooms_by_type = (
        select(func.json_object_agg(room_counts.c.room_type, room_counts.c.room_count))
        .select_from(room_counts)
        .scalar_subquery()
    )
    row = db.execute(
        select(
            models.Organization.name,
            models.Organization.first_real_schedule_approved_at,
            _count(
                SchedulerLessonLogV1,
                SchedulerLessonLogV1.organization_id == organization_id,
                SchedulerLessonLogV1.lesson_id.in_(today_lessons),
                SchedulerLessonLogV1.status == "OCCURRENCE",
                SchedulerLessonLogV1.decision.is_(None),
            ),
            _count(
                SchedulerLessonLogV1,
                SchedulerLessonLogV1.organization_id == organization_id,
                SchedulerLessonLogV1.lesson_id.in_(active_lessons),
                SchedulerLessonLogV1.status == "OCCURRENCE",
                SchedulerLessonLogV1.decision.is_(None),
            ),
            _count(
                models.TeacherWeeklyTimesheet,
                models.TeacherWeeklyTimesheet.organization_id == organization_id,
                models.TeacherWeeklyTimesheet.status == models.TimesheetStatus.SUBMITTED,
            ),
            _count(
                SchedulerProposalV1,
                SchedulerProposalV1.organization_id == organization_id,
                SchedulerProposalV1.status == "PENDING",
            ),
            _count(
                SchedulerLessonLogV1,
                SchedulerLessonLogV1.organization_id == organization_id,
                SchedulerLessonLogV1.lesson_id.in_(today_lessons),
                SchedulerLessonLogV1.status == "OCCURRENCE",
                SchedulerLessonLogV1.decision == "SUBSTITUTED",
            ),
            _count(models.Teacher, models.Teacher.organization_id == organization_id),
            _count(
                models.Class,
                models.Class.organization_id == organization_id,
                models.Class.is_archived.is_(False),
            ),
            _count(
                models.Course,
                models.Course.organization_id == organization_id,
                models.Course.is_archived.is_(False),
            ),
            _count(
                models.Subject,
                models.Subject.organization_id == organization_id,
                models.Subject.is_archived.is_(False),
            ),
            _count(
                models.Room,
                models.Room.organization_id == organization_id,
                models.Room.is_archived.is_(False),
            ),
            rooms_by_type,
        ).where(models.Organization.id == organization_id)
    ).one()
    return (
        schemas.AlertCounts(
            pending_occurrences_today=row[2],
            pending_occurrences_total=row[3],
            pending_timesheets=row[4],
            pending_drafts=row[5],
            active_substitutions_today=row[6],
        ),
        schemas.ResourceCounts(
            teachers_count=row[7],
            classes_count=row[8],
            courses_count=row[9],
            subjects_count=row[10],
            rooms_count=row[11],
            rooms_by_type=row[12] or {},
        ),
        row[0],
        row[1],
    )


def _get_schedule_health(
    db: Session,
    organization_id: int,
    today: date,
) -> schemas.ScheduleHealthWidget | None:
    return _get_v1_schedule_health(db, organization_id, today)


def _get_v1_schedule_health(
    db: Session,
    organization_id: int,
    today: date,
) -> schemas.ScheduleHealthWidget | None:
    """Health from the v1 published version when it exists (preferred)."""
    version = db.execute(
        select(SchedulerVersionV1.id, SchedulerVersionV1.school_year_id).where(
            SchedulerVersionV1.organization_id == organization_id,
            SchedulerVersionV1.status == "ACTIVE",
        )
    ).first()
    if version is None:
        return None
    version_id, school_year_id = version
    rows = db.execute(
        select(
            SchedulerLessonV1.id.label("lesson_id"),
            CurricularAssignment.class_id,
            CurricularAssignment.teacher_id,
            SchedulerLessonV1.school_date,
            SchedulerLessonV1.starts_at,
            SchedulerLessonV1.ends_at,
            models.Class.is_archived,
            models.Class.name.label("class_name"),
            models.Teacher.name.label("teacher_name"),
            models.Subject.name.label("subject_name"),
        )
        .join(
            SchedulerLessonV1,
            and_(
                SchedulerLessonV1.organization_id == CurricularAssignment.organization_id,
                SchedulerLessonV1.school_year_id == CurricularAssignment.school_year_id,
                SchedulerLessonV1.assignment_id == CurricularAssignment.id,
            ),
        )
        .join(
            models.Class,
            and_(
                models.Class.organization_id == CurricularAssignment.organization_id,
                models.Class.id == CurricularAssignment.class_id,
            ),
        )
        .join(
            models.Teacher,
            and_(
                models.Teacher.organization_id == CurricularAssignment.organization_id,
                models.Teacher.id == CurricularAssignment.teacher_id,
            ),
        )
        .join(
            models.Subject,
            and_(
                models.Subject.organization_id == CurricularAssignment.organization_id,
                models.Subject.id == CurricularAssignment.subject_id,
            ),
        )
        .where(
            SchedulerLessonV1.organization_id == organization_id,
            SchedulerLessonV1.version_id == version_id,
        )
        .order_by(SchedulerLessonV1.school_date, SchedulerLessonV1.starts_at, SchedulerLessonV1.id)
    ).all()
    if not rows:
        return None
    # The annual denominator is the population present in the approved version,
    # not every assignment configured for the school year.
    class_ids = {row.class_id for row in rows}
    teacher_ids = {row.teacher_id for row in rows}
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    weekly_counts = defaultdict(int)
    teacher_slots = defaultdict(int)
    class_slots = defaultdict(int)
    for row in rows:
        if week_start <= row.school_date <= week_end:
            weekly_counts[row.class_id] += 1
        teacher_slots[(row.teacher_id, row.school_date, row.starts_at, row.ends_at)] += 1
        class_slots[(row.class_id, row.school_date, row.starts_at, row.ends_at)] += 1
    classes_total = len(class_ids)
    values = list(weekly_counts.values())
    week_total = sum(values)
    mean = week_total / classes_total if classes_total else 0.0
    variance = (
        sum((count - mean) ** 2 for count in values) / classes_total if classes_total > 1 else 0.0
    )
    period_start = min(row.school_date for row in rows)
    period_end = max(row.school_date for row in rows)
    conflicting_lessons = [
        schemas.ScheduleConflictLesson(
            lesson_id=row.lesson_id,
            class_name=row.class_name,
            teacher_id=row.teacher_id,
            teacher_name=row.teacher_name,
            subject_name=row.subject_name,
            school_date=row.school_date,
            starts_at=row.starts_at,
            ends_at=row.ends_at,
        )
        for row in rows
        if teacher_slots[(row.teacher_id, row.school_date, row.starts_at, row.ends_at)] > 1
        or class_slots[(row.class_id, row.school_date, row.starts_at, row.ends_at)] > 1
    ]
    return schemas.ScheduleHealthWidget(
        generation_id=f"v1-{version_id}",
        conflicting_lessons=conflicting_lessons,
        blocks_count=len(rows),
        classes_total=classes_total,
        classes_archived=len({row.class_id for row in rows if row.is_archived}),
        classes_empty_week=classes_total - len(weekly_counts),
        week_slots_avg=round(mean, 1),
        duplicate_teacher_slots=sum(count > 1 for count in teacher_slots.values()),
        duplicate_class_slots=sum(count > 1 for count in class_slots.values()),
        weekly_fairness_spread=round(variance**0.5, 1),
        teacher_week_slots_avg=(round(week_total / len(teacher_ids), 1) if teacher_ids else 0.0),
        annual_class_average=round(len(rows) / classes_total, 1) if classes_total else 0.0,
        annual_teacher_average=round(len(rows) / len(teacher_ids), 1) if teacher_ids else 0.0,
        teachers_total=len(teacher_ids),
        period_start=period_start,
        period_end=period_end,
    )


def _get_class_progress(
    db: Session,
    organization_id: int,
) -> list[schemas.ClassProgressSummary]:
    active_year = (
        select(models.SchedulerSchoolYear.id)
        .where(
            models.SchedulerSchoolYear.organization_id == organization_id,
            models.SchedulerSchoolYear.is_active.is_(True),
        )
        .scalar_subquery()
    )
    ledger = (
        select(
            CurricularExecution.assignment_id.label("assignment_id"),
            CurricularExecutionCredit.module_id.label("module_id"),
            func.sum(CurricularExecutionCredit.delta_minutes).label("minutes"),
        )
        .join(
            CurricularExecution,
            (CurricularExecution.id == CurricularExecutionCredit.execution_id)
            & (CurricularExecution.organization_id == organization_id),
        )
        .where(CurricularExecutionCredit.organization_id == organization_id)
        .group_by(CurricularExecution.assignment_id, CurricularExecutionCredit.module_id)
        .subquery()
    )
    rows = db.execute(
        select(
            models.Class.id,
            models.Class.name,
            models.Class.grade_level,
            models.Course.id,
            models.Course.name,
            func.coalesce(func.sum(ledger.c.minutes), 0),
            func.coalesce(func.sum(models.Module.required_minutes), 0),
        )
        .select_from(models.Class)
        .join(models.Course, models.Class.course_id == models.Course.id)
        # The live selection is authoritative: the projection is rebuilt only
        # on generation, so a module deselected or reselected since then must
        # already leave or rejoin the catalogue total without waiting for a new
        # sync. The executed minutes come from the v1 ledger, not the stale
        # requirement rows.
        .outerjoin(
            models.ClassSubjectLink,
            (models.ClassSubjectLink.organization_id == organization_id)
            & (models.ClassSubjectLink.class_id == models.Class.id)
            & (models.ClassSubjectLink.grade_level == models.Class.grade_level),
        )
        .outerjoin(
            models.class_subject_module,
            (models.class_subject_module.c.organization_id == organization_id)
            & (models.class_subject_module.c.class_subject_link_id == models.ClassSubjectLink.id),
        )
        .outerjoin(
            models.Module,
            (models.Module.organization_id == organization_id)
            & (models.Module.id == models.class_subject_module.c.module_id),
        )
        .outerjoin(
            CurricularAssignment,
            (CurricularAssignment.organization_id == organization_id)
            & (CurricularAssignment.class_id == models.Class.id)
            & (CurricularAssignment.subject_id == models.ClassSubjectLink.subject_id)
            & (CurricularAssignment.school_year_id == active_year),
        )
        .outerjoin(
            ledger,
            (ledger.c.assignment_id == CurricularAssignment.id)
            & (ledger.c.module_id == models.Module.id),
        )
        .where(models.Class.organization_id == organization_id, models.Class.is_archived.is_(False))
        .group_by(
            models.Class.id,
            models.Class.name,
            models.Class.grade_level,
            models.Course.id,
            models.Course.name,
        )
    ).all()
    return [
        schemas.ClassProgressSummary(
            class_id=row[0],
            class_name=row[1],
            grade_level=row[2],
            course_id=row[3],
            course_name=row[4],
            overall_percentage=(
                min(100.0, round(int(row[5]) / int(row[6]) * 100, 1)) if row[6] else 0.0
            ),
            completed_hours=round(int(row[5]) / 60, 1),
            total_hours=round(int(row[6]) / 60, 1),
        )
        for row in rows
    ]
