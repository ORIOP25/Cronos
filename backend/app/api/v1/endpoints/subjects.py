from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.api import deps
from app.services import subject_service

router = APIRouter()


# --- 1. Ler Disciplinas ---
@router.get("/", response_model=list[schemas.SubjectRead])
async def read_subjects(
    db: Annotated[AsyncSession, Depends(deps.get_db, scope="function")],
    current_user: deps.ActiveActor,
):
    # Qualquer utilizador autenticado pode ver a lista de disciplinas
    return await subject_service.get_subjects_by_org(db, current_user.organization_id)


# --- 2. Criar Disciplina ---
@router.post("/", response_model=schemas.SubjectRead)
async def create_subject(
    item: schemas.SubjectCreate,
    db: Annotated[AsyncSession, Depends(deps.get_db, scope="function")],
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
    responses={404: {"description": "Disciplina nÃ£o encontrada"}},
)
async def update_subject(
    subject_id: int,
    subject_in: schemas.SubjectUpdate,
    db: Annotated[AsyncSession, Depends(deps.get_db, scope="function")],
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
        404: {"description": "Disciplina nÃ£o encontrada"},
        400: {"description": "DependÃªncias existentes"},
    },
)
async def delete_subject(
    subject_id: int,
    db: Annotated[AsyncSession, Depends(deps.get_db, scope="function")],
    current_user: deps.AdminActor,  # Apenas Admin
):
    await subject_service.delete_subject(
        db,
        subject_id,
        current_user.organization_id,
        changed_by_membership_id=current_user.membership_id,
    )

    return {"message": "Disciplina removida com sucesso"}
