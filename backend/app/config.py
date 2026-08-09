# Ficheiro: app/config.py

from typing import Literal
from urllib.parse import urlparse

from pydantic import EmailStr, PostgresDsn, RedisDsn, SecretStr, computed_field, model_validator
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
    # Clerk emits short-lived JWTs. Permit a small, bounded difference between
    # the Clerk and application-server clocks when checking nbf/iat.
    CLERK_CLOCK_SKEW_MS: int = 60_000

    # --- CORS ---
    # Lista separada por virgulas (ex: "https://app.exemplo.com,https://admin.exemplo.com")
    CORS_ORIGINS: str = ""

    @computed_field(return_type=list[str])
    def CORS_ORIGINS_LIST(self) -> list[str]:
        if self.CORS_ORIGINS:
            return [_normalize_http_origin(origin, "CORS_ORIGINS") for origin in self.CORS_ORIGINS.split(",") if origin.strip()]
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
    REDIS_URL: RedisDsn = "redis://redis:6379/0"
    RATELIMIT_ENABLED: bool = True

    CONTACT_SMTP_HOST: str = "smtp.hostinger.com"
    CONTACT_SMTP_PORT: int = 465
    CONTACT_SMTP_USERNAME: EmailStr = "contacto@cronos.pt"
    CONTACT_SMTP_PASSWORD: SecretStr | None = None
    CONTACT_EMAIL_TO: EmailStr = "contacto@cronos.pt"
    CONTACT_SMTP_TIMEOUT_SECONDS: int = 10

    # --- Solver (roadmap V2) ---
    # Fallback seguro: manter V1 por omissão até ativação explícita.

    # Permitimos que seja None para não obrigar a ter no .env
    CELERY_BROKER_URL: RedisDsn | None = None

    # --- Lógica Inteligente: Validador ---
    # Este código corre DEPOIS de carregar o .env
    @model_validator(mode="after")
    def set_defaults(self):
        if not 0 <= self.CLERK_CLOCK_SKEW_MS <= 60_000:
            raise ValueError("CLERK_CLOCK_SKEW_MS must be between 0 and 60000.")
        if not 1 <= self.CONTACT_SMTP_PORT <= 65_535:
            raise ValueError("CONTACT_SMTP_PORT must be between 1 and 65535.")
        if not 1 <= self.CONTACT_SMTP_TIMEOUT_SECONDS <= 30:
            raise ValueError("CONTACT_SMTP_TIMEOUT_SECONDS must be between 1 and 30.")
        if self.ENVIRONMENT == "production" and self.CONTACT_SMTP_PASSWORD is None:
            raise ValueError("CONTACT_SMTP_PASSWORD is required in production.")
        self.FRONTEND_URL = _normalize_http_origin(self.FRONTEND_URL, "FRONTEND_URL")
        if self.ENVIRONMENT == "production":
            if not self.CORS_ORIGINS_LIST:
                raise ValueError("CORS_ORIGINS is required in production.")
            origins = [self.FRONTEND_URL, *self.CORS_ORIGINS_LIST, *self.CLERK_AUTHORIZED_PARTIES_LIST]
            if any(urlparse(origin).scheme != "https" or urlparse(origin).hostname in {"localhost", "127.0.0.1", "::1"} for origin in origins):
                raise ValueError("Production browser origins must use HTTPS and cannot be localhost.")
            if not self.CLERK_SECRET_KEY or not self.CLERK_WEBHOOK_SECRET:
                raise ValueError("Clerk secrets are required in production.")
            if self.FRONTEND_URL not in self.CORS_ORIGINS_LIST:
                raise ValueError("FRONTEND_URL must appear in CORS_ORIGINS.")
        if self.FRONTEND_URL not in self.CLERK_AUTHORIZED_PARTIES_LIST:
            raise ValueError("FRONTEND_URL must appear in CLERK_AUTHORIZED_PARTIES.")
        if not self.CELERY_BROKER_URL:
            if self.ENVIRONMENT == "production":
                raise ValueError("CELERY_BROKER_URL is required in production.")
            self.CELERY_BROKER_URL = self.REDIS_URL
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
