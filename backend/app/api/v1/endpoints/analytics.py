from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Any
from app.api import deps
from app import models

router = APIRouter()

@router.get("/availability-heatmap")
async def get_availability_heatmap(
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_user)
):
    # Retornamos uma lista vazia [] para o .reduce() do frontend não rebentar.
    # Quando tivermos lógica de analytics, implementamos aqui.
    return []