from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select
from app import models, schemas

async def get_modules_by_org(db: AsyncSession, organization_id: int):
    stmt = (
        select(models.Module)
        .join(models.Subject)
        .where(models.Subject.organization_id == organization_id)
        .options(selectinload(models.Module.subject))  # ✅ ADICIONAR
        .order_by(models.Module.name)
    )
    result = await db.execute(stmt)
    return result.scalars().all()

async def create_module(db: AsyncSession, item: schemas.ModuleCreate, organization_id: int):
    # Validar se o subject_id pertence à organização
    subject_query = select(models.Subject).where(
        models.Subject.id == item.subject_id,
        models.Subject.organization_id == organization_id
    )
    subject_result = await db.execute(subject_query)
    if not subject_result.scalars().first():
        return "INVALID_SUBJECT"

    db_item = models.Module(**item.model_dump(), organization_id=organization_id)
    db.add(db_item)
    await db.commit()
    await db.refresh(db_item)
    return db_item

async def update_module(db: AsyncSession, module_id: int, item: schemas.ModuleUpdate, organization_id: int):
    # Garantir que o módulo pertence à organização
    result = await db.execute(
        select(models.Module)
        .join(models.Subject)
        .where(
            models.Module.id == module_id,
            models.Module.organization_id == organization_id,
            models.Subject.organization_id == organization_id
        )
    )
    db_item = result.scalars().first()
    
    if not db_item:
        return None

    # Se subject_id for alterado, validar que pertence à organização
    if item.subject_id is not None:
        subject_query = select(models.Subject).where(
            models.Subject.id == item.subject_id,
            models.Subject.organization_id == organization_id
        )
        subject_result = await db.execute(subject_query)
        if not subject_result.scalars().first():
            return "INVALID_SUBJECT"

    for field, value in item.model_dump(exclude_unset=True).items():
        setattr(db_item, field, value)

    db.add(db_item)
    await db.commit()
    await db.refresh(db_item)
    return db_item

async def delete_module(db: AsyncSession, module_id: int, organization_id: int):
    # 1. Verificar existência + org
    result = await db.execute(
        select(models.Module)
        .join(models.Subject)
        .where(
            models.Module.id == module_id,
            models.Module.organization_id == organization_id,
            models.Subject.organization_id == organization_id
        )
    )
    db_item = result.scalars().first()
    if not db_item:
        return "NOT_FOUND"

    # 2. Verificar dependências (ClassProgress)
    # Não apagamos módulos que já estão a ser lecionados (têm progresso registado)
    result_prog = await db.execute(
        select(models.ClassProgress)
        .join(models.Class, models.ClassProgress.class_id == models.Class.id)
        .where(
            models.ClassProgress.module_id == module_id,
            models.Class.organization_id == organization_id,
        )
    )
    if result_prog.first():
        return "DEPENDENCY_ERROR"

    await db.delete(db_item)
    await db.commit()
    return "SUCCESS"
