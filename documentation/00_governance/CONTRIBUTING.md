# Guia de Contribuição — Horário Zen

## Princípios

1. **Documentation-first**: Toda alteração de código que afete comportamento, regras ou arquitetura DEVE atualizar a documentação em `/documentation`.
2. **Tenant isolation**: Toda query/mutation DEVE filtrar por `organization_id`.
3. **4 Pilares**: Toda decisão deve preservar Optimization, Stability, Scalability, Security.

## Ciclo de Desenvolvimento

```bash
# 1. Criar branch
git checkout -b feature/nome-da-feature

# 2. Desenvolver + testar localmente
docker compose up -d
cd backend && pytest --tb=short
cd frontend && npx vitest run

# 3. Verificar lint
cd backend && ruff check app/
cd frontend && npm run lint

# 4. Commit (NÃO automatizado — usar commits descritivos)
git add -A
git commit -m "feat: descrição clara do que foi feito"
```

## Alembic — Regras de Migração

### Regra de ouro: apenas UMA feature que altere schema ativa de cada vez.

As migrações Alembic são lineares (não usam branching). Para evitar conflitos:

1. **Antes de criar uma migração**, verificar que ninguém tem uma migração pendente por merge.
2. **Sempre fazer pull de `main`** antes de `alembic revision --autogenerate`.
3. **Se houver conflito de revision ID**: coordenar com a equipa para decidir qual merge primeiro.
4. **Migrações devem ser reversíveis**: testar `alembic downgrade -1` em dev local.

### Criar migração:
```bash
cd backend
alembic revision --autogenerate -m "descricao_curta_da_mudanca"
# Rever o ficheiro gerado em alembic/versions/
alembic upgrade head
alembic downgrade -1   # testar rollback
alembic upgrade head   # voltar a aplicar
```

## Estilo de Código

### Backend (Python)
- Modelos SQLAlchemy: usar `Mapped[T] = mapped_column(...)` (NUNCA `Column()`)
- Schemas Pydantic: Pydantic v2 com `model_config = ConfigDict(from_attributes=True)`
- Dependencies FastAPI: usar `Annotated`
- Preferir constantes para literais repetidos
- Nada de `bare except`

### Frontend (React)
- Componentes funcionais com hooks
- React Query para dados do servidor
- Zustand para estado de UI/autenticação
- Evitar ternários aninhados
- Usar elementos HTML semânticos (`<button>`, `<progress>`, etc.)

## CI/CD

CI dispara em push/PR para `main`:
- Backend: pytest + coverage
- Frontend: vitest + coverage
- SonarQube: análise de qualidade

Os testes DEVEM passar antes do merge.
