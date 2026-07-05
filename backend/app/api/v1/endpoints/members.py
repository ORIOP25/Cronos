from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app import models, schemas
from app.api import deps
from app.services import member_service


router = APIRouter()


@router.get("", response_model=schemas.MemberListRead)
@router.get("/", response_model=schemas.MemberListRead)
async def list_members(
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)],
    include_archived: bool = False,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
):
    return await member_service.list_members(
        db,
        organization_id=current_user.organization_id,
        include_archived=include_archived,
        skip=skip,
        limit=limit,
    )


@router.get("/me", response_model=schemas.CurrentMemberRead)
async def get_current_member(
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_user)],
):
    return await member_service.current_member(db, current_user=current_user)


@router.post("", response_model=schemas.MemberRead, status_code=201)
@router.post("/", response_model=schemas.MemberRead, status_code=201)
async def create_member(
    member: schemas.MemberCreate,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)],
):
    return await member_service.create_member(
        db,
        member,
        organization_id=current_user.organization_id,
        current_admin=current_user,
    )


@router.get("/{member_id}", response_model=schemas.MemberRead)
async def get_member(
    member_id: int,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)],
):
    return await member_service.get_member_read(db, organization_id=current_user.organization_id, member_id=member_id)


@router.patch("/{member_id}", response_model=schemas.MemberRead)
async def update_member(
    member_id: int,
    member: schemas.MemberUpdate,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)],
):
    return await member_service.update_member(
        db,
        member_id,
        member,
        organization_id=current_user.organization_id,
        current_admin=current_user,
    )


@router.post("/{member_id}/remove")
async def remove_member(
    member_id: int,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)],
):
    return await member_service.remove_member(
        db,
        member_id,
        organization_id=current_user.organization_id,
        current_admin=current_user,
    )


@router.post("/{member_id}/resend-invitation", response_model=schemas.MemberRead)
async def resend_member_invitation(
    member_id: int,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)],
):
    return await member_service.resend_invitation(
        db,
        member_id,
        organization_id=current_user.organization_id,
        current_admin=current_user,
    )


@router.post("/{member_id}/retry-sync", response_model=schemas.MemberRead)
async def retry_member_sync(
    member_id: int,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)],
):
    return await member_service.retry_sync(
        db,
        member_id,
        organization_id=current_user.organization_id,
        current_admin=current_user,
    )


@router.post("/{member_id}/restore", response_model=schemas.MemberRead)
async def restore_member(
    member_id: int,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)],
    restore: schemas.MemberRestore | None = None,
):
    return await member_service.restore_member(
        db,
        member_id,
        restore_in=restore,
        organization_id=current_user.organization_id,
        current_admin=current_user,
    )
