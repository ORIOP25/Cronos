"""Serviço de Dashboard V1 — agrega métricas chave para o painel do diretor."""
from collections import defaultdict
from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import select, func, and_, distinct, desc

from app import models
from app import schemas
from app.services import occurrence_service


def get_dashboard_summary_sync(
    db: Session,
    organization_id: int,
) -> schemas.DashboardV1Response:
    """Retorna estatísticas agregadas para o dashboard principal."""
    today = date.today()

    alerts = _get_alert_counts(db, organization_id, today)
    resources = _get_resource_counts(db, organization_id)
    schedule_health = _get_schedule_health(db, organization_id, today)
    class_progress = _get_class_progress(db, organization_id)
    debts = _get_debt_summary(db, organization_id, today)

    org_name = db.scalar(
        select(models.Organization.name).where(
            models.Organization.id == organization_id
        )
    ) or ""

    return schemas.DashboardV1Response(
        alerts=alerts,
        resources=resources,
        schedule_health=schedule_health,
        class_progress=class_progress,
        debts=debts,
        organization_name=org_name,
    )


def _get_alert_counts(
    db: Session,
    organization_id: int,
    today: date,
) -> schemas.AlertCounts:
    """Contagens para a barra de alertas do dashboard."""

    pending_occurrences_today = db.scalar(
        select(func.count(models.LessonOccurrence.id)).where(
            and_(
                models.LessonOccurrence.organization_id == organization_id,
                models.LessonOccurrence.date == today,
            )
        )
    ) or 0

    pending_timesheets = db.scalar(
        select(func.count(models.TeacherWeeklyTimesheet.id)).where(
            and_(
                models.TeacherWeeklyTimesheet.organization_id == organization_id,
                models.TeacherWeeklyTimesheet.status == models.TimesheetStatus.SUBMITTED,
            )
        )
    ) or 0

    pending_drafts = db.scalar(
        select(func.count(distinct(models.ScheduleOutput.generation_id))).where(
            and_(
                models.ScheduleOutput.organization_id == organization_id,
                models.ScheduleOutput.is_draft.is_(True),
            )
        )
    ) or 0

    active_substitutions_today = db.scalar(
        select(func.count(models.LessonOccurrence.id)).where(
            and_(
                models.LessonOccurrence.organization_id == organization_id,
                models.LessonOccurrence.date == today,
                models.LessonOccurrence.status == models.LessonOccurrenceStatus.SUBSTITUTED,
            )
        )
    ) or 0

    return schemas.AlertCounts(
        pending_occurrences_today=pending_occurrences_today,
        pending_timesheets=pending_timesheets,
        pending_drafts=pending_drafts,
        active_substitutions_today=active_substitutions_today,
    )


def _get_resource_counts(
    db: Session,
    organization_id: int,
) -> schemas.ResourceCounts:
    """Contagens de entidades e distribuição de salas por tipo."""

    teachers_count = db.scalar(
        select(func.count(models.Teacher.id)).where(
            models.Teacher.organization_id == organization_id
        )
    ) or 0

    classes_count = db.scalar(
        select(func.count(models.Class.id)).where(
            models.Class.organization_id == organization_id
        )
    ) or 0

    courses_count = db.scalar(
        select(func.count(models.Course.id)).where(
            models.Course.organization_id == organization_id
        )
    ) or 0

    subjects_count = db.scalar(
        select(func.count(models.Subject.id)).where(
            models.Subject.organization_id == organization_id
        )
    ) or 0

    rooms_count = db.scalar(
        select(func.count(models.Room.id)).where(
            models.Room.organization_id == organization_id
        )
    ) or 0

    rooms_by_type_rows = db.execute(
        select(
            models.Room.type,
            func.count(models.Room.id),
        ).where(
            models.Room.organization_id == organization_id
        ).group_by(models.Room.type)
    ).all()

    rooms_by_type: dict[str, int] = {}
    for room_type, count in rooms_by_type_rows:
        rooms_by_type[room_type.value] = count

    return schemas.ResourceCounts(
        teachers_count=teachers_count,
        classes_count=classes_count,
        courses_count=courses_count,
        subjects_count=subjects_count,
        rooms_count=rooms_count,
        rooms_by_type=rooms_by_type,
    )


def _get_schedule_health(
    db: Session,
    organization_id: int,
    today: date,
) -> Optional[schemas.ScheduleHealthWidget]:
    """Métricas de saúde da última geração ativa."""

    latest_gen = db.scalar(
        select(models.ScheduleOutput.generation_id).where(
            and_(
                models.ScheduleOutput.organization_id == organization_id,
                models.ScheduleOutput.is_draft.is_(False),
            )
        ).order_by(desc(models.ScheduleOutput.id)).limit(1)
    )

    if latest_gen is None:
        return None

    generation_id = latest_gen

    blocks_count = db.scalar(
        select(func.count(models.ScheduleOutput.id)).where(
            and_(
                models.ScheduleOutput.organization_id == organization_id,
                models.ScheduleOutput.is_draft.is_(False),
                models.ScheduleOutput.generation_id == generation_id,
            )
        )
    ) or 0

    classes_total = db.scalar(
        select(func.count(distinct(models.Lesson.class_id))).select_from(
            models.ScheduleOutput
        ).join(
            models.Lesson,
            models.ScheduleOutput.lesson_id == models.Lesson.id,
        ).where(
            and_(
                models.ScheduleOutput.organization_id == organization_id,
                models.ScheduleOutput.is_draft.is_(False),
                models.ScheduleOutput.generation_id == generation_id,
            )
        )
    ) or 0

    week_start = today - timedelta(days=today.weekday())

    slots_per_class_rows = db.execute(
        select(
            models.Lesson.class_id,
            func.count(models.ScheduleOutput.id),
        ).select_from(models.ScheduleOutput).join(
            models.Lesson,
            models.ScheduleOutput.lesson_id == models.Lesson.id,
        ).where(
            and_(
                models.ScheduleOutput.organization_id == organization_id,
                models.ScheduleOutput.is_draft.is_(False),
                models.ScheduleOutput.generation_id == generation_id,
                models.ScheduleOutput.date >= week_start,
            )
        ).group_by(models.Lesson.class_id)
    ).all()

    week_slots_total = sum(count for _, count in slots_per_class_rows)
    classes_with_slots = len([c for c, count in slots_per_class_rows if count > 0])
    classes_empty_week = classes_total - classes_with_slots

    week_slots_avg = round(week_slots_total / classes_total, 1) if classes_total > 0 else 0.0

    slot_counts = [count for _, count in slots_per_class_rows]
    if len(slot_counts) > 1 and classes_total > 0:
        mean = week_slots_total / classes_total
        variance = sum((c - mean) ** 2 for c in slot_counts) / classes_total
        weekly_fairness_spread = round(variance ** 0.5, 1)
    else:
        weekly_fairness_spread = 0.0

    dup_rows = db.execute(
        select(
            models.Lesson.teacher_id,
            models.ScheduleOutput.date,
            models.ScheduleOutput.timeslot_id,
            func.count(models.ScheduleOutput.id),
        ).select_from(models.ScheduleOutput).join(
            models.Lesson,
            models.ScheduleOutput.lesson_id == models.Lesson.id,
        ).where(
            and_(
                models.ScheduleOutput.organization_id == organization_id,
                models.ScheduleOutput.is_draft.is_(False),
                models.ScheduleOutput.generation_id == generation_id,
            )
        ).group_by(
            models.Lesson.teacher_id,
            models.ScheduleOutput.date,
            models.ScheduleOutput.timeslot_id,
        ).having(
            func.count(models.ScheduleOutput.id) > 1
        )
    ).all()

    duplicate_teacher_slots = len(dup_rows)

    dup_class_rows = db.execute(
        select(
            models.Lesson.class_id,
            models.ScheduleOutput.date,
            models.ScheduleOutput.timeslot_id,
            func.count(models.ScheduleOutput.id),
        ).select_from(models.ScheduleOutput).join(
            models.Lesson,
            models.ScheduleOutput.lesson_id == models.Lesson.id,
        ).where(
            and_(
                models.ScheduleOutput.organization_id == organization_id,
                models.ScheduleOutput.is_draft.is_(False),
                models.ScheduleOutput.generation_id == generation_id,
            )
        ).group_by(
            models.Lesson.class_id,
            models.ScheduleOutput.date,
            models.ScheduleOutput.timeslot_id,
        ).having(
            func.count(models.ScheduleOutput.id) > 1
        )
    ).all()

    duplicate_class_slots = len(dup_class_rows)

    distinct_teachers = db.scalar(
        select(func.count(distinct(models.Lesson.teacher_id))).select_from(
            models.ScheduleOutput
        ).join(
            models.Lesson,
            models.ScheduleOutput.lesson_id == models.Lesson.id,
        ).where(
            and_(
                models.ScheduleOutput.organization_id == organization_id,
                models.ScheduleOutput.is_draft.is_(False),
                models.ScheduleOutput.generation_id == generation_id,
            )
        )
    ) or 0

    teacher_week_slots_avg = (
        round(blocks_count / distinct_teachers, 1) if distinct_teachers > 0 else 0.0
    )

    return schemas.ScheduleHealthWidget(
        generation_id=generation_id,
        blocks_count=blocks_count,
        classes_total=classes_total,
        classes_empty_week=classes_empty_week,
        week_slots_avg=week_slots_avg,
        duplicate_teacher_slots=duplicate_teacher_slots,
        duplicate_class_slots=duplicate_class_slots,
        weekly_fairness_spread=weekly_fairness_spread,
        teacher_week_slots_avg=teacher_week_slots_avg,
    )


def _get_class_progress(
    db: Session,
    organization_id: int,
) -> list[schemas.ClassProgressSummary]:
    """Progresso curricular agregado por turma."""

    rows = db.execute(
        select(
            models.Class.id,
            models.Class.name,
            models.Class.grade_level,
            models.Course.id,
            models.Course.name,
            func.coalesce(func.sum(models.ClassProgress.hours_completed), 0.0),
            func.coalesce(func.sum(models.Module.hours_total), 0.0),
        ).select_from(models.Class).join(
            models.Course, models.Class.course_id == models.Course.id
        ).outerjoin(
            models.ClassProgress, models.ClassProgress.class_id == models.Class.id
        ).outerjoin(
            models.Module, models.ClassProgress.module_id == models.Module.id
        ).where(
            models.Class.organization_id == organization_id
        ).group_by(
            models.Class.id,
            models.Class.name,
            models.Class.grade_level,
            models.Course.id,
            models.Course.name,
        ).order_by(
            (func.coalesce(func.sum(models.ClassProgress.hours_completed), 0.0)
             / func.nullif(func.coalesce(func.sum(models.Module.hours_total), 1.0), 0.0))
        )
    ).all()

    result: list[schemas.ClassProgressSummary] = []
    for (
        class_id, class_name, grade_level,
        course_id, course_name,
        completed_hours, total_hours,
    ) in rows:
        pct = round((completed_hours / total_hours * 100), 1) if total_hours > 0 else 0.0
        result.append(schemas.ClassProgressSummary(
            class_id=class_id,
            class_name=class_name,
            course_id=course_id,
            course_name=course_name,
            grade_level=grade_level,
            overall_percentage=min(pct, 100.0),
            completed_hours=round(completed_hours or 0.0, 1),
            total_hours=round(total_hours or 0.0, 1),
        ))

    return result


def _get_debt_summary(
    db: Session,
    organization_id: int,
    today: date,
) -> schemas.DebtSummary:
    """Resumo de dívidas de horas."""

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
