from typing import Any

from fastapi import APIRouter

from app import schemas
from app.api import deps
from app.core.exceptions import AppError
from app.services import class_service

CLASS_NOT_FOUND_MSG = "Turma não encontrada"

router = APIRouter()


@router.get("/", response_model=list[schemas.ClassRead])
async def read_classes(
    db: deps.DbSession,
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
    db: deps.DbSession,
    current_user: deps.AdminActor,
) -> Any:
    """
    Retorna dashboard completo da turma: Curso + Disciplinas + Módulos + Progresso.

    Usado na página ClassDetails.jsx para exibir:
    - Header da turma (nome, capacidade, ano)
    - Curso associado
    - Lista de disciplinas com módulos e barras de progresso

    4 Pilares:
    🔐 Security: Valida org_id — turma só é retornada se pertence à organização
    ⚙ï¸ Stability: 2 queries com selectinload (previne N+1 em async)
    ⚡ Optimization: Progresso calculado server-side com lookup O(1)
    📈 Scalability: Resposta auto-suficiente para o dashboard
    """
    result = await class_service.get_class_full_details(db, class_id, current_user.organization_id)

    if not result:
        raise AppError(kind="not_found", code="resource_not_found", detail=CLASS_NOT_FOUND_MSG)

    return result


# ==========================================
#  PROGRESSO DA TURMA (Módulos)
# ==========================================


@router.patch(
    "/{class_id}/progress",
    response_model=schemas.ClassFullDetailRead,
    responses={404: {"description": CLASS_NOT_FOUND_MSG}, 400: {"description": "Bad Request"}},
)
async def update_class_progress(
    class_id: int,
    payload: schemas.ClassProgressBulkUpdate,
    db: deps.DbSession,
    current_user: deps.AdminActor,
) -> Any:
    """
    Atualiza o progresso de módulos para uma turma (upsert).
    Auto-calcula is_completed quando hours_completed >= hours_total.

    Body: { "progress": [{ "module_id": 1, "hours_completed": 25 }, ...] }

    Retorna: ClassFullDetailRead atualizado (para refresh imediato na UI)

    4 Pilares:
    🔐 Security: Admin only + valida módulo pertence ao curso da turma
    ⚙ï¸ Stability: Transação atómica + clamp de horas (nunca > total)
    ⚡ Optimization: Upsert batch via ON CONFLICT
    📈 Scalability: Suporta N módulos numa única chamada
    """
    await class_service.update_class_progress(
        db,
        class_id,
        payload.progress,
        current_user.organization_id,
        membership_id=current_user.membership_id,
    )

    # Retornar dados atualizados para refresh na UI
    return await class_service.get_class_full_details(db, class_id, current_user.organization_id)


# ==========================================
#  DISCIPLINAS DA TURMA (Class-Subject Link)
#  Gestão curso-cêntrica de professores
# ==========================================


@router.get(
    "/{class_id}/subjects",
    response_model=schemas.ClassSubjectsListRead,
    responses={404: {"description": CLASS_NOT_FOUND_MSG}},
)
async def get_class_subjects(
    class_id: int,
    db: deps.DbSession,
    current_user: deps.ActiveActor,
):
    """
    Lista disciplinas associadas à turma (para o grade_level atual).
    Inclui professor atribuído a cada disciplina.

    Usado na página ClassSubjects.jsx para mostrar:
    - Quais disciplinas a turma tem
    - Quem é o professor de cada disciplina
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
    db: deps.DbSession,
    current_user: deps.AdminActor,
):
    """
    Adiciona uma disciplina à turma (para o grade_level atual).

    Validações:
    - Turma existe e pertence à organização
    - Disciplina existe e pertence à organização
    - Disciplina não está já associada à turma
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
async def update_class_subject(
    class_id: int,
    subject_id: int,
    payload: schemas.ClassSubjectUpdate,
    db: deps.DbSession,
    current_user: deps.AdminActor,
):
    """
    Atribui ou altera o professor e/ou substitui a seleção de módulos.

    Validações:
    - Associação turma/disciplina existe
    - Se teacher_id não é null, professor tem competência na disciplina
    - module_ids substitui a seleção; uma lista vazia é válida

    Enviar teacher_id=null para remover a atribuição.
    """
    await class_service.update_class_subject(
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
    db: deps.DbSession,
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
    db: deps.DbSession,
    current_user: deps.ActiveActor,
):
    """
    Lista disciplinas disponíveis para adicionar à turma.
    (Disciplinas da organização que ainda não estão associadas à turma)
    """
    return await class_service.get_available_subjects_for_class(
        db, class_id, current_user.organization_id
    )


@router.get(
    "/subjects/{subject_id}/eligible-teachers", response_model=list[schemas.EligibleTeacherRead]
)
async def get_eligible_teachers(
    subject_id: int,
    db: deps.DbSession,
    current_user: deps.ActiveActor,
):
    """
    Lista professores elegíveis para lecionar uma disciplina.
    (Professores que têm competência na disciplina)

    Também indica quantas turmas cada professor já tem para esta disciplina.
    """
    return await class_service.get_eligible_teachers_for_subject(
        db, subject_id, current_user.organization_id
    )
