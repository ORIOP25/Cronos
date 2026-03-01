# Ficheiro: backend/app/api/deps.py
from typing import Generator, AsyncGenerator, Annotated
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

# Imports do Projeto
from app.db.database import SessionLocal
from app.config import settings
from app.core import security # As ferramentas que criámos acima
from app import models, schemas
# Importamos o serviço AQUI. O deps conhece o serviço, mas o serviço não conhece o deps.
from app.services import user_service 

# Define onde o FastAPI vai buscar o token (Url do login)
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/auth/token",
    auto_error=False
)

# --- DATABASE ---
async def get_db() -> AsyncGenerator:
    """Dependência para obter sessão de base de dados."""
    async with SessionLocal() as db:
        yield db

# --- AUTH (Proteção de Rotas) ---
async def get_current_user(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    token: str | None = Depends(oauth2_scheme),
) -> models.User:
    """
    Valida o token e retorna o utilizador atual da BD.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Não foi possível validar as credenciais",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # 1. Buscar token do header Authorization ou do cookie (httpOnly)
    if not token:
        token = request.cookies.get(settings.ACCESS_TOKEN_COOKIE_NAME)

    if not token:
        raise credentials_exception

    # 2. Validar estrutura do token (usando a função pura do core)
    token_data = security.verify_token(token)
    
    if token_data is None:
        raise credentials_exception
    
    # 3. Buscar utilizador à BD (usando o user_service)
    user = await user_service.get_user_by_email(db, email=token_data.email)
    
    if user is None:
        raise credentials_exception
        
    return user

# 3. Dependency: Verificar se está Ativo (Segurança Extra)
def get_current_active_user(
    current_user: Annotated[models.User, Depends(get_current_user)],
) -> models.User:
    """
    Garante que o utilizador não foi desativado/bloqueado.
    """
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Utilizador inativo")
    return current_user

# 4. Dependency: Autorização de Admin (Apenas Diretores/Admins)
def get_current_active_admin(
    current_user: Annotated[models.User, Depends(get_current_active_user)],
) -> models.User:
    """
    Garante que o utilizador tem permissões de administração.
    """
    # Verifica se é superuser OU se tem role de 'admin'/'director'
    # Ajusta a string "admin" conforme o que tens na tua base de dados na coluna 'role'
    is_admin = current_user.is_superuser or (hasattr(current_user, 'role') and current_user.role in ['admin', 'director'])
    
    if not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="O utilizador não tem privilégios suficientes"
        )
    return current_user