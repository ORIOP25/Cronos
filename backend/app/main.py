# Ficheiro: app/main.py

from contextlib import asynccontextmanager

import sentry_sdk
import structlog
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis import asyncio as aioredis

# --- Imports de Performance e Segurança ---
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.api import api_router

# --- Imports da Aplicação ---
from app.config import settings
from app.core.clerk import ClerkGateway
from app.core.exceptions import AppError, DomainError
from app.core.logging import setup_logging
from app.core.ratelimit import limiter
from app.db.database import SessionLocal, engine_async

# ==========================================
# CICLO DE VIDA (LIFESPAN)
# ==========================================

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Configurar Logs (PRIMEIRA COISA A FAZER)
    setup_logging()

    # Substituir print por logger.info
    logger.info("-> Servidor a arrancar...", version="0.5", env=settings.ENVIRONMENT)

    redis = aioredis.from_url(str(settings.REDIS_URL), socket_connect_timeout=1)
    app.state.redis = redis
    async with ClerkGateway() as clerk:
        app.state.clerk = clerk
        try:
            try:
                await redis.ping()
                logger.info("redis_ready")
            except Exception as exc:
                logger.warning("redis_not_ready", error_type=type(exc).__name__)
            logger.info("rate_limit_configured", enabled=settings.RATELIMIT_ENABLED)
            yield
        finally:
            await redis.aclose()
            await engine_async.dispose()
            logger.info("ZZZ Servidor a desligar...")


# ==========================================
# INICIALIZAÇÃO DA APP
# ==========================================

if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.ENVIRONMENT,  # 'local' ou 'production'
        # --- Performance & Profiling ---
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        # Dados extra
        send_default_pii=False,  # Evita PII em produção
    )
    logger.info("[OK] Sentry: LIGADO")
else:
    logger.warning("[WARN] Sentry: DESLIGADO (DSN não configurado)")

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="API Escolar Profissional com rate limiting e Docker.",
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url=None if settings.ENVIRONMENT == "production" else "/docs",
    redoc_url=None if settings.ENVIRONMENT == "production" else "/redoc",
    openapi_url=None if settings.ENVIRONMENT == "production" else "/openapi.json",
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(
        "Unhandled application error",
        method=request.method,
        path=request.url.path,
        error_type=type(exc).__name__,
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Ocorreu um erro inesperado. Tente novamente."},
    )


# --- Configuração do Rate Limiter ---
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# --- Configuração de CORS ---
# Nota: Em produção, deves restringir isto aos domínios reais
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS_LIST,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


# --- Domain Error Handler ---
@app.exception_handler(DomainError)
async def domain_error_handler(request: Request, exc: DomainError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message},
    )


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    status_code = {"preflight_failed": 400}.get(exc.code) or {
        "validation": 422,
        "not_found": 404,
        "conflict": 409,
        "forbidden": 403,
        "unavailable": 503,
    }[exc.kind]
    detail = exc.metadata or {"code": exc.code, "message": exc.detail}
    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder({"detail": detail}),
    )


# --- Security Headers ---
@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


# ==========================================
# ROTAS (ROUTERS)
# ==========================================

# 1. Incluir todas as rotas da API v1 (Centralização)
app.include_router(api_router, prefix=settings.API_V1_STR)


# 2. Rota Raiz (Boas vindas simples)
# Mantemos esta rota fora do /api/v1 apenas para testes rápidos de conectividade
@app.get("/", tags=["Root"])
def root():
    return {
        "status": "online",
        "version": settings.APP_VERSION,
        "system": "Cronos",
    }


@app.get("/health/live", include_in_schema=False)
@limiter.exempt
async def live():
    return {"status": "ok"}


@app.get("/health/ready", include_in_schema=False)
@limiter.exempt
async def ready(request: Request):
    from app.api.v1.endpoints.health import readiness

    async with SessionLocal() as db:
        return await readiness(request, db)
