"""Joint lesson group configuration routes (admin only)."""

from fastapi import APIRouter, status

from app import schemas
from app.api import deps
from app.core.exceptions import AppError
from app.services import joint_lesson_service

GROUP_NOT_FOUND_MSG = "Aula conjunta não encontrada"

router = APIRouter()


@router.post(
    "",
    response_model=schemas.JointLessonGroupRead,
    status_code=status.HTTP_201_CREATED,
    responses={400: {"description": "Regra de configuração violada"}},
)
async def create_joint_lesson_group(
    payload: schemas.JointLessonGroupWrite,
    db: deps.DbSession,
    current_user: deps.AdminActor,
):
    group_id = await joint_lesson_service.create_joint_group(
        db,
        payload,
        current_user.organization_id,
        changed_by_membership_id=current_user.membership_id,
    )
    result = await joint_lesson_service.get_joint_group_read(
        db, current_user.organization_id, group_id
    )
    if result is None:
        raise AppError(kind="not_found", code="resource_not_found", detail=GROUP_NOT_FOUND_MSG)
    return result


@router.put(
    "/{group_id}",
    response_model=schemas.JointLessonGroupRead,
    responses={
        400: {"description": "Regra de configuração violada"},
        404: {"description": GROUP_NOT_FOUND_MSG},
        409: {"description": "Módulo ou turma já começados"},
    },
)
async def update_joint_lesson_group(
    group_id: int,
    payload: schemas.JointLessonGroupWrite,
    db: deps.DbSession,
    current_user: deps.AdminActor,
):
    await joint_lesson_service.update_joint_group(
        db,
        group_id,
        payload,
        current_user.organization_id,
        changed_by_membership_id=current_user.membership_id,
    )
    result = await joint_lesson_service.get_joint_group_read(
        db, current_user.organization_id, group_id
    )
    if result is None:
        raise AppError(kind="not_found", code="resource_not_found", detail=GROUP_NOT_FOUND_MSG)
    return result


@router.delete(
    "/{group_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"description": GROUP_NOT_FOUND_MSG}},
)
async def delete_joint_lesson_group(
    group_id: int,
    db: deps.DbSession,
    current_user: deps.AdminActor,
):
    await joint_lesson_service.delete_joint_group(
        db,
        group_id,
        current_user.organization_id,
        changed_by_membership_id=current_user.membership_id,
    )
