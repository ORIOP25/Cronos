# Ficheiro: app/config.py

from typing import Literal
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
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # --- Cookies (Auth) ---
    ACCESS_TOKEN_COOKIE_NAME: str = "hz_access"
    ACCESS_TOKEN_COOKIE_SECURE: bool = False
    ACCESS_TOKEN_COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "lax"
    REFRESH_TOKEN_COOKIE_NAME: str = "hz_refresh"
    REFRESH_TOKEN_COOKIE_SECURE: bool = False
    REFRESH_TOKEN_COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "lax"

    # --- CORS ---
    # Lista separada por virgulas (ex: "https://app.exemplo.com,https://admin.exemplo.com")
    CORS_ORIGINS: str = ""

    @computed_field(return_type=list[str])
    def CORS_ORIGINS_LIST(self) -> list[str]:
        if self.CORS_ORIGINS:
            return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]
        if self.ENVIRONMENT == "local":
            return [
                "http://localhost:5173",
                "http://localhost:3000",
                "http://localhost",
            ]
        return []

    # --- Infraestrutura (Redis & Celery) ---
    # Se não definires no .env, assume o default do Docker
    REDIS_URL: str | RedisDsn = "redis://redis:6379/0"

    # --- Solver (roadmap V2) ---
    # Fallback seguro: manter V1 por omissão até ativação explícita.
    SOLVER_ENGINE_VERSION: Literal["v1", "v2"] = "v1"
    SOLVER_V2_ROLLING_WEEKS: int = 8
    SOLVER_V2_OBJECTIVE_MODE: Literal["lexicographic"] = "lexicographic"

    # Permitimos que seja None para não obrigar a ter no .env
    CELERY_BROKER_URL: str | None = None

    # --- Lógica Inteligente: Validador ---
    # Este código corre DEPOIS de carregar o .env
    @model_validator(mode='after')
    def set_defaults(self):
        # Se o CELERY_BROKER_URL não estiver no .env, usamos o REDIS_URL
        if not self.CELERY_BROKER_URL:
            self.CELERY_BROKER_URL = str(self.REDIS_URL)
        # Guardrail de configuração para V2.
        if self.SOLVER_V2_ROLLING_WEEKS < 1:
            self.SOLVER_V2_ROLLING_WEEKS = 8
        return self
    
    # --- Monitorização (Opcional) ---
    # Pode ser None se estivermos em desenvolvimento local
    SENTRY_DSN: str | None = None
    SENTRY_TRACES_SAMPLE_RATE: float = 1.0

    # Configuração do Pydantic para ler do .env
    model_config = SettingsConfigDict(
        env_file=".env", 
        case_sensitive=True,
        extra="ignore" # Ignora variáveis extra no .env que não usamos
    )

settings = Settings()