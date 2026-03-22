from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from app import models, schemas
from datetime import datetime, date, timedelta, time


async def _get_org_teacher_ids(db: AsyncSession, org_id: int) -> list[int]:
    result = await db.execute(
        select(models.Teacher.id).where(models.Teacher.organization_id == org_id)
    )
    return list(result.scalars().all())


async def _get_availability_preferences_by_time(
    db: AsyncSession,
    org_id: int,
) -> dict[tuple[int, int, time, time], int]:
    """Snapshot preferences by (teacher, day, start, end) before timeslot reset."""
    result = await db.execute(
        select(
            models.Availability.teacher_id,
            models.Timeslot.day_of_week,
            models.Timeslot.start_time,
            models.Timeslot.end_time,
            models.Availability.score,
        )
        .join(models.Timeslot, models.Timeslot.id == models.Availability.timeslot_id)
        .where(models.Timeslot.organization_id == org_id)
    )
    return {
        (teacher_id, day_of_week, start_time, end_time): score
        for teacher_id, day_of_week, start_time, end_time, score in result.all()
    }


def _restore_availabilities_for_new_grid(
    db: AsyncSession,
    teacher_ids: list[int],
    timeslots: list[models.Timeslot],
    previous_preferences: dict[tuple[int, int, time, time], int],
) -> None:
    """Recreate availability matrix for all teachers in the new grid.

    If a new slot matches a previous slot by day/start/end, reuse that score.
    Otherwise default to NEUTRAL so schedule generation remains feasible.
    """
    neutral_score = models.PreferenceLevel.NEUTRAL.value
    for teacher_id in teacher_ids:
        for slot in timeslots:
            score = previous_preferences.get(
                (teacher_id, slot.day_of_week, slot.start_time, slot.end_time),
                neutral_score,
            )
            db.add(
                models.Availability(
                    teacher_id=teacher_id,
                    timeslot_id=slot.id,
                    score=score,
                )
            )

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
    Remove um bloco horário individual.
    Lógica 'Soft': Limpa dependências fracas (Availability) mas bloqueia se houver dados críticos.
    """
    result = await db.execute(select(models.Timeslot).where(models.Timeslot.id == timeslot_id, models.Timeslot.organization_id == org_id))
    item = result.scalars().first()
    
    if not item:
        return "NOT_FOUND"

    # Verificações de Integridade (Firewall para delete individual)
    
    # 1. Horários Gerados (ScheduleOutput)
    query_sched = select(models.ScheduleOutput).where(models.ScheduleOutput.timeslot_id == timeslot_id)
    if (await db.execute(query_sched)).first():
        return "DEPENDENCY_ERROR_SCHEDULE"

    # 2. Substituições (Substitutions) - NOVO
    query_subs = select(models.Substitution).where(models.Substitution.timeslot_id == timeslot_id)
    if (await db.execute(query_subs)).first():
        return "DEPENDENCY_ERROR_SUBSTITUTION"

    # Limpeza de dependências fracas (Availability)
    await db.execute(delete(models.Availability).where(models.Availability.timeslot_id == timeslot_id))

    await db.delete(item)
    await db.commit()
    return "SUCCESS"

# --- GERAÇÃO EM MASSA (RESET ESTRUTURAL) ---

async def _purge_all_dependencies(db: AsyncSession, org_id: int):
    """
    FUNÇÃO CRÍTICA: Prepara a escola para uma redefinição de horários.
    Remove TODOS os dados que dependem da grelha de tempos.
    A ordem é vital para respeitar as Foreign Keys.
    """
    # Identificar timeslots desta org
    timeslot_ids_subquery = select(models.Timeslot.id).where(models.Timeslot.organization_id == org_id)

    # 1. Substituições (Dependem de Timeslot)
    # Se a grelha muda, as substituições passadas/futuras para tempos antigos perdem o sentido.
    await db.execute(
        delete(models.Substitution).where(
            models.Substitution.timeslot_id.in_(timeslot_ids_subquery)
        )
    )

    # 2. Horários Gerados (Dependem de Timeslot)
    await db.execute(
        delete(models.ScheduleOutput).where(
            models.ScheduleOutput.timeslot_id.in_(timeslot_ids_subquery)
        )
    )

    # 3. Disponibilidades (Dependem de Timeslot)
    await db.execute(
        delete(models.Availability).where(
            models.Availability.timeslot_id.in_(timeslot_ids_subquery)
        )
    )

    # 4. Timeslots (A grelha antiga)
    await db.execute(delete(models.Timeslot).where(models.Timeslot.organization_id == org_id))


async def create_bulk_timeslots(
    db: AsyncSession, 
    settings: schemas.TimeslotBulkCreate, 
    org_id: int
):
    """
    Executa o Hard Reset da grelha escolar.
    """
    teacher_ids = await _get_org_teacher_ids(db, org_id)
    previous_preferences = await _get_availability_preferences_by_time(db, org_id)

    # 1. Limpeza Profunda
    await _purge_all_dependencies(db, org_id)
    
    # 2. Reconstrução
    created_count = 0
    dummy_date = date.today()
    current_start_dt = datetime.combine(dummy_date, settings.start_time)
    end_limit_dt = datetime.combine(dummy_date, settings.end_time)

    new_timeslots: list[models.Timeslot] = []

    while True:
        current_end_dt = current_start_dt + timedelta(minutes=settings.slot_duration_minutes)
        
        if current_end_dt > end_limit_dt:
            break
            
        for day in settings.days_of_week:
            new_slot = models.Timeslot(
                day_of_week=day,
                start_time=current_start_dt.time(),
                end_time=current_end_dt.time(),
                organization_id=org_id
            )
            db.add(new_slot)
            new_timeslots.append(new_slot)
            created_count += 1
        
        current_start_dt = current_end_dt + timedelta(minutes=settings.break_duration_minutes)

    await db.flush()

    _restore_availabilities_for_new_grid(
        db,
        teacher_ids,
        new_timeslots,
        previous_preferences,
    )

    await db.commit()
    return created_count