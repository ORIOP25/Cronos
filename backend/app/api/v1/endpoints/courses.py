from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.api import deps
from app.core.exceptions import AppError
from app.services import class_service, course_service

COURSE_NOT_FOUND_MSG = "Curso nÃ£o encontrado"

router = APIRouter()


# --- 1. Listar Cursos (com Disciplinas e Turmas) ---
@router.get("/", response_model=list[schemas.CourseDetailRead])
async def read_courses(
    db: Annotated[AsyncSession, Depends(deps.get_db, scope="function")],
    current_user: deps.ActiveActor,
    skip: int = 0,
    limit: int = 100,
) -> Any:
    """
    Lista cursos da organizaÃ§Ã£o com paginaÃ§Ã£o (offset/limit).
    - skip: NÃºmero de registos a saltar (default: 0)
    - limit: NÃºmero mÃ¡ximo de registos a retornar (default: 100, max: 1000)
    """
    return await course_service.get_courses_by_org(db, current_user.organization_id, skip, limit)


# --- 2. Criar Curso (Course Engine) ---
@router.post(
    "/",
    response_model=schemas.CourseDetailRead,
    responses={400: {"description": "Sigla duplicada ou disciplinas invÃ¡lidas"}},
)
async def create_course(
    item: schemas.CourseCreate,
    db: Annotated[AsyncSession, Depends(deps.get_db, scope="function")],
    current_user: deps.AdminActor,
) -> Any:
    """
    Cria um novo curso e gera automaticamente a sua estrutura (turmas, matriz).
    """
    return await course_service.create_course(
        db,
        item,
        current_user.organization_id,
        changed_by_membership_id=current_user.membership_id,
    )


# --- 3. Obter Detalhes do Curso (Dashboard) ---
# NOVO ENDPOINT FUNDAMENTAL
@router.get(
    "/{course_id}",
    response_model=schemas.CourseDetailRead,
    responses={404: {"description": COURSE_NOT_FOUND_MSG}},
)
async def read_course_detail(
    course_id: int,
    db: Annotated[AsyncSession, Depends(deps.get_db, scope="function")],
    current_user: deps.ActiveActor,
) -> Any:
    """
    Retorna toda a Ã¡rvore do curso: Disciplinas + Turmas Ativas.
    Usado na pÃ¡gina de Detalhes do Curso.
    """
    course = await course_service.get_course_details(db, course_id, current_user.organization_id)
    if not course:
        raise AppError(kind="not_found", code="resource_not_found", detail=COURSE_NOT_FOUND_MSG)
    return course


@router.get(
    "/{course_id}/classes",
    response_model=list[schemas.ClassRead],
    responses={404: {"description": COURSE_NOT_FOUND_MSG}},
)
async def read_course_classes(
    course_id: int,
    db: Annotated[AsyncSession, Depends(deps.get_db, scope="function")],
    current_user: deps.ActiveActor,
) -> Any:
    course = await course_service.get_course_details(db, course_id, current_user.organization_id)
    if not course:
        raise AppError(kind="not_found", code="resource_not_found", detail=COURSE_NOT_FOUND_MSG)
    return await class_service.get_classes_by_course(db, course_id, current_user.organization_id)


@router.post(
    "/{course_id}/classes",
    response_model=schemas.ClassRead,
    responses={404: {"description": COURSE_NOT_FOUND_MSG}},
)
async def create_course_class(
    course_id: int,
    item: schemas.ClassCreateInCourse,
    db: Annotated[AsyncSession, Depends(deps.get_db, scope="function")],
    current_user: deps.AdminActor,
) -> Any:
    return await class_service.create_class_in_course(
        db,
        course_id,
        item,
        current_user.organization_id,
        changed_by_membership_id=current_user.membership_id,
    )


@router.patch(
    "/{course_id}/classes/{class_id}",
    response_model=schemas.ClassRead,
    responses={
        404: {"description": "Turma nÃ£o encontrada neste curso"},
        400: {"description": "Intervalo de anos invÃ¡lido"},
    },
)
async def update_course_class(
    course_id: int,
    class_id: int,
    item: schemas.ClassUpdateInCourse,
    db: Annotated[AsyncSession, Depends(deps.get_db, scope="function")],
    current_user: deps.AdminActor,
) -> Any:
    return await class_service.update_class_in_course(
        db,
        course_id,
        class_id,
        item,
        current_user.organization_id,
        changed_by_membership_id=current_user.membership_id,
    )


@router.delete(
    "/{course_id}/classes/{class_id}",
    responses={404: {"description": "Turma nÃ£o encontrada neste curso"}},
)
async def delete_course_class(
    course_id: int,
    class_id: int,
    db: Annotated[AsyncSession, Depends(deps.get_db, scope="function")],
    current_user: deps.AdminActor,
) -> Any:
    await class_service.delete_class_in_course(
        db,
        course_id,
        class_id,
        current_user.organization_id,
        changed_by_membership_id=current_user.membership_id,
    )
    return {"message": "Turma removida com sucesso"}


# --- 4. Atualizar Curso (PATCH - AtualizaÃ§Ã£o Parcial) ---
@router.patch(
    "/{course_id}",
    response_model=schemas.CourseDetailRead,
    responses={
        404: {"description": COURSE_NOT_FOUND_MSG},
        400: {"description": "Sigla jÃ¡ existente"},
    },
)
async def update_course(
    course_id: int,
    item: schemas.CourseUpdate,
    db: Annotated[AsyncSession, Depends(deps.get_db, scope="function")],
    current_user: deps.AdminActor,
) -> Any:
    """
    Atualiza parcialmente um curso (apenas os campos enviados).

    Regras:
    - Se envias 'subject_ids': substitui completamente (nÃ£o Ã© merge)
    - Se envias 'abbreviation': valida unicidade na organizaÃ§Ã£o
    - Se nÃ£o envias um campo: mantÃ©m o valor existente

    4Âº Pilar - Stability: Rejeita se hÃ¡ classes (impede perda de dados)
    """
    return await course_service.update_course(
        db,
        course_id,
        item,
        current_user.organization_id,
        changed_by_membership_id=current_user.membership_id,
    )


# --- 5. Apagar Curso ---
@router.delete(
    "/{course_id}",
    responses={
        404: {"description": COURSE_NOT_FOUND_MSG},
        400: {"description": "DependÃªncias existentes"},
    },
)
async def delete_course(
    course_id: int,
    db: Annotated[AsyncSession, Depends(deps.get_db, scope="function")],
    current_user: deps.AdminActor,
) -> Any:
    await course_service.delete_course(
        db,
        course_id,
        current_user.organization_id,
        changed_by_membership_id=current_user.membership_id,
    )

    return {"message": "Curso removido com sucesso"}
