from typing import Annotated, List, Any, Annotated
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas, models
from app.api import deps
from app.services import course_service, class_service

COURSE_NOT_FOUND_MSG = "Curso não encontrado"

router = APIRouter()

# --- 1. Listar Cursos (com Disciplinas e Turmas) ---
@router.get("/", response_model=List[schemas.CourseDetailRead])
async def read_courses(
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_user)],
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
@router.post("/", response_model=schemas.CourseDetailRead, responses={400: {"description": "Sigla duplicada ou disciplinas inválidas"}})
async def create_course(
    item: schemas.CourseCreate, 
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)],
) -> Any:
    """
    Cria um novo curso e gera automaticamente a sua estrutura (turmas, matriz).
    """
    result = await course_service.create_course(
        db, item, current_user.organization_id,
        changed_by_user_id=current_user.id,
    )
    
    if result == "ABBREVIATION_EXISTS":
        raise HTTPException(status_code=400, detail=f"A sigla '{item.abbreviation}' já existe nesta organização.")
    if result == "INVALID_SUBJECTS":
        raise HTTPException(status_code=400, detail="Tentativa de associar disciplinas inválidas ou de outra escola.")
    
    return result

# --- 3. Obter Detalhes do Curso (Dashboard) ---
# NOVO ENDPOINT FUNDAMENTAL
@router.get("/{course_id}", response_model=schemas.CourseDetailRead, responses={404: {"description": COURSE_NOT_FOUND_MSG}})
async def read_course_detail(
    course_id: int,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_user)],
) -> Any:
    """
    Retorna toda a árvore do curso: Disciplinas + Turmas Ativas.
    Usado na página de Detalhes do Curso.
    """
    course = await course_service.get_course_details(db, course_id, current_user.organization_id)
    if not course:
        raise HTTPException(status_code=404, detail=COURSE_NOT_FOUND_MSG)
    return course


@router.get("/{course_id}/classes", response_model=List[schemas.ClassRead], responses={404: {"description": COURSE_NOT_FOUND_MSG}})
async def read_course_classes(
    course_id: int,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_user)],
) -> Any:
    course = await course_service.get_course_details(db, course_id, current_user.organization_id)
    if not course:
        raise HTTPException(status_code=404, detail=COURSE_NOT_FOUND_MSG)
    return await class_service.get_classes_by_course(db, course_id, current_user.organization_id)


@router.post("/{course_id}/classes", response_model=schemas.ClassRead, responses={404: {"description": COURSE_NOT_FOUND_MSG}})
async def create_course_class(
    course_id: int,
    item: schemas.ClassCreateInCourse,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)],
) -> Any:
    result = await class_service.create_class_in_course(
        db, course_id, item, current_user.organization_id,
        changed_by_user_id=current_user.id,
    )
    if result == "COURSE_NOT_FOUND":
        raise HTTPException(status_code=404, detail=COURSE_NOT_FOUND_MSG)
    return result


@router.patch("/{course_id}/classes/{class_id}", response_model=schemas.ClassRead, responses={404: {"description": "Turma não encontrada neste curso"}, 400: {"description": "Intervalo de anos inválido"}})
async def update_course_class(
    course_id: int,
    class_id: int,
    item: schemas.ClassUpdateInCourse,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)],
) -> Any:
    result = await class_service.update_class_in_course(
        db, course_id, class_id, item, current_user.organization_id,
        changed_by_user_id=current_user.id,
    )
    if result == "NOT_FOUND":
        raise HTTPException(status_code=404, detail="Turma não encontrada neste curso")
    if result == "INVALID_YEAR_RANGE":
        raise HTTPException(status_code=400, detail="Ano de fim deve ser maior que o ano de início")
    return result


@router.delete("/{course_id}/classes/{class_id}", responses={404: {"description": "Turma não encontrada neste curso"}})
async def delete_course_class(
    course_id: int,
    class_id: int,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)],
) -> Any:
    status = await class_service.delete_class_in_course(
        db, course_id, class_id, current_user.organization_id,
        changed_by_user_id=current_user.id,
    )
    if status == "NOT_FOUND":
        raise HTTPException(status_code=404, detail="Turma não encontrada neste curso")
    return {"message": "Turma removida com sucesso"}

# --- 4. Atualizar Curso (PATCH - Atualização Parcial) ---
@router.patch("/{course_id}", response_model=schemas.CourseDetailRead, responses={404: {"description": COURSE_NOT_FOUND_MSG}, 400: {"description": "Sigla já existente"}})
async def update_course(
    course_id: int,
    item: schemas.CourseUpdate, 
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)],
) -> Any:
    """
    Atualiza parcialmente um curso (apenas os campos enviados).
    
    Regras:
    - Se envias 'subject_ids': substitui completamente (não é merge)
    - Se envias 'abbreviation': valida unicidade na organização
    - Se não envias um campo: mantém o valor existente
    
    4º Pilar - Stability: Rejeita se há classes (impede perda de dados)
    """
    result = await course_service.update_course(
        db, course_id, item, current_user.organization_id,
        changed_by_user_id=current_user.id,
    )
    
    if result == "NOT_FOUND":
        raise HTTPException(status_code=404, detail=COURSE_NOT_FOUND_MSG)
    if result == "ABBREVIATION_EXISTS":
        raise HTTPException(status_code=400, detail="A sigla fornecida já existe nesta organização")
    
    return result

# --- 5. Apagar Curso ---
@router.delete("/{course_id}", responses={404: {"description": COURSE_NOT_FOUND_MSG}, 400: {"description": "Dependências existentes"}})
async def delete_course(
    course_id: int, 
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)],
) -> Any:
    status = await course_service.delete_course(
        db, course_id, current_user.organization_id,
        changed_by_user_id=current_user.id,
    )
    
    if status == "NOT_FOUND":
        raise HTTPException(status_code=404, detail=COURSE_NOT_FOUND_MSG)
    
    if status == "DEPENDENCY_ERROR":
        # Melhoria de UX: Mensagem mais explicita
        raise HTTPException(
            status_code=400, 
            detail="Não é possível apagar: Existem turmas ou histórico associado a este curso."
        )
    
    return {"message": "Curso removido com sucesso"}
