# 🏫 WBS & 5Ws: Refatoração da Configuração da Escola (SchoolConfig)

## 1. Os 5 Ws (The 5 Ws)

*   **Who (Quem):** O Diretor da Escola / Administrador da Organização.
*   **What (O Quê):** Refatorar e simplificar a interface e lógica de configurações da escola (Frontend e Backend), removendo complexidade desnecessária (feriados municipais, histórico de anos letivos) e reorganizando as secções para melhor UX.
*   **Where (Onde):**
    *   **Frontend:** `src/pages/SchoolConfig.jsx` e API clients.
    *   **Backend:** `models.py`, `schemas.py`, `settings_service.py`, `org_settings.py` (endpoints).
*   **When (Quando):** Fase inicial do projeto (Sprint atual), para garantir que a fundação do calendário escolar é sólida, simples e de fácil utilização antes de gerar horários em grande escala.
*   **Why (Porquê):** A interface atual é confusa (muitos CCardHeaders aninhados, tabelas de listagem para dados que devem ser únicos), existem funcionalidades não suportadas de forma fiável (feriados por concelho via API) e campos em locais errados (ex: almoço fora da grelha horária). A simplificação evita erros do utilizador e reduz dívida técnica.

---

## 2. Decisões Consolidadas

1.  **Ano Letivo Único:** A escola terá apenas **1 ano letivo ativo**. O ecrã deixa de ser uma listagem/tabela para passar a ser um formulário fixo. Ao guardar um novo ano, este faz sobrescreve o anterior (Upsert). Pede-se apenas um *prompt* de confirmação no Frontend para evitar erros. O backend não guardará histórico das configurações antigas.
2.  **Feriados Municipais Removidos:** Remove-se totalmente a noção de `region_code` ou concelho. A sincronização automática importará **apenas feriados nacionais**. Feriados locais (municipais, pontes, padroeiros) serão adicionados **manualmente** pela escola através da secção "Pausas e Interrupções Manuais".
3.  **Janela de Almoço na Grelha Horária:** Os campos de hora de almoço (`lunch_window_start`, `lunch_window_end`, `lunch_min_duration_minutes`) saem da tab de definições do ano e passam para a tab "Grelha Horária", ficando junto das configurações de abertura e fecho da escola.
4.  **Campo `repair_stability_window_days`:** Passa a estar visível e gerível na tab "Calendário".

---

## 3. Estrutura Analítica do Projeto (WBS)

### Fase 1: Limpeza do Backend & Base de Dados
**Objetivo:** Adaptar o modelo de dados e os serviços à nova realidade simplificada. **[CONCLUÍDO]**

*   **[x] 1.1. Atualização do Schema da Base de Dados**
    *   Remover as colunas `region_code` e `academic_year` da tabela `OrganizationSettings` e separar `OrganizationGridSettings`.
    *   Gerar e aplicar migração Alembic (`alembic revision --autogenerate` e `alembic upgrade head`).
*   **[x] 1.2. Atualização dos Schemas Pydantic (`schemas.py`)**
    *   Remover `region_code` e `academic_year` de schemas relevantes.
*   **[x] 1.3. Atualização dos Serviços (`settings_service.py`)**
    *   Remover lógica de tratamento de `region_code` e iterador de anos letivos.
    *   Simplificar `_get_pt_holidays` e `sync_holidays`.
    *   Garantir atuação como override global para a organização (sobrescrevendo o registo existente).
*   **[x] 1.4. Atualização dos Endpoints (`org_settings.py`)**
    *   O endpoint `POST /settings/sync-holidays` não exige parâmetros de path ou query.
    *   Alterar `GET /settings/` para devolver um objeto único. Criar endpoint para `grid-settings`.
*   **[x] 1.5. Limpeza de Seed Data e Testes**
    *   Remover as dependências antigas dos scripts de seed (`seed_data_*.py`) e testes (`test_schedule_generate_preflight.py`, `test_org_settings_endpoints.py`, etc.).

### Fase 2: Refatoração do Frontend (`SchoolConfig.jsx`)
**Objetivo:** Reconstruir o UI respeitando o fim dos múltiplos anos e as novas localizações dos campos. **[CONCLUÍDO]**

*   **[x] 2.1. Tab "Calendário" (Substitui "Anos Letivos")**
    *   Eliminar a tabela (`CTable`) de listagem de anos letivos.
    *   Eliminar os "CCardHeaders" aninhados.
    *   O formulário passa a ser fixo, preenchido automaticamente com o registo existente no backend.
    *   Adicionar o campo `repair_stability_window_days` ao formulário.
    *   Remover os campos de Almoço daqui.
    *   Implementar `window.confirm` ao clicar em "Guardar" alertando: *"Ao atualizar estas definições, o ano letivo em vigor será sobrescrito. Tem a certeza?"*.
*   **[x] 2.2. Tab "Interrupções" (Substitui "Calendário Escolar")**
    *   Remover dependência da listagem de anos letivos do tab anterior (usa diretamente o ano letivo configurado no backend).
    *   Remover o dropdown e conceitos de Concelho/Região.
    *   O botão "Sincronizar Feriados Nacionais" passa a ser uma ação direta e global para o ano letivo ativo.
    *   Manter e destacar a secção de "Adicionar Interrupção Manual" para que a escola possa introduzir os seus feriados municipais (ex: "Feriado Municipal da Maia", "22-05-2026").
*   **[x] 2.3. Tab "Grelha Horária"**
    *   Mover os inputs `lunch_window_start`, `lunch_window_end` e `lunch_min_duration_minutes` para este tab.
    *   Ajustar o botão "Guardar e Regenerar Grelha" para tamanho normal (`size="md"` em vez de `lg`), melhorando o aspeto geral.
    *   Garantir validação de obrigatoriedade: todos os campos têm de estar preenchidos.

### Fase 3: Validação e Testes
**Objetivo:** Assegurar que nenhuma regra de negócio do motor (Solver) quebra com estas alterações. **[CONCLUÍDO]**

*   **[x] 3.1. Testes de Integração do Backend**
    *   Verificar e corrigir todos os testes para garantir que a remoção do `region_code` e `academic_year` não quebra pipelines.
    *   Testes de regressão Alfa testados de ponta a ponta e a passar com 100% de sucesso.
*   **[x] 3.2. Teste End-to-End (E2E) Automático / Manual**
    *   Simulado o processo na íntegra através dos testes nativos em Python. Geração limpa e regeneração/reparação também garantidas com a janela de estabilidade.
