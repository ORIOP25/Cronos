"""Tarefas Celery para o gerador de horários — Horário Zen.

Orquestra o fluxo completo:
  1. FETCH  — carrega todos os dados necessários da BD.
  2. SOLVE  — chama o motor CP-SAT (padrão semanal).
  3. EXPAND — converte o padrão semanal em datas absolutas.
  4. SAVE   — grava ScheduleOutput e atualiza projected_end_date.
"""
import uuid
import math
import redis
import structlog
from dataclasses import dataclass
from datetime import date, timedelta
from collections import defaultdict

from celery import Task
from sqlalchemy.orm import Session

from .celery_worker import celery_app
from app.db.database import SessionLocalSync
from app.config import settings
from app.services import room_service, schedule_service, occurrence_service
from app.core.solver_engine import (
    ScheduleEngine,
    LessonInput,
    TimeslotInput,
    RoomInput,
    ScheduledAssignment,
)

logger = structlog.get_logger()

# Constantes SonarQube S1192
ERR_NO_DATES = "Nenhum ano letivo tem 'data de início' e 'data de fim-alvo' configuradas. Configure em Configurações > Anos Letivos."
ERR_NO_LESSONS = "Nenhuma lição ativa encontrada. Atribua professores às disciplinas das turmas."
ERR_ALL_DONE = "Todos os módulos já estão concluídos! Nada a agendar."
ERR_NO_EXPAND = "A expansão para datas não produziu blocos de horário."
ERR_INVALID_HARD_END = "A data-limite rígida é anterior ao início do ano letivo. Corrija em Configurações > Anos Letivos."
ERR_REPAIR_WINDOW_NO_FUTURE = "Modo repair bloqueado: não existe horizonte fora da janela de estabilidade antes do hard end date."
MSG_IMPOSSIBLE = "Sem solução válida com as restrições atuais. Verifique as disponibilidades dos professores e as salas."
HARD_LIMIT_REACHED_DETAIL = "Data-limite rígida atingida; carga remanescente ficou por agendar."
DEFAULT_LUNCH_WINDOW_START_MINUTES = 12 * 60
DEFAULT_LUNCH_WINDOW_END_MINUTES = 14 * 60
DEFAULT_LUNCH_MIN_DURATION_MINUTES = 60
DEFAULT_HARD_END_MONTH = 7
DEFAULT_HARD_END_DAY = 31
DEFAULT_REPAIR_STABILITY_WINDOW_DAYS = 14
GENERATION_TOTAL_STEPS = 10


# ---------------------------------------------------------------------------
# Tipos de dados internos (Fase 2 — expansão)
# ---------------------------------------------------------------------------

@dataclass
class ScheduledBlock:
    """Bloco de horário com data absoluta — resultado da expansão."""
    lesson_id: int
    ts_id: int
    room_id: int
    output_date: date


# ---------------------------------------------------------------------------
# Funções auxiliares puras (sem acesso à BD)
# ---------------------------------------------------------------------------

def _build_blocked_dates(calendar_events: list) -> set:
    """Expande eventos de calendário em conjunto de datas bloqueadas."""
    blocked: set = set()
    for event in calendar_events:
        current = event.start_date
        while current <= event.end_date:
            blocked.add(current)
            current = current + timedelta(days=1)
    return blocked


def _compute_remaining_minutes(lesson, modules_by_subject: dict, progress_map: dict) -> int:
    """Soma de minutos restantes em todos os módulos não concluídos de uma lição."""
    total = 0
    for module in modules_by_subject.get(lesson.subject_id, []):
        hours_done = progress_map.get((lesson.class_id, module.id), 0)
        total += max(0, module.hours_total - hours_done) * 60
    return total


def _build_lesson_inputs(
    lessons: list,
    modules_by_subject: dict,
    progress_map: dict,
    planning_weeks: int,
    min_slot_minutes: int,
) -> list[LessonInput]:
    """Constrói lista de LessonInput filtrando lições já concluídas."""
    result = []
    safe_weeks = max(1, planning_weeks)
    safe_min_slot = max(1, min_slot_minutes)

    for lesson in lessons:
        remaining = _compute_remaining_minutes(lesson, modules_by_subject, progress_map)
        if remaining <= 0:
            continue

        target_weekly_minutes = math.ceil(remaining / safe_weeks)
        if target_weekly_minutes < safe_min_slot:
            target_weekly_minutes = safe_min_slot

        result.append(
            LessonInput(
                lesson_id=lesson.id,
                class_id=lesson.class_id,
                subject_id=lesson.subject_id,
                teacher_id=lesson.teacher_id,
                required_room_type=lesson.subject.required_room_type.value,
                remaining_minutes=remaining,
                target_weekly_minutes=target_weekly_minutes,
            )
        )
    return result


def _build_timeslot_inputs(timeslots: list) -> list[TimeslotInput]:
    """Converte Timeslot ORM em TimeslotInput, calculando duração em minutos."""
    result = []
    for ts in timeslots:
        start_min = ts.start_time.hour * 60 + ts.start_time.minute
        end_min = ts.end_time.hour * 60 + ts.end_time.minute
        duration = max(0, end_min - start_min)
        result.append(
            TimeslotInput(
                ts_id=ts.id,
                day_of_week=ts.day_of_week,
                duration_minutes=duration,
                start_minutes=start_min,
                end_minutes=end_min,
            )
        )
    return result


def _build_room_inputs(rooms: list) -> list[RoomInput]:
    """Converte Room ORM em RoomInput."""
    return [RoomInput(room_id=r.id, room_type=r.type.value) for r in rooms]


def _select_org_settings(settings_list: list):
    """Seleciona as settings com start_date e end_date configuradas (mais recente)."""
    for s in settings_list:
        if s.school_start_date and s.school_target_end_date:
            return s
    return None


def _resolve_repair_window_days(org_settings) -> int:
    value = org_settings.repair_stability_window_days
    if value is None:
        return DEFAULT_REPAIR_STABILITY_WINDOW_DAYS
    return max(1, int(value))


def _resolve_expansion_start_date(
    school_start_date: date,
    *,
    mode: str,
    repair_window_days: int,
) -> date:
    """Define início da expansão; em repair, só fora da janela de estabilidade."""
    if mode != "repair":
        return school_start_date

    frozen_until = date.today() + timedelta(days=max(1, repair_window_days))
    return max(school_start_date, frozen_until + timedelta(days=1))


def _compute_planning_weeks(start_date: date, target_end_date: date) -> int:
    """Número de semanas úteis para distribuir carga até ao alvo."""
    if target_end_date <= start_date:
        return 1
    total_days = (target_end_date - start_date).days + 1
    return max(1, math.ceil(total_days / 7))


def _parse_academic_year_end_year(academic_year: str | None) -> int | None:
    if not academic_year:
        return None
    parts = academic_year.split("/")
    if len(parts) != 2:
        return None
    try:
        return int(parts[1])
    except ValueError:
        return None


def _resolve_hard_end_date(org_settings) -> date | None:
    if org_settings.school_hard_end_date is not None:
        return org_settings.school_hard_end_date

    fallback_year = None
    if org_settings.school_target_end_date is not None:
        fallback_year = org_settings.school_target_end_date.year
    else:
        fallback_year = _parse_academic_year_end_year(org_settings.academic_year)

    if fallback_year is None:
        return None

    return date(fallback_year, DEFAULT_HARD_END_MONTH, DEFAULT_HARD_END_DAY)


def _resolve_planning_target_end_date(target_end_date: date, hard_end_date: date) -> date:
    if target_end_date <= hard_end_date:
        return target_end_date
    return hard_end_date


def _build_repair_window_block_detail(repair_window_days: int, hard_end_date: date) -> str:
    frozen_until = date.today() + timedelta(days=repair_window_days)
    return (
        f"Janela de estabilidade ativa até {frozen_until.isoformat()} e hard end date "
        f"em {hard_end_date.isoformat()}."
    )


def _resolve_lunch_constraints(org_settings) -> tuple[int, int, int]:
    """Resolve janela de almoço e pausa mínima (com defaults seguros)."""
    start = org_settings.lunch_window_start
    end = org_settings.lunch_window_end
    min_duration = org_settings.lunch_min_duration_minutes

    if min_duration is None or min_duration <= 0:
        min_duration = DEFAULT_LUNCH_MIN_DURATION_MINUTES

    if start is None or end is None:
        return (
            DEFAULT_LUNCH_WINDOW_START_MINUTES,
            DEFAULT_LUNCH_WINDOW_END_MINUTES,
            min_duration,
        )

    start_minutes = start.hour * 60 + start.minute
    end_minutes = end.hour * 60 + end.minute
    if end_minutes <= start_minutes:
        return (
            DEFAULT_LUNCH_WINDOW_START_MINUTES,
            DEFAULT_LUNCH_WINDOW_END_MINUTES,
            min_duration,
        )

    window_size = end_minutes - start_minutes
    bounded_min_duration = min(min_duration, window_size)
    return (start_minutes, end_minutes, bounded_min_duration)


def _task_progress_meta(step: int, detail: str, phase: str) -> dict:
    """Meta comum de progresso para monitorização no frontend."""
    return {
        "phase": phase,
        "detail": detail,
        "progress": {
            "current": step,
            "total": GENERATION_TOTAL_STEPS,
        },
    }


# ---------------------------------------------------------------------------
# Fase 2 — Expansão do padrão semanal para datas absolutas
# ---------------------------------------------------------------------------

def expand_to_dates(
    assignments: list[ScheduledAssignment],
    school_start_date: date,
    school_target_end_date: date,
    school_hard_end_date: date,
    blocked_dates: set,
    remaining_map: dict,
) -> tuple[list[ScheduledBlock], int]:
    """Expande o padrão semanal para blocos com datas absolutas.

    Para cada dia útil não bloqueado, agenda os blocos cujas lições ainda
    têm horas pendentes. Para quando todos os remaining_map chegam a 0
    ou quando é atingida a data-limite rígida da escola.
    """
    _ = school_target_end_date
    by_dow: dict = defaultdict(list)
    for assignment in assignments:
        by_dow[assignment.day_of_week].append(assignment)

    remaining = dict(remaining_map)
    result: list[ScheduledBlock] = []
    current = school_start_date
    max_date = school_hard_end_date

    while current <= max_date:
        if all(v <= 0 for v in remaining.values()):
            break
        if current not in blocked_dates:
            dow = current.weekday()
            for assignment in by_dow.get(dow, []):
                if remaining.get(assignment.lesson_id, 0) > 0:
                    result.append(ScheduledBlock(
                        lesson_id=assignment.lesson_id,
                        ts_id=assignment.ts_id,
                        room_id=assignment.room_id,
                        output_date=current,
                    ))
                    remaining[assignment.lesson_id] = max(
                        0, remaining[assignment.lesson_id] - assignment.duration_minutes
                    )
        current = current + timedelta(days=1)

    remaining_minutes = sum(max(0, value) for value in remaining.values())
    return result, remaining_minutes


def _compute_class_end_dates(blocks: list[ScheduledBlock], lesson_class_map: dict) -> dict:
    """Para cada turma, encontra a data do último bloco agendado."""
    class_end_dates: dict = {}
    for block in blocks:
        class_id = lesson_class_map.get(block.lesson_id)
        if class_id is None:
            continue
        if class_id not in class_end_dates or block.output_date > class_end_dates[class_id]:
            class_end_dates[class_id] = block.output_date
    return class_end_dates


# ---------------------------------------------------------------------------
# Funções de persistência
# ---------------------------------------------------------------------------

def _save_results(
    db: Session,
    blocks: list[ScheduledBlock],
    org_id: int,
    gen_id: str,
    lesson_class_map: dict,
    is_draft: bool = False,
) -> dict:
    """Guarda os ScheduleOutput e atualiza projected_end_date de cada turma."""
    for block in blocks:
        schedule_service.create_schedule_output_with_date_sync(
            db=db,
            lesson_id=block.lesson_id,
            timeslot_id=block.ts_id,
            room_id=block.room_id,
            output_date=block.output_date,
            org_id=org_id,
            gen_id=gen_id,
            is_draft=is_draft,
        )

    # Só atualiza projected_end_date quando o horário é ativado (não draft)
    if not is_draft:
        class_end_dates = _compute_class_end_dates(blocks, lesson_class_map)
        for class_id, end_date in class_end_dates.items():
            schedule_service.update_class_projected_end_date_sync(db, class_id, end_date)
        return class_end_dates

    return {}


def _invalidate_cache(org_id: int) -> None:
    """Invalida a cache Redis do horário desta organização."""
    try:
        r = redis.Redis.from_url(str(settings.REDIS_URL))
        r.delete(f"schedule_latest_data_{org_id}")
    except Exception as exc:
        logger.warning("Cache invalidation failed", error=str(exc))


# ---------------------------------------------------------------------------
# Tarefa Celery principal
# ---------------------------------------------------------------------------

@celery_app.task(bind=True)
def generate_schedule_task(self: Task, org_id: int, mode: str = "full") -> dict:
    """Orquestrador completo: FETCH → SOLVE → EXPAND → SAVE."""
    logger.info("Iniciando geração de horário", org_id=org_id, mode=mode)
    gen_id = str(uuid.uuid4())
    db = SessionLocalSync()

    try:
        # 1. FETCH — configurações e dados curriculares
        self.update_state(state="FETCHING", meta=_task_progress_meta(1, "A iniciar pré-processamento...", "FETCHING"))

        self.update_state(state="FETCHING", meta=_task_progress_meta(2, "A ler configurações da escola...", "FETCHING"))
        settings_list = schedule_service.get_org_settings_sync(db, org_id)
        org_settings = _select_org_settings(settings_list)
        if not org_settings:
            return {"status": "Error", "message": ERR_NO_DATES}

        is_repair = mode == "repair"
        repair_window_days = _resolve_repair_window_days(org_settings) if is_repair else 0

        self.update_state(state="FETCHING", meta=_task_progress_meta(3, "A sincronizar lições da matriz turma-disciplina...", "FETCHING"))
        lesson_sync_stats = schedule_service.sync_lessons_from_class_subject_links_sync(db, org_id)

        self.update_state(state="FETCHING", meta=_task_progress_meta(4, "A preparar inputs curriculares e carga remanescente...", "FETCHING"))
        raw_lessons = schedule_service.get_active_lessons_with_subject_sync(db, org_id)
        if not raw_lessons:
            return {"status": "Error", "message": ERR_NO_LESSONS}

        raw_timeslots = schedule_service.get_timeslots_by_org_sync(db, org_id)
        if not raw_timeslots:
            return {"status": "Error", "message": "Não existem blocos horários configurados."}
        timeslot_inputs = _build_timeslot_inputs(raw_timeslots)
        min_slot_minutes = min(ts.duration_minutes for ts in timeslot_inputs if ts.duration_minutes > 0)
        lunch_start_minutes, lunch_end_minutes, lunch_min_duration = _resolve_lunch_constraints(org_settings)

        expansion_start_date = _resolve_expansion_start_date(
            org_settings.school_start_date,
            mode=mode,
            repair_window_days=repair_window_days,
        )
        hard_end_date = _resolve_hard_end_date(org_settings)
        if hard_end_date is None:
            return {"status": "Error", "message": ERR_NO_DATES}
        if hard_end_date < expansion_start_date:
            if is_repair:
                return {
                    "status": "Error",
                    "message": ERR_REPAIR_WINDOW_NO_FUTURE,
                    "detail": _build_repair_window_block_detail(repair_window_days, hard_end_date),
                }
            return {"status": "Error", "message": ERR_INVALID_HARD_END}

        planning_target_end_date = _resolve_planning_target_end_date(
            org_settings.school_target_end_date,
            hard_end_date,
        )
        planning_weeks = _compute_planning_weeks(expansion_start_date, planning_target_end_date)

        modules_by_subject = schedule_service.get_modules_by_subject_sync(db, org_id)
        progress_map = schedule_service.get_class_progress_map_sync(db, org_id)
        lesson_inputs = _build_lesson_inputs(
            raw_lessons,
            modules_by_subject,
            progress_map,
            planning_weeks,
            min_slot_minutes,
        )

        if not lesson_inputs:
            return {"status": "Success", "message": ERR_ALL_DONE, "count": 0}

        self.update_state(state="FETCHING", meta=_task_progress_meta(5, "A carregar salas, disponibilidades e calendário...", "FETCHING"))
        raw_rooms = room_service.get_rooms_by_org_sync(db, org_id)
        raw_availabilities = schedule_service.get_availabilities_by_org_sync(db, org_id)
        calendar_events = schedule_service.get_calendar_events_sync(db, org_id)

        availability_map = {
            (a.teacher_id, a.timeslot_id): a.score for a in raw_availabilities
        }
        blocked_dates = _build_blocked_dates(calendar_events)

        # Repair mode: ler padrão ativo anterior para minimizar perturbações
        previous_pattern = (
            schedule_service.get_active_future_pattern_sync(db, org_id)
            if is_repair else None
        )

        logger.info(
            "Dados carregados",
            lessons=len(lesson_inputs),
            timeslots=len(raw_timeslots),
            rooms=len(raw_rooms),
            planning_weeks=planning_weeks,
            synced_lessons_created=lesson_sync_stats["created"],
            synced_lessons_updated=lesson_sync_stats["updated"],
            synced_lessons_deleted=lesson_sync_stats["deleted"],
        )

        # 2. SOLVE — CP-SAT encontra o padrão semanal ótimo
        self.update_state(state="SOLVING", meta=_task_progress_meta(6, "A otimizar com CP-SAT (fase intensiva)...", "SOLVING"))

        engine = ScheduleEngine(
            lessons=lesson_inputs,
            timeslots=timeslot_inputs,
            rooms=_build_room_inputs(raw_rooms),
            availability_map=availability_map,
            previous_pattern=previous_pattern,
            lunch_window_start_minutes=lunch_start_minutes,
            lunch_window_end_minutes=lunch_end_minutes,
            lunch_min_duration_minutes=lunch_min_duration,
        )
        assignments = engine.solve()

        if assignments is None:
            return {"status": "Impossible", "message": MSG_IMPOSSIBLE}

        # 3. EXPAND — padrão semanal → datas absolutas
        self.update_state(state="EXPANDING", meta=_task_progress_meta(7, "A expandir padrão semanal para datas reais...", "EXPANDING"))

        remaining_map = {li.lesson_id: li.remaining_minutes for li in lesson_inputs}
        lesson_class_map = {lesson.id: lesson.class_id for lesson in raw_lessons}

        blocks, remaining_after_expand = expand_to_dates(
            assignments=assignments,
            school_start_date=expansion_start_date,
            school_target_end_date=org_settings.school_target_end_date,
            school_hard_end_date=hard_end_date,
            blocked_dates=blocked_dates,
            remaining_map=remaining_map,
        )

        if not blocks:
            return {"status": "Error", "message": ERR_NO_EXPAND}

        self.update_state(state="EXPANDING", meta=_task_progress_meta(8, "A validar blocos gerados e projeções...", "EXPANDING"))

        # 4. SAVE — comportamento depende do modo
        self.update_state(state="SAVING", meta=_task_progress_meta(9, "A gravar solução em base de dados...", "SAVING"))

        if is_repair:
            # Repair: guarda como rascunho (is_draft=True) sem apagar o ativo
            _save_results(db, blocks, org_id, gen_id, lesson_class_map, is_draft=True)
            db.commit()
            _invalidate_cache(org_id)
            logger.info("Rascunho de reparação criado", blocks=len(blocks), gen_id=gen_id)
            detail = None
            if remaining_after_expand > 0:
                remaining_hours = round(remaining_after_expand / 60, 1)
                detail = f"{HARD_LIMIT_REACHED_DETAIL} Restam {remaining_hours}h além de {hard_end_date.isoformat()}."
            return {
                "status": "Success",
                "generation_id": gen_id,
                "mode": "repair",
                "is_draft": True,
                "count": len(blocks),
                "detail": detail,
                "progress": {
                    "current": GENERATION_TOTAL_STEPS,
                    "total": GENERATION_TOTAL_STEPS,
                },
            }

        # Full: limpa futuro e grava novo horário ativo
        start_window = min(block.output_date for block in blocks)
        end_window = max(block.output_date for block in blocks)
        schedule_service.clear_schedule_window_sync(db, org_id, start_window, end_window)
        class_end_dates = _save_results(db, blocks, org_id, gen_id, lesson_class_map, is_draft=False)
        db.commit()

        _invalidate_cache(org_id)

        logger.info("Geração concluída", blocks=len(blocks), classes=len(class_end_dates))
        detail = None
        if remaining_after_expand > 0:
            remaining_hours = round(remaining_after_expand / 60, 1)
            detail = f"{HARD_LIMIT_REACHED_DETAIL} Restam {remaining_hours}h além de {hard_end_date.isoformat()}."
        return {
            "status": "Success",
            "generation_id": gen_id,
            "mode": "full",
            "is_draft": False,
            "count": len(blocks),
            "classes_updated": len(class_end_dates),
            "detail": detail,
            "progress": {
                "current": GENERATION_TOTAL_STEPS,
                "total": GENERATION_TOTAL_STEPS,
            },
        }

    except Exception as exc:
        db.rollback()
        logger.error("Erro crítico na geração", error=str(exc), exc_info=True)
        return {"status": "Error", "message": str(exc)}

    finally:
        db.close()


# ---------------------------------------------------------------------------
# Tarefa Celery Beat — Confirmação Automática Diária (Sprint 2)
# ---------------------------------------------------------------------------

@celery_app.task(name="app.solver_tasks.auto_confirm_occurrences_task")
def auto_confirm_occurrences_task() -> dict:
    """Corre todos os dias às 23:59 (Celery Beat).

    Para cada organização com ScheduleOutputs planeados para hoje e sem
    LessonOccurrence manual, cria automaticamente um registo GIVEN e
    incrementa o ClassProgress correspondente.

    Retorna um sumário com o total de registos criados por organização.
    """
    from datetime import date as date_type
    from sqlalchemy import select as sa_select
    from app import models

    db: Session = SessionLocalSync()
    today = date_type.today()
    summary: dict[int, int] = {}

    try:
        # Descobrir todas as organizações com slots agendados para hoje
        org_ids = [
            row.organization_id
            for row in db.execute(
                sa_select(models.ScheduleOutput.organization_id)
                .where(
                    models.ScheduleOutput.date == today,
                    models.ScheduleOutput.is_draft.is_(False),
                )
                .distinct()
            ).all()
        ]

        for org_id in org_ids:
            count = occurrence_service.auto_confirm_daily_sync(db, org_id, today)
            summary[org_id] = count
            logger.info(
                "Auto-confirm diário concluído",
                org_id=org_id,
                registos_criados=count,
                data=str(today),
            )

        return {"status": "OK", "date": str(today), "summary": summary}

    except Exception as exc:
        db.rollback()
        logger.error("Erro no auto-confirm diário", error=str(exc), exc_info=True)
        return {"status": "Error", "message": str(exc)}

    finally:
        db.close()