# Ficheiro: backend/app/core/security.py
from datetime import datetime, timedelta, timezone
from typing import Optional, Union, Any
import bcrypt
from jose import jwt, JWTError
from pydantic import ValidationError

from app.config import settings
from app import schemas

# ==========================================
# 1. CRIPTOGRAFIA DE PASSWORDS
# ==========================================

def hash_password(password: str) -> str:
    """Gera um hash bcrypt de uma password."""
    pwd_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(pwd_bytes, salt)
    return hashed_password.decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica se a password corresponde ao hash."""
    # Bcrypt precisa de bytes, não strings
    password_bytes = plain_password.encode('utf-8')
    hashed_password_bytes = hashed_password.encode('utf-8')
    return bcrypt.checkpw(password_bytes, hashed_password_bytes)

# ==========================================
# 2. GESTÃO DE TOKENS JWT
# ==========================================

def create_token(data: dict, expires_delta: timedelta) -> str:
    """Função genérica interna para criar tokens."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc)})
    
    encoded_jwt = jwt.encode(
        to_encode, 
        settings.SECRET_KEY, 
        algorithm=settings.ALGORITHM
    )
    return encoded_jwt

def create_access_token(data: dict, expires_delta: Union[timedelta, None] = None) -> str:
    """Cria um Access Token (curta duração)."""
    if expires_delta:
        expire_delta = expires_delta
    else:
        expire_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    # Se 'data' tiver apenas o email, o formato costuma ser {'sub': email}
    # O securityCore usava 'to_encode = data.copy()', o security.py usava argumento 'email'.
    # Vamos manter a flexibilidade recebendo 'data'.
    return create_token(data, expire_delta)

def create_refresh_token(email: str) -> str:
    """
    Função específica para criar o Refresh Token (de longa duração).
    """
    expires_delta = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    return create_token(data={"sub": email}, expires_delta=expires_delta)

def verify_token(token: str) -> schemas.TokenData | None:
    """
    Verifica a validade de um token (Pura lógica, sem BD).
    """
    try:
        payload = jwt.decode(
            token, 
            settings.SECRET_KEY, 
            algorithms=[settings.ALGORITHM]
        )
        email: str = payload.get("sub")
        if email is None:
            return None
        return schemas.TokenData(email=email)
    except (JWTError, ValidationError, AttributeError):
        return None