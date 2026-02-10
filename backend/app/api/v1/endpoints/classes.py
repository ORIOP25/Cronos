from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Any
from app import schemas, models
from app.api import deps
from app.services import class_service

router = APIRouter()

@router.get("/", response_model=List[schemas.ClassRead])
async def read_classes(
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_user)
):
    return await class_service.get_classes_by_org(db, current_user.organization_id)

@router.get("/{class_id}", response_model=schemas.ClassFullDetailRead)
async def read_class(
    class_id: int,
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Retorna dashboard completo da turma: Curso + Disciplinas + Módulos + Progresso.
    
    Usado na página ClassDetails.jsx para exibir:
    - Header da turma (nome, capacidade, ano)
    - Curso associado
    - Lista de disciplinas com módulos e barras de progresso
    
    4 Pilares:
    🔐 Security: Valida org_id — turma só é retornada se pertence à organização
    ⚙️ Stability: 2 queries com selectinload (previne N+1 em async)
    ⚡ Optimization: Progresso calculado server-side com lookup O(1)
    📈 Scalability: Resposta auto-suficiente para o dashboard
    """
    result = await class_service.get_class_full_details(db, class_id, current_user.organization_id)
    
    if not result:
        raise HTTPException(status_code=404, detail="Turma não encontrada")
    
    return result

@router.post("/", response_model=schemas.ClassRead)
async def create_class(
    item: schemas.ClassCreate, 
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_admin)
):
    return await class_service.create_class(db, item, current_user.organization_id)

@router.patch("/{class_id}", response_model=schemas.ClassRead)
async def update_class(
    class_id: int,
    item: schemas.ClassUpdate,
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_admin)
):
    updated = await class_service.update_class(db, class_id, item, current_user.organization_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Turma não encontrada")
    return updated

@router.delete("/{class_id}")
async def delete_class(
    class_id: int, 
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_admin)
):
    status = await class_service.delete_class(db, class_id, current_user.organization_id)
    
    if status == "NOT_FOUND":
        raise HTTPException(status_code=404, detail="Turma não encontrada")
    
    if status == "DEPENDENCY_ERROR":
        raise HTTPException(
            status_code=400, 
            detail="Não é possível apagar esta turma pois existem aulas associadas a ela."
        )
    
    return {"message": "Turma removida com sucesso"}

@router.get("/{class_id}/curriculum", response_model=List[schemas.SubjectRead])
async def get_class_curriculum(
    class_id: int,
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_user)
):
    """
    Retorna o currículo (disciplinas) da turma.
    
    A turma está associada a um curso, e o curso define quais disciplinas ela precisa ter.
    Este endpoint facilita a "Matriz de Distribuição de Serviço" (Atribuição de Professores).
    
    Exemplo de uso:
    - GET /api/v1/classes/5/curriculum → Lista as disciplinas do curso do 10º TGEI
    """
    curriculum = await class_service.get_class_curriculum(
        db, 
        class_id, 
        current_user.organization_id
    )
    return curriculum


# ==========================================
#  PROGRESSO DA TURMA (Módulos)
# ==========================================

@router.patch("/{class_id}/progress", response_model=schemas.ClassFullDetailRead)
async def update_class_progress(
    class_id: int,
    payload: schemas.ClassProgressBulkUpdate,
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_admin),
) -> Any:
    """
    Atualiza o progresso de módulos para uma turma (upsert).
    Auto-calcula is_completed quando hours_completed >= hours_total.
    
    Body: { "progress": [{ "module_id": 1, "hours_completed": 25 }, ...] }
    
    Retorna: ClassFullDetailRead atualizado (para refresh imediato na UI)
    
    4 Pilares:
    🔐 Security: Admin only + valida módulo pertence ao curso da turma
    ⚙️ Stability: Transação atómica + clamp de horas (nunca > total)
    ⚡ Optimization: Upsert batch via ON CONFLICT
    📈 Scalability: Suporta N módulos numa única chamada
    """
    status = await class_service.update_class_progress(
        db, class_id, payload.progress, current_user.organization_id
    )
    
    if status == "NOT_FOUND":
        raise HTTPException(status_code=404, detail="Turma não encontrada")
    
    if status == "NO_COURSE":
        raise HTTPException(status_code=400, detail="Turma sem curso associado — não é possível registar progresso")
    
    if isinstance(status, str) and status.startswith("INVALID_MODULE:"):
        module_id = status.split(":")[1]
        raise HTTPException(
            status_code=400, 
            detail=f"Módulo {module_id} não pertence ao curso desta turma"
        )
    
    # Retornar dados atualizados para refresh na UI
    return await class_service.get_class_full_details(db, class_id, current_user.organization_id)