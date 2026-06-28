from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select
from app import models, schemas
from app.services.scheduler_state_service import record_scheduler_change


def _module_demand_snapshot(item: models.Module) -> dict:
    return {
        "subject_id": item.subject_id,
        "hours_total": item.hours_total,
        "order": item.order,
    }


async def _subject_is_scheduled(
    db: AsyncSession, organization_id: int, subject_id: int
) -> bool:
    class_link = await db.scalar(
        select(models.ClassSubjectLink.id).where(
            models.ClassSubjectLink.organization_id == organization_id,
            models.ClassSubjectLink.subject_id == subject_id,
        ).limit(1)
    )
    if class_link is not None:
        return True
    course_link = await db.execute(
        select(models.course_subject_link.c.subject_id).where(
            models.course_subject_link.c.organization_id == organization_id,
            models.course_subject_link.c.subject_id == subject_id,
        ).limit(1)
    )
    return course_link.first() is not None

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

async def create_module(
    db: AsyncSession,
    item: schemas.ModuleCreate,
    organization_id: int,
    changed_by_user_id: int | None = None,
):
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
    await db.flush()
    await record_scheduler_change(
        db,
        organization_id,
        entity_type="SUBJECT_DEMAND",
        entity_id=db_item.id,
        operation=models.SchedulerStateChangeOperation.CREATE,
        before=None,
        after=_module_demand_snapshot(db_item),
        changed_by_user_id=changed_by_user_id,
        active_resource=await _subject_is_scheduled(db, organization_id, db_item.subject_id),
    )
    await db.commit()
    await db.refresh(db_item)
    return db_item

async def update_module(
    db: AsyncSession,
    module_id: int,
    item: schemas.ModuleUpdate,
    organization_id: int,
    changed_by_user_id: int | None = None,
):
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
    before = _module_demand_snapshot(db_item)

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
    await record_scheduler_change(
        db,
        organization_id,
        entity_type="SUBJECT_DEMAND",
        entity_id=db_item.id,
        operation=models.SchedulerStateChangeOperation.UPDATE,
        before=before,
        after=_module_demand_snapshot(db_item),
        changed_by_user_id=changed_by_user_id,
        active_resource=await _subject_is_scheduled(db, organization_id, db_item.subject_id),
    )
    await db.commit()
    await db.refresh(db_item)
    return db_item

async def delete_module(
    db: AsyncSession,
    module_id: int,
    organization_id: int,
    changed_by_user_id: int | None = None,
):
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

    before = _module_demand_snapshot(db_item)
    active_resource = await _subject_is_scheduled(db, organization_id, db_item.subject_id)
    await db.delete(db_item)
    await record_scheduler_change(
        db,
        organization_id,
        entity_type="SUBJECT_DEMAND",
        entity_id=db_item.id,
        operation=models.SchedulerStateChangeOperation.DELETE,
        before=before,
        after=None,
        changed_by_user_id=changed_by_user_id,
        active_resource=active_resource,
    )
    await db.commit()
    return "SUCCESS"
