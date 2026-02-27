from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import select, delete
from app import models, schemas

# --- ASYNC (API) ---
async def get_subjects_by_org(db: AsyncSession, org_id: int):
    stmt = select(models.Subject).where(models.Subject.organization_id == org_id).order_by(models.Subject.name).options(selectinload(models.Subject.modules))
    result = await db.execute(stmt)
    return result.scalars().all()

async def create_subject(db: AsyncSession, item: schemas.SubjectCreate, organization_id: int):
    """
    Cria uma disciplina e os seus módulos (Library) atomicamente.
    """
    # 0. Verificar duplicados
    query_check = select(models.Subject).where(
        models.Subject.name == item.name,
        models.Subject.organization_id == organization_id
    )
    result_check = await db.execute(query_check)
    if result_check.scalars().first():
        # Precisas de importar HTTPException do fastapi
        from fastapi import HTTPException 
        raise HTTPException(
            status_code=400, 
            detail=f"A disciplina '{item.name}' já existe nesta escola."
        )
    # 1. Separar dados da Disciplina e dos Módulos
    # O 'pop' remove 'modules' do dicionário para não dar erro ao criar o objeto Subject
    subject_data = item.model_dump()
    modules_data = subject_data.pop("modules", [])

    # 2. Criar a Disciplina
    db_subject = models.Subject(
        **subject_data,
        organization_id=organization_id
    )
    db.add(db_subject)
    await db.flush()  # Flush gera o ID da disciplina (db_subject.id)

    # 3. Criar os Módulos Associados
    for mod in modules_data:
        db_module = models.Module(
            **mod,
            subject_id=db_subject.id  # Ligação ao Pai
        )
        db.add(db_module)

    # 4. Commit Atómico (Grava tudo ou nada)
    await db.commit()
    
    # 5. Refresh com Eager Loading
    # Precisamos de recarregar o objeto para garantir que devolvemos os módulos na resposta
    query = select(models.Subject).where(models.Subject.id == db_subject.id).options(
        selectinload(models.Subject.modules)
    )
    result = await db.execute(query)
    return result.scalars().first()

# --- HELPERS: Sincronização de Módulos (Smart Diff) ---

async def _delete_removed_modules(db: AsyncSession, existing_modules: dict, incoming_ids: set):
    """Apaga módulos removidos pelo utilizador e o class_progress associado."""
    ids_to_delete = set(existing_modules.keys()) - incoming_ids
    if not ids_to_delete:
        return
    # Bulk delete class_progress (FK) antes dos módulos
    await db.execute(
        delete(models.ClassProgress).where(
            models.ClassProgress.module_id.in_(ids_to_delete)
        )
    )
    # ORM delete — mantém o identity map sincronizado
    for mod_id in ids_to_delete:
        await db.delete(existing_modules[mod_id])
    await db.flush()


async def _reset_module_orders(db: AsyncSession, incoming_modules: list, existing_modules: dict):
    """Evita violação da UniqueConstraint (uq_module_order_per_subject)
    ao reordenar módulos: define ordens temporárias negativas primeiro."""
    modules_to_update = [
        m for m in incoming_modules
        if m.id is not None and m.id in existing_modules
    ]
    if not modules_to_update:
        return
    for i, mod_data in enumerate(modules_to_update, start=1):
        existing_modules[mod_data.id].order = -i
    await db.flush()


def _upsert_modules(db: AsyncSession, incoming_modules: list, existing_modules: dict, subject_id: int):
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
                name=mod_data.name,
                code=mod_data.code,
                hours_total=mod_data.hours_total,
                order=mod_data.order,
                subject_id=subject_id,
            )
            db.add(new_mod)


async def update_subject(db: AsyncSession, subject_id: int, subject_in: schemas.SubjectUpdate, org_id: int):
    # 1. Buscar a disciplina com módulos
    query = select(models.Subject).where(
        models.Subject.id == subject_id,
        models.Subject.organization_id == org_id
    ).options(selectinload(models.Subject.modules))
    result = await db.execute(query)
    subject = result.scalars().first()
    
    if not subject:
        return None

    # 2. Validar Nome Único (Security)
    if subject_in.name and subject_in.name != subject.name:
        q_check = select(models.Subject).where(
            models.Subject.name == subject_in.name,
            models.Subject.organization_id == org_id,
            models.Subject.id != subject_id
        )
        if (await db.execute(q_check)).scalars().first():
            return None 

    # 3. Atualizar campos simples
    update_data = subject_in.model_dump(exclude_unset=True, exclude={'modules'})
    for field, value in update_data.items():
        setattr(subject, field, value)

    # 4. Sincronizar Módulos (Smart diff: update existing, create new, delete removed)
    if subject_in.modules is not None:
        existing_modules = {m.id: m for m in subject.modules}
        incoming_ids = {m.id for m in subject_in.modules if m.id is not None}
        await _delete_removed_modules(db, existing_modules, incoming_ids)
        await _reset_module_orders(db, subject_in.modules, existing_modules)
        _upsert_modules(db, subject_in.modules, existing_modules, subject_id)

    # subject já está tracked pela sessão — commit grava todas as alterações
    await db.commit()
    stmt = select(models.Subject).options(selectinload(models.Subject.modules)).where(models.Subject.id == subject.id)
    result = await db.execute(stmt)
    return result.scalars().first()

async def delete_subject(db: AsyncSession, subject_id: int, org_id: int):
    """
    Remove uma disciplina. Protege se existirem aulas associadas.
    """
    # 1. Buscar disciplina
    result = await db.execute(select(models.Subject).where(models.Subject.id == subject_id, models.Subject.organization_id == org_id))
    item = result.scalars().first()
    
    if not item:
        return "NOT_FOUND"

    # 2. VERIFICAÇÃO DE INTEGRIDADE
    # Verifica se existem aulas (Lessons) desta disciplina
    query_dep = select(models.Lesson).where(models.Lesson.subject_id == subject_id)
    result_dep = await db.execute(query_dep)
    
    if result_dep.first():
        return "DEPENDENCY_ERROR"

    # 3. Apagar
    await db.delete(item)
    await db.commit()
    return "SUCCESS"

# --- SYNC (SOLVER) ---
def get_subjects_by_org_sync(db: Session, org_id: int):
    return db.query(models.Subject).filter(models.Subject.organization_id == org_id).all()