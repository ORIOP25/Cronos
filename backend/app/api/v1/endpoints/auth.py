from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app import schemas, models
from app.api import deps
from app.services import user_service
from app.core import security
from app.core.ratelimit import limiter
from app.config import settings
from typing import Annotated

router = APIRouter()


async def _get_org_name(db: AsyncSession, organization_id: int | None) -> str:
    """Obtém o nome da organização para incluir na resposta Token."""
    if organization_id is None:
        return ""
    org = await db.scalar(select(models.Organization).where(models.Organization.id == organization_id))
    return org.name if org else ""

@router.post("/token", response_model=schemas.Token)
@limiter.limit("5/minute")
async def login_for_access_token(
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
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

    # 6. Retornar Token + ID e Nome da Organização (compatibilidade frontend)
    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "organization_id": user.organization_id,
        "organization_name": await _get_org_name(db, user.organization_id),
        "user_email": user.email,
        "role": user.role,
        "teacher_id": user.teacher_id
    }

@router.post("/register", response_model=schemas.Token, responses={400: {"description": "Email already registered"}})
@limiter.limit("3/minute")
async def register(
    request: Request,
    response: Response,
    payload: schemas.RegisterRequest,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
):
    """
    Regista uma nova conta (Organização + Admin) e devolve token para auto-login.
    Transação atómica: se algo falhar, tudo é revertido.
    """
    try:
        user = await user_service.register_account(db, payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    # Auto-login: gerar tokens e definir cookies
    access_token = security.create_access_token(data={"sub": user.email})
    refresh_tok = security.create_refresh_token(user.email)

    response.set_cookie(
        key=settings.ACCESS_TOKEN_COOKIE_NAME,
        value=access_token,
        httponly=True,
        secure=settings.ACCESS_TOKEN_COOKIE_SECURE,
        samesite=settings.ACCESS_TOKEN_COOKIE_SAMESITE,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )
    response.set_cookie(
        key=settings.REFRESH_TOKEN_COOKIE_NAME,
        value=refresh_tok,
        httponly=True,
        secure=settings.REFRESH_TOKEN_COOKIE_SECURE,
        samesite=settings.REFRESH_TOKEN_COOKIE_SAMESITE,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        path="/",
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "organization_id": user.organization_id,
        "organization_name": await _get_org_name(db, user.organization_id),
        "user_email": user.email,
        "role": user.role,
        "teacher_id": user.teacher_id,
    }


@router.post("/refresh", response_model=schemas.Token)
@limiter.limit("10/minute")
async def refresh_token(
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(deps.get_db)]
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
        "organization_name": await _get_org_name(db, user.organization_id),
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