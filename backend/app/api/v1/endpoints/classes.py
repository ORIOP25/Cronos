from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.api import deps
from app.core.exceptions import AppError
from app.services import class_service

CLASS_NOT_FOUND_MSG = "Turma nÃ£o encontrada"

router = APIRouter()


@router.get("/", response_model=list[schemas.ClassRead])
async def read_classes(
    db: Annotated[AsyncSession, Depends(deps.get_db, scope="function")],
    current_user: deps.AdminActor,
):
    return await class_service.get_classes_by_org(db, current_user.organization_id)


@router.get(
    "/{class_id}",
    response_model=schemas.ClassFullDetailRead,
    responses={404: {"description": CLASS_NOT_FOUND_MSG}},
)
async def read_class(
    class_id: int,
    db: Annotated[AsyncSession, Depends(deps.get_db, scope="function")],
    current_user: deps.AdminActor,
) -> Any:
    """
    Retorna dashboard completo da turma: Curso + Disciplinas + MÃ³dulos + Progresso.

    Usado na pÃ¡gina ClassDetails.jsx para exibir:
    - Header da turma (nome, capacidade, ano)
    - Curso associado
    - Lista de disciplinas com mÃ³dulos e barras de progresso

    4 Pilares:
    ðŸ” Security: Valida org_id â€” turma sÃ³ Ã© retornada se pertence Ã  organizaÃ§Ã£o
    âš™ï¸ Stability: 2 queries com selectinload (previne N+1 em async)
    âš¡ Optimization: Progresso calculado server-side com lookup O(1)
    ðŸ“ˆ Scalability: Resposta auto-suficiente para o dashboard
    """
    result = await class_service.get_class_full_details(db, class_id, current_user.organization_id)

    if not result:
        raise AppError(kind="not_found", code="resource_not_found", detail=CLASS_NOT_FOUND_MSG)

    return result


@router.get("/{class_id}/curriculum", response_model=list[schemas.SubjectRead])
async def get_class_curriculum(
    class_id: int,
    db: Annotated[AsyncSession, Depends(deps.get_db, scope="function")],
    current_user: deps.AdminActor,
):
    """
    Retorna o currÃ­culo (disciplinas) da turma.

    A turma estÃ¡ associada a um curso, e o curso define quais disciplinas ela precisa ter.
    Este endpoint facilita a "Matriz de DistribuiÃ§Ã£o de ServiÃ§o" (AtribuiÃ§Ã£o de Professores).

    Exemplo de uso:
    - GET /api/v1/classes/5/curriculum â†’ Lista as disciplinas do curso do 10Âº TGEI
    """
    curriculum = await class_service.get_class_curriculum(
        db, class_id, current_user.organization_id
    )
    return curriculum


# ==========================================
#  PROGRESSO DA TURMA (MÃ³dulos)
# ==========================================


@router.patch(
    "/{class_id}/progress",
    response_model=schemas.ClassFullDetailRead,
    responses={404: {"description": CLASS_NOT_FOUND_MSG}, 400: {"description": "Bad Request"}},
)
async def update_class_progress(
    class_id: int,
    payload: schemas.ClassProgressBulkUpdate,
    db: Annotated[AsyncSession, Depends(deps.get_db, scope="function")],
    current_user: deps.AdminActor,
) -> Any:
    """
    Atualiza o progresso de mÃ³dulos para uma turma (upsert).
    Auto-calcula is_completed quando hours_completed >= hours_total.

    Body: { "progress": [{ "module_id": 1, "hours_completed": 25 }, ...] }

    Retorna: ClassFullDetailRead atualizado (para refresh imediato na UI)

    4 Pilares:
    ðŸ” Security: Admin only + valida mÃ³dulo pertence ao curso da turma
    âš™ï¸ Stability: TransaÃ§Ã£o atÃ³mica + clamp de horas (nunca > total)
    âš¡ Optimization: Upsert batch via ON CONFLICT
    ðŸ“ˆ Scalability: Suporta N mÃ³dulos numa Ãºnica chamada
    """
    await class_service.update_class_progress(
        db, class_id, payload.progress, current_user.organization_id
    )

    # Retornar dados atualizados para refresh na UI
    return await class_service.get_class_full_details(db, class_id, current_user.organization_id)


# ==========================================
#  DISCIPLINAS DA TURMA (Class-Subject Link)
#  GestÃ£o curso-cÃªntrica de professores
# ==========================================


@router.get(
    "/{class_id}/subjects",
    response_model=schemas.ClassSubjectsListRead,
    responses={404: {"description": CLASS_NOT_FOUND_MSG}},
)
async def get_class_subjects(
    class_id: int,
    db: Annotated[AsyncSession, Depends(deps.get_db, scope="function")],
    current_user: deps.ActiveActor,
):
    """
    Lista disciplinas associadas Ã  turma (para o grade_level atual).
    Inclui professor atribuÃ­do a cada disciplina.

    Usado na pÃ¡gina ClassSubjects.jsx para mostrar:
    - Quais disciplinas a turma tem
    - Quem Ã© o professor de cada disciplina
    """
    result = await class_service.get_class_subjects(db, class_id, current_user.organization_id)

    if not result:
        raise AppError(kind="not_found", code="resource_not_found", detail=CLASS_NOT_FOUND_MSG)

    return result


@router.post(
    "/{class_id}/subjects",
    response_model=schemas.ClassSubjectsListRead,
    responses={404: {"description": CLASS_NOT_FOUND_MSG}, 400: {"description": "Bad Request"}},
)
async def add_class_subject(
    class_id: int,
    payload: schemas.ClassSubjectCreate,
    db: Annotated[AsyncSession, Depends(deps.get_db, scope="function")],
    current_user: deps.AdminActor,
):
    """
    Adiciona uma disciplina Ã  turma (para o grade_level atual).

    ValidaÃ§Ãµes:
    - Turma existe e pertence Ã  organizaÃ§Ã£o
    - Disciplina existe e pertence Ã  organizaÃ§Ã£o
    - Disciplina nÃ£o estÃ¡ jÃ¡ associada Ã  turma
    """
    await class_service.add_class_subject(
        db,
        class_id,
        payload.subject_id,
        current_user.organization_id,
        changed_by_membership_id=current_user.membership_id,
    )

    # Retornar lista atualizada
    return await class_service.get_class_subjects(db, class_id, current_user.organization_id)


@router.patch(
    "/{class_id}/subjects/{subject_id}",
    response_model=schemas.ClassSubjectsListRead,
    responses={404: {"description": CLASS_NOT_FOUND_MSG}, 400: {"description": "Bad Request"}},
)
async def update_class_subject_teacher(
    class_id: int,
    subject_id: int,
    payload: schemas.ClassSubjectUpdate,
    db: Annotated[AsyncSession, Depends(deps.get_db, scope="function")],
    current_user: deps.AdminActor,
):
    """
    Atribui ou altera o professor de uma disciplina da turma.

    ValidaÃ§Ãµes:
    - AssociaÃ§Ã£o turma/disciplina existe
    - Se teacher_id nÃ£o Ã© null, professor tem competÃªncia na disciplina

    Enviar teacher_id=null para remover a atribuiÃ§Ã£o.
    """
    await class_service.update_class_subject_teacher(
        db,
        class_id,
        subject_id,
        payload,
        current_user.organization_id,
        changed_by_membership_id=current_user.membership_id,
    )

    # Retornar lista atualizada
    return await class_service.get_class_subjects(db, class_id, current_user.organization_id)


@router.delete(
    "/{class_id}/subjects/{subject_id}",
    response_model=schemas.ClassSubjectsListRead,
    responses={404: {"description": CLASS_NOT_FOUND_MSG}},
)
async def remove_class_subject(
    class_id: int,
    subject_id: int,
    db: Annotated[AsyncSession, Depends(deps.get_db, scope="function")],
    current_user: deps.AdminActor,
):
    """
    Remove uma disciplina da turma (para o grade_level atual).
    """
    await class_service.remove_class_subject(
        db,
        class_id,
        subject_id,
        current_user.organization_id,
        changed_by_membership_id=current_user.membership_id,
    )

    # Retornar lista atualizada
    return await class_service.get_class_subjects(db, class_id, current_user.organization_id)


@router.get("/{class_id}/available-subjects", response_model=list[schemas.SubjectRead])
async def get_available_subjects(
    class_id: int,
    db: Annotated[AsyncSession, Depends(deps.get_db, scope="function")],
    current_user: deps.ActiveActor,
):
    """
    Lista disciplinas disponÃ­veis para adicionar Ã  turma.
    (Disciplinas da organizaÃ§Ã£o que ainda nÃ£o estÃ£o associadas Ã  turma)
    """
    return await class_service.get_available_subjects_for_class(
        db, class_id, current_user.organization_id
    )


@router.get(
    "/subjects/{subject_id}/eligible-teachers", response_model=list[schemas.EligibleTeacherRead]
)
async def get_eligible_teachers(
    subject_id: int,
    db: Annotated[AsyncSession, Depends(deps.get_db, scope="function")],
    current_user: deps.ActiveActor,
):
    """
    Lista professores elegÃ­veis para lecionar uma disciplina.
    (Professores que tÃªm competÃªncia na disciplina)

    TambÃ©m indica quantas turmas cada professor jÃ¡ tem para esta disciplina.
    """
    return await class_service.get_eligible_teachers_for_subject(
        db, subject_id, current_user.organization_id
    )
