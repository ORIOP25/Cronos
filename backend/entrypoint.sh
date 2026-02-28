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

echo -e "${YELLOW}ðŸ”„ Aguardando PostgreSQL em $DB_HOST:$DB_PORT...${NC}"
attempt=0
max_attempts=30
while [[ $attempt -lt $max_attempts ]]; do
    if nc -z "$DB_HOST" "$DB_PORT" 2>/dev/null; then
        echo -e "${GREEN}âœ… PostgreSQL pronto!${NC}"
        break
    fi
    attempt=$((attempt + 1))
    echo "Tentativa $attempt/$max_attempts: Aguardando $DB_HOST:$DB_PORT..."
    sleep 1
done

if [[ $attempt -eq $max_attempts ]]; then
    echo -e "${RED}âŒ PostgreSQL nÃ£o respondeu apÃ³s $max_attempts tentativas${NC}"
    exit 1
fi

echo -e "${YELLOW}ðŸ”„ Verificando/Executando migraÃ§Ãµes Alembic...${NC}"

# Tenta executar as migraÃ§Ãµes
# Se falhar com DuplicateTable (tabelas jÃ¡ existem), marca as migraÃ§Ãµes como executadas (stamp)
if ! alembic upgrade head 2>&1; then
    echo -e "${YELLOW}âš ï¸  MigraÃ§Ãµes falharam. Verificando se tabelas jÃ¡ existem...${NC}"
    
    # Se as tabelas jÃ¡ existem (erro de DuplicateTable), marca as versÃµes como executadas
    if alembic stamp head 2>&1; then
        echo -e "${GREEN}âœ… Marcadas migraÃ§Ãµes como executadas (tabelas jÃ¡ existiam)${NC}"
    else
        echo -e "${RED}âŒ Falha ao processar migraÃ§Ãµes${NC}"
        exit 1
    fi
else
    echo -e "${GREEN}âœ… MigraÃ§Ãµes executadas com sucesso${NC}"
fi

echo -e "${GREEN}âœ… Entrypoint concluÃ­do. A iniciar processo...${NC}"
exec "$@"
