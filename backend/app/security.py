from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from pydantic import ValidationError

# Importamos os nossos schemas e as nossas configurações
from . import schemas
from .config import settings


def create_token(data: dict, expires_delta: timedelta) -> str:
    """
    Cria um novo token JWT (seja Access ou Refresh).
    """
    # 1. Copia os dados (payload) que queremos incluir no token
    to_encode = data.copy()
    
    # 2. Define o tempo de expiração
    # Usamos datetime.now(timezone.utc) para garantir que é 'timezone-aware'
    expire = datetime.now(timezone.utc) + expires_delta
    
    # 3. Adiciona os campos "padrão" do JWT
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc)})
    
    # 4. "Assina" o token
    # Esta é a operação de criptografia
    encoded_jwt = jwt.encode(
        to_encode, 
        settings.SECRET_KEY, 
        algorithm=settings.ALGORITHM
    )
    
    return encoded_jwt


def create_access_token(email: str) -> str:
    """
    Função específica para criar o Access Token (de curta duração).
    """
    # Define o tempo de expiração a partir das nossas settings
    expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    # "sub" (subject) é o nome padrão para a identidade do utilizador
    return create_token(data={"sub": email}, expires_delta=expires_delta)


def create_refresh_token(email: str) -> str:
    """
    Função específica para criar o Refresh Token (de longa duração).
    """
    expires_delta = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    return create_token(data={"sub": email}, expires_delta=expires_delta)


def verify_token(token: str) -> schemas.TokenData | None:
    """
    Verifica um token. Se for válido, devolve os dados (payload).
    Se for inválido (assinatura errada ou expirado), devolve None.
    """
    try:
        # 1. Tenta "decodificar" o token usando a nossa chave secreta
        payload = jwt.decode(
            token, 
            settings.SECRET_KEY, 
            algorithms=[settings.ALGORITHM]
        )
        
        # 2. Extrai o "subject" (o email) do payload
        email: str = payload.get("sub")
        if email is None:
            # O token é válido, mas não tem o campo 'sub' que esperamos
            return None
            
        # 3. Valida se o payload corresponde ao nosso schema
        token_data = schemas.TokenData(email=email)
        return token_data

    except (JWTError, ValidationError, AttributeError):
        # 4. Se o jwt.decode falhar (assinatura inválida, expirado, etc.)
        # ou se o payload não for válido, devolve None
        return None
    

# Ficheiro: app/security.py
# (Adiciona este código ao FIM do ficheiro)

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession


# Importamos os módulos necessários (alguns já devem estar importados)
from . import crud, database, models
from app.config import settings

# 1. Definimos o "esquema" de autenticação.
# Isto diz ao FastAPI: "Procura um token no 'Authorization: Bearer <token>' header"
# O tokenUrl é o *nosso* endpoint de login (para a documentação /docs)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="f{settings.API_V1_STR}/auth/token")


# 2. A nossa Dependência "Segurança"
async def get_current_user(
    token: str = Depends(oauth2_scheme), 
    db: AsyncSession = Depends(database.get_db)
) -> models.User:
    """
    Dependência que verifica o token e devolve o utilizador da BD.
    """
    
    # 1. Tenta verificar se o token é válido
    token_data = verify_token(token)
    
    if token_data is None:
        # Se o token for inválido (expirado, assinatura errada)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # 2. Se o token for válido, usa o email (do token) para ir buscar o user à BD
    user = await crud.get_user_by_email(db, email=token_data.email)
    
    if user is None:
        # Se o utilizador não existir na BD (ex: foi apagado)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Utilizador não encontrado",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # 3. Se tudo estiver OK, devolve o objeto User completo
    return user