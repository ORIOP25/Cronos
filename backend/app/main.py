# Ficheiro: app/main.py

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.middleware import SlowAPIMiddleware

# --- Imports de Performance e Segurança ---
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend
from redis import asyncio as aioredis
import structlog
import sentry_sdk

# --- Imports da Aplicação ---
from app.config import settings
from app.core.ratelimit import limiter
from app.core.exceptions import DomainError
from app.api.api import api_router
from app.core.logging import setup_logging

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
    
    try:
        redis = aioredis.from_url(str(settings.REDIS_URL))
        FastAPICache.init(RedisBackend(redis), prefix="fastapi-cache")
        logger.info("[OK] Sistema de Cache: LIGADO", url=str(settings.REDIS_URL))
    except Exception as e:
        logger.error("[ERROR] Falha no Redis", error=str(e)) # Log de erro estruturado

    logger.info("[OK] Rate Limit: LIGADO")
    
    yield
    
    logger.info("ZZZ Servidor a desligar...")

# ==========================================
# INICIALIZAÇÃO DA APP
# ==========================================

if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.ENVIRONMENT, # 'local' ou 'production'
        
        # --- Performance & Profiling ---
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        _experiments={
            "profiles_sample_rate": settings.SENTRY_TRACES_SAMPLE_RATE,
        },
        
        # Dados extra
        send_default_pii=settings.ENVIRONMENT != "production", # Evita PII em produção
    )
    logger.info("[OK] Sentry: LIGADO")
else:
    logger.warning("[WARN] Sentry: DESLIGADO (DSN não configurado)")

import traceback

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="API Escolar Profissional com Rate Limiting, Caching e Docker.",
    version="1.0.0",
    lifespan=lifespan
)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    try:
        with open("C:/Users/Hp/Desktop/AnoLetivo25_26/MeuProjeto/backend/500_traceback.log", "a", encoding="utf-8") as f:
            f.write(f"Exception on {request.url.path}:\n")
            f.write(traceback.format_exc())
            f.write("\n" + "="*50 + "\n")
    except Exception:
        pass
    return JSONResponse(status_code=500, content={"detail": str(exc)})

# --- Configuração do Rate Limiter ---
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# --- Configuração de CORS ---
# Nota: Em produção, deves restringir isto aos domínios reais
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS_LIST,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Domain Error Handler ---
@app.exception_handler(DomainError)
async def domain_error_handler(request: Request, exc: DomainError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message},
    )

# --- Security Headers ---
_HEALTH_PATHS = {"/health", "/api/v1/health"}

@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    if request.url.path.rstrip("/") in _HEALTH_PATHS:
        return response
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

    if settings.ENVIRONMENT == "local":
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://*.clerk.accounts.dev https://challenges.cloudflare.com; "
            "worker-src 'self' blob:; "
            "connect-src 'self' https://*.clerk.accounts.dev https://challenges.cloudflare.com; "
            "img-src 'self' https://img.clerk.com data:; "
            "style-src 'self' 'unsafe-inline' https://*.clerk.accounts.dev; "
            "frame-src 'self' https://*.clerk.accounts.dev https://challenges.cloudflare.com; "
            "frame-ancestors 'self'"
        )
    else:
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' https://clerk.cronos.pt; "
            "worker-src 'self' blob:; "
            "connect-src 'self' https://clerk.cronos.pt; "
            "img-src 'self' https://img.clerk.com data:; "
            "style-src 'self' 'unsafe-inline' https://clerk.cronos.pt; "
            "frame-src 'self' https://clerk.cronos.pt; "
            "frame-ancestors 'self'; "
            "upgrade-insecure-requests"
        )

    if settings.ENVIRONMENT == "production":
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
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
        "version": "1.0.0", 
        "system": "Cronos",
        "docs": "/docs"
    }