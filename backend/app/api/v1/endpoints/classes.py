from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from app import schemas
from app.api import deps
from app.services import class_service

router = APIRouter()

@router.get("/", response_model=List[schemas.ClassRead])
async def read_classes(org_id: int, db: AsyncSession = Depends(deps.get_db)):
    return await class_service.get_classes_by_org(db, org_id)

@router.post("/", response_model=schemas.ClassRead)
async def create_class(item: schemas.ClassCreate, org_id: int, db: AsyncSession = Depends(deps.get_db)):
    return await class_service.create_class(db, item, org_id)

@router.delete("/{class_id}")
async def delete_class(class_id: int, org_id: int, db: AsyncSession = Depends(deps.get_db)):
    success = await class_service.delete_class(db, class_id, org_id)
    if not success:
        raise HTTPException(status_code=404, detail="Turma não encontrada")
    return {"ok": True}