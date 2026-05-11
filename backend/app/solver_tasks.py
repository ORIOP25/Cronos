"""Tarefas Celery para o gerador de horários — Apérius.

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
from app.core.solver_v2_candidates import (
    build_candidate_universe,
    prune_candidates_hard_first,
)
from app.core.solver_engine_v2 import ScheduleEngineV2, ScheduledBlockV2
from app.core.solver_v2_expansion import (
    validate_v2_blocks_calendar,
    fill_opportunistic_v2,
    compute_residual_summary,
    _TimeslotInfo,
    _RoomInfo,
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
DEFAULT_SOLVER_ENGINE_VERSION = "v1"
DEFAULT_SOLVER_V2_ROLLING_WEEKS = 8
DEFAULT_SOLVER_V2_OBJECTIVE_MODE = "lexicographic"
GENERATION_TOTAL_STEPS = 10
TASK_CANCEL_KEY_PREFIX = "schedule_task_cancel:"
ACTIVE_TASK_BY_ORG_KEY_PREFIX = "schedule_active_task_org:"


class GenerationCancelledError(Exception):
    """Raised when a schedule generation task receives a cancel request."""


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


@dataclass(frozen=True)
class SolverV2Demand:
    """Demanda curricular V2 por lição com módulo ativo e backlog único."""
    lesson_id: int
    class_id: int
    subject_id: int
    module_id: int
    backlog_minutes: int
    target_end_date: date | None


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


def _resolve_active_module_and_backlog_minutes(
    lesson,
    modules_by_subject: dict,
    progress_map: dict,
) -> tuple[int | None, int]:
    """Resolve módulo ativo e backlog único (minutos) preservando ordem dos módulos."""
    active_module_id: int | None = None
    backlog_minutes = 0
    subject_modules = sorted(
        modules_by_subject.get(lesson.subject_id, []),
        key=lambda module: getattr(module, "order", 0),
    )

    for module in subject_modules:
        hours_total = max(0.0, float(getattr(module, "hours_total", 0) or 0))
        if hours_total <= 0:
            continue

        hours_done_raw = float(progress_map.get((lesson.class_id, module.id), 0) or 0)
        hours_done = min(hours_total, max(0.0, hours_done_raw))
        remaining_minutes = int(round(max(0.0, hours_total - hours_done) * 60))

        if active_module_id is None:
            if remaining_minutes <= 0:
                continue
            active_module_id = module.id

        backlog_minutes += max(0, remaining_minutes)

    return active_module_id, backlog_minutes


def _compute_remaining_minutes(lesson, modules_by_subject: dict, progress_map: dict) -> int:
    """Compat helper: minutos remanescentes totais a partir do módulo ativo."""
    _, backlog_minutes = _resolve_active_module_and_backlog_minutes(
        lesson,
        modules_by_subject,
        progress_map,
    )
    return max(0, int(backlog_minutes))


def _build_solver_v2_demands(
    lessons: list,
    modules_by_subject: dict,
    progress_map: dict,
    *,
    target_end_date: date | None,
    committed_minutes_by_lesson: dict[int, int] | None = None,
) -> list[SolverV2Demand]:
    """Constrói demandas V2 com backlog único por lição e módulo ativo."""
    demands: list[SolverV2Demand] = []
    committed = committed_minutes_by_lesson or {}

    for lesson in lessons:
        active_module_id, backlog_minutes = _resolve_active_module_and_backlog_minutes(
            lesson,
            modules_by_subject,
            progress_map,
        )
        if active_module_id is None or backlog_minutes <= 0:
            continue

        if committed:
            backlog_minutes = max(0, backlog_minutes - max(0, int(committed.get(lesson.id, 0))))
        if backlog_minutes <= 0:
            continue

        demands.append(
            SolverV2Demand(
                lesson_id=lesson.id,
                class_id=lesson.class_id,
                subject_id=lesson.subject_id,
                module_id=active_module_id,
                backlog_minutes=int(max(0, backlog_minutes)),
                target_end_date=target_end_date,
            )
        )

    return demands


def _build_lesson_inputs(
    lessons: list,
    modules_by_subject: dict,
    progress_map: dict,
    planning_weeks: int,
    min_slot_minutes: int,
    committed_minutes_by_lesson: dict[int, int] | None = None,
    target_end_date: date | None = None,
) -> list[LessonInput]:
    """Constrói lista de LessonInput filtrando lições já concluídas.

    Em repair, committed_minutes_by_lesson representa minutos já comprometidos
    no horário publicado até ao limite congelado e reduz o remanescente efetivo.
    """
    result = []
    safe_weeks = max(1, planning_weeks)
    safe_min_slot = max(1, min_slot_minutes)
    demands = _build_solver_v2_demands(
        lessons,
        modules_by_subject,
        progress_map,
        target_end_date=target_end_date,
        committed_minutes_by_lesson=committed_minutes_by_lesson,
    )
    demand_by_lesson_id = {demand.lesson_id: demand for demand in demands}

    for lesson in lessons:
        demand = demand_by_lesson_id.get(lesson.id)
        if demand is None:
            continue

        remaining = max(0, int(demand.backlog_minutes))
        if remaining <= 0:
            continue

        target_weekly_minutes = math.ceil(remaining / safe_weeks)
        if target_weekly_minutes < safe_min_slot:
            target_weekly_minutes = safe_min_slot
        target_weekly_minutes = int(target_weekly_minutes)

        result.append(
            LessonInput(
                lesson_id=lesson.id,
                class_id=lesson.class_id,
                subject_id=lesson.subject_id,
                teacher_id=lesson.teacher_id,
                required_room_type=lesson.subject.required_room_type.value,
                remaining_minutes=int(remaining),
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


def _build_primary_rolling_window(
    *,
    window_start_date: date,
    hard_end_date: date,
    blocked_dates: set[date],
    rolling_weeks: int,
) -> dict[str, int | date]:
    """Constrói janela principal rolling do Solver V2 com exclusão de bloqueios."""
    safe_rolling_weeks = max(1, int(rolling_weeks))
    window_end_candidate = window_start_date + timedelta(days=(safe_rolling_weeks * 7) - 1)
    window_end_date = min(hard_end_date, window_end_candidate)

    if window_end_date < window_start_date:
        return {
            "rolling_weeks": safe_rolling_weeks,
            "window_start_date": window_start_date,
            "window_end_date": window_start_date,
            "window_total_days": 0,
            "window_blocked_days": 0,
            "window_usable_days": 0,
        }

    total_days = (window_end_date - window_start_date).days + 1
    blocked_days = sum(
        1
        for blocked in blocked_dates
        if window_start_date <= blocked <= window_end_date
    )
    usable_days = max(0, total_days - blocked_days)

    return {
        "rolling_weeks": safe_rolling_weeks,
        "window_start_date": window_start_date,
        "window_end_date": window_end_date,
        "window_total_days": int(total_days),
        "window_blocked_days": int(blocked_days),
        "window_usable_days": int(usable_days),
    }


def _compute_planning_weeks_from_primary_window(primary_window: dict[str, int | date]) -> int:
    """Converte dias úteis da janela principal em semanas de planeamento."""
    usable_days = int(primary_window.get("window_usable_days", 0) or 0)
    if usable_days <= 0:
        return 1
    return max(1, math.ceil(usable_days / 7))


def _estimate_capacity_minutes_in_range(
    timeslots: list,
    room_count: int,
    blocked_dates: set[date],
    start_date: date,
    end_date: date,
) -> int:
    """Capacidade teórica agregada (minutos) no intervalo [start_date, end_date]."""
    if end_date < start_date:
        return 0

    safe_room_count = max(0, int(room_count))
    if safe_room_count <= 0:
        return 0

    slot_minutes_by_dow: dict[int, int] = {}
    for ts in timeslots:
        start_minutes = ts.start_time.hour * 60 + ts.start_time.minute
        end_minutes = ts.end_time.hour * 60 + ts.end_time.minute
        duration_minutes = max(0, end_minutes - start_minutes)
        if duration_minutes <= 0:
            continue
        slot_minutes_by_dow[ts.day_of_week] = slot_minutes_by_dow.get(ts.day_of_week, 0) + duration_minutes

    if not slot_minutes_by_dow:
        return 0

    capacity_minutes = 0
    current_date = start_date
    while current_date <= end_date:
        if current_date not in blocked_dates:
            capacity_minutes += slot_minutes_by_dow.get(current_date.weekday(), 0) * safe_room_count
        current_date = current_date + timedelta(days=1)

    return int(max(0, capacity_minutes))


def _build_remaining_summary(
    raw_remaining_minutes: int,
    reconciled_remaining_minutes: int,
    committed_minutes: int,
    post_expand_remaining_minutes: int | None = None,
) -> dict[str, float]:
    summary = {
        "raw_remaining_hours": round(max(0, raw_remaining_minutes) / 60, 1),
        "reconciled_remaining_hours": round(max(0, reconciled_remaining_minutes) / 60, 1),
        "committed_credited_hours": round(max(0, committed_minutes) / 60, 1),
    }
    if post_expand_remaining_minutes is not None:
        summary["post_expand_remaining_hours"] = round(max(0, post_expand_remaining_minutes) / 60, 1)
    return summary


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
    elif org_settings.school_start_date is not None:
        fallback_year = org_settings.school_start_date.year + 1

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


def _resolve_lunch_constraints(grid_settings) -> tuple[int, int, int]:
    """Resolve janela de almoço e pausa mínima (com defaults seguros).

    Lê de OrganizationGridSettings (tab 'Grelha Horária');
    usa defaults seguros quando grid_settings é None ou campos estão vazios.
    """
    if grid_settings is None:
        return (
            DEFAULT_LUNCH_WINDOW_START_MINUTES,
            DEFAULT_LUNCH_WINDOW_END_MINUTES,
            DEFAULT_LUNCH_MIN_DURATION_MINUTES,
        )
    start = grid_settings.lunch_window_start
    end = grid_settings.lunch_window_end
    min_duration = grid_settings.lunch_min_duration_minutes

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


def _resolve_solver_engine_version() -> str:
    version = str(getattr(settings, "SOLVER_ENGINE_VERSION", DEFAULT_SOLVER_ENGINE_VERSION)).lower()
    return version if version in {"v1", "v2"} else DEFAULT_SOLVER_ENGINE_VERSION


def _resolve_solver_v2_rolling_weeks() -> int:
    value = int(getattr(settings, "SOLVER_V2_ROLLING_WEEKS", DEFAULT_SOLVER_V2_ROLLING_WEEKS))
    return max(1, value)


def _resolve_solver_v2_objective_mode() -> str:
    mode = str(getattr(settings, "SOLVER_V2_OBJECTIVE_MODE", DEFAULT_SOLVER_V2_OBJECTIVE_MODE)).lower()
    if mode != DEFAULT_SOLVER_V2_OBJECTIVE_MODE:
        return DEFAULT_SOLVER_V2_OBJECTIVE_MODE
    return mode


def _solver_execution_meta() -> dict[str, int | str]:
    return {
        "solver_version": _resolve_solver_engine_version(),
        "solver_v2_rolling_weeks": _resolve_solver_v2_rolling_weeks(),
        "solver_v2_objective_mode": _resolve_solver_v2_objective_mode(),
    }


def _task_progress_meta(step: int, detail: str, phase: str) -> dict:
    """Meta comum de progresso para monitorização no frontend."""
    meta = {
        "phase": phase,
        "detail": detail,
        "progress": {
            "current": step,
            "total": GENERATION_TOTAL_STEPS,
        },
    }
    meta.update(_solver_execution_meta())
    return meta


def _task_cancel_key(task_id: str) -> str:
    return f"{TASK_CANCEL_KEY_PREFIX}{task_id}"


def _active_task_by_org_key(organization_id: int) -> str:
    return f"{ACTIVE_TASK_BY_ORG_KEY_PREFIX}{organization_id}"


def _is_cancel_requested(task_id: str | None) -> bool:
    if not task_id:
        return False

    try:
        r = redis.Redis.from_url(str(settings.REDIS_URL))
        flag = r.get(_task_cancel_key(task_id))
        return bool(flag and flag.decode("utf-8") == "1")
    except Exception:
        return False


def _raise_if_cancel_requested(task: Task, *, step: int, phase: str) -> None:
    task_id = getattr(task.request, "id", None)
    if not _is_cancel_requested(task_id):
        return

    task.update_state(
        state="CANCELED",
        meta=_task_progress_meta(step, "Cancelamento solicitado pelo utilizador.", phase),
    )
    raise GenerationCancelledError("Geração cancelada pelo utilizador.")


def _cleanup_task_runtime_flags(task_id: str | None, organization_id: int) -> None:
    if not task_id:
        return

    try:
        r = redis.Redis.from_url(str(settings.REDIS_URL))
        r.delete(_task_cancel_key(task_id))

        active_key = _active_task_by_org_key(organization_id)
        active_task = r.get(active_key)
        if active_task and active_task.decode("utf-8") == task_id:
            r.delete(active_key)
    except Exception:
        pass


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
    organization_id: int,
    gen_id: str,
    lesson_class_map: dict,
    is_draft: bool = False,
    cancel_checker=None,
) -> dict:
    """Guarda os ScheduleOutput e atualiza projected_end_date de cada turma."""
    for index, block in enumerate(blocks):
        if cancel_checker and index % 250 == 0:
            cancel_checker()

        schedule_service.create_schedule_output_with_date_sync(
            db=db,
            lesson_id=block.lesson_id,
            timeslot_id=block.ts_id,
            room_id=block.room_id,
            output_date=block.output_date,
            organization_id=organization_id,
            gen_id=gen_id,
            is_draft=is_draft,
        )

    # Só atualiza projected_end_date quando o horário é ativado (não draft)
    if not is_draft:
        if cancel_checker:
            cancel_checker()
        class_end_dates = _compute_class_end_dates(blocks, lesson_class_map)
        for class_id, end_date in class_end_dates.items():
            schedule_service.update_class_projected_end_date_sync(db, class_id, end_date)
        return class_end_dates

    return {}


def _invalidate_cache(organization_id: int) -> None:
    """Invalida a cache Redis do horário desta organização."""
    try:
        r = redis.Redis.from_url(str(settings.REDIS_URL))
        r.delete(f"schedule_latest_data_{organization_id}")
    except Exception as exc:
        logger.warning("Cache invalidation failed", error=str(exc))


# ---------------------------------------------------------------------------
# Tarefa Celery principal
# ---------------------------------------------------------------------------

@celery_app.task(bind=True)
def generate_schedule_task(self: Task, organization_id: int, mode: str = "full") -> dict:
    """Orquestrador completo: FETCH → SOLVE → EXPAND → SAVE."""
    solver_meta = _solver_execution_meta()
    candidate_pruning_summary: dict | None = None

    def _task_result(**payload) -> dict:
        result = dict(payload)
        if candidate_pruning_summary is not None and "candidate_pruning" not in result:
            result["candidate_pruning"] = candidate_pruning_summary
        result.update(solver_meta)
        return result

    logger.info(
        "Iniciando geração de horário",
        organization_id=organization_id,
        mode=mode,
        solver_version=solver_meta["solver_version"],
    )
    gen_id = str(uuid.uuid4())
    task_id = getattr(self.request, "id", None)
    db = SessionLocalSync()

    try:
        # 1. FETCH — configurações e dados curriculares
        self.update_state(state="FETCHING", meta=_task_progress_meta(1, "A iniciar pré-processamento...", "FETCHING"))
        _raise_if_cancel_requested(self, step=1, phase="FETCHING")

        self.update_state(state="FETCHING", meta=_task_progress_meta(2, "A ler configurações da escola...", "FETCHING"))
        _raise_if_cancel_requested(self, step=2, phase="FETCHING")
        settings_list = schedule_service.get_org_settings_sync(db, organization_id)
        org_settings = _select_org_settings(settings_list)
        if not org_settings:
            return _task_result(status="Error", message=ERR_NO_DATES)

        is_repair = mode == "repair"
        repair_window_days = _resolve_repair_window_days(org_settings) if is_repair else 0

        self.update_state(state="FETCHING", meta=_task_progress_meta(3, "A sincronizar lições da matriz turma-disciplina...", "FETCHING"))
        _raise_if_cancel_requested(self, step=3, phase="FETCHING")
        lesson_sync_stats = schedule_service.sync_lessons_from_class_subject_links_sync(db, organization_id)

        self.update_state(state="FETCHING", meta=_task_progress_meta(4, "A preparar inputs curriculares e carga remanescente...", "FETCHING"))
        _raise_if_cancel_requested(self, step=4, phase="FETCHING")
        raw_lessons = schedule_service.get_active_lessons_with_subject_sync(db, organization_id)
        if not raw_lessons:
            return _task_result(status="Error", message=ERR_NO_LESSONS)

        raw_timeslots = schedule_service.get_timeslots_by_org_sync(db, organization_id)
        if not raw_timeslots:
            return _task_result(status="Error", message="Não existem blocos horários configurados.")
        timeslot_inputs = _build_timeslot_inputs(raw_timeslots)
        min_slot_minutes = min(ts.duration_minutes for ts in timeslot_inputs if ts.duration_minutes > 0)
        grid_settings = schedule_service.get_grid_settings_sync(db, organization_id)
        lunch_start_minutes, lunch_end_minutes, lunch_min_duration = _resolve_lunch_constraints(grid_settings)

        expansion_start_date = _resolve_expansion_start_date(
            org_settings.school_start_date,
            mode=mode,
            repair_window_days=repair_window_days,
        )
        hard_end_date = _resolve_hard_end_date(org_settings)
        if hard_end_date is None:
            return _task_result(status="Error", message=ERR_NO_DATES)
        if hard_end_date < expansion_start_date:
            if is_repair:
                return _task_result(
                    status="Error",
                    message=ERR_REPAIR_WINDOW_NO_FUTURE,
                    detail=_build_repair_window_block_detail(repair_window_days, hard_end_date),
                )
            return _task_result(status="Error", message=ERR_INVALID_HARD_END)

        planning_target_end_date = _resolve_planning_target_end_date(
            org_settings.school_target_end_date,
            hard_end_date,
        )

        calendar_events = schedule_service.get_calendar_events_sync(db, organization_id)
        blocked_dates = _build_blocked_dates(calendar_events)
        primary_window = _build_primary_rolling_window(
            window_start_date=expansion_start_date,
            hard_end_date=hard_end_date,
            blocked_dates=blocked_dates,
            rolling_weeks=_resolve_solver_v2_rolling_weeks(),
        )
        planning_weeks = _compute_planning_weeks_from_primary_window(primary_window)

        modules_by_subject = schedule_service.get_modules_by_subject_sync(db, organization_id)
        progress_map = schedule_service.get_class_progress_map_sync(db, organization_id)

        raw_lesson_inputs = _build_lesson_inputs(
            raw_lessons,
            modules_by_subject,
            progress_map,
            planning_weeks,
            min_slot_minutes,
            target_end_date=planning_target_end_date,
        )
        lesson_inputs = _build_lesson_inputs(
            raw_lessons,
            modules_by_subject,
            progress_map,
            planning_weeks,
            min_slot_minutes,
            target_end_date=planning_target_end_date,
        )
        raw_remaining_minutes = sum(li.remaining_minutes for li in raw_lesson_inputs)
        reconciled_remaining_minutes = sum(li.remaining_minutes for li in lesson_inputs)
        committed_minutes = sum(
            int(round(max(0.0, float(v)) * 60)) for v in progress_map.values()
        ) if is_repair else 0

        if not lesson_inputs:
            return _task_result(
                status="Success",
                message=ERR_ALL_DONE,
                count=0,
                remaining_summary=_build_remaining_summary(
                    raw_remaining_minutes,
                    reconciled_remaining_minutes,
                    committed_minutes,
                    post_expand_remaining_minutes=0,
                ),
            )

        self.update_state(state="FETCHING", meta=_task_progress_meta(5, "A carregar salas, disponibilidades e calendário...", "FETCHING"))
        _raise_if_cancel_requested(self, step=5, phase="FETCHING")
        raw_rooms = room_service.get_rooms_by_org_sync(db, organization_id)
        raw_availabilities = schedule_service.get_availabilities_by_org_sync(db, organization_id)

        availability_map = {
            (a.teacher_id, a.timeslot_id): a.score for a in raw_availabilities
        }
        room_inputs = _build_room_inputs(raw_rooms)

        if solver_meta["solver_version"] == "v2":
            raw_candidates = build_candidate_universe(
                lessons=lesson_inputs,
                timeslots=timeslot_inputs,
                rooms=room_inputs,
                window_start_date=primary_window["window_start_date"],
                window_end_date=primary_window["window_end_date"],
                blocked_dates=blocked_dates,
            )
            pruned_candidates, pruning_telemetry = prune_candidates_hard_first(
                raw_candidates,
                availability_map=availability_map,
                lunch_window_start_minutes=lunch_start_minutes,
                lunch_window_end_minutes=lunch_end_minutes,
                lunch_min_duration_minutes=lunch_min_duration,
            )
            candidate_pruning_summary = pruning_telemetry.to_dict()

            logger.info(
                "Pruning hard-first V2 concluido",
                candidates_before=pruning_telemetry.candidates_before,
                candidates_after=pruning_telemetry.candidates_after,
                removed_total=pruning_telemetry.removed_total,
                removed_ratio=pruning_telemetry.removed_ratio,
                removed_by_reason=pruning_telemetry.removed_by_reason,
            )

            if not pruned_candidates:
                return _task_result(status="Impossible", message=MSG_IMPOSSIBLE)

        # Repair mode: ler padrão ativo anterior para minimizar perturbações
        previous_pattern = (
            schedule_service.get_active_future_pattern_sync(db, organization_id)
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

        # 2. SOLVE — CP-SAT encontra o padrão ótimo
        self.update_state(state="SOLVING", meta=_task_progress_meta(6, "A otimizar com a engine de cálculo...", "SOLVING"))
        _raise_if_cancel_requested(self, step=6, phase="SOLVING")

        if solver_meta["solver_version"] == "v2":
            # --- Solver V2: lexicographic engine on real dates ---
            frozen_until = (
                date.today() + timedelta(days=repair_window_days) if is_repair else None
            )
            published_block_keys: set[tuple[int, date, int]] = set()
            if is_repair and previous_pattern:
                # previous_pattern is {(lesson_id, ts_id): 1} — not date-keyed;
                # churn comparison uses published blocks from repair context
                published_block_keys = set()

            backlog_by_lesson = {li.lesson_id: li.remaining_minutes for li in lesson_inputs}

            v2_engine = ScheduleEngineV2(
                candidates=pruned_candidates,
                window_start_date=primary_window["window_start_date"],
                window_end_date=primary_window["window_end_date"],
                school_target_end_date=planning_target_end_date,
                hard_end_date=hard_end_date,
                published_blocks=published_block_keys,
                frozen_until=frozen_until,
            )
            v2_result = v2_engine.solve()
            _raise_if_cancel_requested(self, step=6, phase="SOLVING")

            if v2_result.status == "infeasible":
                return _task_result(status="Impossible", message=MSG_IMPOSSIBLE)

            # F.01 — Validate blocks against calendar (safety net)
            primary_v2_blocks, rejected_blocks = validate_v2_blocks_calendar(
                v2_result.blocks,
                blocked_dates=blocked_dates,
                hard_end_date=hard_end_date,
            )

            if not primary_v2_blocks:
                return _task_result(status="Error", message=ERR_NO_EXPAND)

            # Build backlog and relationship maps for fill
            backlog_by_lesson = {li.lesson_id: li.remaining_minutes for li in lesson_inputs}
            lesson_class_map_fill = {lesson.id: lesson.class_id for lesson in raw_lessons}
            lesson_teacher_map_fill = {lesson.id: lesson.teacher_id for lesson in raw_lessons}
            lesson_room_type_fill = {li.lesson_id: li.required_room_type for li in lesson_inputs}

            # Build timeslots grouped by day_of_week (with start/end minutes for lunch calc)
            _ts_by_dow: dict[int, list[_TimeslotInfo]] = defaultdict(list)
            for ti in timeslot_inputs:
                _ts_by_dow[ti.day_of_week].append(
                    _TimeslotInfo(
                        ts_id=ti.ts_id,
                        day_of_week=ti.day_of_week,
                        duration_minutes=ti.duration_minutes,
                        start_minutes=ti.start_minutes,
                        end_minutes=ti.end_minutes,
                    )
                )
            # Sort each day's timeslots by start_minutes for correct daily ordering
            for dow in _ts_by_dow:
                _ts_by_dow[dow].sort(key=lambda t: t.start_minutes)

            # Build rooms grouped by type
            _rooms_by_type: dict[str, list[_RoomInfo]] = defaultdict(list)
            for ri in room_inputs:
                _rooms_by_type[ri.room_type].append(
                    _RoomInfo(room_id=ri.room_id, room_type=ri.room_type)
                )

            # F.02 — Fill-opportunistic: dense greedy fill across all slots
            self.update_state(state="EXPANDING", meta=_task_progress_meta(7, "A preencher slots disponíveis (fill-opportunistic)...", "EXPANDING"))
            _raise_if_cancel_requested(self, step=7, phase="EXPANDING")

            fill_result = fill_opportunistic_v2(
                primary_v2_blocks,
                backlog_by_lesson=backlog_by_lesson,
                lesson_class_map=lesson_class_map_fill,
                lesson_teacher_map=lesson_teacher_map_fill,
                lesson_room_type_map=lesson_room_type_fill,
                timeslots_by_dow=dict(_ts_by_dow),
                rooms_by_type=dict(_rooms_by_type),
                window_start_date=primary_window["window_start_date"],
                # Fill runs across the ENTIRE school year — not just the 8-week CP-SAT window.
                window_end_date=hard_end_date,
                hard_end_date=hard_end_date,
                blocked_dates=blocked_dates,
                # Lunch window: same constraints as Phase D (prune_candidates_hard_first)
                lunch_window_start_minutes=lunch_start_minutes,
                lunch_window_end_minutes=lunch_end_minutes,
                lunch_min_duration_minutes=lunch_min_duration,
            )

            # F.03 — Compute transparent residual
            residual = compute_residual_summary(
                backlog_by_lesson,
                fill_result,
                hard_end_date=hard_end_date,
            )

            # Convert all blocks to ScheduledBlock for shared save pipeline
            blocks_v2: list[ScheduledBlock] = [
                ScheduledBlock(
                    lesson_id=b.lesson_id,
                    ts_id=b.ts_id,
                    room_id=b.room_id,
                    output_date=b.output_date,
                )
                for b in fill_result.all_blocks
            ]

            if not blocks_v2:
                return _task_result(status="Error", message=ERR_NO_EXPAND)

            remaining_after_expand = residual.backlog_remaining_minutes
            remaining_summary = _build_remaining_summary(
                raw_remaining_minutes,
                reconciled_remaining_minutes,
                committed_minutes,
                post_expand_remaining_minutes=remaining_after_expand,
            )

            v2_metrics: dict = {
                "solver_v2_projected_end_date": str(v2_result.projected_end_date) if v2_result.projected_end_date else None,
                "solver_v2_spread_days": v2_result.end_date_spread_days,
                "solver_v2_churn_blocks": v2_result.churn_blocks,
                "solver_v2_wall_time": v2_result.solver_wall_time,
                "solver_v2_fill_blocks_added": len(fill_result.fill_blocks),
                "solver_v2_backlog_remaining_hours": residual.backlog_remaining_hours,
                "solver_v2_hard_limit_reached": residual.hard_limit_reached,
            }

            # SAVE
            self.update_state(state="SAVING", meta=_task_progress_meta(9, "A gravar solução V2 em base de dados...", "SAVING"))
            _raise_if_cancel_requested(self, step=9, phase="SAVING")

            lesson_class_map = {lesson.id: lesson.class_id for lesson in raw_lessons}

            if is_repair:
                _save_results(
                    db, blocks_v2, organization_id, gen_id, lesson_class_map,
                    is_draft=True,
                    cancel_checker=lambda: _raise_if_cancel_requested(self, step=9, phase="SAVING"),
                )
                _raise_if_cancel_requested(self, step=9, phase="SAVING")
                db.commit()
                _invalidate_cache(organization_id)
                logger.info("Rascunho V2 criado", blocks=len(blocks_v2), gen_id=gen_id)
                return _task_result(
                    status="Success",
                    generation_id=gen_id,
                    mode="repair",
                    is_draft=True,
                    count=len(blocks_v2),
                    detail=residual.detail,
                    remaining_summary=remaining_summary,
                    **v2_metrics,
                    progress={"current": GENERATION_TOTAL_STEPS, "total": GENERATION_TOTAL_STEPS},
                )

            # Full mode V2
            start_window = min(b.output_date for b in blocks_v2)
            end_window = max(b.output_date for b in blocks_v2)
            schedule_service.clear_schedule_window_sync(db, organization_id, start_window, end_window)
            class_end_dates = _save_results(
                db, blocks_v2, organization_id, gen_id, lesson_class_map,
                is_draft=False,
                cancel_checker=lambda: _raise_if_cancel_requested(self, step=9, phase="SAVING"),
            )
            _raise_if_cancel_requested(self, step=9, phase="SAVING")
            db.commit()
            _invalidate_cache(organization_id)
            logger.info("Geração V2 concluída", blocks=len(blocks_v2), fill_added=len(fill_result.fill_blocks), classes=len(class_end_dates))
            return _task_result(
                status="Success",
                generation_id=gen_id,
                mode="full",
                is_draft=False,
                count=len(blocks_v2),
                classes_updated=len(class_end_dates),
                detail=residual.detail,
                remaining_summary=remaining_summary,
                **v2_metrics,
                progress={"current": GENERATION_TOTAL_STEPS, "total": GENERATION_TOTAL_STEPS},
            )

        # --- Solver V1: original weekly-pattern engine ---
        engine = ScheduleEngine(
            lessons=lesson_inputs,
            timeslots=timeslot_inputs,
            rooms=room_inputs,
            availability_map=availability_map,
            previous_pattern=previous_pattern,
            lunch_window_start_minutes=lunch_start_minutes,
            lunch_window_end_minutes=lunch_end_minutes,
            lunch_min_duration_minutes=lunch_min_duration,
        )
        assignments = engine.solve()
        _raise_if_cancel_requested(self, step=6, phase="SOLVING")

        if assignments is None:
            return _task_result(status="Impossible", message=MSG_IMPOSSIBLE)

        # 3. EXPAND — padrão semanal → datas absolutas
        self.update_state(state="EXPANDING", meta=_task_progress_meta(7, "A expandir padrão semanal para datas reais...", "EXPANDING"))
        _raise_if_cancel_requested(self, step=7, phase="EXPANDING")

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
        remaining_summary = _build_remaining_summary(
            raw_remaining_minutes,
            reconciled_remaining_minutes,
            committed_minutes,
            post_expand_remaining_minutes=remaining_after_expand,
        )

        if not blocks:
            return _task_result(status="Error", message=ERR_NO_EXPAND)

        self.update_state(state="EXPANDING", meta=_task_progress_meta(8, "A validar blocos gerados e projeções...", "EXPANDING"))
        _raise_if_cancel_requested(self, step=8, phase="EXPANDING")

        # 4. SAVE — comportamento depende do modo
        self.update_state(state="SAVING", meta=_task_progress_meta(9, "A gravar solução em base de dados...", "SAVING"))
        _raise_if_cancel_requested(self, step=9, phase="SAVING")

        if is_repair:
            # Repair: guarda como rascunho (is_draft=True) sem apagar o ativo
            _save_results(
                db,
                blocks,
                organization_id,
                gen_id,
                lesson_class_map,
                is_draft=True,
                cancel_checker=lambda: _raise_if_cancel_requested(self, step=9, phase="SAVING"),
            )
            _raise_if_cancel_requested(self, step=9, phase="SAVING")
            db.commit()
            _invalidate_cache(organization_id)
            logger.info("Rascunho de reparação criado", blocks=len(blocks), gen_id=gen_id)
            detail = None
            if remaining_after_expand > 0:
                remaining_hours = round(remaining_after_expand / 60, 1)
                detail = f"{HARD_LIMIT_REACHED_DETAIL} Restam {remaining_hours}h além de {hard_end_date.isoformat()}."
            return _task_result(
                status="Success",
                generation_id=gen_id,
                mode="repair",
                is_draft=True,
                count=len(blocks),
                detail=detail,
                remaining_summary=remaining_summary,
                progress={
                    "current": GENERATION_TOTAL_STEPS,
                    "total": GENERATION_TOTAL_STEPS,
                },
            )

        # Full: limpa futuro e grava novo horário ativo
        _raise_if_cancel_requested(self, step=9, phase="SAVING")
        start_window = min(block.output_date for block in blocks)
        end_window = max(block.output_date for block in blocks)
        schedule_service.clear_schedule_window_sync(db, organization_id, start_window, end_window)
        class_end_dates = _save_results(
            db,
            blocks,
            organization_id,
            gen_id,
            lesson_class_map,
            is_draft=False,
            cancel_checker=lambda: _raise_if_cancel_requested(self, step=9, phase="SAVING"),
        )
        _raise_if_cancel_requested(self, step=9, phase="SAVING")
        db.commit()

        _invalidate_cache(organization_id)

        logger.info("Geração concluída", blocks=len(blocks), classes=len(class_end_dates))
        detail = None
        if remaining_after_expand > 0:
            remaining_hours = round(remaining_after_expand / 60, 1)
            detail = f"{HARD_LIMIT_REACHED_DETAIL} Restam {remaining_hours}h além de {hard_end_date.isoformat()}."
        return _task_result(
            status="Success",
            generation_id=gen_id,
            mode="full",
            is_draft=False,
            count=len(blocks),
            classes_updated=len(class_end_dates),
            detail=detail,
            remaining_summary=remaining_summary,
            progress={
                "current": GENERATION_TOTAL_STEPS,
                "total": GENERATION_TOTAL_STEPS,
            },
        )

    except GenerationCancelledError as exc:
        db.rollback()
        logger.warning(
            "Geração cancelada pelo utilizador",
            organization_id=organization_id,
            mode=mode,
            task_id=task_id,
        )
        return _task_result(
            status="Canceled",
            message=str(exc),
            detail="Cancelamento solicitado pelo utilizador.",
            progress={
                "current": 9,
                "total": GENERATION_TOTAL_STEPS,
            },
        )

    except Exception as exc:
        db.rollback()
        logger.error("Erro crítico na geração", error=str(exc), exc_info=True)
        return _task_result(status="Error", message=str(exc))

    finally:
        _cleanup_task_runtime_flags(task_id, organization_id)
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

        for organization_id in org_ids:
            count = occurrence_service.auto_confirm_daily_sync(db, organization_id, today)
            summary[organization_id] = count
            logger.info(
                "Auto-confirm diário concluído",
                organization_id=organization_id,
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