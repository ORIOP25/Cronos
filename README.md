# Cronos

SaaS para gestão e geração de horários no Ensino Profissional em Portugal. Sistema operacional dinâmico que planeia, replaneia e regista execução real — não um calendário anual estático.

## Arquitetura

| Camada | Stack |
|--------|-------|
| Backend | Python 3.12, FastAPI, SQLAlchemy Async, Pydantic v2, Celery |
| Frontend | React 19, Vite, CoreUI, React Query, Clerk |
| Base de Dados | PostgreSQL 15 local / PostgreSQL 16 CI |
| Cache / Queue | Redis 7 |
| Scheduling Engine | OR-Tools CP-SAT (Solver V2) |

## Estado Atual

Fase atual: beta baseline hardening. As funcionalidades principais estao
fechadas; o foco e qualidade operacional, UX consistente, CI/CD, schema drift,
documentacao e limpeza de legado.

## Arranque Rápido (Dev Local)

```bash
# 1. Criar .env com credenciais
cp backend/.env.example backend/.env
# Editar backend/.env com valores reais

# 2. Criar .env para docker-compose na raiz
cp .env.example .env  # (se existir) ou criar manualmente:
# POSTGRES_PASSWORD=<senha>

# 3. Arrancar tudo
docker compose up -d

# 4. Aceder
# Frontend: http://localhost:5173
# API Docs:  http://localhost:8000/docs
```

## Estrutura

```
MeuProjeto/
├── backend/          # FastAPI + Alembic + Celery
│   ├── app/          # Código da aplicação
│   ├── alembic/      # Migrações de base de dados
│   ├── scripts/      # Scripts de manutenção
│   └── tests/        # Testes pytest
├── frontend/         # React + Vite
│   └── src/
│       ├── pages/        # Páginas da app
│       ├── components/   # Componentes reutilizáveis
│       └── test/         # Testes Vitest
├── documentation/    # Documentação estruturada (11 áreas)
│   ├── 01_product_strategy/
│   ├── 02_domain_model/
│   ├── 03_scheduler_engine/
│   └── ...
├── .agents/skills/   # Skills para AI-assisted development
└── docker-compose.yml
```

## Documentação

Toda a documentação oficial está em [`documentation/`](documentation/). Estrutura por camadas (Clean Architecture):

- **Layer 1 (Interface)**: `05_backend_api/`, `06_frontend_ux/`
- **Layer 2 (Regras de Negócio)**: `01_product_strategy/`, `02_domain_model/`, `03_scheduler_engine/`, `04_operational_features/`
- **Layer 3 (Base de Dados)**: `07_data_and_seed/`, `08_security_quality/`, `09_ops_observability/`

Ver [`documentation/README.md`](documentation/README.md) para o índice completo.

## Qualidade

- CI/CD: GitHub Actions (pytest + coverage, Vitest coverage, build, Alembic check, trigger audit, Playwright E2E)
- Segurança: Rate limiting, CORS, security headers, httpOnly cookies
- Tenant isolation: `organization_id` em todas as queries
- Auditoria: Ver [`documentation/08_security_quality/AUDITORIA_ARQUITETURAL_ALPHA_1.0.md`](documentation/08_security_quality/AUDITORIA_ARQUITETURAL_ALPHA_1.0.md)
