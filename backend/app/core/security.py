# Ficheiro: app/core/security.py
from datetime import datetime, timedelta, timezone
from typing import Union
from jose import jwt

# CONFIGURAÇÕES (Idealmente viriam de variáveis de ambiente, mas para MVP ficam aqui)
SECRET_KEY = "segredo_super_secreto_mudar_em_producao"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 horas

def create_access_token(data: dict, expires_delta: Union[timedelta, None] = None):
    """Gera um token JWT com validade definida."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt