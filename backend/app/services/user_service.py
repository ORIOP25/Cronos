import bcrypt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List
from sqlalchemy import desc, delete
from app import models, schemas
from app.services.teacher_service import get_teachers_by_org
from app.models import UserRole

# --- Funções de Segurança (Hashing) ---

def hash_password(password: str) -> str:
    """Gera um hash bcrypt de uma password."""
    # Geramos um "salt" e fazemos o hash
    pwd_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(pwd_bytes, salt)
    return hashed_password.decode('utf-8') # Devolve como string

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica se a password em texto simples corresponde ao hash."""
    password_bytes = plain_password.encode('utf-8')
    hashed_password_bytes = hashed_password.encode('utf-8')
    # O bcrypt faz a verificação por nós
    return bcrypt.checkpw(password_bytes, hashed_password_bytes)

# --- CRUD: User (Utilizador) ---

async def get_user_by_email(db: AsyncSession, email: str) -> models.User | None:
    """Procura um utilizador pelo seu email."""
    # "select(models.User)" é o mesmo que "SELECT * FROM user"
    # ".where(...)" é o nosso "WHERE email = ..."
    query = select(models.User).where(models.User.email == email)
    
    # "await db.execute(...)" corre o comando
    result = await db.execute(query)
    
    # ".scalars().first()" dá-nos o primeiro resultado (ou None)
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