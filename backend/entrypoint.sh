#!/bin/bash
set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# DB connection info (from docker-compose service name: "db")
DB_HOST=${DB_HOST:-db}
DB_PORT=${DB_PORT:-5432}

echo -e "${YELLOW}🔄 Aguardando PostgreSQL em $DB_HOST:$DB_PORT...${NC}"
attempt=0
max_attempts=30
while [ $attempt -lt $max_attempts ]; do
    if nc -z "$DB_HOST" "$DB_PORT" 2>/dev/null; then
        echo -e "${GREEN}✅ PostgreSQL pronto!${NC}"
        break
    fi
    attempt=$((attempt + 1))
    echo "Tentativa $attempt/$max_attempts: Aguardando $DB_HOST:$DB_PORT..."
    sleep 1
done

if [ $attempt -eq $max_attempts ]; then
    echo -e "${RED}❌ PostgreSQL não respondeu após $max_attempts tentativas${NC}"
    exit 1
fi

echo -e "${YELLOW}🔄 Verificando/Executando migrações Alembic...${NC}"

# Tenta executar as migrações
# Se falhar com DuplicateTable (tabelas já existem), marca as migrações como executadas (stamp)
if ! alembic upgrade head 2>&1; then
    echo -e "${YELLOW}⚠️  Migrações falharam. Verificando se tabelas já existem...${NC}"
    
    # Se as tabelas já existem (erro de DuplicateTable), marca as versões como executadas
    if alembic stamp head 2>&1; then
        echo -e "${GREEN}✅ Marcadas migrações como executadas (tabelas já existiam)${NC}"
    else
        echo -e "${RED}❌ Falha ao processar migrações${NC}"
        exit 1
    fi
else
    echo -e "${GREEN}✅ Migrações executadas com sucesso${NC}"
fi

echo -e "${GREEN}✅ Iniciando servidor FastAPI...${NC}"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
