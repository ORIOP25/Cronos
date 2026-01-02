# Ficheiro: backend/app/api/deps.py
from typing import Generator, AsyncGenerator
from fastapi import Depends, HTTPException, status
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
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/token")

# --- DATABASE ---
async def get_db() -> AsyncGenerator:
    """Dependência para obter sessão de base de dados."""
    async with SessionLocal() as db:
        yield db

# --- AUTH (Proteção de Rotas) ---
async def get_current_user(
    token: str = Depends(oauth2_scheme), 
    db: AsyncSession = Depends(get_db)
) -> models.User:
    """
    Valida o token e retorna o utilizador atual da BD.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Não foi possível validar as credenciais",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # 1. Validar estrutura do token (usando a função pura do core)
    token_data = security.verify_token(token)
    
    if token_data is None:
        raise credentials_exception
    
    # 2. Buscar utilizador à BD (usando o user_service)
    user = await user_service.get_user_by_email(db, email=token_data.email)
    
    if user is None:
        raise credentials_exception
        
    return user