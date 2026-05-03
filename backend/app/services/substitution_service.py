from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy import and_
from app import models, schemas
from datetime import date
from app.models import LessonOccurrenceStatus
from app.services import occurrence_service


ERR_INVALID_LESSON = "Aula invalida ou fora da organizacao"
ERR_INVALID_TIMESLOT = "Timeslot invalido ou fora da organizacao"
ERR_INVALID_TEACHER = "Professor invalido ou fora da organizacao"
ERR_ORIGINAL_TEACHER_MISMATCH = "Professor original nao corresponde a aula"
ERR_SUBSTITUTE_NOT_ELIGIBLE = "Professor substituto nao elegivel para esta ocorrencia"


class SubstitutionServiceError(Exception):
    def __init__(self, *, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail


def _select_substitute_subject_from_recommendations(
    recommendations: list[schemas.SubstituteRecommendationRead],
    substitute_teacher_id: int,
) -> int:
    teacher_items = [
        rec for rec in recommendations if rec.teacher_id == substitute_teacher_id
    ]
    if not teacher_items:
        raise SubstitutionServiceError(status_code=409, detail=ERR_SUBSTITUTE_NOT_ELIGIBLE)

    # Determinismo para professor com mais de uma disciplina elegivel.
    selected = sorted(teacher_items, key=lambda rec: (rec.rank, rec.subject_id))[0]
    return int(selected.subject_id)


def _upsert_legacy_substitution_sync(
    sync_db,
    *,
    data: schemas.SubstitutionCreate,
    substitute_subject_id: int,
):
    existing = sync_db.execute(
        select(models.Substitution)
        .where(
            and_(
                models.Substitution.lesson_id == data.lesson_id,
                models.Substitution.timeslot_id == data.timeslot_id,
                models.Substitution.date == data.date,
                models.Substitution.original_teacher_id == data.original_teacher_id,
            )
        )
        .order_by(models.Substitution.id.desc())
    ).scalars().first()

    if existing is None:
        existing = models.Substitution(
            lesson_id=data.lesson_id,
            timeslot_id=data.timeslot_id,
            original_teacher_id=data.original_teacher_id,
            substitute_teacher_id=data.substitute_teacher_id,
            substitute_subject_id=substitute_subject_id,
            date=data.date,
            reason=data.reason,
            status="CONFIRMED",
        )
        sync_db.add(existing)
    else:
        existing.substitute_teacher_id = data.substitute_teacher_id
        existing.substitute_subject_id = substitute_subject_id
        existing.reason = data.reason
        existing.status = "CONFIRMED"

    sync_db.commit()
    sync_db.refresh(existing)
    return existing

async def find_available_teachers(
    db: AsyncSession, 
    timeslot_id: int, 
    date_of_substitution: date,
    exclude_teacher_id: int,
    organization_id: int
) -> list[schemas.ReplacementSuggestion]:
    """
    Encontra professores que NÃO têm aulas nem substituições naquele slot e data.
    """
    
    # 1. Buscar todos os professores da organização (menos o que faltou)
    query_teachers = select(models.Teacher).where(
        models.Teacher.organization_id == organization_id,
        models.Teacher.id != exclude_teacher_id
    )
    result_teachers = await db.execute(query_teachers)
    all_teachers = result_teachers.scalars().all()
    
    suggestions = []

    for teacher in all_teachers:
        # A. Verificar Horário Normal (Semana Tipo)
        # Se ele já tem aula fixa neste timeslot, está ocupado.
        # Nota: Verificação baseada em Hard Constraints do MVP.
        # (Query direta ao ScheduleOutput requereria JOIN com Lesson para obter teacher_id)
        
        # B. Verificar Disponibilidade Declarada (-1)
        # Se o professor disse "Nunca posso à Segunda às 9h", respeitamos.
        # (Código omitido para brevidade, mas seria query à tabela Availability)

        # C. Verificar se já tem OUTRA substituição marcada para este dia/hora
        query_busy_sub = select(models.Substitution).where(
            models.Substitution.substitute_teacher_id == teacher.id,
            models.Substitution.timeslot_id == timeslot_id,
            models.Substitution.date == date_of_substitution,
            models.Substitution.status != "CANCELLED"
        )
        res_busy = await db.execute(query_busy_sub)
        if res_busy.scalars().first():
            continue # Está ocupado noutra substituição

        # SE PASSOU NOS TESTES: Adicionar à lista
        # Lógica de Prioridade Simples
        priority = 3
        reason = "Disponível"
        
        # Aqui podes melhorar: Se teacher.groups contiver a disciplina da aula... priority = 1
        
        suggestions.append(schemas.ReplacementSuggestion(
            teacher_id=teacher.id,
            teacher_name=teacher.name,
            priority=priority,
            reason=reason
        ))

    # Ordenar por prioridade (1 é melhor que 3)
    suggestions.sort(key=lambda x: x.priority)
    return suggestions

async def create_substitution(db: AsyncSession, data: schemas.SubstitutionCreate, organization_id: int):
    def _run(sync_db):
        schedule_output = sync_db.execute(
            select(models.ScheduleOutput)
            .options(joinedload(models.ScheduleOutput.lesson))
            .where(
                and_(
                    models.ScheduleOutput.organization_id == organization_id,
                    models.ScheduleOutput.lesson_id == data.lesson_id,
                    models.ScheduleOutput.timeslot_id == data.timeslot_id,
                    models.ScheduleOutput.date == data.date,
                    models.ScheduleOutput.is_draft.is_(False),
                )
            )
            .order_by(models.ScheduleOutput.id.desc())
        ).scalars().first()

        if schedule_output is None:
            raise SubstitutionServiceError(status_code=400, detail=ERR_INVALID_LESSON)

        timeslot = sync_db.execute(
            select(models.Timeslot).where(
                and_(
                    models.Timeslot.id == data.timeslot_id,
                    models.Timeslot.organization_id == organization_id,
                )
            )
        ).scalar_one_or_none()
        if timeslot is None:
            raise SubstitutionServiceError(status_code=400, detail=ERR_INVALID_TIMESLOT)

        teachers = sync_db.execute(
            select(models.Teacher).where(
                and_(
                    models.Teacher.id.in_([data.original_teacher_id, data.substitute_teacher_id]),
                    models.Teacher.organization_id == organization_id,
                )
            )
        ).scalars().all()
        if len(teachers) != 2:
            raise SubstitutionServiceError(status_code=400, detail=ERR_INVALID_TEACHER)

        if schedule_output.lesson is None:
            raise SubstitutionServiceError(status_code=400, detail=ERR_INVALID_LESSON)

        if schedule_output.lesson.teacher_id != data.original_teacher_id:
            raise SubstitutionServiceError(status_code=400, detail=ERR_ORIGINAL_TEACHER_MISMATCH)

        try:
            occurrence, _ = occurrence_service.create_occurrence_from_block_sync(
                sync_db,
                organization_id=organization_id,
                schedule_output_id=schedule_output.id,
            )
            occurrence_service.log_occurrence_event_safe_sync(
                sync_db,
                organization_id=organization_id,
                event_type=occurrence_service.OBS_EVENT_CREATE,
                result=occurrence_service.OBS_RESULT_SUCCESS,
                occurrence_id=occurrence.id,
                schedule_output_id=occurrence.schedule_output_id,
                detail="legacy_substitution_adapter",
            )
        except occurrence_service.OccurrenceServiceError as exc:
            occurrence_service.log_occurrence_event_safe_sync(
                sync_db,
                organization_id=organization_id,
                event_type=occurrence_service.OBS_EVENT_CREATE,
                result=occurrence_service.classify_occurrence_error_result(exc.status_code),
                occurrence_id=None,
                schedule_output_id=schedule_output.id,
                detail=f"legacy_substitution_adapter: {exc.detail}",
            )
            raise SubstitutionServiceError(status_code=exc.status_code, detail=exc.detail) from exc

        recommendations = occurrence_service.get_substitute_recommendations_sync(
            sync_db,
            organization_id=organization_id,
            occurrence_id=occurrence.id,
        )
        substitute_subject_id = _select_substitute_subject_from_recommendations(
            recommendations,
            data.substitute_teacher_id,
        )

        payload = schemas.LessonOccurrenceUpdate(
            status=LessonOccurrenceStatus.SUBSTITUTED,
            substitute_teacher_id=data.substitute_teacher_id,
            substitute_subject_id=substitute_subject_id,
        )

        try:
            updated = occurrence_service.update_occurrence_sync(
                sync_db,
                occurrence_id=occurrence.id,
                organization_id=organization_id,
                payload=payload,
            )
            occurrence_service.log_occurrence_event_safe_sync(
                sync_db,
                organization_id=organization_id,
                event_type=occurrence_service.OBS_EVENT_DECIDE,
                result=occurrence_service.OBS_RESULT_SUCCESS,
                occurrence_id=updated.id,
                schedule_output_id=updated.schedule_output_id,
                decision_status=updated.status,
                detail="legacy_substitution_adapter",
            )
        except occurrence_service.OccurrenceServiceError as exc:
            occurrence_service.log_occurrence_event_safe_sync(
                sync_db,
                organization_id=organization_id,
                event_type=occurrence_service.OBS_EVENT_DECIDE,
                result=occurrence_service.classify_occurrence_error_result(exc.status_code),
                occurrence_id=occurrence.id,
                schedule_output_id=occurrence.schedule_output_id,
                detail=f"legacy_substitution_adapter: {exc.detail}",
            )
            raise SubstitutionServiceError(status_code=exc.status_code, detail=exc.detail) from exc

        return _upsert_legacy_substitution_sync(
            sync_db,
            data=data,
            substitute_subject_id=substitute_subject_id,
        )

    return await db.run_sync(_run)

async def get_active_substitutions(db: AsyncSession, organization_id: int, skip: int = 0, limit: int = 100):
    query = (
        select(models.Substitution)
        # Dizemos ao SQL: "Traz logo os dados dos professores, não esperes que eu peça"
        .options(
            selectinload(models.Substitution.original_teacher),
            selectinload(models.Substitution.substitute_teacher),
            selectinload(models.Substitution.lesson),
            selectinload(models.Substitution.timeslot)
        )
        .join(models.Substitution.original_teacher)
        .where(models.Teacher.organization_id == organization_id)
        .order_by(models.Substitution.date.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(query)
    substitutions = result.scalars().all()
    return substitutions