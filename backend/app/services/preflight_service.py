from datetime import date
from sqlalchemy import func, select as sa_select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog
from app import models
from app.services import schedule_service, settings_service
from app.services.scheduler_planning import (
    build_blocked_dates as _build_blocked_dates,
    build_primary_window as _build_primary_window,
    compute_remaining_minutes as _compute_remaining_minutes,
    estimate_capacity_minutes_in_range as _estimate_capacity_minutes_in_range,
    resolve_expansion_start_date,
    select_adaptive_near_future_weeks as _select_adaptive_near_future_weeks,
)
from app.core.task_keys import (
    resolve_repair_window_days as _resolve_repair_window_days,
)

logger = structlog.get_logger(__name__)


async def _get_latest_settings_with_dates(
    db: AsyncSession,
    organization_id: int,
) -> models.OrganizationSettings | None:
    settings_result = await db.execute(
        sa_select(models.OrganizationSettings).where(
            models.OrganizationSettings.organization_id == organization_id,
            models.OrganizationSettings.school_start_date.isnot(None),
            models.OrganizationSettings.school_hard_end_date.isnot(None),
        )
    )
    return settings_result.scalars().first()


def _resolve_preflight_hard_end_date(org_settings: models.OrganizationSettings) -> date | None:
    return org_settings.school_hard_end_date


def _validate_repair_generation_window(org_settings: models.OrganizationSettings) -> str | None:
    repair_window_days = _resolve_repair_window_days(org_settings)
    editable_start_date = resolve_expansion_start_date(
        org_settings.school_start_date,
        adaptive_repair=True,
        repair_window_days=repair_window_days,
    )
    hard_end_date = _resolve_preflight_hard_end_date(org_settings)
    if hard_end_date is None:
        return None
    if hard_end_date < editable_start_date:
        return (
            "Reparacao adaptativa bloqueada: nao existe horizonte fora da janela "
            f"de estabilidade (até {editable_start_date.isoformat()}) antes do hard end date "
            f"({hard_end_date.isoformat()})."
        )
    return None


async def _ensure_auto_holidays(
    db: AsyncSession,
    organization_id: int,
    org_settings: models.OrganizationSettings,
) -> str | None:
    holiday_count = await db.scalar(
        sa_select(func.count(models.SchoolCalendarEvent.id)).where(
            models.SchoolCalendarEvent.organization_id == organization_id,
            models.SchoolCalendarEvent.source == models.CalendarEventSource.auto,
        )
    )
    if holiday_count:
        return None

    try:
        imported = await settings_service.sync_holidays(
            db,
            organization_id=organization_id,
        )
    except Exception:
        return (
            "Falha ao sincronizar feriados automáticos. "
            "Aceda a Configurações > Calendário Escolar e clique em 'Sincronizar Feriados'."
        )

    if imported <= 0:
        return (
            "Não foi possível carregar feriados automáticos. "
            "Aceda a Configurações > Calendário Escolar e clique em 'Sincronizar Feriados'."
        )
    return None


async def _get_generation_workload_counts(db: AsyncSession, organization_id: int) -> tuple[int, int]:
    class_subject_count = await db.scalar(
        sa_select(func.count(models.ClassSubjectLink.id))
        .join(models.Class, models.ClassSubjectLink.class_id == models.Class.id)
        .where(
            models.Class.organization_id == organization_id,
            models.ClassSubjectLink.organization_id == organization_id,
            models.Class.is_archived == False,  # noqa: E712
            models.ClassSubjectLink.teacher_id.isnot(None),
            models.ClassSubjectLink.grade_level == models.Class.grade_level,
        )
    )
    lesson_count = await db.scalar(
        sa_select(func.count(models.Lesson.id))
        .join(models.Class, models.Lesson.class_id == models.Class.id)
        .where(
            models.Lesson.organization_id == organization_id,
            models.Class.is_archived == False,  # noqa: E712
        )
    )
    return class_subject_count or 0, lesson_count or 0


async def _collect_generation_teacher_ids(db: AsyncSession, organization_id: int) -> set[int]:
    class_subject_teacher_rows = await db.execute(
        sa_select(models.ClassSubjectLink.teacher_id)
        .join(models.Class, models.ClassSubjectLink.class_id == models.Class.id)
        .where(
            models.Class.organization_id == organization_id,
            models.ClassSubjectLink.organization_id == organization_id,
            models.Class.is_archived == False,  # noqa: E712
            models.ClassSubjectLink.teacher_id.isnot(None),
            models.ClassSubjectLink.grade_level == models.Class.grade_level,
        )
        .distinct()
    )
    class_subject_teacher_ids = {row[0] for row in class_subject_teacher_rows.all()}

    lesson_teacher_rows = await db.execute(
        sa_select(models.Lesson.teacher_id)
        .join(models.Class, models.Lesson.class_id == models.Class.id)
        .where(
            models.Lesson.organization_id == organization_id,
            models.Class.is_archived == False,  # noqa: E712
        )
        .distinct()
    )
    lesson_teacher_ids = {row[0] for row in lesson_teacher_rows.all()}
    return class_subject_teacher_ids | lesson_teacher_ids


async def _collect_generation_subject_ids(db: AsyncSession, organization_id: int) -> set[int]:
    class_subject_subject_rows = await db.execute(
        sa_select(models.ClassSubjectLink.subject_id)
        .join(models.Class, models.ClassSubjectLink.class_id == models.Class.id)
        .where(
            models.Class.organization_id == organization_id,
            models.ClassSubjectLink.organization_id == organization_id,
            models.Class.is_archived == False,  # noqa: E712
            models.ClassSubjectLink.teacher_id.isnot(None),
            models.ClassSubjectLink.grade_level == models.Class.grade_level,
        )
        .distinct()
    )
    class_subject_ids = {row[0] for row in class_subject_subject_rows.all()}

    lesson_subject_rows = await db.execute(
        sa_select(models.Lesson.subject_id)
        .join(models.Class, models.Lesson.class_id == models.Class.id)
        .where(
            models.Lesson.organization_id == organization_id,
            models.Class.is_archived == False,  # noqa: E712
        )
        .distinct()
    )
    lesson_subject_ids = {row[0] for row in lesson_subject_rows.all()}
    return class_subject_ids | lesson_subject_ids


async def _validate_teacher_availabilities(
    db: AsyncSession,
    teacher_ids: set[int],
) -> str | None:
    if not teacher_ids:
        return None

    available_teacher_rows = await db.execute(
        sa_select(models.Availability.teacher_id)
        .where(models.Availability.teacher_id.in_(teacher_ids))
        .distinct()
    )
    available_teacher_ids = {row[0] for row in available_teacher_rows.all()}
    missing_availability_ids = teacher_ids - available_teacher_ids
    if not missing_availability_ids:
        return None

    teacher_name_rows = await db.execute(
        sa_select(models.Teacher.name)
        .where(models.Teacher.id.in_(missing_availability_ids))
        .order_by(models.Teacher.name)
    )
    missing_names = [row[0] for row in teacher_name_rows.all()]
    return (
        "Professores sem disponibilidade configurada: "
        f"{', '.join(missing_names)}. "
        "Configure em Professores > Disponibilidade."
    )


async def _validate_subject_requirements(
    db: AsyncSession,
    organization_id: int,
    subject_ids: set[int],
) -> list[str]:
    if not subject_ids:
        return []

    errors: list[str] = []
    module_rows = await db.execute(
        sa_select(models.Module.subject_id, models.Module.hours_total)
        .where(models.Module.subject_id.in_(subject_ids))
    )
    modules_by_subject: dict[int, list[int]] = {}
    for subject_id, hours_total in module_rows.all():
        modules_by_subject.setdefault(subject_id, []).append(hours_total)

    missing_module_subject_ids = {
        subject_id
        for subject_id in subject_ids
        if subject_id not in modules_by_subject
    }
    invalid_module_subject_ids = {
        subject_id
        for subject_id, hours_list in modules_by_subject.items()
        if any(hours <= 0 for hours in hours_list)
    }
    impacted_subject_ids = missing_module_subject_ids | invalid_module_subject_ids

    if impacted_subject_ids:
        subject_rows = await db.execute(
            sa_select(models.Subject.id, models.Subject.name)
            .where(models.Subject.id.in_(impacted_subject_ids))
        )
        subject_name_map = {row[0]: row[1] for row in subject_rows.all()}

        if missing_module_subject_ids:
            missing_names = sorted(
                subject_name_map.get(sid, f"ID {sid}")
                for sid in missing_module_subject_ids
            )
            errors.append(
                "Disciplinas sem módulos definidos: "
                f"{', '.join(missing_names)}. "
                "Adicione módulos com horas > 0 em Disciplinas."
            )

        if invalid_module_subject_ids:
            invalid_names = sorted(
                subject_name_map.get(sid, f"ID {sid}")
                for sid in invalid_module_subject_ids
            )
            errors.append(
                "Disciplinas com módulos inválidos (hours_total <= 0): "
                f"{', '.join(invalid_names)}. "
                "Corrija a carga horária dos módulos."
            )

    required_type_rows = await db.execute(
        sa_select(models.Subject.required_room_type)
        .where(models.Subject.id.in_(subject_ids))
        .distinct()
    )
    required_room_types = {row[0] for row in required_type_rows.all()}
    available_type_rows = await db.execute(
        sa_select(models.Room.type)
        .where(models.Room.organization_id == organization_id)
        .distinct()
    )
    available_room_types = {row[0] for row in available_type_rows.all()}

    missing_room_types = required_room_types - available_room_types
    if missing_room_types:
        missing_labels = sorted(rt.value for rt in missing_room_types)
        errors.append(
            "Não existem salas para os tipos exigidos: "
            f"{', '.join(missing_labels)}. "
            "Adicione salas desses tipos em Salas."
        )

    return errors


def _build_preflight_primary_window(
    *,
    org_settings: models.OrganizationSettings,
    adaptive_repair: bool,
    blocked_dates: set[date],
    class_count: int,
    teacher_count: int,
    room_count: int,
    timeslot_count: int,
    lesson_count: int,
) -> dict | None:
    hard_end_date = _resolve_preflight_hard_end_date(org_settings)
    if hard_end_date is None:
        return None

    repair_window_days = _resolve_repair_window_days(org_settings) if adaptive_repair else 0
    window_start = resolve_expansion_start_date(
        org_settings.school_start_date,
        adaptive_repair=adaptive_repair,
        repair_window_days=repair_window_days,
    )

    near_future_weeks = _select_adaptive_near_future_weeks(
        class_count=class_count,
        teacher_count=teacher_count,
        room_count=room_count,
        timeslot_count=timeslot_count,
        lesson_count=lesson_count,
        blocked_dates_count=len(blocked_dates),
        remaining_days=(hard_end_date - window_start).days + 1,
    )
    primary_window = _build_primary_window(
        window_start_date=window_start,
        hard_end_date=hard_end_date,
        blocked_dates=blocked_dates,
        horizon_weeks=near_future_weeks,
    )
    return {
        "near_future_horizon_weeks": near_future_weeks,
        "start_date": primary_window["window_start_date"],
        "end_date": primary_window["window_end_date"],
        "total_days": int(primary_window["window_total_days"]),
        "blocked_days": int(primary_window["window_blocked_days"]),
        "usable_days": int(primary_window["window_usable_days"]),
    }


async def _build_hard_end_feasibility(
    db: AsyncSession,
    organization_id: int,
    org_settings: models.OrganizationSettings,
    adaptive_repair: bool,
    room_count: int,
    blocked_dates: set[date],
) -> dict | None:
    hard_end_date = _resolve_preflight_hard_end_date(org_settings)
    if hard_end_date is None:
        return None

    repair_window_days = _resolve_repair_window_days(org_settings) if adaptive_repair else 0
    horizon_start = resolve_expansion_start_date(
        org_settings.school_start_date,
        adaptive_repair=adaptive_repair,
        repair_window_days=repair_window_days,
    )

    def _run(sync_db) -> tuple[int, int]:
        lessons = schedule_service.get_active_lessons_with_subject_sync(sync_db, organization_id)
        modules_by_subject = schedule_service.get_modules_by_subject_sync(sync_db, organization_id)
        progress_map = schedule_service.get_class_progress_map_sync(sync_db, organization_id)

        remaining_minutes = 0
        if lessons:
            for lesson in lessons:
                remaining = _compute_remaining_minutes(lesson, modules_by_subject, progress_map)
                remaining_minutes += max(0, int(remaining))
        else:
            link_rows = (
                sync_db.query(
                    models.ClassSubjectLink.class_id,
                    models.ClassSubjectLink.subject_id,
                )
                .join(models.Class, models.ClassSubjectLink.class_id == models.Class.id)
                .filter(
                    models.Class.organization_id == organization_id,
                    models.ClassSubjectLink.organization_id == organization_id,
                    models.Class.is_archived == False,  # noqa: E712
                    models.ClassSubjectLink.teacher_id.isnot(None),
                    models.ClassSubjectLink.grade_level == models.Class.grade_level,
                )
                .distinct()
                .all()
            )

            for class_id, subject_id in link_rows:
                for module in modules_by_subject.get(subject_id, []):
                    hours_done = float(progress_map.get((class_id, module.id), 0) or 0)
                    remaining_hours = max(0.0, float(module.hours_total) - hours_done)
                    remaining_minutes += int(round(remaining_hours * 60))

        if remaining_minutes <= 0:
            return (0, 0)

        timeslots = schedule_service.get_timeslots_by_org_sync(sync_db, organization_id)
        capacity_minutes = _estimate_capacity_minutes_in_range(
            timeslots=timeslots,
            room_count=max(0, int(room_count)),
            blocked_dates=blocked_dates,
            start_date=horizon_start,
            end_date=hard_end_date,
        )
        return (remaining_minutes, capacity_minutes)

    backlog_minutes, capacity_minutes = await db.run_sync(_run)
    expected_residual_minutes = max(0, backlog_minutes - max(0, capacity_minutes))

    return {
        "start_date": horizon_start,
        "hard_end_date": hard_end_date,
        "backlog_hours": round(max(0, backlog_minutes) / 60, 1),
        "capacity_hours": round(max(0, capacity_minutes) / 60, 1),
        "expected_residual_hours": round(expected_residual_minutes / 60, 1),
        "feasible_until_hard_end": expected_residual_minutes == 0,
    }


def _build_repair_infeasible_error(feasibility: dict) -> str:
    return (
        "Reparacao adaptativa bloqueada: carga reconciliada estimada "
        f"({feasibility['backlog_hours']}h) excede a capacidade teorica maxima "
        f"({feasibility['capacity_hours']}h) no horizonte "
        f"{feasibility['start_date'].isoformat()} a {feasibility['hard_end_date'].isoformat()}. "
        f"Residual esperado ate hard end: {feasibility['expected_residual_hours']}h."
    )


async def _preflight_check(
    db: AsyncSession,
    organization_id: int,
    strategy: models.ScheduleGenerationStrategy = (
        models.ScheduleGenerationStrategy.COMPLETE_GENERATION
    ),
    *,
    replace_pending_draft: bool = False,
    school_year_id: int | None = None,
) -> tuple[list[str], dict]:
    """Valida pré-condições e devolve erros + resumo de preflight híbrido."""
    errors: list[str] = []
    preflight_summary: dict = {
        "strategy": strategy.value,
        "primary_window": None,
        "hard_end_feasibility": None,
    }

    pending_conditions = [
        models.ScheduleDraft.organization_id == organization_id,
        models.ScheduleDraft.draft_state == models.ScheduleDraftState.PENDING,
    ]
    if school_year_id is not None:
        pending_conditions.append(models.ScheduleDraft.school_year_id == school_year_id)
    pending_draft_count = await db.scalar(
        sa_select(func.count(models.ScheduleDraft.id)).where(*pending_conditions)
    )
    if pending_draft_count and not replace_pending_draft:
        return (
            [
                "Existe um rascunho pendente de aprovação. "
                "Por favor, aprove ou rejeite o rascunho atual antes de iniciar uma nova geração."
            ],
            preflight_summary,
        )

    org_settings = await _get_latest_settings_with_dates(db, organization_id)
    if not org_settings:
        return (
            [
                "Nenhum ano letivo com 'data de inicio' e 'data-limite rigida'. "
                "Configure em Configurações > Anos Letivos."
            ],
            preflight_summary,
        )

    adaptive_repair = strategy == models.ScheduleGenerationStrategy.ADAPTIVE_REPAIR
    if adaptive_repair:
        window_error = _validate_repair_generation_window(org_settings)
        if window_error:
            errors.append(window_error)

    holiday_error = await _ensure_auto_holidays(db, organization_id, org_settings)
    if holiday_error:
        errors.append(holiday_error)

    class_subject_count, lesson_count = await _get_generation_workload_counts(db, organization_id)
    if not class_subject_count and not lesson_count:
        errors.append(
            "Nenhuma carga letiva ativa encontrada. "
            "Atribua professores em Turmas > Disciplinas (modelo novo) "
            "ou configure as licoes curriculares."
        )

    ts_count = await db.scalar(
        sa_select(func.count(models.Timeslot.id)).where(models.Timeslot.organization_id == organization_id)
    )
    if not ts_count:
        errors.append(
            "Nenhum período horário configurado. Configure em Configurações > Grelha Horária."
        )

    room_count = await db.scalar(
        sa_select(func.count(models.Room.id)).where(models.Room.organization_id == organization_id)
    )
    if not room_count:
        errors.append("Nenhuma sala configurada.")

    calendar_events = await db.execute(
        sa_select(models.SchoolCalendarEvent).where(models.SchoolCalendarEvent.organization_id == organization_id)
    )
    blocked_dates = _build_blocked_dates(calendar_events.scalars().all())

    teacher_ids = await _collect_generation_teacher_ids(db, organization_id)
    preflight_summary["primary_window"] = _build_preflight_primary_window(
        org_settings=org_settings,
        adaptive_repair=adaptive_repair,
        blocked_dates=blocked_dates,
        class_count=int(class_subject_count or 0),
        teacher_count=len(teacher_ids),
        room_count=int(room_count or 0),
        timeslot_count=int(ts_count or 0),
        lesson_count=int(lesson_count or class_subject_count or 0),
    )
    teacher_error = await _validate_teacher_availabilities(db, teacher_ids)
    if teacher_error:
        errors.append(teacher_error)

    subject_ids = await _collect_generation_subject_ids(db, organization_id)
    errors.extend(await _validate_subject_requirements(db, organization_id, subject_ids))

    if not errors:
        feasibility = await _build_hard_end_feasibility(
            db,
            organization_id,
            org_settings,
            adaptive_repair,
            int(room_count or 0),
            blocked_dates,
        )
        preflight_summary["hard_end_feasibility"] = feasibility

        if (
            adaptive_repair
            and feasibility is not None
            and not feasibility["feasible_until_hard_end"]
        ):
            errors.append(_build_repair_infeasible_error(feasibility))

    return errors, preflight_summary
