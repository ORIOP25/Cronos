# Ficheiro: backend/app/api/endpoints/analytics.py

from typing import Annotated
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.api import deps
from app import models

router = APIRouter()

@router.get("/availability-heatmap")
async def get_availability_heatmap(
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_user)],
):
    """
    Calcula a taxa de disponibilidade.
    Lógica V3 (Corrigida): 
    - Disponíveis = Total - Impossíveis.
    - 'Evitar' (0) conta como DISPONÍVEL para efeitos de cobertura.
    """
    organization_id = current_user.organization_id

    # 1. Total de Professores
    result_total = await db.execute(
        select(func.count(models.Teacher.id))
        .where(models.Teacher.organization_id == organization_id)
    )
    total_teachers = result_total.scalar() or 0

    if total_teachers == 0:
        return []

    # 2. Todos os Timeslots
    result_slots = await db.execute(
        select(models.Timeslot).where(models.Timeslot.organization_id == organization_id)
    )
    timeslots = result_slots.scalars().all()

    # 3. Contar Apenas os IMPOSSÍVEIS (Score == -1)
    # Agora o 'Evitar' (0) não entra aqui, logo é contado como 'Disponível' em baixo.
    stmt = (
        select(
            models.Availability.timeslot_id, 
            func.count(models.Availability.teacher_id)
        )
        .join(models.Teacher)
        .where(models.Teacher.organization_id == organization_id)
        .where(models.Availability.score == -1) # <--- MUDANÇA AQUI (Era <= 0)
        .group_by(models.Availability.timeslot_id)
    )
    
    result_impossible = await db.execute(stmt)
    impossible_map = {row[0]: row[1] for row in result_impossible.all()}

    # 4. Montar Resposta
    heatmap_data = []
    
    for slot in timeslots:
        impossible_count = impossible_map.get(slot.id, 0)
        
        # Disponíveis = Todos - Os que disseram "Impossível"
        # Assim, o "Evitar" está incluído nos disponíveis.
        available_count = max(0, total_teachers - impossible_count)
        
        ratio = available_count / total_teachers if total_teachers > 0 else 0
        
        heatmap_data.append({
            "timeslot_id": slot.id,
            "day_of_week": slot.day_of_week,
            "start_time": str(slot.start_time),
            "total_teachers": total_teachers,
            "available_count": available_count,
            "availability_ratio": ratio
        })

    return heatmap_data