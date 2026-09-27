"""ServiÃ§o de Dashboard V1 â€” agrega mÃ©tricas chave para o painel do diretor."""

from collections import defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import String, and_, cast, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app import models, schemas
from app.scheduler.infrastructure.models import (
    CurricularAssignment,
    SchedulerLessonV1,
    SchedulerProposalV1,
    SchedulerVersionV1,
)
from app.services import occurrence_service
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
    if organization.first_real_schedule_approved_at is None:
        bases = await SchoolReadinessService(db).evaluate_bases(
            organization_id,
            resolve_fingerprint=False,
        )
        prevalidation = await PreflightService(db).evaluate(
            organization_id=organization_id,
            resolve_fingerprint=False,
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
        )

    return await db.run_sync(_run)


def get_dashboard_summary_sync(
    db: Session,
    organization_id: int,
    *,
    bases: schemas.BasesReadinessResponse | None = None,
    prevalidation: schemas.PreflightReport | None = None,
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
    debts = _get_debt_summary(db, organization_id, today)

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
    room_counts = (
        select(
            cast(models.Room.type, String).label("room_type"),
            func.count(models.Room.id).label("room_count"),
        )
        .where(models.Room.organization_id == organization_id)
        .group_by(models.Room.type)
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
                models.LessonOccurrence,
                models.LessonOccurrence.organization_id == organization_id,
                models.LessonOccurrence.date == today,
                models.LessonOccurrence.decided_at.is_(None),
            ),
            _count(
                models.LessonOccurrence,
                models.LessonOccurrence.organization_id == organization_id,
                models.LessonOccurrence.is_active.is_(True),
                models.LessonOccurrence.decided_at.is_(None),
            ),
            _count(
                models.TeacherWeeklyTimesheet,
                models.TeacherWeeklyTimesheet.organization_id == organization_id,
                models.TeacherWeeklyTimesheet.status == models.TimesheetStatus.SUBMITTED,
            ),
            _count(
                models.ScheduleDraft,
                models.ScheduleDraft.organization_id == organization_id,
                models.ScheduleDraft.draft_state == models.ScheduleDraftState.PENDING,
            ),
            _count(
                models.LessonOccurrence,
                models.LessonOccurrence.organization_id == organization_id,
                models.LessonOccurrence.is_active.is_(True),
                models.LessonOccurrence.date == today,
                models.LessonOccurrence.status == models.LessonOccurrenceStatus.SUBSTITUTED,
            ),
            _count(models.Teacher, models.Teacher.organization_id == organization_id),
            _count(models.Class, models.Class.organization_id == organization_id),
            _count(models.Course, models.Course.organization_id == organization_id),
            _count(models.Subject, models.Subject.organization_id == organization_id),
            _count(models.Room, models.Room.organization_id == organization_id),
            rooms_by_type,
        ).where(models.Organization.id == organization_id)
    ).one()
    v1_pending_proposals = db.execute(
        select(func.count())
        .select_from(SchedulerProposalV1)
        .where(
            SchedulerProposalV1.organization_id == organization_id,
            SchedulerProposalV1.status == "PENDING",
        )
    ).scalar_one()
    return (
        schemas.AlertCounts(
            pending_occurrences_today=row[2],
            pending_occurrences_total=row[3],
            pending_timesheets=row[4],
            pending_drafts=row[5] + int(v1_pending_proposals or 0),
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
    v1_health = _get_v1_schedule_health(db, organization_id, today)
    if v1_health is not None:
        return v1_health
    latest_version = (
        select(models.ActiveScheduleBlock.schedule_version_id)
        .where(
            models.ActiveScheduleBlock.organization_id == organization_id,
            models.ActiveScheduleBlock.status == models.ActiveScheduleBlockStatus.ACTIVE,
        )
        .order_by(desc(models.ActiveScheduleBlock.id))
        .limit(1)
        .scalar_subquery()
    )

    blocks = list(
        db.execute(
            select(
                models.ActiveScheduleBlock.schedule_version_id,
                models.ActiveScheduleBlock.class_id,
                models.ActiveScheduleBlock.teacher_id,
                models.ActiveScheduleBlock.date,
                models.ActiveScheduleBlock.timeslot_id,
            ).where(
                models.ActiveScheduleBlock.organization_id == organization_id,
                models.ActiveScheduleBlock.status == models.ActiveScheduleBlockStatus.ACTIVE,
                models.ActiveScheduleBlock.schedule_version_id == latest_version,
            )
        ).all()
    )
    if not blocks:
        return None
    generation_id = blocks[0].schedule_version_id
    blocks_count = len(blocks)
    class_ids = {row.class_id for row in blocks}
    teacher_ids = {row.teacher_id for row in blocks}
    week_start = today - timedelta(days=today.weekday())
    weekly_counts = defaultdict(int)
    teacher_slots = defaultdict(int)
    class_slots = defaultdict(int)
    for row in blocks:
        if row.date >= week_start:
            weekly_counts[row.class_id] += 1
        teacher_slots[(row.teacher_id, row.date, row.timeslot_id)] += 1
        class_slots[(row.class_id, row.date, row.timeslot_id)] += 1

    classes_total = len(class_ids)
    values = list(weekly_counts.values())
    week_total = sum(values)
    mean = week_total / classes_total if classes_total else 0.0
    variance = (
        sum((count - mean) ** 2 for count in values) / classes_total if classes_total > 1 else 0.0
    )
    return schemas.ScheduleHealthWidget(
        generation_id=generation_id,
        blocks_count=blocks_count,
        classes_total=classes_total,
        classes_empty_week=classes_total - len(weekly_counts),
        week_slots_avg=round(mean, 1),
        duplicate_teacher_slots=sum(count > 1 for count in teacher_slots.values()),
        duplicate_class_slots=sum(count > 1 for count in class_slots.values()),
        weekly_fairness_spread=round(variance**0.5, 1),
        teacher_week_slots_avg=(round(blocks_count / len(teacher_ids), 1) if teacher_ids else 0.0),
    )


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
            CurricularAssignment.class_id,
            CurricularAssignment.teacher_id,
            SchedulerLessonV1.school_date,
            SchedulerLessonV1.starts_at,
            SchedulerLessonV1.ends_at,
        )
        .join(
            SchedulerLessonV1,
            and_(
                SchedulerLessonV1.organization_id == CurricularAssignment.organization_id,
                SchedulerLessonV1.school_year_id == CurricularAssignment.school_year_id,
                SchedulerLessonV1.assignment_id == CurricularAssignment.id,
            ),
        )
        .where(
            SchedulerLessonV1.organization_id == organization_id,
            SchedulerLessonV1.version_id == version_id,
        )
    ).all()
    class_ids = set(
        db.execute(
            select(CurricularAssignment.class_id).where(
                CurricularAssignment.organization_id == organization_id,
                CurricularAssignment.school_year_id == school_year_id,
            )
        ).scalars()
    )
    if not rows or not class_ids:
        return None
    teacher_ids = {row.teacher_id for row in rows}
    week_start = today - timedelta(days=today.weekday())
    weekly_counts = defaultdict(int)
    teacher_slots = defaultdict(int)
    class_slots = defaultdict(int)
    for row in rows:
        if row.school_date >= week_start:
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
    return schemas.ScheduleHealthWidget(
        generation_id=f"v1-{version_id}",
        blocks_count=len(rows),
        classes_total=classes_total,
        classes_empty_week=classes_total - len(weekly_counts),
        week_slots_avg=round(mean, 1),
        duplicate_teacher_slots=sum(count > 1 for count in teacher_slots.values()),
        duplicate_class_slots=sum(count > 1 for count in class_slots.values()),
        weekly_fairness_spread=round(variance**0.5, 1),
        teacher_week_slots_avg=(round(len(rows) / len(teacher_ids), 1) if teacher_ids else 0.0),
    )


def _get_class_progress(
    db: Session,
    organization_id: int,
) -> list[schemas.ClassProgressSummary]:
    ledger = (
        select(
            models.ProgressLedgerEntry.class_id.label("class_id"),
            models.ProgressLedgerEntry.module_id.label("module_id"),
            func.sum(models.ProgressLedgerEntry.completed_minutes_delta).label("minutes"),
        )
        .where(models.ProgressLedgerEntry.organization_id == organization_id)
        .group_by(
            models.ProgressLedgerEntry.class_id,
            models.ProgressLedgerEntry.module_id,
        )
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
        .outerjoin(
            models.ClassSubjectLink,
            and_(
                models.ClassSubjectLink.class_id == models.Class.id,
                models.ClassSubjectLink.grade_level == models.Class.grade_level,
            ),
        )
        .outerjoin(models.Module, models.Module.subject_id == models.ClassSubjectLink.subject_id)
        .outerjoin(
            ledger,
            and_(
                ledger.c.class_id == models.Class.id,
                ledger.c.module_id == models.Module.id,
            ),
        )
        .where(models.Class.organization_id == organization_id)
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


def _get_debt_summary(
    db: Session,
    organization_id: int,
    today: date,
) -> schemas.DebtSummary:
    """Resumo de dÃ­vidas de horas."""

    debt_list = occurrence_service.get_debts_sync(db, organization_id)

    affected_class_ids = set()
    for item in debt_list.items:
        affected_class_ids.add(item.class_id)

    return schemas.DebtSummary(
        total_gaps=debt_list.total_gaps,
        total_hours_owed=debt_list.total_hours_owed,
        total_gaps_overdue=debt_list.total_gaps_overdue,
        total_hours_owed_overdue=debt_list.total_hours_owed_overdue,
        affected_classes_count=len(affected_class_ids),
        as_of_date=today,
    )
