# WBS técnico — baseline definitiva de testes

## Objetivo

Estabelecer uma execução determinística, observável e segura para o Cronos. A seleção de suites é estrutural: `unit`, `integration/transactional`, `integration/committed` e `contracts`. Nenhuma suite depende de classificação automática por nomes de fixtures ou markers.

## Estrutura e comandos

```text
scripts/test.mjs
docker-compose.test.yml
backend/tests/unit/
backend/tests/integration/{transactional,committed}/
backend/tests/contracts/
frontend/vitest.config.js       # projetos node e dom
frontend/playwright.config.js   # public, auth, app, provider, faults
```

```powershell
node scripts/test.mjs setup --scope all
node scripts/test.mjs doctor --profile all
node scripts/test.mjs fast --scope all
node scripts/test.mjs integration
node scripts/test.mjs e2e --project public
node scripts/test.mjs all --scope all
node scripts/test.mjs benchmark --profile fast
```

O runner usa `spawn` com argumentos separados, não instala dependências durante `fast`, aceita forwarding apenas depois de `--`, preserva a falha primária e limpa somente o Compose project criado pelo próprio run.

## Backend

- PostgreSQL e Redis reais são iniciados por Compose com imagens pinadas por digest e portas loopback dinâmicas.
- As migrações são sempre executadas por Alembic, com credenciais distintas de migrator e runtime.
- Cada worker xdist recebe uma base dedicada (`cronos_test_gw0`, `cronos_test_gw1`); os testes de contrato são seriais.
- A proteção de base aceita apenas `cronos_test_db`, `cronos_ci_db` e os respetivos nomes de worker.
- A limpeza é limitada às tabelas públicas do banco temporário; não existe `metadata.create_all`, SQLite ou prune global.
- `pytest-socket` restringe a suite rápida a loopback e `pytest-xdist` executa integrações em dois workers.

## Frontend

- Vitest separa explicitamente os projetos `node` e `dom`, com isolamento, pool de threads e limites de workers.
- MSW está disponível para handlers de rede; o servidor falha em requests não tratadas.
- `@testing-library/user-event` é usado nas interações assíncronas relevantes.
- Playwright tem cinco projetos independentes (`public`, `auth`, `app`, `provider`, `faults`), `retries: 0`, waits observáveis e apenas a dependência técnica do setup.
- O gate global de `console.error` falha em ruído inesperado; erros deliberados são silenciados no teste que os espera.

## CI e evidência

Backend, frontend e E2E permanecem jobs separados. Cada job deve publicar resultados JUnit/Playwright e artefactos de falha, executar gates de dependências, lint, cobertura e build, e limpar sempre os recursos temporários. Os artefactos locais ficam em `.test-artifacts/`, ignorado pelo Git.

## Critérios de aceitação

- `doctor` verde para o perfil solicitado.
- Fast sem Docker e sem tráfego externo.
- Integrações com migração real, xdist=2 e contratos seriais.
- Sem testes desaparecidos: a remoção única é `test_test_suite_classification.py`, substituída pela seleção estrutural.
- Duas execuções consecutivas de `all` e E2E sem retries, com cobertura e artefactos.
- Main não é alterada; a implementação vive na branch de trabalho criada para esta baseline.
