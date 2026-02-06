from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import select, delete
from app import models, schemas
# Importamos Lesson para garantir que não apagamos disciplinas em uso
from app.models import Lesson

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

async def update_subject(db: AsyncSession, subject_id: int, subject_in: schemas.SubjectUpdate, org_id: int):
    # 1. Buscar a disciplina
    query = select(models.Subject).where(
        models.Subject.id == subject_id,
        models.Subject.organization_id == org_id
    )
    result = await db.execute(query)
    subject = result.scalars().first()
    
    if not subject:
        return None

    # 2. Validar Nome Único (Security)
    if subject_in.name and subject_in.name != subject.name:
        q_check = select(models.Subject).where(
            models.Subject.name == subject_in.name,
            models.Subject.organization_id == org_id,
            models.Subject.id != subject_id # Exclui o próprio da verificação
        )
        if (await db.execute(q_check)).scalars().first():
            # Retorna None ou levanta exceção para o endpoint tratar
            return None 

    # 3. Atualizar campos simples
    update_data = subject_in.model_dump(exclude_unset=True, exclude={'modules'})
    for field, value in update_data.items():
        setattr(subject, field, value)

    # 4. Atualizar Módulos (Optimization/Scalability)
    # Estratégia "Replace": Apaga os antigos e cria os novos. 
    # Garante consistência com o que vem do Frontend Wizard.
    if subject_in.modules is not None:
        # A) Apagar módulos antigos desta disciplina
        await db.execute(delete(models.Module).where(models.Module.subject_id == subject_id))
        
        # B) Criar novos módulos
        for mod_data in subject_in.modules:
            new_mod = models.Module(
                **mod_data.model_dump(), 
                subject_id=subject_id
            )
            db.add(new_mod)

    db.add(subject)
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