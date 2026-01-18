#C:\Users\Hp\Desktop\AnoLetivo25_26\MeuProjeto\backend\app\services\user_service.py

import bcrypt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List
from sqlalchemy import desc, delete
from app import models, schemas
from app.services.teacher_service import get_teachers_by_org
from app.models import UserRole
from app.core.security import hash_password

# --- CRUD: User (Utilizador) ---

async def get_user_by_email(db: AsyncSession, email: str) -> models.User | None:
    query = select(models.User).where(models.User.email == email)
    result = await db.execute(query)
    
    return result.scalars().first()


async def create_user(
    db: AsyncSession, 
    user: schemas.UserCreate, 
    org_id: int | None = None,     # <--- Agora é opcional (pode ser None)
    role: UserRole = UserRole.admin, # <--- Por defeito, quem se regista é Admin
    teacher_id: int | None = None
):
    """
    Cria um utilizador.
    - Se org_id for None: Cria uma NOVA organização (cenário de Registo).
    - Se org_id for passado: Adiciona o user à organização existente (cenário de Admin criar profs).
    """
    hashed_pwd = hash_password(user.password)
    
    final_org_id = org_id

    # 1. Se não temos organização, criamos uma (Lógica de /register)
    if final_org_id is None:
        db_org = models.Organization(name=f"Escola de {user.email}")
        db.add(db_org)
        await db.commit()
        await db.refresh(db_org)
        final_org_id = db_org.id
    
    # 2. Criar Utilizador
    db_user = models.User(
        email=user.email,
        hashed_password=hashed_pwd,
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