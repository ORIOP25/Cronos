# Tech Spec — Disponibilidade das Turmas

## Purpose

Este documento especifica a disponibilidade semanal das turmas.
Define decisões de produto, modelo de dados, contratos, regras do motor, plano TDD e critérios de aceitação.

**Estado:** implementação presente no ramo local `feat/class-availability-engine`.
A verificação final e a entrega estão pendentes.
O código, os testes, as migrações e a configuração são a fonte de verdade; este documento fica como registo das decisões.
**Data:** 14 de outubro de 2026.
**Base observada:** branch `main` no commit `4773d76`; `origin/main` avançou para `ade64f3` com a seleção de módulos por turma (PR #131), integrada neste ramo.
**Origem:** item 3 dos pedidos da escola piloto, reunião de 13 de outubro de 2026.

Depois da implementação, os guias da secção [Documentação a atualizar](#documentação-a-atualizar) descrevem o comportamento.

## Estado de implementação e rastreabilidade

O responsável de produto pediu um único ramo e worktree novos para esta funcionalidade.
As três fases lógicas do [plano de implementação](#plano-de-implementação) foram consolidadas localmente em `feat/class-availability-engine`.
A sequência original de três pull requests não foi executada.
Os grupos de servidor e motor (2), ecrãs (3) e importação CSV (4) foram implementados e testados localmente.
A documentação dos grupos 2.7, 3.9 e 4.7 é atualizada no mesmo ramo, nos guias da secção [Documentação a atualizar](#documentação-a-atualizar).
As entregas 2.8, 3.10, 4.8, 5.1 e 5.2 do [WBS](CLASS_AVAILABILITY_WBS.md) continuam abertas.

A migração real é `backend/alembic/versions/0003_class_availability.py`, com `down_revision = "0002_class_subject_modules"`, renumerada depois de `main` integrar a cadeia de seleção de módulos por turma.

Evidência local em `.test-artifacts/*/run.json`, no commit do ramo `c7618ce`, com árvores de teste não limpas (a linha de base foi medida numa árvore limpa):

| Medição | Linha de base | Ramo da funcionalidade |
| :--- | :--- | :--- |
| Backend `fast --scope backend` | 739 | 778 |
| Frontend `fast --scope frontend` | 592 | 622 (85 ficheiros) |
| `integration` | 426 + 61 contratos | 518 + 66 contratos (artifact `1792014351559-27680`) |
| `ruff check` e `ruff format --check` | — | verde (315 ficheiros) |
| `npm run verify:checks` | — | verde |

O código e a verificação local estão presentes. A CI obrigatória final (`backend`, `frontend`, `e2e-runtime`, `e2e-browser`), a verificação manual e a produção continuam incompletas e não são reclamadas.

As provas de migração correram numa stack de teste descartável e isolada e passaram: `alembic upgrade head` (`0001 → 0002 → 0003`), `alembic check` sem drift, `alembic downgrade 0002_class_subject_modules`, nova subida para head, `python -m scripts.audit_triggers` e `python -m scripts.audit_database_integrity`. Evidência sanitizada em `.test-artifacts/cronos-avail-verify-migration-evidence.md`.

A entrega é acompanhada no pull request do ramo `feat/class-availability-engine`.

O percurso e2e local está bloqueado pela política de execução, não por credenciais em falta. As credenciais de teste do Clerk estão fornecidas fora do repositório, mas a regra de permissões nega a leitura de ficheiros `*.env` (mesmo `node --env-file`). O ficheiro de credenciais não é lido, copiado nem codificado.

A reconstrução do contentor do frontend foi tentada com `docker compose up -d --build frontend`. Falhou antes de alterar serviços porque faltam `CRONOS_APP_PASSWORD`, `POSTGRES_PASSWORD` e `VITE_CLERK_PUBLISHABLE_KEY` neste worktree novo. A configuração segura fica pendente; não se copiam valores reais de ambiente.

## Intended Reader

Este documento destina-se a engenheiros backend, frontend e do motor de horários, e a revisores.

## Prerequisites

Leia estes documentos antes da implementação:

- [Repository Agent Instructions](../../AGENTS.md).
- [Documentation Standard](../00_getting_started/DOCUMENTATION_STANDARD.md).
- [School Configuration](SCHOOL_CONFIGURATION.md).
- [Scheduler Engine](../03_scheduler_engine/README.md) e [Scheduler V1 Tech Spec](../03_scheduler_engine/SCHEDULER_V1_TECH_SPEC_V2.md).
- [Bulk Import CSV](../07_data_and_seed/BULK_IMPORT_CSV.md).
- [Security and Tenant Isolation](../08_security_quality/SECURITY_AND_TENANT_ISOLATION.md).
- [Command Reference](../00_getting_started/COMMAND_REFERENCE.md).

Carregue os skills `cronos-base`, `ponytail` (`full`), `cronos-backend`, `cronos-scheduler`, `cronos-frontend` e `cronos-frontend-designer`.
Aplique as quatro práticas obrigatórias do `AGENTS.md`: clean code, Clean Architecture, TDD e Ponytail.

## What the System Does

### Problema

Hoje, o administrador marca cada bloco da semana de um professor como Preferencial, Neutro, Evitar ou Impossível.
As turmas não têm esta opção.
A escola não consegue dizer, por exemplo, que uma turma não pode ter aulas à sexta à tarde.
O horário gerado ignora essa restrição.

### Comportamento atual observado

| Área | Comportamento | Fonte |
| :--- | :--- | :--- |
| Níveis | `PreferenceLevel`: `PREFERRED = 2`, `NEUTRAL = 1`, `AVOID = 0`, `IMPOSSIBLE = -1`. | `backend/app/models.py` |
| Guardar professores | Uma linha por bloco da versão visível da grelha. Substitui todas as linhas. Regista `TEACHER_AVAILABILITY`. | `backend/app/services/teacher_service.py` (`set_teacher_availability`) |
| Leitura para o motor | Impossível vira indisponibilidade obrigatória. Evitar vira indisponibilidade preferencial. | `backend/app/scheduler/infrastructure/snapshot.py` (`_load_unavailability`) |
| Regra do Preferencial | Com um bloco Preferencial, os blocos não preferenciais contam como Evitar. | `snapshot.py` (`_load_unavailability`) |
| Motor por recurso | O domínio já trata `UnavailableResource.CLASS` como obrigatório e como preferencial. | `backend/app/scheduler/domain/capacity.py`, `quality.py`, `candidate_validation.py`, `backend/app/scheduler/infrastructure/placement_model.py` |
| Uso atual de `CLASS` | Só blocos operacionais e aulas registadas. Nenhuma preferência da turma. | `snapshot.py` (`_load_operational_reservations`, `_load_baseline`) |
| Peso do Evitar | O custo de preferências é o quarto critério, depois das datas de conclusão e dos furos. | [Scheduler V1 Tech Spec](../03_scheduler_engine/SCHEDULER_V1_TECH_SPEC_V2.md#quality-priorities-stage-evidence-and-caching) |
| Verificação prévia | Mede o défice por atribuição (turma, disciplina, professor). Não soma as disciplinas da turma. | `capacity.py` (`aggregate_capacity_check`) |
| Falha da geração | O worker grava só `result_code` e `stop_reason`. Os diagnósticos perdem-se. | `backend/app/scheduler_v1_worker.py` (`_finish`) |
| Mensagem de falha | Texto genérico. Não diz que turma falhou. | `frontend/src/components/schedules/GenerationStatusPanel.jsx` |
| Alteração de grelha | Copia a disponibilidade dos professores por bloco, com decisão do administrador. | `backend/app/services/grid_change_service.py`, `backend/app/services/timeslot_service.py` |
| Importação CSV | Só cria recursos novos. Os modelos são fixos. | `backend/app/services/bulk_import_policy.py` |
| Janela de edição | `TeacherAvailabilityModal` usa `AvailabilityGrid`, `AvailabilityToolbar` e `useAvailabilityDraft`. | `frontend/src/components/`, `frontend/src/hooks/useAvailabilityDraft.js` |

O motor já respeita a indisponibilidade de uma turma em todas as fases.
A funcionalidade nova alimenta esse mecanismo existente.

### Decisões de produto fechadas

O responsável de produto aprovou estas decisões em 14 de outubro de 2026.

| ID | Decisão | Requisito |
| :--- | :--- | :--- |
| D01 | As turmas usam os mesmos 4 níveis e os mesmos nomes dos professores. | Preferencial, Neutro, Evitar, Impossível. |
| D02 | As turmas seguem as regras do motor dos professores. | Impossível é obrigatório. Evitar é um custo. Um Preferencial torna os outros blocos Evitar. |
| D03 | A página da turma tem um cartão "Disponibilidade". | O cartão mostra um resumo e o botão "Editar disponibilidade". |
| D04 | O botão abre a mesma janela dos professores. | Grelha, 4 ferramentas, contador e "Guardar". |
| D05 | Cada turma tem uma só grelha, que se mantém de ano para ano. | Sem chave de ano letivo. |
| D06 | Só o administrador vê e edita. | Os professores não veem a grelha das turmas. |
| D07 | Uma turma nova começa com todos os blocos em Neutro. | Sem linhas guardadas. |
| D08 | Guardar não altera o horário publicado. | Uma proposta pendente fica desatualizada. |
| D09 | Uma turma com todos os blocos Impossível bloqueia a geração. | Bloqueio na pré-validação, com ligação para a turma. |
| D10 | A mensagem de falha indica as turmas que não cabem. | Nome da turma, mínimo de horas em falta e ligação para a turma. Genérica quando a causa é uma combinação. |
| D11 | A alteração de grelha trata as turmas como os professores. | Cópia automática no bloco igual. Decisão do administrador no bloco que muda. |
| D12 | A importação CSV fica nesta entrega. | Secção "Disponibilidade das turmas" na página Importar dados. |
| D13 | O ficheiro tem uma linha por turma e por dia, e uma coluna por bloco. | O modelo traz as horas da grelha, as turmas existentes e os níveis atuais. |
| D14 | O ficheiro substitui a grelha inteira de cada turma que contém. | As turmas ausentes ficam iguais. Célula vazia é Neutro. |
| D15 | A cópia entre turmas fica nesta entrega, como "Aplicar a outras turmas…". | Lista agrupada por curso, confirmação e substituição completa da grelha das turmas escolhidas. |
| D16 | A cópia exige as alterações guardadas. | Com alterações por guardar, o botão pede "Guarde primeiro". |

O responsável de produto confirmou que não existem dados reais em produção.
A migração não precisa de preenchimento inicial nem de plano de reversão de dados.

### Âmbito

Incluído:

- Modelo de dados, migração e isolamento por organização.
- API de leitura, gravação e cópia.
- Leitura pelo motor, fingerprint e pré-validação.
- Diagnóstico por turma, persistência dos diagnósticos de falha e mensagem de falha.
- Alteração de grelha: regeneração e versões.
- Importação CSV com modelo dinâmico.
- Cartão, janela, "Aplicar a outras turmas…", secção de importação e painel de alteração de grelha.

Excluído:

- Importação CSV das preferências dos professores. O item 4 reutiliza o formato definido aqui.
- Alterações ao objetivo de otimização. O peso do Evitar muda só no item 8.
- Diagnóstico de impossibilidades que resultam de combinações de turmas e professores.
- Disponibilidade por ano letivo (D05).
- Tutorial. O tutorial não usa a página da turma.

## Why the Behavior Exists

A escola precisa de impedir aulas de uma turma em certos períodos, por exemplo por transporte ou atividades fixas.
O motor já sabe excluir e penalizar períodos de uma turma, por isso a alteração fica fora do solver.

As linhas guardam só os níveis diferentes de Neutro.
Uma linha em falta significa Neutro (D07).
Esta escolha evita o inspetor e a reparação de matriz que os professores usam.
Também reduz a cópia, a importação e a alteração de grelha às linhas com significado.
Uma restrição `CHECK` mantém uma só representação para Neutro.

A regra do Preferencial fica igual à dos professores (D02).
Duas regras diferentes para o mesmo nível confundiriam o administrador.

O diagnóstico por turma é um limite inferior provado.
Uma turma só assiste a uma aula de cada vez.
Se a soma das horas em falta da turma excede a soma dos períodos onde pode ter aula, nenhum horário completo existe.
A verificação não usa o almoço, por isso nunca acusa uma turma sem prova.

## Components and Ownership

| Responsabilidade | Implementação |
| :--- | :--- |
| Tabela e coluna de diagnósticos | Nova migração em `backend/alembic/versions/`, `backend/app/models.py`, `backend/app/scheduler/infrastructure/models.py` |
| Leitura, gravação e cópia | Novo `backend/app/services/class_availability_service.py`, `backend/app/api/v1/endpoints/classes.py`, `backend/app/schemas.py` |
| Leitura pelo motor | `backend/app/scheduler/infrastructure/snapshot.py` |
| Desempate da construção de recuperação | `backend/app/scheduler/infrastructure/recovery_construction.py` |
| Défice por turma (puro) | `backend/app/scheduler/domain/capacity.py`, `backend/app/scheduler/domain/diagnostics.py` |
| Resultado da geração inicial | `backend/app/scheduler/application/generation.py` |
| Persistência e leitura dos diagnósticos | `backend/app/scheduler_v1_worker.py`, `backend/app/scheduler/infrastructure/jobs.py`, `backend/app/scheduler/infrastructure/queries.py` |
| Pré-validação | `backend/app/services/preflight_service.py` |
| Fingerprint de geração | `backend/app/services/scheduler_fingerprint_service.py` |
| Alteração de grelha | `backend/app/services/grid_change_service.py`, `backend/app/services/timeslot_service.py` |
| Importação CSV | `backend/app/services/bulk_import_policy.py`, `backend/app/services/bulk_import_service.py`, `backend/app/api/v1/endpoints/imports.py` |
| Privacidade | `backend/scripts/privacy.py` |
| Hooks de dados | `frontend/src/features/catalog/data.js`, `frontend/src/features/imports/data.js` |
| Ecrãs | `frontend/src/pages/ClassDetails.jsx`, `frontend/src/components/TeacherAvailabilityModal.jsx`, componentes novos em `frontend/src/components/`, `frontend/src/pages/BulkImport.jsx`, `frontend/src/components/schedules/GenerationStatusPanel.jsx`, `frontend/src/features/schoolConfig/SchoolConfigSections.jsx` |

## Data or Request Flow

### Modelo de dados

Crie a tabela `class_availability`. Uma linha guarda um nível diferente de Neutro para uma turma num bloco.

| Coluna | Tipo | Regra |
| :--- | :--- | :--- |
| `organization_id` | `integer NOT NULL` | FK para `organization(id)` com `ON DELETE CASCADE`. |
| `class_id` | `integer NOT NULL` | FK composta `(organization_id, class_id)` para `class(organization_id, id)` com `ON DELETE CASCADE`. |
| `timeslot_id` | `integer NOT NULL` | FK composta `(organization_id, timeslot_id)` para `timeslot(organization_id, id)` com `ON DELETE CASCADE`. |
| `score` | `integer NOT NULL` | `CHECK (score IN (-1, 0, 2))`. Neutro nunca é guardado. |

- Chave primária: `(organization_id, class_id, timeslot_id)`.
- Índice: `(organization_id, timeslot_id)`, para a alteração de grelha.
- As FKs compostas usam as restrições existentes `uq_class_org_id` e `uq_timeslot_org_id`.

Defina o modelo `ClassAvailability` em `models.py`, com chave primária composta.
Não crie relações ORM na turma. O serviço usa `insert` e `delete` explícitos.

Acrescente a coluna `diagnostics_json jsonb NULL` a `scheduler_job_v1`.
A coluna guarda os diagnósticos de uma geração que terminou sem horário.

### Migração

Crie uma migração com `down_revision` igual à cabeça de `main` no momento da implementação.
Os itens 1 e 2 reservam `0002` e `0003`. Use o número seguinte livre, por exemplo `0004_class_availability`.

> Implementação local: a migração real é `0003_class_availability`, com `down_revision = "0002_class_subject_modules"`, após a integração da migração de seleção de módulos por turma em `main`. A cadeia mantém-se linear sobre a baseline `0001_scheduler_v1_baseline`.

1. Crie a tabela, as FKs, a chave primária, o índice e o `CHECK`.
2. Ative `ENABLE ROW LEVEL SECURITY` e `FORCE ROW LEVEL SECURITY`.
3. Crie a política `tenant_isolation` para `cronos_app`, igual à de `availability`.
4. Conceda `SELECT, INSERT, DELETE` a `cronos_app`.
5. Acrescente `diagnostics_json` a `scheduler_job_v1`.
6. O `downgrade` remove a coluna e a tabela.

Se esta migração for a primeira depois da baseline, atualize `test_migration_history_has_one_frozen_baseline`.
O teste mantém a baseline congelada e passa a exigir uma cadeia linear sem ramos.
O Tech Spec — Módulos por Turma, na branch `feat/class-module-selection`, descreve a mesma alteração.

Acrescente `"class_availability": "delete"` a `PRIVACY_TABLES` em `backend/scripts/privacy.py`.

### Contrato HTTP

| Método e rota | Ator | Comportamento |
| :--- | :--- | :--- |
| `GET /api/v1/classes/{class_id}/availability?on_date=` | `AdminActor` | Devolve `list[AvailabilitySelfRead]`, uma entrada por bloco da versão visível. Bloco sem linha devolve `score = 1`. |
| `PUT /api/v1/classes/{class_id}/availability?on_date=` | `AdminActor` | Recebe uma entrada por bloco da versão visível. Substitui as linhas da turma nesses blocos. Devolve `{"status": "success", "count": n}`. |
| `POST /api/v1/classes/{class_id}/availability/copy?on_date=` | `AdminActor` | Recebe `{"target_class_ids": [...]}`. Copia a grelha guardada da turma de origem. Devolve `{"updated_class_ids": [...]}`. |
| `GET /api/v1/imports/templates/class_availability` | `AdminActor` | Gera o modelo a partir da grelha visível e das turmas não arquivadas. |
| `POST /api/v1/imports/validate` e `/commit` | `AdminActor` | Aceitam `files.class_availability`. |
| `GET /api/v1/scheduler/jobs/{job_id}` | `ActiveActor` | Acrescenta `diagnostics`. |
| `POST /api/v1/school/grid-changes/preview` | `AdminActor` | Cada entrada de `affected_availabilities` acrescenta `classes`. |
| `GET /api/v1/readiness/prevalidation` | `AdminActor` | Acrescenta o bloqueio `CLASS_WITHOUT_AVAILABILITY`. |

Renomeie `TeacherAvailabilityPayload` para `WeeklyAvailabilityPayload`.
As rotas dos professores e da turma usam o mesmo esquema.

Regras do `PUT`, iguais às dos professores:

- IDs de bloco repetidos devolvem `400 duplicate_timeslot`.
- Um conjunto diferente dos blocos da versão visível devolve `400 bad_request`.
- Uma turma de outra organização devolve `404 resource_not_found`.
- Uma turma arquivada devolve o erro atual de turma arquivada (`400 bad_request`).

Novo esquema `ClassAvailabilityCopyRequest`:

| Campo | Tipo | Regra |
| :--- | :--- | :--- |
| `target_class_ids` | `list[StrictPositiveInt]` | Entre 1 e 500 IDs. |

Regras da cópia:

- IDs repetidos devolvem `400 bad_request`.
- A turma de origem na lista devolve `400 bad_request`.
- Uma turma de outra organização ou inexistente devolve `404 resource_not_found`.
- Uma turma de destino arquivada devolve `400 bad_request`.
- A cópia usa os blocos da versão visível em `on_date`. As linhas de outras versões não mudam.

Novo esquema `SchedulerV1JobDiagnosticRead`, dentro de `SchedulerV1JobRead.diagnostics`:

| Campo | Tipo |
| :--- | :--- |
| `code` | `str` |
| `minimum_missing_minutes` | `int \| None` |
| `class_id` | `int \| None` |
| `class_name` | `str \| None` |
| `course_id` | `int \| None` |
| `subject_name` | `str \| None` |

`queries.get_job` resolve os nomes a partir dos IDs guardados, filtrando por `organization_id`.
Uma turma apagada depois da falha aparece com `class_name = None`.

### Fluxo de gravação

1. O administrador pinta a grelha e clica em "Guardar disponibilidade".
2. O frontend envia uma entrada por bloco.
3. `class_availability_service.replace_class_availability` valida o pedido.
4. O serviço apaga as linhas da turma nos blocos da versão e insere as linhas diferentes de Neutro.
5. O serviço chama `record_scheduler_change` com `entity_type="CLASS_AVAILABILITY"` e `operation=BULK_IMPORT`.
6. `active_resource` é verdadeiro quando a turma não está arquivada e tem pelo menos uma ligação turma–disciplina.
7. Uma proposta pendente fica desatualizada pelo mecanismo atual de revisões (D08).

A cópia chama a mesma função para cada turma de destino, com a grelha da turma de origem.
Cada turma de destino gera um registo `CLASS_AVAILABILITY`.
A importação CSV também chama a mesma função, uma vez por turma.

### Regras do motor

#### Leitura das preferências

Extraia de `_load_unavailability` uma função pura no mesmo módulo:

```python
def _preference_unavailability(
    resource_type: UnavailableResource,
    scores: Iterable[tuple[int, int, int]],  # (resource_id, timeslot_id, score)
    calendar: _CalendarData,
    extra_preferred: Iterable[tuple[int, int]] = (),
) -> tuple[list[Unavailability], list[Unavailability]]:
    """Weekly preference rows become hard and soft unavailability."""
```

| Nível | Efeito |
| :--- | :--- |
| Impossível | Indisponibilidade obrigatória em todos os períodos com a assinatura do bloco. |
| Evitar | Indisponibilidade preferencial nesses períodos. |
| Preferencial | Com pelo menos um bloco Preferencial, os períodos sem bloco Preferencial ficam preferenciais. |

- `_load_unavailability` chama a função para `TEACHER`, com `teacher_preferred_timeslots` em `extra_preferred`.
- `_load_unavailability` chama a função para `CLASS`, com as linhas de `class_availability`.
- O comportamento dos professores não muda. Os testes atuais confirmam.

O domínio, a validação, a capacidade e o modelo de colocação não mudam.
`placement_model.py` e `quality.py` já penalizam `CLASS` preferencial.
`capacity.py` e `candidate_validation.py` já excluem `CLASS` obrigatório.

`recovery_construction.py` ordena as opções só pela preferência do professor.
Acrescente a preferência da turma ao mesmo critério de desempate.

#### Fingerprint

`generation_input_snapshot` acrescenta `class_availability`.
Cada entrada tem `class_id`, `timeslot_id` e `score`, por ordem de `(class_id, timeslot_id)`.
Inclua só as turmas não arquivadas.

#### Défice por turma

Estenda `aggregate_capacity_check` em `capacity.py`. `CapacityCheck` ganha `class_deficits: Mapping[int, int]`.

1. Para cada turma, some `residual_minutes` das atribuições com resto positivo.
2. Junte os períodos de `eligible_periods` dessas atribuições. Conte cada período uma vez.
3. O défice é a soma do resto menos a soma da duração dos períodos.
4. Guarde só as turmas com défice positivo.

- Reutilize os períodos elegíveis que a verificação por atribuição já calcula. Não os calcule duas vezes.
- `proven_infeasible` passa a considerar `deficits` e `class_deficits`.
- Os chamadores (`generate_complete`, `repair_published_schedule` e `diagnose_capacity`) recebem a regra pela mesma função.
- `diagnose_capacity` passa a receber o `CapacityCheck` já calculado, para não repetir o cálculo.

`diagnose_capacity` passa a devolver também um `Diagnosis` por turma com défice:

| Campo | Valor |
| :--- | :--- |
| `code` | Novo `DiagnosisCode.INSUFFICIENT_CLASS_TIME` |
| `evidence_kind` | `PROVEN_LOWER_BOUND` |
| `scope` | `CLASS:{class_id}` |
| `minimum_missing_minutes` | O défice |
| `affected_class_ids` | `(class_id,)` |

Acrescente `affected_subject_id: int | None = None` a `Diagnosis`.
`diagnose_capacity` preenche o campo nos diagnósticos `INSUFFICIENT_INTERSECTION`.

#### Diagnósticos de falha

1. `GenerationResult` ganha `diagnoses: tuple[Diagnosis, ...] = ()`.
2. Quando a verificação prova a impossibilidade, `generate_complete` devolve `OUTCOME_INFEASIBLE` com `diagnose_capacity(snapshot, check)`.
3. `RepairResult` já tem `diagnoses`. A recuperação adaptativa recebe os défices por turma pela mesma verificação.
4. `_finish` no worker recebe os diagnósticos e `finish_job` grava-os em `diagnostics_json`.
5. `diagnostics_json` usa a forma de `_diagnostics_summary` em `backend/app/scheduler/application/publishing.py`.
   Torne a função pública e acrescente `affected_subject_id`. As propostas de recuperação já usam esta forma.
6. `queries.get_job` devolve uma entrada de `diagnostics` por turma afetada, com os nomes atuais.

Uma falha sem prova por turma (pesquisa, combinação ou interrupção) não tem diagnósticos de turma.
O frontend mostra então a mensagem genérica atual (D10).

### Pré-validação

Em `PreflightService.evaluate`, depois de `MISSING_TEACHER_AVAILABILITY`, acrescente um bloqueio por turma:

| Campo | Valor |
| :--- | :--- |
| `code` | `CLASS_WITHOUT_AVAILABILITY` |
| `severity` | `BLOCKER` |
| `message` | `A turma {turma} tem todos os blocos marcados como Impossível. Marque pelo menos um bloco como Neutro, Evitar ou Preferencial.` |
| `route` | `/courses/{course_id}/classes/{class_id}` |

- O filtro segue `_collect_generation_teacher_ids`: turma não arquivada, ligação com professor e `grade_level` igual ao da turma.
- Uma turma está bloqueada quando cada bloco da versão visível tem uma linha com `score = -1`.
- A verificação é uma consulta. Uma linha em falta significa um bloco possível.

O servidor não repete este bloqueio no pedido de geração.
Uma turma sem blocos possíveis produz um défice provado, que a mensagem de falha nomeia.

### Alteração de grelha

Regeneração no lugar (`apply_grid_regeneration`, antes de existir horário):

1. Leia as linhas de `class_availability` por `(class_id, dia, início, fim)` antes de apagar os blocos.
2. Os blocos apagados levam as linhas por `ON DELETE CASCADE`.
3. Recrie as linhas nos blocos novos com a mesma assinatura. Os blocos sem correspondência ficam Neutro.

Alteração por versões (`grid_change_service.py`):

1. A análise lê as linhas de `class_availability` dos blocos atuais.
2. Cada entrada de `affected_availabilities` acrescenta `classes: [{"class_id", "score"}]`.
3. Um bloco só com turmas também cria uma entrada.
4. A fingerprint da análise inclui `class_availabilities`, por ordem.
5. A proposta copia as linhas das turmas com a mesma regra dos professores: `EXACT` ou decisão `COPY`.

`GridChangeAffectedAvailability` ganha `classes: list[dict]`, com valor por omissão `[]`.

### Remoção de turmas e de blocos

As FKs com `ON DELETE CASCADE` apagam as linhas quando a turma ou o bloco são apagados.
Uma turma arquivada mantém as linhas. A fingerprint e o motor ignoram turmas arquivadas.

### Importação CSV

#### Formato

O modelo `Cronos_DisponibilidadeTurmas_Template.csv` usa `;` e BOM UTF-8, como os outros modelos.

| Sigla do curso | Nome da turma | Dia | 08:30 | 09:20 | … |
| :--- | :--- | :--- | :--- | :--- | :--- |
| TGEI | TGEI 25/28 | Segunda | Neutro | Neutro | … |
| TGEI | TGEI 25/28 | Sexta | Neutro | Evitar | … |

- As colunas de hora são as horas de início distintas da versão visível, por ordem.
- Há uma linha por turma não arquivada e por dia com blocos. Ordem: sigla, turma, dia.
- Cada célula traz o nível guardado. Uma hora sem bloco nesse dia fica vazia.
- Sem turmas, o modelo traz só o cabeçalho.
- Sem blocos, o pedido do modelo devolve `400 bad_request` com `A escola ainda não configurou blocos.`

#### Validação

| Situação | Resultado |
| :--- | :--- |
| As três primeiras colunas diferentes do modelo | `header_invalid` ou `resource_mismatch`, como hoje. |
| Coluna de hora inválida ou repetida | Erro `header_invalid`. |
| Coluna de hora que não existe na grelha | Erro: `A grelha não tem blocos que comecem às {hora}. Descarregue um modelo novo.` |
| Falta uma hora da grelha | Erro: `Falta a coluna {hora}. Descarregue um modelo novo.` |
| Turma inexistente no curso | Erro `class_reference_missing`, como nas Atribuições. |
| Dia desconhecido ou sem blocos | Erro: `Escreva um dia com blocos na grelha, por exemplo Segunda.` |
| Turma e dia repetidos | Erro: `Esta turma já tem uma linha para este dia.` |
| Nível desconhecido | Erro: `Escreva Impossível, Evitar, Neutro ou Preferencial.` |
| Nível numa hora sem bloco nesse dia | Erro: `Este dia não tem bloco às {hora}. Deixe a célula vazia.` |

- As horas aceitam `H:MM`, `HH:MM` e `HH:MM:SS`. O Excel pode mudar o formato.
- Os dias aceitam o nome com ou sem `-feira`, acentos e maiúsculas.
- Os níveis aceitam acentos e maiúsculas diferentes.
- A turma pode existir ou vir no mesmo lote, no ficheiro de Cursos e turmas.
- O campo do erro numa célula é o título da coluna, por exemplo `08:30`.

#### Aplicação

- Cada turma do ficheiro fica com a grelha inteira do ficheiro (D14).
- Um dia sem linha conta como Neutro. Uma célula vazia conta como Neutro.
- O `commit` aplica as grelhas depois de criar cursos, turmas e atribuições.
- `created_counts["class_availability"]` conta as turmas atualizadas.
- A pré-visualização mostra sigla, turma e número de blocos diferentes de Neutro.

#### Código

- `IMPORT_RESOURCES` e `BulkImportFiles` acrescentam `class_availability`.
- `parse_resource_file` aceita cabeçalhos dinâmicos para `class_availability`. Compara só as três colunas fixas.
- `ImportSnapshot` acrescenta os blocos da versão visível: `timeslot_id`, dia e hora de início.
- Novo `_validate_class_availability` em `bulk_import_policy.py`, puro, como os outros validadores.
- Nova função pura `render_class_availability_template(blocks, classes, scores)`. O serviço carrega os dados.
- `download_template` passa a receber a sessão e a organização. Os modelos fixos não mudam.

### Interface

#### Página da turma (`ClassDetails.jsx`)

- Acrescente o cartão "Disponibilidade" depois do cartão do cabeçalho.
- Resumo sem restrições: `Sem restrições. Todos os blocos estão em Neutro.`
- Resumo com restrições: `{n} impossíveis · {n} a evitar · {n} preferenciais`. Omita os níveis com zero.
- O botão `Editar disponibilidade` abre a janela da turma.
- A turma arquivada mostra o resumo sem o botão.

#### Janela de disponibilidade

Extraia de `TeacherAvailabilityModal` um componente partilhado `AvailabilityEditorModal`.
O componente tem os estados de carga, erro e grelha vazia, a barra de ferramentas, a grelha, o rodapé e a gravação.
`TeacherAvailabilityModal` passa a configurar o componente. O comportamento dos professores não muda.

Novo `ClassAvailabilityModal`:

- Título: `Disponibilidade — {turma}`.
- Nota: `Os alunos não usam a aplicação. Esta grelha só afeta os horários gerados a partir de agora.`
- Sucesso ao guardar: toast `Disponibilidade da turma guardada.`
- O rodapé acrescenta `Aplicar a outras turmas…`.
- Com alterações por guardar, o botão fica desativado com o texto de ajuda `Guarde primeiro as alterações.` (D16).

#### Aplicar a outras turmas

1. O botão troca o corpo da janela pela lista de turmas. Não abre uma segunda janela.
2. A lista usa `useClasses` e `useCourses`. Agrupa por curso e ordena por nome.
3. Cada turma tem um `CFormCheck`. A turma de origem não aparece.
4. O rodapé mostra `Voltar` e `Aplicar a {n} turmas`, desativado com zero turmas.
5. `ConfirmationModal` pede confirmação: `Vai substituir a disponibilidade de {n} turmas pela grelha de {turma}.`
6. O sucesso mostra o toast `Disponibilidade aplicada a {n} turmas.` e volta à grelha.
7. Um erro de bloqueio aparece na janela. Um erro transitório mostra um toast.

#### Mensagem de falha (`GenerationStatusPanel.jsx`)

Com diagnósticos de turma, o estado `INFEASIBLE` mostra:

> Não é possível colocar todas as aulas. Turmas sem tempo suficiente:
> - TGEI 25/28: faltam pelo menos 3 h 20 min.
> - TM 24/27 · Matemática: faltam pelo menos 1 h 30 min em que a turma e o professor estejam livres.
>
> Reveja a disponibilidade destas turmas.

- `INSUFFICIENT_CLASS_TIME` mostra a turma. `INSUFFICIENT_INTERSECTION` mostra a turma e a disciplina.
- Cada turma é uma ligação para `/courses/{course_id}/classes/{class_id}`.
- Os minutos aparecem em horas e minutos, arredondados para cima ao minuto.
- Sem diagnósticos de turma, a mensagem genérica atual fica igual.

#### Alteração de grelha (`SchoolConfigSections.jsx`)

O texto de cada bloco afetado passa a contar professores e turmas:
`{p} professor(es) e {t} turma(s) com disponibilidade neste bloco.` Omita a parte com zero.

#### Importar dados (`BulkImport.jsx`)

Acrescente a entrada `class_availability` a `IMPORT_RESOURCES`:

- Rótulo: `Disponibilidade das turmas`. Origem: `/courses`.
- Instruções:
  - `O modelo já traz as turmas, as horas da grelha e a disponibilidade atual.`
  - `Cada linha é uma turma num dia. Cada coluna de hora é um bloco.`
  - `Escreva Impossível, Evitar, Neutro ou Preferencial. Uma célula vazia conta como Neutro.`
  - `Cada turma do ficheiro fica com a grelha do ficheiro. As turmas que não aparecem ficam iguais.`
  - `Não apague colunas de hora. Se a grelha mudar, descarregue um modelo novo.`
- `getImportFieldLabel` devolve o próprio campo quando o mapa não o tem. Assim, os erros mostram `08:30`.
- A descrição da página passa a referir a atualização da disponibilidade das turmas.

#### Hooks

- `useClassAvailability({ classId, onDate })`: chave `class-availability`.
- `useSaveClassAvailability()`: grava o pedido na cache, como o hook dos professores. Invalida `class-availability` e chama `invalidatePreparationQueries`.
- `useCopyClassAvailability()`: invalida `class-availability` e chama `invalidatePreparationQueries`.
- A importação acrescenta `class-availability` a `IMPORT_INVALIDATIONS`.

## Contracts and Invariants

- Toda a consulta a `class_availability` filtra por `organization_id`. A RLS forçada protege a tabela.
- Neutro nunca é guardado. Uma linha em falta significa Neutro.
- Os níveis têm o mesmo efeito no motor para professores e turmas.
- Guardar, copiar e importar substituem a grelha inteira da turma na versão visível.
- Um diagnóstico de turma é sempre um limite inferior provado.
- A mensagem de falha nunca nomeia uma turma sem prova.
- Só o administrador lê e escreve a disponibilidade das turmas.

## States and Transitions

| De | Para | Efeito |
| :--- | :--- | :--- |
| Bloco Neutro | Bloco Impossível ou Evitar | A geração seguinte exclui ou penaliza os períodos. |
| Sem blocos Preferencial | Com um bloco Preferencial | Os outros blocos da turma passam a contar como Evitar. |
| Pelo menos um bloco possível | Todos os blocos Impossível | A pré-validação bloqueia a geração. |
| Proposta pendente | Gravação, cópia ou importação | A proposta fica desatualizada. |

## Failure Modes

| Falha | Comportamento |
| :--- | :--- |
| Conjunto de blocos inválido no `PUT` | `400`. A grelha não muda. |
| Turma de outra organização | `404 resource_not_found`. |
| Turma arquivada | `400 bad_request`. |
| Cópia com turma inválida | O pedido falha inteiro. Nenhuma turma muda. |
| Ficheiro CSV com erros | A validação lista os erros. O `commit` não grava nada. |
| Turma sem tempo suficiente | A geração termina `INFEASIBLE` com o diagnóstico da turma. |
| Impossibilidade por combinação | A geração termina com a mensagem genérica. |
| Rede falha durante a gravação | Toast de erro. A grelha mantém o rascunho. |

## Plano de implementação

Entregue em três pull requests a partir de `main`. Cada passo começa com um teste que falha.

| PR | Conteúdo | Efeito visível |
| :--- | :--- | :--- |
| 1 — Servidor e motor | Migração, modelo, privacidade, serviço, rotas, leitura pelo motor, desempate da recuperação, fingerprint, pré-validação, alteração de grelha, défice por turma e diagnósticos persistidos. | Bloqueio na pré-validação. A API devolve diagnósticos. |
| 2 — Ecrãs | Cartão, `AvailabilityEditorModal`, `ClassAvailabilityModal`, aplicar a outras turmas, mensagem de falha e painel da alteração de grelha. | A funcionalidade completa sem CSV. |
| 3 — Importação CSV | Modelo dinâmico, validação, aplicação e secção na página Importar dados. | A importação. |

Os PRs 2 e 3 começam depois de o PR 1 estar integrado em `main`. Podem correr em paralelo.

> Implementação local: as três fases foram consolidadas num único ramo e worktree, `feat/class-availability-engine`.
> A sequência original de três pull requests não foi executada.
> Ver [Estado de implementação e rastreabilidade](#estado-de-implementação-e-rastreabilidade).

O [WBS — Disponibilidade das Turmas](CLASS_AVAILABILITY_WBS.md) é dono da decomposição do trabalho.
Define os pacotes, as dependências, o caminho crítico e os critérios de conclusão.

### Ordem com os itens 1 e 2

- O número da migração depende da ordem de integração em `main`. O último PR a integrar renumera.
- Os três itens alteram `snapshot.py`, `preflight_service.py` e `scheduler_fingerprint_service.py`. Cada PR que integrar depois resolve os conflitos.
- O item 1 muda os minutos de cada atribuição. O défice por turma usa `residual_minutes`, por isso acompanha a seleção sem alterações.
- O item 2 exige que uma aula conjunta respeite todas as turmas (J11). A regra obrigatória já cobre a disponibilidade das turmas.
- Quando o item 2 integrar, o défice por turma conta cada unidade conjunta uma vez em cada turma membro. O item 2 atualiza o teste.

## Testes

### Domínio (unitários)

Em `backend/tests/unit/` (ficheiros de capacidade, diagnóstico e geração existentes, ou novos do mesmo padrão):

- Uma turma com a soma das disciplinas acima dos períodos livres tem défice igual à diferença.
- Um período elegível para duas disciplinas da turma conta uma vez.
- Uma turma com tempo suficiente não tem défice.
- Uma turma com atribuições concluídas não tem défice.
- `diagnose_capacity` devolve `INSUFFICIENT_CLASS_TIME` com `CLASS:{id}` e o défice.
- `diagnose_capacity` preenche `affected_subject_id` em `INSUFFICIENT_INTERSECTION`.
- `generate_complete` com défice por turma devolve `OUTCOME_INFEASIBLE` e os diagnósticos, sem pesquisa.
- `measure_initial_quality` conta como preferência violada uma aula num período Evitar da turma.

### Servidor e motor (integração)

| Cenário | Ficheiro sugerido |
| :--- | :--- |
| A tabela tem RLS forçada e a política `tenant_isolation`. | `backend/tests/contracts/test_rls_database_policies.py` |
| O `CHECK` recusa `score = 1`. | Teste novo `test_class_availability.py` |
| `GET` devolve Neutro para blocos sem linha. | `test_class_availability.py` |
| `PUT` guarda só níveis diferentes de Neutro e regista `CLASS_AVAILABILITY`. | `test_class_availability.py` |
| `PUT` recusa blocos repetidos, conjunto inválido e turma arquivada. | `test_class_availability.py` |
| `PUT` e cópia com turma de outra organização devolvem 404. | `test_tenant_isolation_business.py` |
| A cópia substitui a grelha dos destinos e recusa a origem na lista. | `test_class_availability.py` |
| Professor não lê nem escreve a disponibilidade das turmas. | `test_teacher_role_regression.py` |
| Impossível da turma vira indisponibilidade obrigatória `CLASS` no snapshot. | `test_scheduler_v1_adaptive_changes.py` ou teste novo de snapshot |
| Evitar e a regra do Preferencial viram indisponibilidade preferencial `CLASS`. | Mesmo ficheiro |
| A disponibilidade dos professores no snapshot não muda. | Testes atuais |
| Uma geração completa não coloca aulas da turma num bloco Impossível. | `test_scheduler_v1_api.py` ou teste novo |
| Gravar a disponibilidade de uma turma com disciplinas desatualiza a proposta pendente. | `test_scheduler_v1_rule_revisions.py` |
| A fingerprint muda quando a disponibilidade da turma muda. | `test_scheduler_fingerprint_service.py` |
| A pré-validação devolve `CLASS_WITHOUT_AVAILABILITY` com a rota da turma. | `backend/tests/contracts/test_preflight_service.py` |
| A regeneração da grelha mantém os níveis no bloco igual. | `test_grid_version_service.py` |
| A análise da alteração de grelha lista as turmas por bloco. | `test_grid_change_preview.py` |
| A proposta da alteração de grelha copia as linhas das turmas com `EXACT` e `COPY`. | `test_grid_change_proposal.py` |
| Um job `INFEASIBLE` grava e devolve os diagnósticos com os nomes das turmas. | `test_scheduler_v1_lifecycle.py` |
| O modelo CSV traz as horas, as turmas e os níveis atuais. | `test_bulk_import.py` |
| A validação CSV cobre cada linha da tabela de validação. | `backend/tests/unit/` (política pura) e `test_bulk_import.py` |
| O `commit` CSV substitui as grelhas, aceita turmas do mesmo lote e deixa as outras iguais. | `test_bulk_import.py` |

### Frontend

- `frontend/src/test/TeacherAvailabilityModal.test.jsx`: continua verde depois da extração.
- Novo `frontend/src/test/ClassAvailabilityModal.test.jsx`: carga, gravação, `Guarde primeiro`, lista de turmas, confirmação e toast.
- `frontend/src/test/ClassDetails.test.jsx`: resumo sem restrições, resumo com contagens e turma arquivada.
- `frontend/src/test/featureDataHooks.test.jsx`: os três hooks usam as rotas certas e invalidam as consultas.
- `frontend/src/test/GenerationStatusPanel.test.jsx`: lista de turmas com ligações, e mensagem genérica sem diagnósticos.
- `frontend/src/test/SchoolConfigGridChange.test.jsx`: contagem de professores e turmas.
- `frontend/src/test/BulkImport.test.jsx`: secção nova, instruções e erro com o título da coluna.

### E2E

Acrescente um percurso em `frontend/e2e/readiness/` ou numa pasta nova:
marque todos os blocos de uma turma como Impossível, confirme o bloqueio na pré-validação e aplique a grelha de outra turma.

## Verification Procedure

Use os comandos da [Command Reference](../00_getting_started/COMMAND_REFERENCE.md#verification-by-change-type) para cada tipo de alteração:

1. Lógica pura do domínio: `fast --scope backend -- -k scheduler`.
2. Endpoint, serviço, importação e consultas: `fast --scope backend`, depois `integration -- -k <área>`.
3. Migração e RLS: `integration` completo, depois as verificações de drift e de triggers.
4. Motor, jobs e propostas: `integration -- -k scheduler`. A CI não corre todos estes testes.
5. Frontend: `fast --scope frontend -- <ficheiro>`, depois `npm run verify:checks`.
6. Percurso: `e2e --project <nome>`, quando existirem as credenciais de teste do Clerk.
7. Reconstrua o contentor do frontend depois dos PRs 2 e 3.
8. CI: `backend`, `frontend`, `e2e-runtime` e `e2e-browser` verdes antes do merge. Depois, `Deploy check` em `main`.

Verificação manual depois do PR 3:

1. Abra uma turma como administrador. Confirme o resumo `Sem restrições`.
2. Marque sexta à tarde como Impossível e guarde. Confirme o resumo.
3. Aplique a grelha a outra turma. Confirme o resumo da outra turma.
4. Gere o horário. Confirme que nenhuma das duas turmas tem aulas à sexta à tarde.
5. Marque todos os blocos de uma turma como Impossível. Confirme o bloqueio em `/schedules`.
6. Descarregue o modelo CSV, altere uma turma, importe e confirme a grelha.

## Riscos e limitações

- O Evitar pesa menos do que a conclusão e os furos. Uma turma pode ter aulas num bloco Evitar. O item 8 trata o peso.
- Com um bloco Preferencial, Neutro e Evitar têm o mesmo efeito. É a regra atual dos professores (D02).
- O défice por turma ignora o almoço e os dias sem horas suficientes. A mensagem pode ficar genérica num caso impossível.
- O modelo CSV e a cópia usam só a versão visível da grelha. Uma versão futura pendente edita-se na janela, com `on_date`.
- Uma turma arquivada mantém as linhas. Se for reativada, recupera a grelha.
- `queries.get_job` mostra o nome atual da turma, não o nome no momento da falha.

## Documentação a atualizar

| Documento | Alteração |
| :--- | :--- |
| [School Configuration](SCHOOL_CONFIGURATION.md) | Disponibilidade das turmas e efeito na alteração de grelha. |
| [Data Model](../01_system_architecture/DATA_MODEL.md) | Tabela `class_availability` e coluna `diagnostics_json`. |
| [API Reference](../05_backend_api/API_REFERENCE.md) | Rotas da disponibilidade da turma, `diagnostics` do job e `classes` da alteração de grelha. |
| [Bulk Import CSV](../07_data_and_seed/BULK_IMPORT_CSV.md) | Secção "Disponibilidade das turmas" e modelo dinâmico. |
| [Scheduler Engine](../03_scheduler_engine/README.md) | Preferências das turmas, défice por turma e diagnósticos de falha. |
| [Feedback Message Matrix](../06_frontend_ux/FEEDBACK_MESSAGE_MATRIX.md) | Mensagens novas da janela, da cópia, da importação e da falha. |
| [Glossary](../00_getting_started/GLOSSARY.md) | Termo "disponibilidade da turma", se o glossário o exigir. |

## Source Map

- Modelos: `backend/app/models.py`, `backend/app/scheduler/infrastructure/models.py`
- Snapshot: `backend/app/scheduler/infrastructure/snapshot.py`
- Domínio: `backend/app/scheduler/domain/capacity.py`, `diagnostics.py`, `candidate.py`
- Geração e worker: `backend/app/scheduler/application/generation.py`, `backend/app/scheduler_v1_worker.py`
- Serviços: `backend/app/services/teacher_service.py`, `preflight_service.py`, `scheduler_fingerprint_service.py`, `grid_change_service.py`, `timeslot_service.py`, `bulk_import_policy.py`
- Ecrãs: `frontend/src/pages/ClassDetails.jsx`, `frontend/src/components/TeacherAvailabilityModal.jsx`, `frontend/src/components/AvailabilityGrid.jsx`, `frontend/src/pages/BulkImport.jsx`

## Related Documents

- [School Configuration](SCHOOL_CONFIGURATION.md)
- [Scheduler V1 Tech Spec](../03_scheduler_engine/SCHEDULER_V1_TECH_SPEC_V2.md)
- [Bulk Import CSV](../07_data_and_seed/BULK_IMPORT_CSV.md)
- [Resource Removal](../05_backend_api/RESOURCE_REMOVAL.md)
