#!/bin/bash
set -e

# --- Variáveis ---
DB_HOST=${DB_HOST:-db}
DB_PORT=${DB_PORT:-5432}
RUN_MIGRATIONS=${RUN_MIGRATIONS:-1}

echo "[entrypoint] À espera do PostgreSQL em ${DB_HOST}:${DB_PORT}..."
attempt=0
max_attempts=30
while [[ $attempt -lt $max_attempts ]]; do
    if nc -z "$DB_HOST" "$DB_PORT" 2>/dev/null; then
        echo "[entrypoint] PostgreSQL está pronto."
        break
    fi
    attempt=$((attempt + 1))
    echo "[entrypoint] Tentativa ${attempt}/${max_attempts}: à espera de ${DB_HOST}:${DB_PORT}"
    sleep 1
done

if [[ $attempt -eq $max_attempts ]]; then
    echo "[entrypoint] ERRO: PostgreSQL não respondeu após ${max_attempts} tentativas."
    exit 1
fi

if [[ "$RUN_MIGRATIONS" == "1" ]]; then
    echo "[entrypoint] A executar migrações Alembic..."

    # 1. Reparar estado inconsistente de migrações (se necessário)
    python scripts/repair_migrations.py

    # 2. Executar migrações
    alembic upgrade head

    # 3. Hard guard: confirmar que tabelas core existem
    python -c "from scripts.repair_migrations import verify_migrations; verify_migrations()"

    echo "[entrypoint] Migrações Alembic concluídas."
else
    echo "[entrypoint] A saltar migrações Alembic (RUN_MIGRATIONS=${RUN_MIGRATIONS})."
fi

echo "[entrypoint] A iniciar processo..."
exec "$@"
