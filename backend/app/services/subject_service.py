from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app import models, schemas
from app.services.scheduler_state_service import record_scheduler_change


def _subject_demand_snapshot(subject: models.Subject) -> dict:
    return {
        "required_room_type": subject.required_room_type,
        "module_sequence": [
            {
                "id": module.id,
                "order": module.order,
                "hours_total": module.hours_total,
            }
            for module in sorted(subject.modules, key=lambda item: (item.order, item.id or 0))
        ],
    }


async def _subject_is_scheduled(db: AsyncSession, organization_id: int, subject_id: int) -> bool:
    class_link = await db.scalar(
        select(models.ClassSubjectLink.id)
        .where(
            models.ClassSubjectLink.organization_id == organization_id,
            models.ClassSubjectLink.subject_id == subject_id,
        )
        .limit(1)
    )
    if class_link is not None:
        return True
    course_link = await db.execute(
        select(models.course_subject_link.c.subject_id)
        .where(
            models.course_subject_link.c.organization_id == organization_id,
            models.course_subject_link.c.subject_id == subject_id,
        )
        .limit(1)
    )
    return course_link.first() is not None


# --- ASYNC (API) ---
async def get_subjects_by_org(db: AsyncSession, organization_id: int):
    stmt = (
        select(models.Subject)
        .where(models.Subject.organization_id == organization_id)
        .order_by(models.Subject.name)
        .options(selectinload(models.Subject.modules))
    )
    result = await db.execute(stmt)
    return result.scalars().all()


async def create_subject(
    db: AsyncSession,
    item: schemas.SubjectCreate,
    organization_id: int,
    changed_by_membership_id: int | None = None,
):
    """
    Cria uma disciplina e os seus módulos (Library) atomicamente.
    """
    # 0. Verificar duplicados
    query_check = select(models.Subject).where(
        models.Subject.name == item.name, models.Subject.organization_id == organization_id
    )
    result_check = await db.execute(query_check)
    if result_check.scalars().first():
        from app.core.exceptions import DomainError

        raise DomainError(
            f"A disciplina '{item.name}' já existe nesta escola.",
            status_code=400,
        )
    # 1. Separar dados da Disciplina e dos Módulos
    # O 'pop' remove 'modules' do dicionário para não dar erro ao criar o objeto Subject
    subject_data = item.model_dump()
    modules_data = subject_data.pop("modules", [])

    # 2. Criar a Disciplina
    db_subject = models.Subject(**subject_data, organization_id=organization_id)
    db.add(db_subject)
    await db.flush()  # Flush gera o ID da disciplina (db_subject.id)

    # 3. Criar os Módulos Associados
    for mod in modules_data:
        db_module = models.Module(
            **mod,
            organization_id=organization_id,
            subject_id=db_subject.id,  # Ligação ao Pai
        )
        db.add(db_module)

    await db.flush()
    await db.refresh(db_subject, ["modules"])
    await record_scheduler_change(
        db,
        organization_id,
        entity_type="SUBJECT_DEMAND",
        entity_id=db_subject.id,
        operation=models.SchedulerStateChangeOperation.CREATE,
        before=None,
        after=_subject_demand_snapshot(db_subject),
        changed_by_membership_id=changed_by_membership_id,
        active_resource=False,
    )

    # 4. Commit Atómico (Grava tudo ou nada)
    await db.flush()

    # 5. Refresh com Eager Loading
    # Precisamos de recarregar o objeto para garantir que devolvemos os módulos na resposta
    query = (
        select(models.Subject)
        .where(models.Subject.id == db_subject.id)
        .options(selectinload(models.Subject.modules))
    )
    result = await db.execute(query)
    return result.scalars().first()


# --- HELPERS: Sincronização de Módulos (Smart Diff) ---


async def _delete_removed_modules(
    db: AsyncSession, existing_modules: dict, incoming_ids: set, organization_id: int
):
    """Delete unused modules while preserving append-only progress history."""
    ids_to_delete = set(existing_modules.keys()) - incoming_ids
    if not ids_to_delete:
        return
    referenced = await db.scalar(
        select(models.ProgressLedgerEntry.id)
        .where(
            models.ProgressLedgerEntry.organization_id == organization_id,
            models.ProgressLedgerEntry.module_id.in_(ids_to_delete),
        )
        .limit(1)
    )
    if referenced is not None:
        raise ValueError("Modules with progress history cannot be deleted.")
    # ORM delete — mantém o identity map sincronizado
    for mod_id in ids_to_delete:
        await db.delete(existing_modules[mod_id])
    await db.flush()


async def _reset_module_orders(db: AsyncSession, incoming_modules: list, existing_modules: dict):
    """Move retained modules outside both order ranges before reordering."""
    modules_to_update = [
        m for m in incoming_modules if m.id is not None and m.id in existing_modules
    ]
    if not modules_to_update:
        return
    temporary_start = (
        max(
            [module.order for module in existing_modules.values()]
            + [module.order for module in incoming_modules]
        )
        + 1
    )
    for offset, mod_data in enumerate(modules_to_update):
        existing_modules[mod_data.id].order = temporary_start + offset
    await db.flush()


def _upsert_modules(
    db: AsyncSession,
    incoming_modules: list,
    existing_modules: dict,
    subject_id: int,
    organization_id: int,
):
    """Atualiza módulos existentes e cria novos (com ordens finais)."""
    for mod_data in incoming_modules:
        if mod_data.id is not None and mod_data.id in existing_modules:
            existing_mod = existing_modules[mod_data.id]
            existing_mod.name = mod_data.name
            existing_mod.code = mod_data.code
            existing_mod.hours_total = mod_data.hours_total
            existing_mod.order = mod_data.order
        else:
            new_mod = models.Module(
                organization_id=organization_id,
                name=mod_data.name,
                code=mod_data.code,
                hours_total=mod_data.hours_total,
                order=mod_data.order,
                subject_id=subject_id,
            )
            db.add(new_mod)


async def update_subject(
    db: AsyncSession,
    subject_id: int,
    subject_in: schemas.SubjectUpdate,
    organization_id: int,
    changed_by_membership_id: int | None = None,
):
    # 1. Buscar a disciplina com módulos
    query = (
        select(models.Subject)
        .where(models.Subject.id == subject_id, models.Subject.organization_id == organization_id)
        .options(selectinload(models.Subject.modules))
    )
    result = await db.execute(query)
    subject = result.scalars().first()

    if not subject:
        return None
    before = _subject_demand_snapshot(subject)
    active_resource = await _subject_is_scheduled(db, organization_id, subject_id)

    # 2. Validar Nome Único (Security)
    if subject_in.name and subject_in.name != subject.name:
        q_check = select(models.Subject).where(
            models.Subject.name == subject_in.name,
            models.Subject.organization_id == organization_id,
            models.Subject.id != subject_id,
        )
        if (await db.execute(q_check)).scalars().first():
            return None

    # 3. Atualizar campos simples
    update_data = subject_in.model_dump(exclude_unset=True, exclude={"modules"})
    for field, value in update_data.items():
        setattr(subject, field, value)

    # 4. Sincronizar Módulos (Smart diff: update existing, create new, delete removed)
    if subject_in.modules is not None:
        existing_modules = {m.id: m for m in subject.modules}
        incoming_ids = {m.id for m in subject_in.modules if m.id is not None}
        await _delete_removed_modules(db, existing_modules, incoming_ids, organization_id)
        await _reset_module_orders(db, subject_in.modules, existing_modules)
        _upsert_modules(db, subject_in.modules, existing_modules, subject_id, organization_id)

    await db.flush()
    await db.refresh(subject, ["modules"])
    await record_scheduler_change(
        db,
        organization_id,
        entity_type="SUBJECT_DEMAND",
        entity_id=subject.id,
        operation=models.SchedulerStateChangeOperation.UPDATE,
        before=before,
        after=_subject_demand_snapshot(subject),
        changed_by_membership_id=changed_by_membership_id,
        active_resource=active_resource,
    )

    # subject já está tracked pela sessão — commit grava todas as alterações
    await db.flush()
    stmt = (
        select(models.Subject)
        .options(selectinload(models.Subject.modules))
        .where(models.Subject.id == subject.id)
    )
    result = await db.execute(stmt)
    return result.scalars().first()


async def delete_subject(
    db: AsyncSession,
    subject_id: int,
    organization_id: int,
    changed_by_membership_id: int | None = None,
):
    """
    Remove uma disciplina. Protege se existirem aulas associadas.
    """
    # 1. Buscar disciplina
    result = await db.execute(
        select(models.Subject)
        .where(
            models.Subject.id == subject_id,
            models.Subject.organization_id == organization_id,
        )
        .options(selectinload(models.Subject.modules))
    )
    item = result.scalars().first()

    if not item:
        return "NOT_FOUND"

    for model in (
        models.ClassSubjectLink,
        models.ActiveScheduleBlock,
        models.ScheduleDraftBlock,
        models.OperationalScheduleBlock,
    ):
        if (
            await db.execute(
                select(model.id).where(
                    model.organization_id == organization_id,
                    model.subject_id == subject_id,
                )
            )
        ).first():
            return "DEPENDENCY_ERROR"

    # 3. Apagar
    before = _subject_demand_snapshot(item)
    active_resource = await _subject_is_scheduled(db, organization_id, subject_id)
    await db.delete(item)
    await record_scheduler_change(
        db,
        organization_id,
        entity_type="SUBJECT_DEMAND",
        entity_id=item.id,
        operation=models.SchedulerStateChangeOperation.DELETE,
        before=before,
        after=None,
        changed_by_membership_id=changed_by_membership_id,
        active_resource=active_resource,
    )
    await db.flush()
    return "SUCCESS"

