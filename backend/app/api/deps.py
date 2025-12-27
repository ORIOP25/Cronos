# Ficheiro: app/api/deps.py
from typing import AsyncGenerator
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import SessionLocal
from app.services import user_service
from app.core import security  # Importamos o ficheiro que acabaste de criar

# Configura onde a API vai buscar o token (no url /token)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/token")

# --- DATABASE ---
async def get_db() -> AsyncGenerator:
    async with SessionLocal() as session:
        yield session

# --- AUTH (Proteção de Rotas) ---
async def get_current_user(
    token: str = Depends(oauth2_scheme), 
    db: AsyncSession = Depends(get_db)
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Não foi possível validar as credenciais",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        # Descodificar o Token usando a chave do security.py
        payload = jwt.decode(token, security.SECRET_KEY, algorithms=[security.ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    # Buscar user à BD
    user = await user_service.get_user_by_email(db, email=email)
    if user is None:
        raise credentials_exception
    return user