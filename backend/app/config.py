# Ficheiro: app/config.py

from typing import Literal, Optional
from pydantic import PostgresDsn, RedisDsn, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_core import MultiHostUrl

class Settings(BaseSettings):
    """
    Configurações globais da aplicação.
    Centraliza segredos, URLs e constantes do sistema.
    """
    
    # --- Constantes do Projeto ---
    PROJECT_NAME: str = "Horário-Zen API"
    API_V1_STR: str = "/api/v1"

    # --- Ambiente (Validação: Só aceita estas 3 strings) ---
    ENVIRONMENT: Literal["local", "staging", "production"] = "local"

   # --- Base de Dados (Validação: Tem de ser um URL Postgres real) ---
    DATABASE_URL: PostgresDsn

    # --- Configuração de Segurança ---
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8

    # --- Infraestrutura (Redis & Celery) ---
    # Se não definires no .env, assume o default do Docker
    REDIS_URL: RedisDsn = "redis://redis:6379/0"

    # Permitimos que seja Optional para não obrigar a ter no .env
    CELERY_BROKER_URL: Optional[str] = None

    # --- Lógica Inteligente: Validador ---
    # Este código corre DEPOIS de carregar o .env
    @model_validator(mode='after')
    def set_defaults(self):
        # Se o CELERY_BROKER_URL não estiver no .env, usamos o REDIS_URL
        if not self.CELERY_BROKER_URL:
            self.CELERY_BROKER_URL = str(self.REDIS_URL)
        return self
    
    # --- Monitorização (Opcional) ---
    # Pode ser None se estivermos em desenvolvimento local
    SENTRY_DSN: Optional[str] = None

    # Configuração do Pydantic para ler do .env
    model_config = SettingsConfigDict(
        env_file=".env", 
        case_sensitive=True,
        extra="ignore" # Ignora variáveis extra no .env que não usamos
    )

settings = Settings()