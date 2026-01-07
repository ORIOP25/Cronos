from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app import models, schemas

async def get_courses_by_org(db: AsyncSession, org_id: int):
    result = await db.execute(select(models.Course).where(models.Course.organization_id == org_id))
    return result.scalars().all()

async def create_course(db: AsyncSession, item: schemas.CourseCreate, org_id: int):
    db_item = models.Course(**item.model_dump(), organization_id=org_id)
    db.add(db_item)
    await db.commit()
    await db.refresh(db_item)
    return db_item

async def delete_course(db: AsyncSession, course_id: int, org_id: int):
    # 1. Verificar existência
    result = await db.execute(select(models.Course).where(models.Course.id == course_id, models.Course.organization_id == org_id))
    course = result.scalars().first()
    if not course:
        return "NOT_FOUND"

    # 2. Verificar dependências (Turmas)
    # Não apagamos cursos que têm turmas ativas
    result_classes = await db.execute(select(models.Class).where(models.Class.course_id == course_id))
    if result_classes.first():
        return "DEPENDENCY_ERROR"

    await db.delete(course)
    await db.commit()
    return "SUCCESS"