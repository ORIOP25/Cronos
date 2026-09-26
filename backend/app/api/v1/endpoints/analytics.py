# Ficheiro: backend/app/api/endpoints/analytics.py


from fastapi import APIRouter
from sqlalchemy import func, select

from app import models
from app.api import deps
from app.services import grid_version_service

router = APIRouter()


@router.get("/availability-heatmap")
async def get_availability_heatmap(
    db: deps.DbSession,
    current_user: deps.ActiveActor,
):
    """
    Calcula a taxa de disponibilidade.
    LÃ³gica V3 (Corrigida):
    - DisponÃ­veis = Total - ImpossÃ­veis.
    - 'Evitar' (0) conta como DISPONÃVEL para efeitos de cobertura.
    """
    organization_id = current_user.organization_id

    # 1. Total de Professores
    result_total = await db.execute(
        select(func.count(models.Teacher.id)).where(
            models.Teacher.organization_id == organization_id
        )
    )
    total_teachers = result_total.scalar() or 0

    if total_teachers == 0:
        return []

    # 2. Blocos da versão visível da grelha
    resolved = await grid_version_service.resolve_grid(
        db,
        organization_id,
        await grid_version_service.school_today(db, organization_id),
    )
    timeslots = sorted(resolved.blocks, key=lambda slot: (slot.day_of_week, slot.start_time))

    # 3. Contar Apenas os IMPOSSÃVEIS (Score == -1)
    # Agora o 'Evitar' (0) nÃ£o entra aqui, logo Ã© contado como 'DisponÃ­vel' em baixo.
    stmt = (
        select(models.Availability.timeslot_id, func.count(models.Availability.teacher_id))
        .join(models.Teacher)
        .where(models.Teacher.organization_id == organization_id)
        .where(models.Availability.score == -1)  # <--- MUDANÃ‡A AQUI (Era <= 0)
        .group_by(models.Availability.timeslot_id)
    )

    result_impossible = await db.execute(stmt)
    impossible_map = {row[0]: row[1] for row in result_impossible.all()}

    # 4. Montar Resposta
    heatmap_data = []

    for slot in timeslots:
        impossible_count = impossible_map.get(slot.id, 0)

        # DisponÃ­veis = Todos - Os que disseram "ImpossÃ­vel"
        # Assim, o "Evitar" estÃ¡ incluÃ­do nos disponÃ­veis.
        available_count = max(0, total_teachers - impossible_count)

        ratio = available_count / total_teachers if total_teachers > 0 else 0

        heatmap_data.append(
            {
                "timeslot_id": slot.id,
                "day_of_week": slot.day_of_week,
                "start_time": str(slot.start_time),
                "total_teachers": total_teachers,
                "available_count": available_count,
                "availability_ratio": ratio,
            }
        )

    return heatmap_data
