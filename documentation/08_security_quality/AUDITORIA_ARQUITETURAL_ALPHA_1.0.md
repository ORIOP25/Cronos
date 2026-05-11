# AUDITORIA ARQUITETURAL COMPLETA — Apérius Alpha 1.0

*(Auditoria de raiz focada em risco sistémico e capacidade de crescimento)*

---

## 🔴 CRÍTICO (Impede crescimento com segurança)

### 1. Password da Base de Dados Hardcoded em 3 locais

`docker-compose.yml:10`, `docker-compose.yml:42`, `.github/workflows/ci.yml:19`

A password `mysecretpassword` está exposta em plaintext no docker-compose.yml e nos workflows de CI. O docker-compose.yml vai para o repositório e, ao contrário do `.env`, NÃO está no `.gitignore`.

**Impacto**: Qualquer pessoa com acesso ao repo tem credenciais da BD de dev. Se alguma vez for usado o mesmo ficheiro em staging/produção, é catastrófico.

**Recomendação**: Mover `POSTGRES_USER`/`POSTGRES_PASSWORD` para o `.env` (já ignorado pelo `.gitignore`). O docker-compose deve ler via `${POSTGRES_USER}` etc.

---

### 2. Duas Pipelines CI com Responsabilidades Sobrepostas

- `ci.yml` (linhas 1-74): Corre testes backend com `pytest --tb=short -q` em push/PR na main
- `test.yml` (linhas 1-92): Corre testes backend + frontend + SonarQube em push/PR na main/master

Ambas disparam nos mesmos eventos (`push` e `PR` para `main`), resultando em **execução duplicada de todos os testes backend** a cada commit. Usam passwords, secrets e service images diferentes.

**Impacto**: Duplicação de custo de CI, divergência de configuração (ex: `POSTGRES_DB` diferente entre workflows), duas fontes de verdade para "os testes passaram".

**Recomendação**: Consolidar num único workflow `ci.yml`. Manter o SonarQube como step condicional ou job separado dentro do mesmo workflow. Apagar `test.yml` ou mantê-lo apenas como trigger manual.

---

### 3. Celery Worker Usa Driver Síncrono Diferente do Backend

No `docker-compose.yml:77`:
```yaml
worker:
  environment:
    - DATABASE_URL=postgresql+psycopg2://postgres:mysecretpassword@db:5432/horario_zen_db
```

O backend usa `+asyncpg`, o worker/beat usam `+psycopg2`. A base de dados em `app/db/database.py` faz replace inteligente, mas os containers recebem URLs diferentes, o que invalida a lógica de fallback.

**Impacto**: Se a lógica de replace falhar em alguma edge case, há risco de o worker não conseguir ligar à BD. Além disso, a manutenção de duas strings de conexão é propensa a erros.

**Recomendação**: Passar a mesma `DATABASE_URL` com `+asyncpg` para todos os serviços. O `app/db/database.py` já trata da conversão para driver síncrono. Remover a divergência do docker-compose.

---

### 4. Redis Sem Persistência (Perda de Dados de Sessão/Rate Limit)

`docker-compose.yml:23-28`: O serviço Redis não tem volume montado. Se o container Redis cair, perde-se:
- Estado de rate limiting (todas as organizações ficam vulneráveis a abusos até rebuild)
- Tarefas Celery em fila
- Cancel flags de geração de horários

**Impacto**: Um restart do Redis durante uma geração de horário deixa a flag de cancelamento órfã, bloqueando capacidade de cancelar a tarefa. Reinício também reseta todos os rate limits.

**Recomendação**: Adicionar volume `redis_data` e montar em `/data`. Configurar `redis.conf` com `appendonly yes`.

---

### 5. Injeção de Python Arbitrário no entrypoint.sh

`entrypoint.sh:32-90`, `95-115`, `121-207`: O entrypoint contém 3 blocos inline de Python não testados, com lógica complexa de reparação de estado inconsistente de migrações e bootstrap de admin.

**Impacto**: Se qualquer um destes blocos falhar silenciosamente, o container arranca com BD inconsistente. O bloco de bootstrap é particularmente perigoso porque:
- Cria `OrganizationSettings` e `GridSettings` com defaults hardcoded
- Não verifica unicidade do email antes de criar (embora a lógica pareça idempotente, depende de ordem de execução)

**Recomendação**: Extrair estes blocos para scripts Python separados (ex: `scripts/repair_migrations.py`, `scripts/bootstrap_admin.py`) com testes unitários. O entrypoint deve apenas orquestrar.

---

### 6. Falsos Positivos e Conflitos de Nomes nos Formulários do Frontend

```
components/Forms/RoomForm.jsx   ← conflito de nome com
components/ImportForms/RoomForm.jsx

components/Forms/TimeslotForm.jsx   ← conflito de nome com
components/ImportForms/TimeslotForm.jsx
```

Além disso, `components/ImportForms/LessonForm.jsx` está marcado como deprecado em `plan.md:52` mas ainda existe no diretório.

**Impacto**: Conflito de importações em IDEs, risco de importar o formulário errado. Código deprecado que pode ser usado acidentalmente.

**Recomendação**: Renomear os formulários de importação (ex: `ImportForms/RoomImportForm.jsx`). Apagar ficheiros deprecados (`ServiceDistribution.jsx`, `LessonForm.jsx`).

---

## 🟠 ALTO (Degradação progressiva)

### 7. Padrão de Codificação Inconsistente nos Modelos SQLAlchemy

`models.py`: Mistura dois estilos de definição de colunas:
- **Estilo Novo** (SQLAlchemy 2.0): `Mapped[int] = mapped_column(...)` — usado em Organization, User, Teacher, Class, Room, etc.
- **Estilo Legado**: `id = Column(Integer, primary_key=True)` — usado em Constraint (linha 386), Substitution (linhas 495-519)

Exemplo específico:
```python
# Linha 386 - Constraint: estilo legado
id = Column(Integer, primary_key=True, index=True)

# Linha 495 - Substitution: estilo legado em TODOS os campos
id = Column(Integer, primary_key=True, index=True)
lesson_id = Column(Integer, ForeignKey("lesson.id"), nullable=False)
```

**Impacto**: Inconsistência no codebase dificulta onboarding. O estilo legado perde type hints e pode permitir erros que o `Mapped` capturaria.

**Recomendação**: Migrar `Constraint` e `Substitution` para o estilo `Mapped[T]`. Adicionar regra de lint para proibir `Column()` em novos modelos.

---

### 8. Driver de BD Inexistente no Frontend (package.json)

`frontend/package.json:25`: `"luxon": "^3.7.2"`

O nome correto do pacote é `luxon` (com 'o'), não `luxon` (com 'u'). Este pacote:
- Ou é um typo-squatting package (risco de segurança)
- Ou simplesmente não existe e a instalação falha silenciosamente em cache

**Impacto**: Se for um pacote malicioso (typo-squatting), é uma vulnerabilidade de supply chain. Se não existir, o build pode quebrar em CI limpo.

**Recomendação**: Verificar imediatamente. Se for typo, corrigir para `luxon`. Se não estiver a ser usado, remover.

---

### 9. Nenhum `.env.example` ou `env.template`

O projeto não tem ficheiro de template para variáveis de ambiente. Um novo developer tem de adivinhar/reverse-engineerar as variáveis necessárias lendo `config.py` e `docker-compose.yml`.

**Impacto**: Onboarding lento, risco de configuração errada em staging/produção, impossibilidade de automação de deploy.

**Recomendação**: Criar `backend/.env.example` e `frontend/.env.example` com todas as variáveis documentadas (valores placeholder, nunca reais).

---

### 10. Estrutura de Documentação Excelente mas com Débito Técnico Documental

A estrutura em 11 diretórios (`00_governance` a `10_migration_map`) é excecional e bem organizada. No entanto:
- `documentation/10_migration_map/FILES_CANDIDATE_DELETE.md` lista ficheiros que já deviam ter sido apagados (os JSON do Sonar data provavelmente de um scan antigo)
- `plan.md` na raiz é um plano de execução tático, não devia estar na raiz do repo
- `GERADOR_HORARIOS_PLANO.md` e `ANALISE_ENDPOINT_RESUMO.md` são ficheiros legacy grandes na raiz de `documentation/` que o próprio `FILES_CANDIDATE_DELETE.md` identifica como candidatos a apagar
- Vários WBS parecem ser snapshots históricos de implementações concluídas (ex: `WBS_SOLVER_V2_SUPER_DETALHADA_IMPLEMENTACAO_LOCAL_2026-04-20.md`)

**Impacto**: A documentação começa a acumular ruído que torna difícil encontrar a verdade atual.

**Recomendação**: Executar a limpeza planeada no `FILES_CANDIDATE_DELETE.md`. Mover `plan.md` para `documentation/10_migration_map/`. Arquivar WBS concluídos num subdiretório `archive/`.

---

## 🟡 MÉDIO (Risco de manutenção)

### 11. `str(str(...))` Redundante em ratelimit.py

`ratelimit.py:18`: `storage_uri=str(str(settings.REDIS_URL))`

Chamada dupla de `str()` — não causa erro mas indica falta de revisão.

---

### 12. TimeslotUpdate: Validador com Lógica Frágil

`schemas.py:308-316`: O `@model_validator` `check_times` do `TimeslotUpdate` usa `if self.start_time and self.end_time`. Isto falha se `start_time` ou `end_time` forem `time(0, 0)` (meia-noite), pois `bool(time(0,0))` é `False`.

**Impacto**: Um admin que configure um timeslot com início ou fim à meia-noite não terá validação de coerência temporal.

---

### 13. Sentry `traces_sample_rate` Hardcoded a 1.0

`main.py:62-64`: O sample rate está a 100% sem distinção entre ambientes.

**Impacto**: Em produção, 100% de tracing consome quota rapidamente e pode causar throttling. O comentário no código reconhece o problema mas não o resolve.

**Recomendação**: Mover para `config.py` como setting configurável: `SENTRY_TRACES_SAMPLE_RATE: float = 0.1`.

---

### 14. Diretórios Vazios (Código Morto Estrutural)

- `frontend/src/assets/marketing/` — vazio
- `frontend/src/components/luxury/` — vazio  
- `backend/scripts/` — vazio

Estes diretórios foram criados para features planeadas mas mantêm-se vazios. Geram confusão e expectativas falsas.

---

### 15. Alembic: 25 Migrações Lineares Sem Branch Management

25 ficheiros de migração sequenciais (`alembic/versions/`). Se duas branches de feature criarem migrações em paralelo, haverá conflito nos revision IDs.

**Impacto**: Bloqueia desenvolvimento paralelo de features que alterem schema. Risco médio para alpha, mas alto quando a equipa crescer.

**Recomendação**: Documentar no contributing guide que apenas uma feature que altere schema pode estar ativa de cada vez. Ou adotar Alembic branching (embora complexo).

---

### 16. Skills: Duplicação de Conteúdo entre `.agents/skills/*/SKILL.md` e `.github/agents/Agent_HorarioZen.md`

Os 6 ficheiros de skill (≈300 linhas cada, total ≈1800 linhas) e o `Agent_HorarioZen.md` (135 linhas) contêm **redundância massiva**:
- Os 4 pilares de engenharia repetem-se em TODAS as skills
- O Delivery Protocol repete-se em TODAS
- O Documentation Protocol repete-se em TODAS
- As Safety Rules repetem-se em TODAS

**Impacto**: Para alterar uma regra global (ex: adicionar um 5º pilar), seria preciso editar 7 ficheiros. Isto é insustentável a médio prazo.

**Recomendação**: Criar um `SKILL_BASE.md` partilhado com as regras comuns. Cada skill herda/importa (via prompt injection) a base + as suas especializações. Alternativa: consolidar `Agent_HorarioZen.md` (que já é o Lead Architect) como base e fazer as skills mais leves, apenas com especializações.

---

### 17. Docker: Porta 8000 Exposta mas Comentário Diz o Contrário

`docker-compose.yml:52-53`:
```yaml
ports:
  - "8000:8000"
```
O comentário na linha 38 diz "A porta 8000 fica fechada para fora, só o Nginx a vê", mas `ports: "8000:8000"` expõe a porta 8000 para o host. O comentário está factualmente errado. Além disso, não existe serviço Nginx no docker-compose.

**Impacto**: Em dev local é conveniente, mas se este compose for usado como base para produção, a API fica exposta sem proxy reverso.

---

### 18. `schedule_service.py` com 1089 Linhas — Violação de SRP

O ficheiro de serviço de horários tem 1089 linhas e mistura:
- CRUD de timeslots
- CRUD de lessons  
- CRUD de constraints
- Sincronização de ClassSubjectLink→Lesson
- Gestão de rascunhos (draft lifecycle)
- Limpeza de janelas
- Resolução de conflitos de output
- Visualização semanal
- Cálculo de diff

**Impacto**: Difícil de testar isoladamente, difícil de navegar, alto acoplamento.

**Recomendação**: Partir em `schedule_service.py` (core), `schedule_draft_service.py`, `schedule_view_service.py`.

---

### 19. `occurrence_service.py` com 1527 Linhas

O maior ficheiro do projeto. Contém toda a lógica de:
- Máquina de estados de ocorrências
- Criação de ocorrências
- Atualização com validações complexas
- Cálculo de dívidas (debt)
- Recomendação de substitutos
- Auto-confirmação diária
- Observabilidade

**Impacto**: Testar uma edge case na máquina de estados requer compreender 1500 linhas de contexto.

**Recomendação**: Partir em `occurrence_state_machine.py`, `occurrence_crud.py`, `debt_service.py`, `substitution_recommendation.py`.

---

## 🔵 BAIXO (Melhorias incrementais)

### 20. `check_times` no `TimeslotUpdate` não verifica todos os casos

Se apenas `start_time` for enviado sem `end_time`, a validação é skipped. O utilizador pode submeter `{"start_time": "18:00"}` sem `end_time` e não há validação.

---

### 21. `create_user` em `user_service.py` Tem Dois Caminhos de Criação de Organização

`register_account()` (linha 25) e `create_user()` (linha 70 quando `org_id=None`) ambos criam organizações, mas com lógica ligeiramente diferente (um cria Teacher profile, outro não). Duas fontes de verdade para criação de organização.

---

### 22. `.editorconfig` Inexistente

Sem `.editorconfig`, developers com diferentes IDEs podem introduzir inconsistências de indentação/tabs/espaços.

---

### 23. `requirements.txt` Sem Versões Pinned para Dependências Transitivas

Apenas top-level dependencies estão listadas. Isto pode causar builds não-determinísticos.

**Recomendação**: Usar `pip freeze` para gerar `requirements.lock` ou adotar `pip-tools`/`poetry`.

---

### 24. Frontend: Nenhum TypeScript

O frontend é JavaScript puro (`.jsx`). TypeScript reduziria significativamente a classe de bugs relacionados a shape de dados (especialmente com os schemas complexos do backend).

---

### 25. `backend/README.md` vs Raiz Sem README

Existe `backend/README.md` e `frontend/README.md`, mas **não existe `README.md` na raiz do projeto**. O `documentation/README.md` funciona como índice mas não é o que aparece no GitHub.

---

### 26. `pytest.ini` vs `pyproject.toml`

`pytest.ini` está obsoleto; a recomendação moderna é configurar pytest em `pyproject.toml`.

---

### 27. `alembic.ini:87` — URL Placeholder Nunca Usada

```ini
sqlalchemy.url = driver://user:pass@localhost/dbname
```
Esta linha é inútil porque o `env.py` faz override. Mas pode confundir novos developers.

---

### 28. `simulate_user.py` na Raiz

Script de simulação na raiz do projeto sem documentação sobre o que faz ou como usar.

---

## 📊 RESUMO E MÉTRICAS

| Categoria | CRITICAL | HIGH | MEDIUM | LOW | Total |
|-----------|----------|------|--------|-----|-------|
| Segurança/Infra | 3 | 2 | 0 | 0 | 5 |
| Arquitetura/Patterns | 0 | 2 | 3 | 5 | 10 |
| Documentação | 0 | 1 | 1 | 1 | 3 |
| CI/CD | 1 | 0 | 0 | 0 | 1 |
| Frontend | 1 | 1 | 0 | 1 | 3 |
| Backend | 1 | 0 | 3 | 2 | 6 |
| **Total** | **6** | **6** | **7** | **9** | **28** |

**Arquivos problemáticos (por nº de findings):**
1. `docker-compose.yml` — 3 findings
2. `entrypoint.sh` — 2 findings
3. `models.py` — 1 finding (padrão inconsistente)
4. `schedule_service.py` — 1 finding (tamanho)
5. `occurrence_service.py` — 1 finding (tamanho)
6. `package.json` (frontend) — 1 finding (typo)

---

## 🎯 PLANO DE AÇÃO RECOMENDADO (Ordem de Prioridade)

### Sprint 0 (Esta semana — antes de qualquer feature nova):
1. ✅ Remover passwords hardcoded do docker-compose → `.env`
2. ✅ Consolidar CI pipelines (apagar `test.yml`)
3. ✅ Corrigir `luxon` → `luxon` no package.json do frontend
4. ✅ Criar `.env.example`
5. ✅ Adicionar volume Redis ao docker-compose

### Sprint 1 (Antes do próximo release):
6. Extrair Python inline do entrypoint.sh para scripts testáveis
7. Unificar DATABASE_URL entre containers
8. Migrar `Constraint` e `Substitution` para `Mapped[T]`
9. Apagar diretórios vazios e ficheiros deprecados
10. Executar limpeza documental planeada no `FILES_CANDIDATE_DELETE.md`

### Sprint 2+ (Débito técnico):
11. Partir `schedule_service.py` e `occurrence_service.py`
12. Refatorar estrutura de skills (extrair base comum)
13. Adicionar TypeScript ao frontend
14. Adotar `pip-tools`/`poetry` para lock de dependências
