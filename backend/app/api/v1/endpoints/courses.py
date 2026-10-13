from typing import Any

from fastapi import APIRouter

from app import schemas
from app.api import deps
from app.core.exceptions import AppError
from app.services import class_service, course_service

COURSE_NOT_FOUND_MSG = "Curso não encontrado"

router = APIRouter()


# --- 1. Listar Cursos (com Disciplinas e Turmas) ---
@router.get("/", response_model=list[schemas.CourseDetailRead])
async def read_courses(
    db: deps.DbSession,
    current_user: deps.ActiveActor,
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
@router.post(
    "/",
    response_model=schemas.CourseDetailRead,
    responses={400: {"description": "Sigla duplicada ou disciplinas inválidas"}},
)
async def create_course(
    item: schemas.CourseCreate,
    db: deps.DbSession,
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
    db: deps.DbSession,
    current_user: deps.ActiveActor,
) -> Any:
    """
    Retorna toda a árvore do curso: Disciplinas + Turmas Ativas.
    Usado na página de Detalhes do Curso.
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
    db: deps.DbSession,
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
    db: deps.DbSession,
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
        404: {"description": "Turma não encontrada neste curso"},
        400: {"description": "Intervalo de anos inválido"},
    },
)
async def update_course_class(
    course_id: int,
    class_id: int,
    item: schemas.ClassUpdateInCourse,
    db: deps.DbSession,
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
    responses={404: {"description": "Turma não encontrada neste curso"}},
)
async def delete_course_class(
    course_id: int,
    class_id: int,
    db: deps.DbSession,
    current_user: deps.AdminActor,
) -> Any:
    remove_effect = await class_service.delete_class_in_course(
        db,
        course_id,
        class_id,
        current_user.organization_id,
        changed_by_membership_id=current_user.membership_id,
    )
    return {"message": "Turma removida com sucesso", "remove_effect": remove_effect}


# --- 4. Atualizar Curso (PATCH - Atualização Parcial) ---
@router.patch(
    "/{course_id}",
    response_model=schemas.CourseDetailRead,
    responses={
        404: {"description": COURSE_NOT_FOUND_MSG},
        400: {"description": "Sigla já existente"},
    },
)
async def update_course(
    course_id: int,
    item: schemas.CourseUpdate,
    db: deps.DbSession,
    current_user: deps.AdminActor,
) -> Any:
    """
    Atualiza parcialmente um curso (apenas os campos enviados).

    Regras:
    - Se envias 'subject_ids': substitui completamente (não é merge)
    - Se envias 'abbreviation': valida unicidade na organização
    - Se não envias um campo: mantém o valor existente

    4º Pilar - Stability: Rejeita se há classes (impede perda de dados)
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
        400: {"description": "Dependências existentes"},
    },
)
async def delete_course(
    course_id: int,
    db: deps.DbSession,
    current_user: deps.AdminActor,
) -> Any:
    remove_effect = await course_service.delete_course(
        db,
        course_id,
        current_user.organization_id,
        changed_by_membership_id=current_user.membership_id,
    )

    return {"message": "Curso removido com sucesso", "remove_effect": remove_effect}
