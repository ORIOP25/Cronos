#C:\Users\Hp\Desktop\AnoLetivo25_26\MeuProjeto\backend\app\services\user_service.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List
from sqlalchemy import desc, delete
from app import models, schemas
from app.services.teacher_service import get_teachers_by_org
from app.models import UserRole

# --- CRUD: User (Utilizador) ---

EMAIL_ALREADY_EXISTS_MSG = "Este email já está registado"


async def get_user_by_email(db: AsyncSession, email: str) -> models.User | None:
    query = select(models.User).where(models.User.email == email)
    result = await db.execute(query)
    
    return result.scalars().first()


async def register_account(
    db: AsyncSession,
    payload: schemas.RegisterRequest,
) -> models.User:
    """
    Regista uma nova conta: cria Organization + User (Admin) numa única transação.
    Se algo falhar, faz rollback de tudo.
    """
    # 1. Verificar e-mail duplicado
    existing = await get_user_by_email(db, payload.email)
    if existing:
        raise ValueError(EMAIL_ALREADY_EXISTS_MSG)

    # 2. Criar Organização
    db_org = models.Organization(name=payload.school_name)
    db.add(db_org)
    await db.flush()  # Obtém o ID sem fazer commit

    # 3. Criar perfil de Professor para o Admin (na mesma transação)
    db_teacher = models.Teacher(
        name=payload.admin_name,
        organization_id=db_org.id,
    )
    db.add(db_teacher)
    await db.flush()  # Obtém db_teacher.id

    # 4. Criar Utilizador Admin (ligado ao perfil de Professor)
    db_user = models.User(
        name=payload.admin_name,
        email=payload.email,
        clerk_user_id=None,
        organization_id=db_org.id,
        role=models.UserRole.admin,
        is_active=True,
        teacher_id=db_teacher.id,
    )
    db.add(db_user)

    # 5. Commit atómico (tudo ou nenhum)
    await db.commit()
    await db.refresh(db_user)

    return db_user


async def create_user(
    db: AsyncSession, 
    user: schemas.UserCreate, 
    organization_id: int | None = None,     # <--- Agora é opcional (pode ser None)
    role: UserRole | None = None,
    teacher_id: int | None = None
):
    """
    Cria um utilizador.
    - Se organization_id for None: Cria uma NOVA organização (cenário de Registo).
    - Se organization_id for passado: Adiciona o user à organização existente (cenário de Admin criar profs).
    """
    final_org_id = organization_id

    # 1. Se não temos organização, criamos uma (Lógica de /register)
    if final_org_id is None:
        db_org = models.Organization(name=f"Escola de {user.email}")
        db.add(db_org)
        await db.commit()
        await db.refresh(db_org)
        final_org_id = db_org.id

    # Definir role por defeito dependendo do contexto
    if role is None:
        role = UserRole.admin if organization_id is None else UserRole.teacher
    
    # 2. Criar Utilizador
    db_user = models.User(
        email=user.email,
        clerk_user_id=None,
        organization_id=final_org_id,
        role=role,
        teacher_id=teacher_id
    )
    
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)
    
    return db_user

# --- CRUD: Organization (Colégio) ---

async def create_organization(db: AsyncSession, org: schemas.OrganizationCreate) -> models.Organization:
    """Cria uma nova organização."""
    db_org = models.Organization(name=org.name)
    
    db.add(db_org)
    await db.commit()
    await db.refresh(db_org)
    return db_org