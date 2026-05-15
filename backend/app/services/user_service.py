from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app import models, schemas
from app.models import UserRole

# --- CRUD: User (Utilizador) ---

EMAIL_ALREADY_EXISTS_MSG = "Este email já está registado"


async def get_user_by_email(db: AsyncSession, email: str) -> models.User | None:
    query = select(models.User).where(models.User.email == email)
    result = await db.execute(query)

    return result.scalars().first()


async def create_user(
    db: AsyncSession,
    user: schemas.UserCreate,
    organization_id: int,
    role: UserRole | None = None,
    teacher_id: int | None = None
):
    if role is None:
        role = UserRole.teacher

    db_user = models.User(
        email=user.email,
        clerk_user_id=user.clerk_user_id,
        name=user.name,
        organization_id=organization_id,
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