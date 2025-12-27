# Ficheiro: app/db/database.py

# --- Imports Async (Para a API) ---
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

# --- Imports Sync (Para o Celery) ---
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

# --- Importar Configurações Centralizadas ---
from app.config import settings

# ==========================================
# 1. PREPARAÇÃO DOS URLS
# ==========================================
# Objetivo: Garantir que o Celery recebe SEMPRE driver síncrono 
# e o FastAPI recebe SEMPRE driver assíncrono, não importa o input.

# Passo 1: Obter a string original
raw_url = str(settings.DATABASE_URL)

# Passo 2: Remover quaisquer drivers específicos (+asyncpg, +psycopg2) para limpar
# Isto garante que começamos com uma base neutra
base_url = raw_url.replace("+asyncpg", "").replace("+psycopg2", "")

# Passo 3: Corrigir prefixo antigo (Render usa 'postgres://', SQLA quer 'postgresql://')
if base_url.startswith("postgres://"):
    base_url = base_url.replace("postgres://", "postgresql://", 1)

# AGORA TEMOS: base_url = "postgresql://user:pass@host:port/db" (Puro Síncrono)

# Definição Final dos URLs
SYNC_DB_URL = base_url
ASYNC_DB_URL = base_url.replace("postgresql://", "postgresql+asyncpg://")

# ==========================================
# MUNDO 1: ASSÍNCRONO (Para FastAPI)
# ==========================================
engine_async = create_async_engine(
    ASYNC_DB_URL,
    echo=False,
    # pool_pre_ping=True: Verifica se a conexão está viva antes de usar (essencial para Docker)
    pool_pre_ping=True 
)

SessionLocal = async_sessionmaker(
    bind=engine_async,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

# ==========================================
# MUNDO 2: SÍNCRONO (Para Celery)
# ==========================================
engine_sync = create_engine(
    SYNC_DB_URL,
    echo=False,
    pool_pre_ping=True # Recupera de quedas da BD automaticamente
)

# Esta é a fábrica que o Solver (Celery) vai usar!
SessionLocalSync = sessionmaker(
    autocommit=False, 
    autoflush=False, 
    bind=engine_sync
)

# ==========================================
# BASE DECLARATIVA (Partilhada)
# ==========================================
class Base(DeclarativeBase):
    pass