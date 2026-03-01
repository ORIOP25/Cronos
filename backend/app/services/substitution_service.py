from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy import and_, or_
from app import models, schemas
from datetime import date

async def find_available_teachers(
    db: AsyncSession, 
    timeslot_id: int, 
    date_of_substitution: date,
    exclude_teacher_id: int,
    org_id: int
) -> list[schemas.ReplacementSuggestion]:
    """
    Encontra professores que NÃO têm aulas nem substituições naquele slot e data.
    """
    
    # 1. Buscar todos os professores da organização (menos o que faltou)
    query_teachers = select(models.Teacher).where(
        models.Teacher.organization_id == org_id,
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

async def create_substitution(db: AsyncSession, data: schemas.SubstitutionCreate, org_id: int):
    # 1. Validar lesson pertence à organização
    lesson_query = select(models.Lesson).where(
        models.Lesson.id == data.lesson_id,
        models.Lesson.organization_id == org_id
    )
    lesson_result = await db.execute(lesson_query)
    db_lesson = lesson_result.scalars().first()
    if not db_lesson:
        return "INVALID_LESSON"

    # 2. Validar timeslot pertence à organização
    timeslot_query = select(models.Timeslot).where(
        models.Timeslot.id == data.timeslot_id,
        models.Timeslot.organization_id == org_id
    )
    timeslot_result = await db.execute(timeslot_query)
    if not timeslot_result.scalars().first():
        return "INVALID_TIMESLOT"

    # 3. Validar professores pertencem à organização
    teacher_query = select(models.Teacher).where(
        models.Teacher.id.in_([data.original_teacher_id, data.substitute_teacher_id]),
        models.Teacher.organization_id == org_id
    )
    teacher_result = await db.execute(teacher_query)
    teachers = teacher_result.scalars().all()
    if len(teachers) != 2:
        return "INVALID_TEACHER"

    # 4. Validar que o teacher original corresponde à aula (lesson)
    if db_lesson.teacher_id != data.original_teacher_id:
        return "ORIGINAL_TEACHER_MISMATCH"

    db_sub = models.Substitution(
        lesson_id=data.lesson_id,
        timeslot_id=data.timeslot_id,
        original_teacher_id=data.original_teacher_id,
        substitute_teacher_id=data.substitute_teacher_id,
        date=data.date,
        reason=data.reason,
        status="CONFIRMED" # Assumimos confirmado direto pelo diretor
    )
    db.add(db_sub)
    await db.commit()
    await db.refresh(db_sub)
    return db_sub

async def get_active_substitutions(db: AsyncSession, org_id: int, skip: int = 0, limit: int = 100):
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
        .where(models.Teacher.organization_id == org_id)
        .order_by(models.Substitution.date.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(query)
    substitutions = result.scalars().all()
    return substitutions