from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app import models, schemas

async def get_modules_by_org(db: AsyncSession, org_id: int):
    # Fazemos um join com Subject para garantir que o módulo pertence à organização certa
    stmt = (
        select(models.Module)
        .join(models.Subject)
        .where(models.Subject.organization_id == org_id)
        .order_by(models.Module.name)
    )
    result = await db.execute(stmt)
    return result.scalars().all()

async def create_module(db: AsyncSession, item: schemas.ModuleCreate):
    # Nota: Validar se o subject_id pertence à organização seria o ideal aqui
    db_item = models.Module(**item.model_dump())
    db.add(db_item)
    await db.commit()
    await db.refresh(db_item)
    return db_item

async def update_module(db: AsyncSession, module_id: int, item: schemas.ModuleCreate):
    # Busca simples (assumindo validação de org na rota ou query futura)
    result = await db.execute(select(models.Module).where(models.Module.id == module_id))
    db_item = result.scalars().first()
    
    if not db_item:
        return None

    for field, value in item.model_dump().items():
        setattr(db_item, field, value)

    db.add(db_item)
    await db.commit()
    await db.refresh(db_item)
    return db_item

async def delete_module(db: AsyncSession, module_id: int):
    # 1. Verificar existência
    result = await db.execute(select(models.Module).where(models.Module.id == module_id))
    db_item = result.scalars().first()
    if not db_item:
        return "NOT_FOUND"

    # 2. Verificar dependências (ClassProgress)
    # Não apagamos módulos que já estão a ser lecionados (têm progresso registado)
    result_prog = await db.execute(select(models.ClassProgress).where(models.ClassProgress.module_id == module_id))
    if result_prog.first():
        return "DEPENDENCY_ERROR"

    await db.delete(db_item)
    await db.commit()
    return "SUCCESS"