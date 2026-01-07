from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from app import models, schemas
# Importar modelos dependentes
from app.models import Availability, ScheduleOutput

async def get_timeslots_by_org(db: AsyncSession, org_id: int):
    # Ordenar por Dia da Semana e depois Hora de Início
    stmt = select(models.Timeslot).where(models.Timeslot.organization_id == org_id)\
        .order_by(models.Timeslot.day_of_week, models.Timeslot.start_time)
    result = await db.execute(stmt)
    return result.scalars().all()

async def create_timeslot(db: AsyncSession, item: schemas.TimeslotCreate, org_id: int):
    db_item = models.Timeslot(**item.model_dump(), organization_id=org_id)
    db.add(db_item)
    await db.commit()
    await db.refresh(db_item)
    return db_item

async def update_timeslot(
    db: AsyncSession, 
    timeslot_id: int, 
    item: schemas.TimeslotUpdate, 
    org_id: int
):
    query = select(models.Timeslot).where(
        models.Timeslot.id == timeslot_id,
        models.Timeslot.organization_id == org_id
    )
    result = await db.execute(query)
    db_item = result.scalars().first()
    
    if not db_item:
        return None

    update_data = item.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_item, field, value)

    db.add(db_item)
    await db.commit()
    await db.refresh(db_item)
    return db_item

async def delete_timeslot(db: AsyncSession, timeslot_id: int, org_id: int):
    """
    Remove um bloco horário. 
    - Aulas (ScheduleOutput): BLOQUEIA (Segurança)
    - Disponibilidades (Availability): LIMPA (Cascata)
    """
    # 1. Buscar item para garantir que existe e pertence à org
    result = await db.execute(select(models.Timeslot).where(models.Timeslot.id == timeslot_id, models.Timeslot.organization_id == org_id))
    item = result.scalars().first()
    
    if not item:
        return "NOT_FOUND"

    # 2. VERIFICAÇÃO DE INTEGRIDADE FORTE (Horários Gerados)
    # Se já geraste um horário com este bloco, não podes apagar senão o horário fica com buracos.
    query_sched = select(models.ScheduleOutput).where(models.ScheduleOutput.timeslot_id == timeslot_id)
    result_sched = await db.execute(query_sched)
    if result_sched.first():
        return "DEPENDENCY_ERROR_SCHEDULE"

    # 3. LIMPEZA DE DEPENDÊNCIAS FRACAS (Disponibilidades)
    # Se o bloco vai deixar de existir, as preferências dos professores para ele são lixo.
    # Apagamos silenciosamente para desbloquear o utilizador.
    await db.execute(delete(models.Availability).where(models.Availability.timeslot_id == timeslot_id))

    # 4. Apagar o Bloco
    await db.delete(item)
    await db.commit()
    return "SUCCESS"