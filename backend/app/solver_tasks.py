"""Tarefas Celery para o gerador de horários — Horário Zen.

Orquestra o fluxo completo:
  1. FETCH  — carrega todos os dados necessários da BD.
  2. SOLVE  — chama o motor CP-SAT (padrão semanal).
  3. EXPAND — converte o padrão semanal em datas absolutas.
  4. SAVE   — grava ScheduleOutput e atualiza projected_end_date.
"""
import uuid
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
from app.services import room_service, schedule_service
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
MSG_IMPOSSIBLE = "Sem solução válida com as restrições atuais. Verifique as disponibilidades dos professores e as salas."


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
) -> list[LessonInput]:
    """Constrói lista de LessonInput filtrando lições já concluídas."""
    result = []
    for lesson in lessons:
        remaining = _compute_remaining_minutes(lesson, modules_by_subject, progress_map)
        if remaining <= 0:
            continue
        result.append(
            LessonInput(
                lesson_id=lesson.id,
                class_id=lesson.class_id,
                subject_id=lesson.subject_id,
                teacher_id=lesson.teacher_id,
                required_room_type=lesson.subject.required_room_type.value,
                remaining_minutes=remaining,
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
        result.append(TimeslotInput(ts_id=ts.id, day_of_week=ts.day_of_week, duration_minutes=duration))
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


# ---------------------------------------------------------------------------
# Fase 2 — Expansão do padrão semanal para datas absolutas
# ---------------------------------------------------------------------------

def expand_to_dates(
    assignments: list[ScheduledAssignment],
    school_start_date: date,
    school_target_end_date: date,
    blocked_dates: set,
    remaining_map: dict,
) -> list[ScheduledBlock]:
    """Expande o padrão semanal para blocos com datas absolutas.

    Para cada dia útil não bloqueado, agenda os blocos cujas lições ainda
    têm horas pendentes. Para quando todos os remaining_map chegam a 0
    ou ultrapassamos o horizonte de segurança (target + 365 dias).
    """
    by_dow: dict = defaultdict(list)
    for assignment in assignments:
        by_dow[assignment.day_of_week].append(assignment)

    remaining = dict(remaining_map)
    result: list[ScheduledBlock] = []
    current = school_start_date
    max_date = school_target_end_date + timedelta(days=365)

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

    return result


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
            is_draft=False,
        )

    class_end_dates = _compute_class_end_dates(blocks, lesson_class_map)
    for class_id, end_date in class_end_dates.items():
        schedule_service.update_class_projected_end_date_sync(db, class_id, end_date)

    return class_end_dates


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
        self.update_state(state="FETCHING", meta={"detail": "A ler dados..."})

        settings_list = schedule_service.get_org_settings_sync(db, org_id)
        org_settings = _select_org_settings(settings_list)
        if not org_settings:
            return {"status": "Error", "message": ERR_NO_DATES}

        raw_lessons = schedule_service.get_active_lessons_with_subject_sync(db, org_id)
        if not raw_lessons:
            return {"status": "Error", "message": ERR_NO_LESSONS}

        modules_by_subject = schedule_service.get_modules_by_subject_sync(db, org_id)
        progress_map = schedule_service.get_class_progress_map_sync(db, org_id)
        lesson_inputs = _build_lesson_inputs(raw_lessons, modules_by_subject, progress_map)

        if not lesson_inputs:
            return {"status": "Success", "message": ERR_ALL_DONE, "count": 0}

        raw_timeslots = schedule_service.get_timeslots_by_org_sync(db, org_id)
        raw_rooms = room_service.get_rooms_by_org_sync(db, org_id)
        raw_availabilities = schedule_service.get_availabilities_by_org_sync(db, org_id)
        calendar_events = schedule_service.get_calendar_events_sync(db, org_id)

        availability_map = {
            (a.teacher_id, a.timeslot_id): a.score for a in raw_availabilities
        }
        blocked_dates = _build_blocked_dates(calendar_events)

        logger.info(
            "Dados carregados",
            lessons=len(lesson_inputs),
            timeslots=len(raw_timeslots),
            rooms=len(raw_rooms),
        )

        # 2. SOLVE — CP-SAT encontra o padrão semanal ótimo
        self.update_state(state="SOLVING", meta={"detail": "A otimizar com CP-SAT..."})

        engine = ScheduleEngine(
            lessons=lesson_inputs,
            timeslots=_build_timeslot_inputs(raw_timeslots),
            rooms=_build_room_inputs(raw_rooms),
            availability_map=availability_map,
        )
        assignments = engine.solve()

        if assignments is None:
            return {"status": "Impossible", "message": MSG_IMPOSSIBLE}

        # 3. EXPAND — padrão semanal → datas absolutas
        self.update_state(state="EXPANDING", meta={"detail": "A expandir para datas reais..."})

        remaining_map = {li.lesson_id: li.remaining_minutes for li in lesson_inputs}
        lesson_class_map = {lesson.id: lesson.class_id for lesson in raw_lessons}

        blocks = expand_to_dates(
            assignments=assignments,
            school_start_date=org_settings.school_start_date,
            school_target_end_date=org_settings.school_target_end_date,
            blocked_dates=blocked_dates,
            remaining_map=remaining_map,
        )

        if not blocks:
            return {"status": "Error", "message": ERR_NO_EXPAND}

        # 4. SAVE — limpa futuro e grava novos blocos
        self.update_state(state="SAVING", meta={"detail": "A gravar solução..."})

        schedule_service.clear_future_schedule_sync(db, org_id)
        class_end_dates = _save_results(db, blocks, org_id, gen_id, lesson_class_map)
        db.commit()

        _invalidate_cache(org_id)

        logger.info("Geração concluída", blocks=len(blocks), classes=len(class_end_dates))
        return {
            "status": "Success",
            "generation_id": gen_id,
            "count": len(blocks),
            "classes_updated": len(class_end_dates),
        }

    except Exception as exc:
        db.rollback()
        logger.error("Erro crítico na geração", error=str(exc), exc_info=True)
        return {"status": "Error", "message": str(exc)}

    finally:
        db.close()