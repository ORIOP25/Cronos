from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, with_loader_criteria

from app import models, schemas
from app.core.exceptions import AppError
from app.services import resource_removal
from app.services.scheduler_state_service import record_scheduler_change


async def _course_demand_snapshot(db: AsyncSession, organization_id: int, course_id: int) -> dict:
    subject_ids = await db.scalars(
        select(models.course_subject_link.c.subject_id).where(
            models.course_subject_link.c.organization_id == organization_id,
            models.course_subject_link.c.course_id == course_id,
        )
    )
    classes = await db.scalars(
        select(models.Class).where(
            models.Class.organization_id == organization_id,
            models.Class.course_id == course_id,
        )
    )
    return {
        "subject_ids": sorted(subject_ids.all()),
        "classes": sorted(
            (
                {
                    "size": item.size,
                    "start_year": item.start_year,
                    "end_year": item.end_year,
                    "grade_level": item.grade_level,
                    "is_archived": item.is_archived,
                }
                for item in classes.all()
            ),
            key=lambda item: (
                item["start_year"],
                item["end_year"],
                item["grade_level"],
                item["size"],
            ),
        ),
    }


# --- LEITURA ---
async def get_courses_by_org(
    db: AsyncSession, organization_id: int, skip: int = 0, limit: int = 100
):
    """
    Lista cursos da organização com paginação offset/limit.

    4º Pilar:
    - Optimization: selectinload carrega subjects+classes em 3 queries (não N+1)
    - Scalability: offset/limit permite crescimento sem impacto

    Nota: Carregamos subjects e classes porque a tabela precisa da contagem
    e o modal de edição precisa dos dados completos para popular o form.
    Para ~50 cursos com ~10 disciplinas cada, o overhead é negligível.
    """
    # Sanitize limit (max 1000 para evitar sobre-carga)
    limit = min(max(limit, 1), 1000)
    skip = max(skip, 0)

    query = (
        select(models.Course)
        .where(
            models.Course.organization_id == organization_id,
            models.Course.is_archived.is_(False),
        )
        .options(selectinload(models.Course.subjects), selectinload(models.Course.classes))
        .order_by(models.Course.name)
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(query)
    return result.scalars().all()


async def get_course_details(db: AsyncSession, course_id: int, organization_id: int):
    """Retorna a árvore completa do curso para a Dashboard"""
    query = (
        select(models.Course)
        .where(models.Course.id == course_id, models.Course.organization_id == organization_id)
        .options(
            selectinload(models.Course.subjects),
            selectinload(models.Course.classes),  # Carregar turmas
            with_loader_criteria(models.Class, models.Class.is_archived.is_(False)),
            with_loader_criteria(models.Subject, models.Subject.is_archived.is_(False)),
        )
    )
    result = await db.execute(query)
    return result.scalars().first()


# --- CRIAÇÃO (O MOTOR NOVO) ---
async def create_course(
    db: AsyncSession,
    item: schemas.CourseCreate,
    organization_id: int,
    changed_by_membership_id: int | None = None,
):
    """
    Cria Curso + Associa Disciplinas + Define Professores + Gera Turmas
    Tudo numa transação atómica.
    """
    # 1. Validar Abreviatura Única (Regra de Negócio)
    q_check = select(models.Course).where(
        models.Course.abbreviation == item.abbreviation.upper(),
        models.Course.organization_id == organization_id,
    )
    if (await db.execute(q_check)).scalars().first():
        raise AppError(
            kind="bad_request",
            code="bad_request",
            detail=f"Course abbreviation '{item.abbreviation}' already exists.",
        )

    # 2. Preparar as Disciplinas (ANTES DE CRIAR O CURSO)
    # Buscamos as disciplinas primeiro para injetar logo na criação
    subjects_to_link = []
    if item.subject_ids:
        q_subjects = select(models.Subject).where(
            models.Subject.id.in_(item.subject_ids),
            models.Subject.organization_id == organization_id,
        )
        subjects_to_link = (await db.execute(q_subjects)).scalars().all()

        if len(subjects_to_link) != len(item.subject_ids):
            raise AppError(
                kind="bad_request",
                code="bad_request",
                detail="One or more subjects do not belong to the organization.",
            )

    # 3. Criar o Objeto Curso (SEM disciplinas, evita lazy loading em async)
    course_data = item.model_dump(
        exclude={"subject_ids", "classes_config", "teacher_assignments", "abbreviation"}
    )

    db_course = models.Course(
        **course_data,
        organization_id=organization_id,
        abbreviation=item.abbreviation.upper(),
        # ❌ NÃO atribuir subjects aqui (trigga lazy loading em async)
    )

    db.add(db_course)
    await db.flush()  # Gerar ID do curso

    # 3.5. Associar disciplinas via INSERT (evita lazy load em async)
    # ⚠️ NÃO usar db_course.subjects.extend() - causa MissingGreenlet
    if subjects_to_link:
        # Inserir directamente na tabela de ligação
        stmt = insert(models.course_subject_link).values(
            [
                {
                    "organization_id": organization_id,
                    "course_id": db_course.id,
                    "subject_id": subject.id,
                }
                for subject in subjects_to_link
            ]
        )
        await db.execute(stmt)

    # 4. Criar Turmas Automaticamente
    # Agora que já temos o ID do curso (pós-flush), podemos criar as turmas
    for cls_conf in item.classes_config:
        start_short = cls_conf.start_year % 100
        end_short = cls_conf.end_year % 100
        class_name = cls_conf.name or f"{db_course.abbreviation} {start_short}/{end_short}"

        new_class = models.Class(
            name=class_name,
            size=cls_conf.size,
            course_id=db_course.id,
            organization_id=organization_id,
            grade_level=cls_conf.grade_level,
            start_year=cls_conf.start_year,
            end_year=cls_conf.end_year,
        )
        db.add(new_class)

    await db.flush()
    await record_scheduler_change(
        db,
        organization_id,
        entity_type="COURSE_DEMAND",
        entity_id=db_course.id,
        operation=models.SchedulerStateChangeOperation.BULK_IMPORT,
        before=None,
        after=await _course_demand_snapshot(db, organization_id, db_course.id),
        changed_by_membership_id=changed_by_membership_id,
        metadata={"class_count": len(item.classes_config)},
    )

    # 5. Commit Final
    await db.flush()

    # 6. Retornar com eager load (selectinload) para evitar lazy loading em async
    # ⚠️ NÃO usar .refresh() com relacionamentos - causa MissingGreenlet
    return await get_course_details(db, db_course.id, organization_id)


# --- UPDATE E DELETE ---
async def update_course(
    db: AsyncSession,
    course_id: int,
    item: schemas.CourseUpdate,
    organization_id: int,
    changed_by_membership_id: int | None = None,
):
    """
    Atualiza um curso (PATCH - apenas campos enviados).
    """
    query = select(models.Course).where(
        models.Course.id == course_id, models.Course.organization_id == organization_id
    )

    result = await db.execute(query)
    db_item = result.scalars().first()

    if not db_item:
        raise AppError(
            kind="not_found",
            code="resource_not_found",
            detail=f"Course {course_id} was not found in organization {organization_id}.",
        )
    before = await _course_demand_snapshot(db, organization_id, course_id)

    # SECURITY: Se estão a mudar abbreviation, validar uniqueness
    if item.abbreviation is not None and item.abbreviation.upper() != db_item.abbreviation:
        q_check = select(models.Course).where(
            models.Course.abbreviation == item.abbreviation.upper(),
            models.Course.organization_id == organization_id,
            models.Course.id != course_id,
        )
        if (await db.execute(q_check)).scalars().first():
            raise AppError(
                kind="bad_request",
                code="bad_request",
                detail=f"Course abbreviation '{item.abbreviation}' already exists.",
            )

    # 1. Aplicar updates Escalares (Campos simples)
    update_data = item.model_dump(exclude_unset=True, exclude={"subject_ids"})
    for field, value in update_data.items():
        if value is None:
            continue
        if field == "abbreviation":
            setattr(db_item, field, value.upper())
        else:
            setattr(db_item, field, value)

    # Gravar as alterações escalares primeiro
    db.add(db_item)
    await db.flush()

    # 2. Atualizar Relações (SQL Directo para evitar MissingGreenlet)
    if item.subject_ids is not None:
        # CORREÇÃO CRÍTICA: Expirar a relação no ORM para evitar que ele
        # re-insira os dados antigos durante o commit.
        db.expire(db_item, ["subjects"])

        # Validar IDs
        stmt_subjects = select(models.Subject).where(
            models.Subject.id.in_(item.subject_ids),
            models.Subject.organization_id == organization_id,
        )
        new_subjects = (await db.execute(stmt_subjects)).scalars().all()

        # Remover antigas
        await db.execute(
            delete(models.course_subject_link).where(
                models.course_subject_link.c.organization_id == organization_id,
                models.course_subject_link.c.course_id == course_id,
            )
        )

        # Inserir novas
        if new_subjects:
            stmt = insert(models.course_subject_link).values(
                [
                    {
                        "organization_id": organization_id,
                        "course_id": course_id,
                        "subject_id": subject.id,
                    }
                    for subject in new_subjects
                ]
            )
            await db.execute(stmt)

    await record_scheduler_change(
        db,
        organization_id,
        entity_type="COURSE_DEMAND",
        entity_id=course_id,
        operation=models.SchedulerStateChangeOperation.UPDATE,
        before=before,
        after=await _course_demand_snapshot(db, organization_id, course_id),
        changed_by_membership_id=changed_by_membership_id,
    )
    await db.flush()

    # Retornar com eager load fresco
    return await get_course_details(db, course_id, organization_id)


async def delete_course(
    db: AsyncSession,
    course_id: int,
    organization_id: int,
    changed_by_membership_id: int | None = None,
) -> str:
    """Remove um curso da gestão atual e devolve o efeito aplicado.

    A regra do domínio mantém-se: as turmas atuais têm de ser removidas
    primeiro. Um curso cujas turmas estejam apenas arquivadas é arquivado; um
    curso sem turmas é eliminado fisicamente. As ligações curriculares são
    retiradas na mesma transação.
    """
    result = await db.execute(
        select(models.Course).where(
            models.Course.id == course_id, models.Course.organization_id == organization_id
        )
    )
    course = result.scalars().first()
    if not course:
        raise AppError(
            kind="not_found",
            code="resource_not_found",
            detail=f"Course {course_id} was not found in organization {organization_id}.",
        )

    active_class = await db.scalar(
        select(models.Class.id)
        .where(
            models.Class.course_id == course_id,
            models.Class.organization_id == organization_id,
            models.Class.is_archived.is_(False),
        )
        .limit(1)
    )
    if active_class is not None:
        raise AppError(
            kind="bad_request",
            code="course_has_classes",
            detail=f"Course {course_id} has classes and cannot be deleted.",
        )

    archived_class = await db.scalar(
        select(models.Class.id)
        .where(
            models.Class.course_id == course_id,
            models.Class.organization_id == organization_id,
        )
        .limit(1)
    )
    before = await _course_demand_snapshot(db, organization_id, course_id)
    effect = "archive" if archived_class is not None else "hard_delete"
    await resource_removal.remove_course_configuration(db, organization_id, course_id)

    if effect == "hard_delete":
        operation = models.SchedulerStateChangeOperation.DELETE
        after = None
        await db.delete(course)
    else:
        operation = models.SchedulerStateChangeOperation.UPDATE
        course.is_archived = True
        after = {**before, "is_archived": True}

    await record_scheduler_change(
        db,
        organization_id,
        entity_type="COURSE_DEMAND",
        entity_id=course_id,
        operation=operation,
        before=before,
        after=after,
        changed_by_membership_id=changed_by_membership_id,
        active_resource=False,
    )
    await db.flush()
    return effect
