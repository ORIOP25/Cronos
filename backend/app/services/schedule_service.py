from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from sqlalchemy.future import select
from sqlalchemy import delete, desc
from app import models, schemas

# ==========================================
#  ASYNC (API / FRONTEND)
# ==========================================

# --- TIMESLOTS ---
async def get_timeslots_by_org(db: AsyncSession, org_id: int):
    result = await db.execute(select(models.Timeslot).where(models.Timeslot.organization_id == org_id))
    return result.scalars().all()

async def create_timeslot(db: AsyncSession, item: schemas.TimeslotCreate, org_id: int):
    # O item.model_dump() já vai ter 'start_time' como objeto time.
    db_item = models.Timeslot(**item.model_dump(), organization_id=org_id)
    db.add(db_item)
    await db.commit()
    await db.refresh(db_item)
    return db_item

# --- LESSONS ---
async def get_lessons_by_org(db: AsyncSession, org_id: int):
    result = await db.execute(select(models.Lesson).where(models.Lesson.organization_id == org_id))
    return result.scalars().all()

async def create_lesson(db: AsyncSession, item: schemas.LessonCreate, org_id: int):
    db_item = models.Lesson(**item.model_dump(), organization_id=org_id)
    db.add(db_item)
    await db.commit()
    await db.refresh(db_item)
    return db_item

# --- CONSTRAINTS ---
async def create_constraint(db: AsyncSession, item: schemas.ConstraintCreate, org_id: int):
    db_item = models.Constraint(**item.dict(), organization_id=org_id)
    db.add(db_item)
    await db.commit()
    await db.refresh(db_item)
    return db_item

async def get_constraints_by_org(db: AsyncSession, org_id: int):
    """Lista todas as restrições."""
    result = await db.execute(select(models.Constraint).where(models.Constraint.organization_id == org_id))
    return result.scalars().all()

async def delete_constraint(db: AsyncSession, constraint_id: int, org_id: int):
    """Apaga uma regra de horário."""
    query = select(models.Constraint).where(
        models.Constraint.id == constraint_id,
        models.Constraint.organization_id == org_id
    )
    result = await db.execute(query)
    item = result.scalars().first()
    
    if item:
        await db.delete(item)
        await db.commit()
        return True
    return False

# --- OUTPUT (RESULTADOS) ---
async def get_latest_schedule_by_org(db: AsyncSession, org_id: int):
    """Vai buscar o horário gerado mais recente."""
    
    # 1. Descobrir qual é o último generation_id
    gen_query = select(models.ScheduleOutput.generation_id)\
        .where(models.ScheduleOutput.organization_id == org_id)\
        .order_by(desc(models.ScheduleOutput.id))\
        .limit(1)
    
    gen_res = await db.execute(gen_query)
    latest_gen_id = gen_res.scalars().first()
    
    if not latest_gen_id:
        return []
        
    # 2. Buscar tudo desse ID
    lines_query = select(models.ScheduleOutput).where(
        models.ScheduleOutput.organization_id == org_id,
        models.ScheduleOutput.generation_id == latest_gen_id
    )
    lines_res = await db.execute(lines_query)
    return lines_res.scalars().all()

# --- LIMPEZA GERAL (Reset) ---
async def delete_all_schedule_data(db: AsyncSession, org_id: int):
    """Apaga Outputs, Constraints, Aulas e Slots de uma organização."""
    # Ordem importa por causa das Foreign Keys
    await db.execute(delete(models.ScheduleOutput).where(models.ScheduleOutput.organization_id == org_id))
    await db.execute(delete(models.Constraint).where(models.Constraint.organization_id == org_id))
    await db.execute(delete(models.Lesson).where(models.Lesson.organization_id == org_id))
    await db.execute(delete(models.Timeslot).where(models.Timeslot.organization_id == org_id))
    await db.commit()

# ==========================================
#  SYNC (SOLVER / CELERY)
# ==========================================
# Estas funções são usadas pelo Celery Worker que não suporta bem async/await.

def get_lessons_by_org_sync(db: Session, org_id: int):
    return db.query(models.Lesson).filter(models.Lesson.organization_id == org_id).all()

def get_timeslots_by_org_sync(db: Session, org_id: int):
    return db.query(models.Timeslot).filter(models.Timeslot.organization_id == org_id).all()

def get_constraints_by_org_sync(db: Session, org_id: int):
    return db.query(models.Constraint).filter(models.Constraint.organization_id == org_id).all()

def get_availabilities_by_org_sync(db: Session, org_id: int):
    """
    Retorna todas as disponibilidades dos professores desta organização.
    Faz um JOIN com a tabela Teacher para filtrar pelo org_id.
    """
    return db.query(models.Availability)\
             .join(models.Teacher)\
             .filter(models.Teacher.organization_id == org_id)\
             .all()

def create_schedule_output_sync(db: Session, lesson_id, timeslot_id, room_id, org_id, gen_id):
    db_out = models.ScheduleOutput(
        lesson_id=lesson_id,
        timeslot_id=timeslot_id,
        room_id=room_id,
        organization_id=org_id,
        generation_id=gen_id
    )
    db.add(db_out)
    # Nota: O commit é feito pelo caller no final para performance

def clear_schedule_sync(db: Session, org_id: int):
    """
    Apaga todos os registos de horários gerados anteriormente para esta organização.
    (Usado pelo Celery antes de gravar um novo horário)
    """
    db.query(models.ScheduleOutput)\
      .filter(models.ScheduleOutput.organization_id == org_id)\
      .delete()
    # Não fazemos commit aqui porque o solver_tasks.py faz commit no final de tudo.