# Ficheiro: app/config.py

from typing import Literal
from urllib.parse import urlparse

from pydantic import PostgresDsn, RedisDsn, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _normalize_http_origin(value: str, field_name: str) -> str:
    candidate = value.strip().rstrip("/")
    parsed = urlparse(candidate)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.path not in {"", "/"}
        or parsed.params
        or parsed.query
        or parsed.fragment
        or "*" in candidate
        or parsed.username
        or parsed.password
    ):
        raise ValueError(f"{field_name} must contain exact absolute HTTP(S) origins.")
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


class Settings(BaseSettings):
    """
    Configurações globais da aplicação.
    Centraliza segredos, URLs e constantes do sistema.
    """

    # --- Constantes do Projeto ---
    PROJECT_NAME: str = "Cronos API"
    API_V1_STR: str = "/api/v1"
    APP_VERSION: str = "0.1.0"

    # --- Ambiente (Validação: Só aceita estas 3 strings) ---
    ENVIRONMENT: Literal["local", "staging", "production"] = "local"

    # --- Base de Dados (Validação: Tem de ser um URL Postgres real) ---
    DATABASE_URL: PostgresDsn
    MIGRATION_DATABASE_URL: PostgresDsn | None = None
    DATABASE_POOLING_ENABLED: bool = True

    # --- Configuração de Segurança ---
    # --- Clerk Authentication ---
    CLERK_SECRET_KEY: str = ""
    CLERK_WEBHOOK_SECRET: str = ""
    CLERK_WEBHOOK_MAX_ATTEMPTS: int = 5
    CLERK_WEBHOOK_RETRY_BASE_SECONDS: int = 60
    FRONTEND_URL: str = "http://localhost:5173"
    CLERK_AUTHORIZED_PARTIES: str = ""
    CLERK_INVITATION_REDIRECT_URL: str = ""

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
        # Production: fallback to FRONTEND_URL so CORS never breaks
        return [self.FRONTEND_URL] if self.FRONTEND_URL else []

    @computed_field(return_type=list[str])
    def CLERK_AUTHORIZED_PARTIES_LIST(self) -> list[str]:
        source = self.CLERK_AUTHORIZED_PARTIES or self.FRONTEND_URL
        return list(
            dict.fromkeys(
                _normalize_http_origin(value, "CLERK_AUTHORIZED_PARTIES")
                for value in source.split(",")
                if value.strip()
            )
        )

    # --- Infraestrutura (Redis & Celery) ---
    # Se não definires no .env, assume o default do Docker
    REDIS_URL: str | RedisDsn = "redis://redis:6379/0"
    RATELIMIT_ENABLED: bool = True

    # --- Solver (roadmap V2) ---
    # Fallback seguro: manter V1 por omissão até ativação explícita.

    # Permitimos que seja None para não obrigar a ter no .env
    CELERY_BROKER_URL: str | None = None

    # --- Lógica Inteligente: Validador ---
    # Este código corre DEPOIS de carregar o .env
    @model_validator(mode="after")
    def set_defaults(self):
        self.FRONTEND_URL = _normalize_http_origin(self.FRONTEND_URL, "FRONTEND_URL")
        if self.FRONTEND_URL not in self.CLERK_AUTHORIZED_PARTIES_LIST:
            raise ValueError("FRONTEND_URL must appear in CLERK_AUTHORIZED_PARTIES.")
        # Se o CELERY_BROKER_URL não estiver no .env, usamos o REDIS_URL
        if not self.CELERY_BROKER_URL:
            self.CELERY_BROKER_URL = str(self.REDIS_URL)
        if not self.CLERK_INVITATION_REDIRECT_URL:
            self.CLERK_INVITATION_REDIRECT_URL = f"{self.FRONTEND_URL.rstrip('/')}/login"
        redirect = urlparse(self.CLERK_INVITATION_REDIRECT_URL)
        if redirect.scheme not in {"http", "https"} or not redirect.netloc:
            raise ValueError("CLERK_INVITATION_REDIRECT_URL must be an absolute HTTP(S) URL.")
        if self.ENVIRONMENT == "production" and redirect.hostname in {"localhost", "127.0.0.1"}:
            raise ValueError(
                "CLERK_INVITATION_REDIRECT_URL cannot point to localhost in production."
            )
        # Guardrail de configuração para V2.
        return self

    # --- Monitorização (Opcional) ---
    # Pode ser None se estivermos em desenvolvimento local
    SENTRY_DSN: str | None = None
    SENTRY_TRACES_SAMPLE_RATE: float = 0.1

    # Configuração do Pydantic para ler do .env
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",  # Ignora variáveis extra no .env que não usamos
    )


settings = Settings()
