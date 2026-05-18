#!/bin/bash
set -e

DB_HOST=${DB_HOST:-db}
DB_PORT=${DB_PORT:-5432}
RUN_MIGRATIONS=${RUN_MIGRATIONS:-1}

echo "[entrypoint] A espera do PostgreSQL em ${DB_HOST}:${DB_PORT}..."
attempt=0
max_attempts=30
while [[ $attempt -lt $max_attempts ]]; do
    if nc -z "$DB_HOST" "$DB_PORT" 2>/dev/null; then
        echo "[entrypoint] Porta PostgreSQL aberta."
        break
    fi
    attempt=$((attempt + 1))
    echo "[entrypoint] Tentativa ${attempt}/${max_attempts}: a espera de ${DB_HOST}:${DB_PORT}"
    sleep 2
done

if [[ $attempt -eq $max_attempts ]]; then
    echo "[entrypoint] ERRO: PostgreSQL nao respondeu apos ${max_attempts} tentativas."
    exit 1
fi

# Pequena pausa extra para PostgreSQL terminar recovery
sleep 2

if [[ "$RUN_MIGRATIONS" == "1" ]]; then
    echo "[entrypoint] A reparar estado de migracoes (se necessario)..."
    python scripts/repair_migrations.py || true

    echo "[entrypoint] A executar migracoes Alembic..."
    alembic upgrade head

    echo "[entrypoint] A verificar tabelas core..."
    python -c "
from app.db.database import engine_sync
from sqlalchemy import text
import sys
try:
    with engine_sync.connect() as conn:
        conn.execute(text('SELECT 1 FROM \"user\" LIMIT 1'))
        conn.execute(text('SELECT 1 FROM organization LIMIT 1'))
    print('[verify] Tabelas core confirmadas.')
except Exception:
    print('[verify] Tabelas core ausentes. Alembic reportou up-to-date mas sem tabelas.')
    sys.exit(1)
" || {
        echo "[entrypoint] Alembic em estado inconsistente. A forcar reset do stamp..."
        python -c "
from app.db.database import engine_sync
from sqlalchemy import text
with engine_sync.connect() as conn:
    conn.execute(text('DROP TABLE IF EXISTS alembic_version'))
print('[repair] alembic_version removida. Vou re-correr migrate.')
"
        alembic upgrade head
        python -c "
from app.db.database import engine_sync
from sqlalchemy import text
with engine_sync.connect() as conn:
    conn.execute(text('SELECT 1 FROM \"user\" LIMIT 1'))
print('[verify] Tabelas core confirmadas apos reset.')
" || {
            echo "[entrypoint] ERRO FATAL: Nao foi possivel criar tabelas core mesmo apos reset."
            exit 1
        }
    }

    echo "[entrypoint] Migracoes Alembic concluidas."
else
    echo "[entrypoint] A saltar migracoes (RUN_MIGRATIONS=${RUN_MIGRATIONS})."
fi

echo "[entrypoint] A iniciar processo..."
exec "$@"
