"""Serviço de Ocorrências de Aulas (Sprint 2).

Responsabilidades:
- Confirmar automaticamente aulas como GIVEN (cron diário)
- Registar faltas (GAP) e substituições (SUBSTITUTED) manualmente
- Calcular dívidas de horas (ClassProgress vs. previsto até hoje)
- Encontrar professores disponíveis para substituição num slot
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import select, and_
from sqlalchemy.orm import Session, joinedload

from app import models
from app import schemas

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
OCCURRENCE_NOT_FOUND = "Ocorrência não encontrada"


# ---------------------------------------------------------------------------
# Funções de leitura
# ---------------------------------------------------------------------------

def get_occurrence_sync(
    db: Session, occurrence_id: int, org_id: int
) -> Optional[models.LessonOccurrence]:
    """Devolve uma ocorrência pelo ID, validando o tenant."""
    return db.execute(
        select(models.LessonOccurrence).where(
            and_(
                models.LessonOccurrence.id == occurrence_id,
                models.LessonOccurrence.org_id == org_id,
            )
        )
    ).scalar_one_or_none()


def list_occurrences_sync(
    db: Session,
    org_id: int,
    class_id: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> list[models.LessonOccurrence]:
    """Lista ocorrências com filtros opcionais."""
    stmt = (
        select(models.LessonOccurrence)
        .options(
            joinedload(models.LessonOccurrence.schedule_output).joinedload(
                models.ScheduleOutput.lesson
            )
        )
        .where(models.LessonOccurrence.org_id == org_id)
    )
    if class_id is not None:
        stmt = stmt.join(
            models.ScheduleOutput,
            models.LessonOccurrence.schedule_output_id == models.ScheduleOutput.id,
        ).join(
            models.Lesson,
            models.ScheduleOutput.lesson_id == models.Lesson.id,
        ).where(models.Lesson.class_id == class_id)
    if date_from is not None:
        stmt = stmt.where(models.LessonOccurrence.date >= date_from)
    if date_to is not None:
        stmt = stmt.where(models.LessonOccurrence.date <= date_to)
    stmt = stmt.order_by(models.LessonOccurrence.date.desc())
    return list(db.execute(stmt).scalars().unique())


# ---------------------------------------------------------------------------
# Actualização pelo diretor
# ---------------------------------------------------------------------------

def update_occurrence_sync(
    db: Session,
    occurrence_id: int,
    org_id: int,
    payload: schemas.LessonOccurrenceUpdate,
) -> models.LessonOccurrence:
    """Permite ao diretor marcar uma ocorrência como GAP ou SUBSTITUTED."""
    occurrence = get_occurrence_sync(db, occurrence_id, org_id)
    if occurrence is None:
        raise ValueError(OCCURRENCE_NOT_FOUND)

    occurrence.status = payload.status  # type: ignore[assignment]
    occurrence.substitute_teacher_id = payload.substitute_teacher_id
    occurrence.substitute_subject_id = payload.substitute_subject_id
    db.commit()
    db.refresh(occurrence)
    return occurrence


# ---------------------------------------------------------------------------
# Confirmação automática diária (chamada pelo cron Celery Beat)
# ---------------------------------------------------------------------------

def auto_confirm_daily_sync(db: Session, org_id: int, target_date: date) -> int:
    """Cria registos GIVEN para todos os ScheduleOutputs do dia sem ocorrência.

    Retorna o número de registos criados.
    Returns 0 se não houver slots planeados para essa data.
    """
    # 1. Buscar todos os ScheduleOutputs planeados para target_date
    scheduled_slots = list(
        db.execute(
            select(models.ScheduleOutput)
            .options(joinedload(models.ScheduleOutput.timeslot))
            .where(
                and_(
                    models.ScheduleOutput.organization_id == org_id,
                    models.ScheduleOutput.date == target_date,
                    models.ScheduleOutput.is_draft.is_(False),
                )
            )
        )
        .scalars()
        .unique()
    )

    created_count = 0
    for slot in scheduled_slots:
        # 2. Verificar se já existe uma ocorrência manual para este slot
        existing = db.execute(
            select(models.LessonOccurrence).where(
                and_(
                    models.LessonOccurrence.schedule_output_id == slot.id,
                    models.LessonOccurrence.date == target_date,
                )
            )
        ).scalar_one_or_none()

        if existing is not None:
            continue  # Diretor já registou manualmente — respeitar

        # 3. Calcular horas do timeslot
        ts = slot.timeslot
        if ts is not None:
            start_dt = datetime.combine(target_date, ts.start_time)
            end_dt = datetime.combine(target_date, ts.end_time)
            hours = (end_dt - start_dt).total_seconds() / 3600.0
        else:
            hours = 0.0

        # 4. Criar ocorrência GIVEN
        occurrence = models.LessonOccurrence(
            org_id=org_id,
            schedule_output_id=slot.id,
            date=target_date,
            status=models.LessonOccurrenceStatus.given,
            hours_given=hours,
            created_at=datetime.now(timezone.utc),
        )
        db.add(occurrence)

        # 5. Incrementar ClassProgress
        _increment_class_progress(db, slot, hours)
        created_count += 1

    db.commit()
    return created_count


def _increment_class_progress(
    db: Session, slot: models.ScheduleOutput, hours: float
) -> None:
    """Incrementa ClassProgress para o módulo activo da Lesson deste slot.

    Nota: Lê a lesson com join ao subject para encontrar o módulo activo.
    A função só actualiza o primeiro módulo não-completo (módulos sequenciais).
    """
    # Carregar a lesson com subject e class
    lesson = db.execute(
        select(models.Lesson)
        .options(joinedload(models.Lesson.subject).joinedload(models.Subject.modules))
        .where(models.Lesson.id == slot.lesson_id)
    ).unique().scalar_one_or_none()

    if lesson is None or lesson.subject is None:
        return

    # Módulos ordenados sequencialmente
    ordered_modules = sorted(lesson.subject.modules, key=lambda m: m.order)

    for module in ordered_modules:
        progress = db.execute(
            select(models.ClassProgress).where(
                and_(
                    models.ClassProgress.class_id == lesson.class_id,
                    models.ClassProgress.module_id == module.id,
                )
            )
        ).scalar_one_or_none()

        if progress is None:
            # Primeiro progresso deste módulo
            progress = models.ClassProgress(
                class_id=lesson.class_id,
                module_id=module.id,
                hours_completed=0,
                is_completed=False,
            )
            db.add(progress)
            db.flush()

        if progress.is_completed:
            continue  # Módulo já concluído — passa para o próximo

        # Módulo activo encontrado: incrementar horas
        progress.hours_completed += int(round(hours))
        if progress.hours_completed >= module.hours_total:
            progress.is_completed = True
        return  # Só actualiza um módulo por vez


# ---------------------------------------------------------------------------
# Dívidas de horas
# ---------------------------------------------------------------------------

def get_debts_sync(
    db: Session, org_id: int, class_id: Optional[int] = None
) -> schemas.DebtListRead:
    """Calcula dívidas: slots passados com status=GAP por turma/disciplina."""
    # Buscar ocorrências GAP com data ≤ hoje
    today = date.today()
    stmt = (
        select(models.LessonOccurrence)
        .options(
            joinedload(models.LessonOccurrence.schedule_output)
            .joinedload(models.ScheduleOutput.lesson)
            .joinedload(models.Lesson.class_model),
            joinedload(models.LessonOccurrence.schedule_output)
            .joinedload(models.ScheduleOutput.lesson)
            .joinedload(models.Lesson.subject),
            joinedload(models.LessonOccurrence.schedule_output)
            .joinedload(models.ScheduleOutput.lesson)
            .joinedload(models.Lesson.teacher),
        )
        .where(
            and_(
                models.LessonOccurrence.org_id == org_id,
                models.LessonOccurrence.status == models.LessonOccurrenceStatus.gap,
                models.LessonOccurrence.date <= today,
            )
        )
    )
    if class_id is not None:
        stmt = (
            stmt
            .join(
                models.ScheduleOutput,
                models.LessonOccurrence.schedule_output_id == models.ScheduleOutput.id,
            )
            .join(models.Lesson, models.ScheduleOutput.lesson_id == models.Lesson.id)
            .where(models.Lesson.class_id == class_id)
        )

    occurrences = list(db.execute(stmt).scalars().unique())

    # Agregar por (class_id, subject_id)
    key_counts: dict[tuple[int, int], int] = defaultdict(int)
    key_hours: dict[tuple[int, int], float] = defaultdict(float)
    key_meta: dict[tuple[int, int], dict] = {}

    for occ in occurrences:
        so = occ.schedule_output
        if so is None or so.lesson is None:
            continue
        lesson = so.lesson
        key = (lesson.class_id, lesson.subject_id)
        key_counts[key] += 1
        key_hours[key] += occ.hours_given
        if key not in key_meta:
            key_meta[key] = {
                "class_name": lesson.class_model.name if lesson.class_model else "—",
                "subject_name": lesson.subject.name if lesson.subject else "—",
                "teacher_id": lesson.teacher_id,
                "teacher_name": lesson.teacher.name if lesson.teacher else None,
            }

    items = [
        schemas.DebtItem(
            class_id=k[0],
            class_name=key_meta[k]["class_name"],
            subject_id=k[1],
            subject_name=key_meta[k]["subject_name"],
            teacher_id=key_meta[k]["teacher_id"],
            teacher_name=key_meta[k]["teacher_name"],
            gap_occurrences=key_counts[k],
            hours_owed=round(key_hours[k], 2),
        )
        for k in sorted(key_counts.keys())
    ]

    return schemas.DebtListRead(
        total_gaps=sum(key_counts.values()),
        total_hours_owed=round(sum(key_hours.values()), 2),
        items=items,
    )


# ---------------------------------------------------------------------------
# Encontrar substitutos disponíveis
# ---------------------------------------------------------------------------

def get_available_substitutes_sync(
    db: Session, org_id: int, timeslot_id: int, target_date: date
) -> list[schemas.AvailableSubstituteRead]:
    """Devolve professores assignados à organização que:
    1. Têm disponibilidade (score ≥ 0) no timeslot indicado.
    2. Não têm já uma aula agendada (ScheduleOutput) para essa data.

    Retorna uma lista de candidatos com a disciplina que leccionam.
    """
    # 1. Timeslot info (para saber o dia da semana)
    ts = db.execute(
        select(models.Timeslot).where(
            and_(
                models.Timeslot.id == timeslot_id,
                models.Timeslot.organization_id == org_id,
            )
        )
    ).scalar_one_or_none()

    if ts is None:
        return []

    day_of_week = ts.day_of_week

    # 2. Professores com availability score ≥ 0 (não impossível) para este timeslot
    available_teacher_ids = {
        row.teacher_id
        for row in db.execute(
            select(models.Availability.teacher_id).where(
                and_(
                    models.Availability.timeslot_id == timeslot_id,
                    models.Availability.score >= 0,
                )
            )
        ).all()
    }

    if not available_teacher_ids:
        return []

    # 3. Professores já ocupados nesta data/timeslot (têm ScheduleOutput)
    busy_teacher_ids = {
        row.teacher_id
        for row in db.execute(
            select(models.Lesson.teacher_id)
            .join(models.ScheduleOutput, models.ScheduleOutput.lesson_id == models.Lesson.id)
            .where(
                and_(
                    models.ScheduleOutput.organization_id == org_id,
                    models.ScheduleOutput.timeslot_id == timeslot_id,
                    models.ScheduleOutput.date == target_date,
                    models.ScheduleOutput.is_draft.is_(False),
                )
            )
        ).all()
    }

    free_teacher_ids = available_teacher_ids - busy_teacher_ids

    if not free_teacher_ids:
        return []

    # 4. Buscar ClassSubjectLinks para os professores livres (para saber que disciplina dão)
    links = list(
        db.execute(
            select(models.ClassSubjectLink)
            .options(
                joinedload(models.ClassSubjectLink.teacher),
                joinedload(models.ClassSubjectLink.subject),
                joinedload(models.ClassSubjectLink.class_),
            )
            .where(
                and_(
                    models.ClassSubjectLink.teacher_id.in_(free_teacher_ids),
                )
            )
            .join(
                models.Class,
                models.ClassSubjectLink.class_id == models.Class.id,
            )
            .where(
                and_(
                    models.Class.organization_id == org_id,
                    models.Class.is_archived.is_(False),
                )
            )
        )
        .scalars()
        .unique()
    )

    results = [
        schemas.AvailableSubstituteRead(
            teacher_id=link.teacher_id,
            teacher_name=link.teacher.name if link.teacher else "—",
            subject_id=link.subject_id,
            subject_name=link.subject.name if link.subject else "—",
            class_id=link.class_id,
            class_name=link.class_.name if link.class_ else "—",
        )
        for link in links
        if link.teacher_id is not None
    ]

    return results
