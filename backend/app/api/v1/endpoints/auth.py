from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from app import schemas
from app.api import deps
from app.services import user_service
from app.core import security
from app.core.ratelimit import limiter

router = APIRouter()

@router.post("/token", response_model=schemas.Token)
@limiter.limit("5/minute")
async def login_for_access_token(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(), 
    db: AsyncSession = Depends(deps.get_db)
):
    # 1. Verificar User e Password
    user = await user_service.get_user_by_email(db, form_data.username)
    if not user or not security.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou password incorretos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # 2. Gerar Token
    access_token = security.create_access_token(data={"sub": user.email})
    
    # 3. Retornar Token + ID da Organização (útil para o frontend)
    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "organization_id": user.organization_id,
        "user_email": user.email,
        "role": user.role,
        "teacher_id": user.teacher_id
    }

@router.post("/register", response_model=schemas.UserRead)
async def register(
    user: schemas.UserCreate, 
    db: AsyncSession = Depends(deps.get_db)
):
    # Verificar se email já existe
    db_user = await user_service.get_user_by_email(db, email=user.email)
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    return await user_service.create_user(db, user)