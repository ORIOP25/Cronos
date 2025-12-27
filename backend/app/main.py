# Ficheiro: app/main.py

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
    logger.info("🚀 Servidor a arrancar...", version="0.5", env=settings.ENVIRONMENT)
    
    try:
        redis = aioredis.from_url(str(settings.REDIS_URL))
        FastAPICache.init(RedisBackend(redis), prefix="fastapi-cache")
        logger.info("✅ Sistema de Cache: LIGADO", url=str(settings.REDIS_URL))
    except Exception as e:
        logger.error("❌ Falha no Redis", error=str(e)) # Log de erro estruturado

    logger.info("✅ Rate Limit: LIGADO")
    
    yield
    
    logger.info("💤 Servidor a desligar...")

# ==========================================
# INICIALIZAÇÃO DA APP
# ==========================================

if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.ENVIRONMENT, # 'local' ou 'production'
        
        # --- Performance & Profiling ---
        # Em produção real, baixa isto para 0.1 (10%) ou 0.2 para poupar quota.
        # Para testes agora, deixa a 1.0 (100%).
        traces_sample_rate=1.0, 
        _experiments={
            "profiles_sample_rate": 1.0, # Profiling (ver que funções demoram mais)
        },
        
        # Dados extra
        send_default_pii=True, # Envia info do user (IP, headers) - cuidado com GDPR em prod
    )
    logger.info("✅ Sentry: LIGADO")
else:
    logger.warning("⚠️ Sentry: DESLIGADO (DSN não configurado)")

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="API Escolar Profissional com Rate Limiting, Caching e Docker.",
    version="1.0.0",
    lifespan=lifespan
)

# --- Configuração do Rate Limiter ---
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# --- Configuração de CORS ---
# Nota: Em produção, deves restringir isto aos domínios reais
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite Local
        "http://localhost:3000",  # Alternativa Local
        "http://localhost",       # Nginx Docker
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
        "system": "Horário-Zen",
        "docs": "/docs"
    }