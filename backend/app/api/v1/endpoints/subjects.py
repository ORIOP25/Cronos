from fastapi import APIRouter

from app import schemas
from app.api import deps
from app.services import joint_lesson_service, subject_service

router = APIRouter()


# --- 1. Ler Disciplinas ---
@router.get("/", response_model=list[schemas.SubjectRead])
async def read_subjects(
    db: deps.DbSession,
    current_user: deps.ActiveActor,
):
    # Qualquer utilizador autenticado pode ver a lista de disciplinas
    return await subject_service.get_subjects_by_org(db, current_user.organization_id)


# --- 1b. Turmas candidatas a uma aula conjunta ---
@router.get(
    "/{subject_id}/joint-candidates",
    response_model=list[schemas.JointCandidateRead],
)
async def get_joint_candidates(
    subject_id: int,
    class_id: int,
    db: deps.DbSession,
    current_user: deps.AdminActor,
    group_id: int | None = None,
    include_source: bool = False,
):
    return await joint_lesson_service.get_joint_candidates(
        db,
        subject_id,
        class_id,
        current_user.organization_id,
        group_id=group_id,
        include_source=include_source,
    )


# --- 2. Criar Disciplina ---
@router.post("/", response_model=schemas.SubjectRead)
async def create_subject(
    item: schemas.SubjectCreate,
    db: deps.DbSession,
    current_user: deps.AdminActor,
):
    return await subject_service.create_subject(
        db,
        item,
        current_user.organization_id,
        changed_by_membership_id=current_user.membership_id,
    )


# --- 3. Atualizar Disciplina ---
@router.patch(
    "/{subject_id}",
    response_model=schemas.SubjectRead,
    responses={404: {"description": "Disciplina não encontrada"}},
)
async def update_subject(
    subject_id: int,
    subject_in: schemas.SubjectUpdate,
    db: deps.DbSession,
    current_user: deps.AdminActor,  # Apenas Admin
):
    return await subject_service.update_subject(
        db,
        subject_id,
        subject_in,
        current_user.organization_id,
        changed_by_membership_id=current_user.membership_id,
    )


# --- 4. Apagar Disciplina   ---
@router.delete(
    "/{subject_id}",
    responses={
        404: {"description": "Disciplina não encontrada"},
        400: {"description": "Dependências existentes"},
    },
)
async def delete_subject(
    subject_id: int,
    db: deps.DbSession,
    current_user: deps.AdminActor,  # Apenas Admin
):
    remove_effect = await subject_service.delete_subject(
        db,
        subject_id,
        current_user.organization_id,
        changed_by_membership_id=current_user.membership_id,
    )

    return {"message": "Disciplina removida com sucesso", "remove_effect": remove_effect}
