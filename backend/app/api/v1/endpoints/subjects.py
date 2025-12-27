from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from app import schemas
from app.api import deps
from app.services import subject_service

router = APIRouter()

@router.get("/", response_model=List[schemas.SubjectRead])
async def read_subjects(org_id: int, db: AsyncSession = Depends(deps.get_db)):
    return await subject_service.get_subjects_by_org(db, org_id)

@router.post("/", response_model=schemas.SubjectRead)
async def create_subject(item: schemas.SubjectCreate, org_id: int, db: AsyncSession = Depends(deps.get_db)):
    return await subject_service.create_subject(db, item, org_id)

@router.delete("/{subject_id}")
async def delete_subject(subject_id: int, org_id: int, db: AsyncSession = Depends(deps.get_db)):
    success = await subject_service.delete_subject(db, subject_id, org_id)
    if not success:
        raise HTTPException(status_code=404, detail="Disciplina não encontrada")
    return {"ok": True}