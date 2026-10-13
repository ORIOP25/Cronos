from ipaddress import IPv4Network, IPv6Network, ip_network
from typing import Literal
from urllib.parse import urlparse

from pydantic import EmailStr, PostgresDsn, RedisDsn, SecretStr, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LOCAL_FRONTEND_ORIGIN = "http://localhost:5173"


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
    DEPLOYED_REVISION: str = ""
    RAILWAY_GIT_COMMIT_SHA: str = ""

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
    CLERK_ACCESS_TIMEOUT_SECONDS: int = 10
    FRONTEND_URL: str = LOCAL_FRONTEND_ORIGIN
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
            return [
                _normalize_http_origin(origin, "CORS_ORIGINS")
                for origin in self.CORS_ORIGINS.split(",")
                if origin.strip()
            ]
        if self.ENVIRONMENT == "local":
            return [
                LOCAL_FRONTEND_ORIGIN,
                "http://127.0.0.1:5173",
                "http://localhost:3000",
                "http://localhost",
            ]
        # Production: fallback to FRONTEND_URL so CORS never breaks
        return [self.FRONTEND_URL] if self.FRONTEND_URL else []

    @computed_field(return_type=list[str])
    def CLERK_AUTHORIZED_PARTIES_LIST(self) -> list[str]:
        source = self.CLERK_AUTHORIZED_PARTIES or self.FRONTEND_URL
        origins = [
            _normalize_http_origin(value, "CLERK_AUTHORIZED_PARTIES")
            for value in source.split(",")
            if value.strip()
        ]
        if self.ENVIRONMENT == "local" and urlparse(self.FRONTEND_URL).hostname in {
            "localhost",
            "127.0.0.1",
        }:
            origins.extend([LOCAL_FRONTEND_ORIGIN, "http://127.0.0.1:5173"])
        return list(dict.fromkeys(origins))

    # --- Infraestrutura (Redis & Celery) ---
    # Se não definires no .env, assume o default do Docker
    REDIS_URL: RedisDsn = "redis://redis:6379/0"
    RATELIMIT_ENABLED: bool = True

    RESEND_API_KEY: SecretStr | None = None
    CONTACT_EMAIL_FROM: EmailStr = "website@forms.cronos.pt"
    CONTACT_EMAIL_TO: EmailStr = "contacto@cronos.pt"
    CONTACT_EMAIL_TIMEOUT_SECONDS: int = 10
    TURNSTILE_SECRET_KEY: SecretStr | None = None
    TURNSTILE_ALLOWED_HOSTNAMES: str = "cronos.pt,www.cronos.pt"
    TURNSTILE_TIMEOUT_SECONDS: int = 5
    TRUSTED_PROXY_IPS: str = ""

    @computed_field(return_type=list[str])
    def TURNSTILE_ALLOWED_HOSTNAMES_LIST(self) -> list[str]:
        return list(
            dict.fromkeys(
                hostname.strip().lower()
                for hostname in self.TURNSTILE_ALLOWED_HOSTNAMES.split(",")
                if hostname.strip()
            )
        )

    @computed_field(return_type=list[IPv4Network | IPv6Network])
    def TRUSTED_PROXY_NETWORKS(self) -> list[IPv4Network | IPv6Network]:
        return [
            ip_network(value.strip(), strict=False)
            for value in self.TRUSTED_PROXY_IPS.split(",")
            if value.strip()
        ]

    # --- Solver (roadmap V2) ---
    # Fallback seguro: manter V1 por omissão até ativação explícita.

    # Permitimos que seja None para não obrigar a ter no .env
    CELERY_BROKER_URL: RedisDsn | None = None

    # --- Scheduler v1: limites de laboratório explícitos (W11 calibra) ---
    SCHEDULER_V1_JOB_TIMEOUT_SECONDS: int = 900
    SCHEDULER_V1_HEARTBEAT_SECONDS: float = 5.0
    SCHEDULER_V1_ABANDONED_SECONDS: int = 120
    SCHEDULER_V1_NUM_WORKERS: int = 1
    # Return the first validated complete schedule; quality search is opt-in.
    SCHEDULER_V1_STOP_AT_FIRST_COMPLETE: bool = True

    # --- Lógica Inteligente: Validador ---
    # Este código corre DEPOIS de carregar o .env
    @model_validator(mode="after")
    def set_defaults(self):
        self._validate_numeric_limits()
        self._validate_shared_settings()
        if self.ENVIRONMENT == "production":
            self._validate_production_settings()
        self._set_celery_default()
        self._set_and_validate_invitation_redirect()
        return self

    def _validate_numeric_limits(self) -> None:
        if not 0 <= self.CLERK_CLOCK_SKEW_MS <= 60_000:
            raise ValueError("CLERK_CLOCK_SKEW_MS must be between 0 and 60000.")
        if not 1 <= self.CLERK_ACCESS_TIMEOUT_SECONDS <= 30:
            raise ValueError("CLERK_ACCESS_TIMEOUT_SECONDS must be between 1 and 30.")
        if not 1 <= self.CONTACT_EMAIL_TIMEOUT_SECONDS <= 30:
            raise ValueError("CONTACT_EMAIL_TIMEOUT_SECONDS must be between 1 and 30.")
        if not 1 <= self.TURNSTILE_TIMEOUT_SECONDS <= 30:
            raise ValueError("TURNSTILE_TIMEOUT_SECONDS must be between 1 and 30.")
        if not 1 <= self.SCHEDULER_V1_JOB_TIMEOUT_SECONDS <= 86_400:
            raise ValueError("SCHEDULER_V1_JOB_TIMEOUT_SECONDS must be between 1 and 86400.")
        if not 0.5 <= self.SCHEDULER_V1_HEARTBEAT_SECONDS <= 60:
            raise ValueError("SCHEDULER_V1_HEARTBEAT_SECONDS must be between 0.5 and 60.")
        if not 1 <= self.SCHEDULER_V1_ABANDONED_SECONDS <= 86_400:
            raise ValueError("SCHEDULER_V1_ABANDONED_SECONDS must be between 1 and 86400.")
        if not 1 <= self.SCHEDULER_V1_NUM_WORKERS <= 64:
            raise ValueError("SCHEDULER_V1_NUM_WORKERS must be between 1 and 64.")

    def _validate_shared_settings(self) -> None:
        if not self.TURNSTILE_ALLOWED_HOSTNAMES_LIST:
            raise ValueError("TURNSTILE_ALLOWED_HOSTNAMES cannot be empty.")
        # Evaluate proxy networks during startup so malformed entries fail fast.
        _ = self.TRUSTED_PROXY_NETWORKS
        self.FRONTEND_URL = _normalize_http_origin(self.FRONTEND_URL, "FRONTEND_URL")
        if self.FRONTEND_URL not in self.CLERK_AUTHORIZED_PARTIES_LIST:
            raise ValueError("FRONTEND_URL must appear in CLERK_AUTHORIZED_PARTIES.")

    def _validate_production_settings(self) -> None:
        if not self.TRUSTED_PROXY_NETWORKS:
            raise ValueError("TRUSTED_PROXY_IPS is required in production.")
        if any(network.prefixlen == 0 for network in self.TRUSTED_PROXY_NETWORKS):
            raise ValueError("TRUSTED_PROXY_IPS cannot trust the entire address space.")
        if not self.CORS_ORIGINS_LIST:
            raise ValueError("CORS_ORIGINS is required in production.")
        origins = [
            self.FRONTEND_URL,
            *self.CORS_ORIGINS_LIST,
            *self.CLERK_AUTHORIZED_PARTIES_LIST,
        ]
        if any(
            urlparse(origin).scheme != "https"
            or urlparse(origin).hostname in {"localhost", "127.0.0.1", "::1"}
            for origin in origins
        ):
            raise ValueError("Production browser origins must use HTTPS and cannot be localhost.")
        if not self.CLERK_SECRET_KEY or not self.CLERK_WEBHOOK_SECRET:
            raise ValueError("Clerk secrets are required in production.")
        if self.RESEND_API_KEY is None:
            raise ValueError("RESEND_API_KEY is required in production.")
        if self.TURNSTILE_SECRET_KEY is None:
            raise ValueError("TURNSTILE_SECRET_KEY is required in production.")
        if self.FRONTEND_URL not in self.CORS_ORIGINS_LIST:
            raise ValueError("FRONTEND_URL must appear in CORS_ORIGINS.")

    def _set_celery_default(self) -> None:
        if not self.CELERY_BROKER_URL:
            if self.ENVIRONMENT == "production":
                raise ValueError("CELERY_BROKER_URL is required in production.")
            self.CELERY_BROKER_URL = self.REDIS_URL

    def _set_and_validate_invitation_redirect(self) -> None:
        if not self.CLERK_INVITATION_REDIRECT_URL:
            self.CLERK_INVITATION_REDIRECT_URL = f"{self.FRONTEND_URL.rstrip('/')}/login"
        redirect = urlparse(self.CLERK_INVITATION_REDIRECT_URL)
        if redirect.scheme not in {"http", "https"} or not redirect.netloc:
            raise ValueError("CLERK_INVITATION_REDIRECT_URL must be an absolute HTTP(S) URL.")
        if self.ENVIRONMENT == "production" and redirect.hostname in {"localhost", "127.0.0.1"}:
            raise ValueError(
                "CLERK_INVITATION_REDIRECT_URL cannot point to localhost in production."
            )

    # Configuração do Pydantic para ler do .env
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",  # Ignora variáveis extra no .env que não usamos
    )


settings = Settings()
