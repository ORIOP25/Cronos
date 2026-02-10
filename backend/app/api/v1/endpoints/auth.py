from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from app import schemas
from app.api import deps
from app.services import user_service
from app.core import security
from app.core.ratelimit import limiter
from app.config import settings

router = APIRouter()

@router.post("/token", response_model=schemas.Token)
@limiter.limit("5/minute")
async def login_for_access_token(
    request: Request,
    response: Response,
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
    
    # 2. Validar que a conta está ativa (NOVO)
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="A sua conta está inativa. Contacte o administrador para mais informações.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # 3. Gerar Token
    access_token = security.create_access_token(data={"sub": user.email})
    
    # 4. Guardar access token em cookie httpOnly (mitiga XSS)
    response.set_cookie(
        key=settings.ACCESS_TOKEN_COOKIE_NAME,
        value=access_token,
        httponly=True,
        secure=settings.ACCESS_TOKEN_COOKIE_SECURE,
        samesite=settings.ACCESS_TOKEN_COOKIE_SAMESITE,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/"
    )

    # 5. Guardar refresh token em cookie httpOnly
    refresh_token = security.create_refresh_token(user.email)
    response.set_cookie(
        key=settings.REFRESH_TOKEN_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        secure=settings.REFRESH_TOKEN_COOKIE_SECURE,
        samesite=settings.REFRESH_TOKEN_COOKIE_SAMESITE,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        path="/"
    )

    # 6. Retornar Token + ID da Organização (compatibilidade frontend)
    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "organization_id": user.organization_id,
        "user_email": user.email,
        "role": user.role,
        "teacher_id": user.teacher_id
    }

@router.post("/register", response_model=schemas.UserRead)
@limiter.limit("3/minute")
async def register(
    request: Request,
    user: schemas.UserCreate, 
    db: AsyncSession = Depends(deps.get_db)
):
    # Verificar se email já existe
    db_user = await user_service.get_user_by_email(db, email=user.email)
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    return await user_service.create_user(db, user)


@router.post("/refresh", response_model=schemas.Token)
@limiter.limit("10/minute")
async def refresh_token(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(deps.get_db)
):
    """Renova o access token usando o refresh token em cookie."""
    refresh_token = request.cookies.get(settings.REFRESH_TOKEN_COOKIE_NAME)
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token em falta")

    token_data = security.verify_token(refresh_token)
    if token_data is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token inválido")

    user = await user_service.get_user_by_email(db, token_data.email)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Utilizador inválido")

    access_token = security.create_access_token(data={"sub": user.email})
    response.set_cookie(
        key=settings.ACCESS_TOKEN_COOKIE_NAME,
        value=access_token,
        httponly=True,
        secure=settings.ACCESS_TOKEN_COOKIE_SECURE,
        samesite=settings.ACCESS_TOKEN_COOKIE_SAMESITE,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/"
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "organization_id": user.organization_id,
        "user_email": user.email,
        "role": user.role,
        "teacher_id": user.teacher_id
    }


@router.post("/logout")
async def logout(response: Response):
    """Limpa cookies de autenticacao."""
    response.delete_cookie(key=settings.ACCESS_TOKEN_COOKIE_NAME, path="/")
    response.delete_cookie(key=settings.REFRESH_TOKEN_COOKIE_NAME, path="/")
    return {"message": "logout_ok"}