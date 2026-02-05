from typing import List, Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas, models
from app.api import deps
from app.services import course_service

router = APIRouter()

# --- 1. Listar Cursos (Resumo) com Paginação ---
@router.get("/", response_model=List[schemas.CourseRead])
async def read_courses(
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_user),
    skip: int = 0,
    limit: int = 100,
) -> Any:
    """
    Lista cursos da organização com paginação (offset/limit).
    - skip: Número de registos a saltar (default: 0)
    - limit: Número máximo de registos a retornar (default: 100, max: 1000)
    """
    return await course_service.get_courses_by_org(db, current_user.organization_id, skip, limit)

# --- 2. Criar Curso (Course Engine) ---
@router.post("/", response_model=schemas.CourseDetailRead)
async def create_course(
    item: schemas.CourseCreate, 
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_admin),
) -> Any:
    """
    Cria um novo curso e gera automaticamente a sua estrutura (turmas, matriz).
    """
    return await course_service.create_course(db, item, current_user.organization_id)

# --- 3. Obter Detalhes do Curso (Dashboard) ---
# NOVO ENDPOINT FUNDAMENTAL
@router.get("/{course_id}", response_model=schemas.CourseDetailRead)
async def read_course_detail(
    course_id: int,
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Retorna toda a árvore do curso: Disciplinas + Turmas Ativas.
    Usado na página de Detalhes do Curso.
    """
    course = await course_service.get_course_details(db, course_id, current_user.organization_id)
    if not course:
        raise HTTPException(status_code=404, detail="Curso não encontrado")
    return course

# --- 4. Atualizar Curso (PATCH - Atualização Parcial) ---
@router.patch("/{course_id}", response_model=schemas.CourseDetailRead)
async def update_course(
    course_id: int,
    item: schemas.CourseUpdate, 
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_admin),
) -> Any:
    """
    Atualiza parcialmente um curso (apenas os campos enviados).
    
    Regras:
    - Se envias 'subject_ids': substitui completamente (não é merge)
    - Se envias 'abbreviation': valida unicidade na organização
    - Se não envias um campo: mantém o valor existente
    
    4º Pilar - Stability: Rejeita se há classes (impede perda de dados)
    """
    result = await course_service.update_course(db, course_id, item, current_user.organization_id)
    
    if result == "NOT_FOUND":
        raise HTTPException(status_code=404, detail="Curso não encontrado")
    if result == "ABBREVIATION_EXISTS":
        raise HTTPException(status_code=400, detail="A sigla fornecida já existe nesta organização")
    
    return result

# --- 5. Apagar Curso ---
@router.delete("/{course_id}")
async def delete_course(
    course_id: int, 
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_admin),
) -> Any:
    status = await course_service.delete_course(db, course_id, current_user.organization_id)
    
    if status == "NOT_FOUND":
        raise HTTPException(status_code=404, detail="Curso não encontrado")
    
    if status == "DEPENDENCY_ERROR":
        # Melhoria de UX: Mensagem mais explicita
        raise HTTPException(
            status_code=400, 
            detail="Não é possível apagar: Existem turmas ou histórico associado a este curso."
        )
    
    return {"message": "Curso removido com sucesso"}