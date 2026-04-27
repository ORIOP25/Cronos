# Relatório de Implementação — Fase G: Persistência de Draft e Ciclo de Vida do Motor V2

**Data**: 22 de Abril de 2026
**Autor**: Antigravity / Equipa de Scheduling

## Sumário Executivo
Este relatório detalha a conclusão da **Fase G** da WBS do Solver V2. Esta fase era o marco final do ciclo de vida dos horários antes de serem ativados no sistema. Focou-se em garantir que blocos em modo *repair* não corrompem a integridade dos horários já publicados, validando a persistência atómica, e desenvolvendo salvaguardas (preflight e endpoints de aprovação/rejeição) para promover transparência ao utilizador final.

## Conclusões da Implementação

### 1. G.01 — Persistência Atómica (Imutabilidade do Publicado)
A fundação do sistema de Drafts já estava consolidada através dos processos implementados no *Sprint 3* e nas tarefas de Celery (`solver_tasks.py`).
- O modo *repair* força a geração com flag `is_draft=True`.
- O solver `v2_engine` assegura, com suporte nas condicionantes CP-SAT (`frozen_until`), que não há alocações de horários para datas passadas ou dentro da *stability window*.
- A persistência é atómica gerida por uma única transação em `_save_results_sync()`.

### 2. G.02 — Safety Net Preflight
Implementou-se a restrição que bloqueia novas solicitações de geração (`/api/v1/schedule/generate`) sempre que uma organização possuir um rascunho pendente.
**Estratégia**:
Adicionámos uma verificação assíncrona ao `_preflight_check` nativo em `backend/app/api/v1/endpoints/schedule.py`. 
Ao detetar um rascunho com o auxílio do `schedule_service.list_draft_gen_ids_sync`, a API rejeita o pedido com HTTP 400 (preflight_failed), informando textualmente o utilizador:
> *"Existe um rascunho pendente de aprovação. Por favor, aprove ou rejeite o rascunho atual antes de iniciar uma nova geração."*

### 3. G.03 & G.04 — Aprovação e Rejeição
Estas operações (que atuam sobre o ciclo de vida dos registos `ScheduleOutput`) foram auditadas e encontravam-se já em estrito cumprimento com os requisitos do Solver V2:
- **Aprovar**: Exclui os blocos "ativos" cujo `date` ultrapassa a janela de estabilidade e promove (`is_draft=False`) os blocos emergentes da geração associada ao draft.
- **Rejeitar**: Elimina integralmente o draft isolado, devolvendo o estado pré-geração.

### 4. G.05 — Suite de Testes Dedicada
Construída uma robusta suite de testes de integração (`test_solver_v2_draft_lifecycle.py`), que alavanca ferramentas de povoamento do *preflight test suite* para validar end-to-end:
1. `test_g02_generate_blocked_when_draft_exists`: Confirmação do trigger `400 Bad Request` com o erro de preflight formatado.
2. `test_g03_approve_draft_promotes_blocks`: Validação de conversão de metadados (`is_draft` `True` -> `False`).
3. `test_g04_reject_draft_drops_blocks`: Certificação de que os blocos de draft desaparecem definitivamente sem danificar dependências.

## Testes e Validação
Executada a totalidade dos testes da pipeline V2 (Expansão, Lexicographic, Preflight e Draft Lifecycle) resultando em **43/43 PASSED**.

## Próximos Passos
Com a Fase G fechada, a Engine Base do **Zen Scheduler V2 (Local Implementation)** atinge a sua estabilidade arquitetural de *backend*. Os próximos desenvolvimentos irão enveredar pelas integrações Frontend, nomeadamente exibir as métricas de qualidade V2 e providenciar as telas de aprovação/rejeição para o utilizador da escola interagir com este motor avançado.
