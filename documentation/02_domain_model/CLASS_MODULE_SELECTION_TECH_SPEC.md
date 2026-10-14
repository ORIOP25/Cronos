# Tech Spec — Módulos por Turma

## Purpose

Este documento especifica a seleção de módulos por turma.
Define decisões de produto, modelo de dados, contratos, regras do motor, plano TDD e critérios de aceitação.

**Estado:** proposto. A implementação ainda não começou.
**Data:** 14 de outubro de 2026.
**Base observada:** branch `main` no commit `4773d76`.
**Origem:** item 1 dos pedidos da escola piloto, reunião de 13 de outubro de 2026.

Depois da implementação, os guias da secção [Documentação a atualizar](#documentação-a-atualizar) descrevem o comportamento.
Este documento fica como registo das decisões.

## Intended Reader

Este documento destina-se a engenheiros backend, frontend e do motor de horários, e a revisores.

## Prerequisites

Leia estes documentos antes da implementação:

- [Repository Agent Instructions](../../AGENTS.md).
- [Documentation Standard](../00_getting_started/DOCUMENTATION_STANDARD.md).
- [Professional Education](PROFESSIONAL_EDUCATION.md).
- [Scheduler Engine](../03_scheduler_engine/README.md) e [Scheduler V1 Tech Spec](../03_scheduler_engine/SCHEDULER_V1_TECH_SPEC_V2.md).
- [Security and Tenant Isolation](../08_security_quality/SECURITY_AND_TENANT_ISOLATION.md).
- [Command Reference](../00_getting_started/COMMAND_REFERENCE.md).

Carregue os skills `cronos-base`, `ponytail` (`full`), `cronos-domain`, `cronos-backend`, `cronos-scheduler` e `cronos-frontend`.
Aplique as quatro práticas obrigatórias do `AGENTS.md`: clean code, Clean Architecture, TDD e Ponytail.

## What the System Does

### Problema

Hoje, uma turma com uma disciplina recebe todos os módulos dessa disciplina.
Na realidade, uma turma pode ter só alguns módulos, por exemplo o 1, o 3 e o 5.
O horário gerado inclui horas que a turma não precisa.
A escola não consegue representar o plano curricular real.

### Comportamento atual observado

| Área | Comportamento | Fonte |
| :--- | :--- | :--- |
| Projeção curricular | Cria um `CurricularRequirement` por cada módulo da disciplina. | `backend/app/scheduler/infrastructure/curriculum.py` (`sync_curricular_projection`) |
| Anos escolares | A ligação turma–disciplina tem chave `grade_level`. Cada ano projeta todos os módulos. | `backend/app/models.py` (`ClassSubjectLink`) |
| Requisito removido | O sync apaga o requisito de um módulo que deixou de se aplicar. | `curriculum.py` |
| Histórico | `completed_by_module` rejeita créditos de módulos fora dos requisitos. | `backend/app/scheduler/domain/demand.py` |
| Progresso | `_build_subject_with_progress` usa todos os módulos da disciplina. | `backend/app/services/class_service.py` |
| Pré-validação | Verifica se a disciplina tem módulos. Não verifica a turma. | `backend/app/services/preflight_service.py` |
| Migrações | `test_migration_history_has_one_frozen_baseline` aceita apenas a baseline. | `backend/tests/unit/test_migration_tenant_ref_contract.py` |
| Fixtures | `seed_v1_assignment` cria `ClassSubjectLink` diretamente. | `backend/tests/_support/scheduler_v1.py` |

O segundo ponto tem um efeito direto: as turmas de 10.º, 11.º e 12.º recebem todos os módulos da mesma disciplina.
Os dados de exemplo em [sample_import_48_classes](../07_data_and_seed/sample_import_48_classes/) mostram este caso.

O quarto ponto impede a regra D06 sem alterações.
Um módulo desmarcado com sumários deixaria créditos sem requisito, e o motor falharia.

### Decisões de produto fechadas

O responsável de produto aprovou estas decisões em 14 de outubro de 2026.

| ID | Decisão | Requisito |
| :--- | :--- | :--- |
| D01 | A seleção pertence ao ano escolar atual da turma. | Guardar a seleção na ligação turma–disciplina (`class_subject_link`), que tem chave `grade_level`. |
| D02 | A checklist fica na página "Disciplinas e Professores". | Rota `/courses/:courseId/classes/:classId/subjects`. Uma linha expansível por disciplina. |
| D03 | Uma disciplina nova na turma tem todos os módulos marcados. | Aplica-se ao ecrã e ao CSV de Atribuições. |
| D04 | As ligações existentes ficam com todos os módulos marcados. | A migração faz o preenchimento inicial. |
| D05 | Um módulo novo numa disciplina existente não fica marcado em nenhuma turma. | A página Disciplinas avisa o administrador. |
| D06 | Desmarcar é sempre permitido. | Inclui módulos com histórico e o último módulo marcado. |
| D07 | O histórico nunca se apaga. | Um módulo retirado com histórico fica fechado nos minutos já executados. |
| D08 | Uma disciplina da turma sem módulos marcados bloqueia a geração. | Bloqueio na pré-validação e no servidor. A mensagem indica as duas saídas. |
| D09 | Cada clique grava logo. | Os controlos ficam bloqueados durante a gravação. |
| D10 | O progresso conta só os módulos marcados. | Progresso da turma, progresso do professor e painel inicial. |
| D11 | Voltar a marcar um módulo retoma o histórico. | As horas já registadas voltam a contar. |

### Âmbito

Incluído:

- Modelo de dados, migração e isolamento por organização.
- API de leitura e gravação da seleção.
- Projeção curricular, regra de módulos retirados e leitores do motor.
- Pré-validação, prontidão e fingerprint de geração.
- Progresso da turma, do professor e do painel.
- Ecrãs "Disciplinas e Professores", página da turma, página Disciplinas e tutorial.

Excluído:

- Aplicar a seleção a várias turmas de uma vez.
- Uma coluna de módulos no CSV de Atribuições. O CSV marca todos os módulos (D03).
- Alterações ao solver CP-SAT ou ao objetivo de otimização.
- A remoção de uma disciplina inteira com histórico. Ver [Problema relacionado fora de âmbito](#problema-relacionado-fora-de-âmbito).

## Why the Behavior Exists

A escola tem de representar o plano curricular real de cada turma e de cada ano.
O motor só deve planear as horas que a turma vai dar.
A seleção por ano acompanha o modelo existente, em que a ligação turma–disciplina tem chave `grade_level`.

A regra de fechar um módulo retirado preserva o ledger append-only.
O Scheduler V1 Tech Spec exige "Never rewrite execution evidence" (D18).
Fechar o módulo em vez de o apagar mantém a reprodução do histórico válida.
Os algoritmos de planeamento e os validadores do domínio não mudam.

## Components and Ownership

| Responsabilidade | Implementação |
| :--- | :--- |
| Tabela de seleção e coluna `planned` | Nova migração em `backend/alembic/versions/`, `backend/app/models.py`, `backend/app/scheduler/infrastructure/models.py` |
| Leitura e gravação da seleção | `backend/app/services/class_service.py`, `backend/app/api/v1/endpoints/classes.py`, `backend/app/schemas.py` |
| Regra do módulo retirado (pura) | `backend/app/scheduler/domain/demand.py` |
| Projeção curricular | `backend/app/scheduler/infrastructure/curriculum.py` |
| Visão de planeamento dos requisitos | `backend/app/scheduler/infrastructure/progress.py` |
| Leitores do motor | `snapshot.py`, `operations.py`, `occurrences.py` em `backend/app/scheduler/infrastructure/` |
| Painel e alteração de grelha | `backend/app/services/dashboard_service.py`, `backend/app/services/grid_change_service.py` |
| Pré-validação | `backend/app/services/preflight_service.py` |
| Prontidão | `backend/app/services/school_readiness_service.py` |
| Fingerprint de geração | `backend/app/services/scheduler_fingerprint_service.py` |
| Progresso do professor | `backend/app/services/teacher_service.py` |
| Privacidade | `backend/scripts/privacy.py` |
| Hooks de dados | `frontend/src/features/catalog/data.js` |
| Ecrãs | `frontend/src/pages/ClassSubjects.jsx`, `ClassDetails.jsx`, `Subjects.jsx` |
| Tutorial | `frontend/src/features/tutorial/tutorialApiAdapter.js` |

## Data or Request Flow

### Modelo de dados

Crie a tabela `class_subject_module`. Uma linha representa um módulo marcado numa ligação turma–disciplina.

| Coluna | Tipo | Regra |
| :--- | :--- | :--- |
| `organization_id` | `integer NOT NULL` | FK para `organization(id)` com `ON DELETE CASCADE`. |
| `class_subject_link_id` | `integer NOT NULL` | FK composta `(organization_id, class_subject_link_id)` para `class_subject_link(organization_id, id)` com `ON DELETE CASCADE`. |
| `module_id` | `integer NOT NULL` | FK composta `(organization_id, module_id)` para `module(organization_id, id)` com `ON DELETE CASCADE`. |

- Chave primária: `(organization_id, class_subject_link_id, module_id)`. Segue o padrão de `course_subject_link`.
- Índices: `organization_id` e `(organization_id, module_id)`.
- As FKs compostas usam as restrições existentes `uq_class_subject_link_org_id` e `uq_module_org_id`.
- O serviço valida que o módulo pertence à disciplina da ligação. A base de dados não cobre esta regra.

Acrescente a coluna `planned boolean NOT NULL DEFAULT true` a `curricular_requirement`.
`planned = false` marca um módulo retirado que tem histórico.

Defina a tabela como `Table` em `models.py`, como `course_subject_link`.
Não crie uma relação ORM `secondary`. As FKs compostas partilham `organization_id`.
O serviço usa `insert` e `delete` explícitos na tabela.

### Migração

Crie `0002_class_subject_modules` com `down_revision = "0001_scheduler_v1_baseline"`.
É a primeira migração depois da consolidação.

1. Crie a tabela, as FKs, os índices e a chave primária.
2. Ative `ENABLE ROW LEVEL SECURITY` e `FORCE ROW LEVEL SECURITY`.
3. Crie a política `tenant_isolation` para `cronos_app`, igual à de `class_subject_link`.
4. Conceda `SELECT, INSERT, DELETE` a `cronos_app`.
5. Preencha a tabela com todos os módulos de cada ligação existente (D04).
6. Acrescente a coluna `planned` a `curricular_requirement`.
7. O `downgrade` remove a coluna e a tabela.

O preenchimento inicial corre como `cronos_migrator`, que tem `BYPASSRLS`:

```sql
INSERT INTO class_subject_module (organization_id, class_subject_link_id, module_id)
SELECT l.organization_id, l.id, m.id
FROM class_subject_link l
JOIN module m ON m.organization_id = l.organization_id AND m.subject_id = l.subject_id;
```

Atualize `test_migration_history_has_one_frozen_baseline` para a nova política.
O teste mantém a baseline congelada e passa a exigir uma cadeia linear sem ramos.
O [CONTRIBUTING](../00_getting_started/CONTRIBUTING.md) já define esta regra.
Esta alteração adapta o contrato e não enfraquece nenhuma proteção.

Acrescente `"class_subject_module": "delete"` a `backend/scripts/privacy.py`.

### Contrato HTTP

| Método e rota | Alteração |
| :--- | :--- |
| `GET /api/v1/classes/{class_id}/subjects` | Cada disciplina inclui `modules`, ordenado por `order`. |
| `POST /api/v1/classes/{class_id}/subjects` | Contrato igual. Marca todos os módulos da disciplina (D03). |
| `PATCH /api/v1/classes/{class_id}/subjects/{subject_id}` | Aceita `module_ids` opcional. Substitui a seleção. |
| `GET /api/v1/classes/{class_id}` | Mostra só os módulos marcados. Os totais contam só esses módulos. |
| `PATCH /api/v1/classes/{class_id}/progress` | Rejeita módulos não marcados, com o erro atual de módulo fora do currículo. |
| `GET /api/v1/readiness/prevalidation` | Acrescenta o bloqueio `CLASS_SUBJECT_WITHOUT_MODULES`. |
| Pedidos de geração e de alteração de grelha | Recusam com `CLASS_SUBJECT_WITHOUT_MODULES` (D08). |

Novo esquema `ClassSubjectModuleRead`, dentro de `ClassSubjectRead.modules`:

| Campo | Tipo |
| :--- | :--- |
| `id` | `int` |
| `name` | `str` |
| `code` | `str \| None` |
| `hours_total` | `float` |
| `order` | `int` |
| `selected` | `bool` |

`ClassSubjectUpdate` ganha `module_ids: list[int] | None`.
O serviço usa `exclude_unset`, como já faz para `teacher_id`.
O pedido pode enviar `teacher_id`, `module_ids` ou ambos.

Regras de validação de `module_ids`:

- Uma lista vazia é válida (D06).
- IDs repetidos devolvem `400 bad_request`.
- Um módulo de outra disciplina devolve `400 bad_request`.
- Um módulo de outra organização devolve `404 resource_not_found`. A consulta filtra por `organization_id`.
- Uma turma arquivada devolve o erro atual de turma arquivada.

### Fluxo de gravação

1. O administrador clica num módulo. O frontend envia a lista completa de `module_ids`.
2. O serviço valida a lista e substitui as linhas de `class_subject_module`.
3. O serviço chama `record_scheduler_change` com `entity_type="CLASS_SUBJECT_ASSIGNMENT"` e `operation=UPDATE`.
4. `_class_subject_snapshot` inclui `module_ids` ordenados, para o registo de alterações.
5. A resposta devolve a lista atualizada. O frontend atualiza a cache e invalida as consultas afetadas.
6. Uma proposta pendente fica desatualizada pelo mecanismo atual de revisões.

`add_class_subject` insere todos os módulos da disciplina depois de criar a ligação.
A importação CSV chama `add_class_subject`, por isso não precisa de alteração.

### Regras do motor

#### Projeção curricular

`sync_curricular_projection` passa a ler `class_subject_module`:

| Situação do módulo | Requisito |
| :--- | :--- |
| Marcado | `planned = true`, `required_minutes = module.required_minutes`, `sequence = module.order + 1`. |
| Desmarcado, com créditos de execução na atribuição | A linha fica com `planned = false`. |
| Desmarcado, sem créditos de execução | A linha é apagada, como hoje. |

- `sequence = module.order + 1` mantém a sequência estável quando a seleção muda. O domínio exige só sequências únicas.
- Uma ligação ativa com professor e sem módulos marcados levanta `SnapshotConfigurationError("CLASS_SUBJECT_WITHOUT_MODULES", ...)`.
- O caso inclui disciplinas sem módulos, que hoje o sync ignora em silêncio.
- `scheduler.py` e `grid_change_service.py` já traduzem `SnapshotConfigurationError`.
- O tratamento de atribuições removidas com histórico não muda.

Um crédito de execução é uma linha de `CurricularExecutionCredit` com o `module_id`, numa execução da atribuição.

#### Regra do módulo retirado

Crie uma função pura em `demand.py`:

```python
def close_retired_modules(
    modules: Sequence[ModuleRequirement],
    retired: AbstractSet[int],
    completed: Mapping[int, int],
) -> tuple[tuple[ModuleRequirement, ...], dict[int, int]]:
    """Planning view: a retired module is closed at its executed minutes."""
```

| Módulo | Resultado |
| :--- | :--- |
| Planeado | Fica igual. |
| Retirado com minutos executados | `required_minutes` passa a ser igual aos minutos executados. Fica concluído. |
| Retirado sem minutos executados | Sai da lista. |

A função devolve também os minutos executados, limitados aos módulos que ficam.
Um módulo concluído não recebe créditos novos nem aulas futuras.
`frontier_credit` e `project_module_slices` já saltam módulos concluídos.

#### Leitores dos requisitos

Crie um carregador em `progress.py` que devolve a visão de planeamento:

1. Carrega todas as linhas de requisito, incluindo `planned = false`.
2. Reproduz o histórico com os minutos do catálogo, através de `completed_by_module`.
3. Aplica `close_retired_modules`.

| Leitor | Visão |
| :--- | :--- |
| `snapshot.py` (`_load_assignments` e `_build_assignments`) | Planeamento. Carregue os minutos executados antes de construir as atribuições. |
| `proposals.py` | Herda a visão do `bundle.snapshot`. Confirme as duas chamadas a `split_version_history`. |
| `operations.py` (crédito do sumário com `frontier_credit`) | Planeamento. |
| `occurrences.py` (capacidade da substituição) | Planeamento. |
| `progress.py` (liquidação de dívida no reinício do ano) | Planeamento. |
| `progress.py` (`_requirements` e `_load_assignment_requirements`) | Todas as linhas. Reproduzem o histórico. |
| `dashboard_service.py` (progresso das turmas) | Só `planned = true`. |
| `grid_change_service.py` (procura da grelha) | Só `planned = true`. |
| `resource_removal.py` (remoção de módulos) | Todas as linhas. Um módulo com histórico continua protegido. |

O motor reprojeta as aulas publicadas não registadas com os requisitos atuais (`_reproject_baseline`).
As aulas registadas entram como ocupação e são copiadas para a proposta depois da pesquisa.
Por isso, as aulas futuras de um módulo retirado passam para o módulo marcado seguinte.

Confirme que nenhuma validação compara os slices das aulas registadas com os requisitos fechados.
Uma falta registada num módulo retirado pode ter slices além dos minutos executados.
O cenário de integração "falta registada num módulo retirado" cobre este caso.

### Pré-validação, prontidão e fingerprint

Pré-validação, em `PreflightService.evaluate`, depois de `INVALID_TEACHER_ASSIGNMENT`:

| Campo | Valor |
| :--- | :--- |
| `code` | `CLASS_SUBJECT_WITHOUT_MODULES` |
| `severity` | `BLOCKER` |
| `message` | `A turma {turma} tem a disciplina {disciplina} sem módulos selecionados. Remova a disciplina ou selecione pelo menos um módulo.` |
| `route` | `/courses/{course_id}/classes/{class_id}/subjects` |

O filtro segue `invalid_assignment_rows`: turma não arquivada e `grade_level` igual ao da turma.

Prontidão: em `evaluate_bases`, `valid_link` passa a exigir um módulo marcado com `required_minutes > 0`.

Fingerprint: `generation_input_snapshot` acrescenta `class_subject_modules`.
Cada entrada tem `class_id`, `subject_id`, `grade_level` e `module_id`, por ordem.
Uma alteração da seleção conta como alteração para a decisão de nova geração.

### Progresso

`_build_subject_with_progress` recebe os módulos marcados em vez de `subject.modules`.
`get_class_full_details`, `update_class_progress` e `get_teacher_progress` passam esses módulos.
Uma disciplina sem módulos marcados mostra zero horas e uma lista vazia.

### Interface

#### Disciplinas e Professores (`ClassSubjects.jsx`)

- Cada `SubjectRow` mostra um botão `Módulos: {marcados} de {total} · {horas} h`.
- O botão tem `aria-expanded` e `aria-controls`.
- A lista expandida tem um `CFormCheck` por módulo, com o rótulo `{código} {nome} · {horas} h`. O código é opcional.
- Cada alteração chama a mutação com a lista completa. Os controlos ficam desativados enquanto a mutação corre.
- O sucesso mostra o toast `Módulos atualizados.` com um `id` fixo, para não acumular toasts.
- Um erro transitório mostra um toast. Um bloqueio mostra o erro junto à lista, como `teacherBlock`.
- Sem módulos marcados, a linha mostra o ícone de aviso e `Sem módulos`, como `Sem professor`.
- O cabeçalho acrescenta `{n} sem módulos` quando `n > 0`.
- Uma disciplina sem módulos mostra `Esta disciplina não tem módulos. Adicione-os em Disciplinas.`
- No tutorial e em `readOnly`, a lista é só de leitura.

#### Página da turma (`ClassDetails.jsx`)

- A tabela "Disciplinas & Professores" acrescenta a coluna `Módulos`, com `{marcados}/{total}`.
- O progresso por disciplina mostra só os módulos marcados. A API já os filtra.
- Uma disciplina sem módulos marcados mostra `Nenhum módulo selecionado para esta turma.`

#### Disciplinas (`Subjects.jsx`)

Ao atualizar uma disciplina existente com um módulo novo (sem `id`), mostre um só toast:
`Disciplina atualizada. Os módulos novos não foram marcados nas turmas. Marque-os nas turmas que os vão ter.`

#### Hooks

- Renomeie `useUpdateClassSubjectTeacher` para `useUpdateClassSubject`.
- O hook aceita `{ classId, subjectId, teacherId, moduleIds }` e envia só os campos definidos.
- O sucesso grava a resposta em `class-subjects` e invalida `classes` e `teacher-progress`.
- O sucesso mantém `invalidatePreparationQueries`.
- `getClassSubjects` no adaptador do tutorial devolve `modules`, todos com `selected: true`.

## Contracts and Invariants

- Toda a consulta à seleção filtra por `organization_id`. A RLS forçada protege a tabela.
- Um módulo marcado pertence à disciplina da ligação.
- A seleção nunca apaga histórico de execução.
- Um módulo retirado com histórico fica concluído para o planeamento. Não recebe créditos novos.
- A reprodução do histórico usa sempre os minutos do catálogo.
- Uma ligação ativa sem módulos marcados nunca chega ao solver.
- O progresso conta só os módulos marcados.

## States and Transitions

| De | Para | Efeito no motor |
| :--- | :--- | :--- |
| Marcado | Desmarcado, sem créditos | O requisito é apagado na geração seguinte. |
| Marcado | Desmarcado, com créditos | O requisito fica `planned = false` e concluído para o planeamento. |
| Desmarcado | Marcado | O requisito volta a `planned = true` com os minutos do catálogo. O histórico conta outra vez. |
| Um ou mais marcados | Nenhum marcado | A pré-validação e o servidor bloqueiam a geração. |

## Failure Modes

| Falha | Comportamento |
| :--- | :--- |
| Módulo de outra disciplina | `400 bad_request`. A seleção não muda. |
| Módulo de outra organização | `404 resource_not_found`. |
| Disciplina da turma sem módulos marcados | `BLOCKER` na pré-validação. A geração devolve `CLASS_SUBJECT_WITHOUT_MODULES`. |
| Créditos de um módulo retirado | O carregador fecha o módulo. O motor não falha. |
| Rede falha durante a gravação | Toast de erro. A lista volta ao estado do servidor. |

## Plano de implementação

Entregue em dois pull requests a partir de `main`. Cada passo começa com um teste que falha.

### PR 1 — Servidor e motor

Este PR não muda o que o utilizador vê, porque todos os módulos ficam marcados.

1. **Contrato da migração.** Atualize `test_migration_history_has_one_frozen_baseline`. Escreva a migração, o modelo e a coluna `planned`.
2. **Isolamento e privacidade.** Confirme `test_rls_database_policies.py` e os testes de isolamento. Atualize `privacy.py`.
3. **Fixtures.** `seed_v1_assignment` insere a seleção. Atualize os testes que criam `ClassSubjectLink` diretamente e chegam ao sync, à pré-validação, à prontidão ou ao progresso.
4. **API.** Leitura de `modules`, gravação de `module_ids`, `add_class_subject` com todos os módulos e o registo de alterações.
5. **Domínio.** `close_retired_modules`, com testes unitários.
6. **Projeção.** `sync_curricular_projection` com seleção, `planned`, `sequence` e o novo erro.
7. **Leitores.** O carregador de planeamento e cada leitor da tabela de leitores.
8. **Pré-validação, prontidão e fingerprint.**
9. **Progresso.** Turma, professor e painel.
10. **Documentação** do comportamento do servidor e do motor.

### PR 2 — Ecrãs

1. Hook `useUpdateClassSubject` e invalidações.
2. Checklist em `ClassSubjects.jsx`.
3. Coluna e progresso em `ClassDetails.jsx`.
4. Aviso em `Subjects.jsx`.
5. Adaptador do tutorial.
6. Percurso e2e.
7. Documentação dos ecrãs e mensagens.
8. Reconstrução do contentor local do frontend.

## Testes

### Domínio (unitários)

Em `backend/tests/unit/test_scheduler_progress_domain.py` ou num ficheiro novo do mesmo padrão:

- Um módulo planeado fica igual.
- Um módulo retirado com minutos fica concluído nesses minutos.
- Um módulo retirado sem minutos sai, e o mapa de minutos perde a chave.
- `frontier_credit` sobre a visão de planeamento nunca credita um módulo retirado.

### Servidor e motor (integração)

| Cenário | Ficheiro sugerido |
| :--- | :--- |
| A migração marca todos os módulos das ligações existentes. | Teste novo de migração ou `test_class_subjects.py` |
| `GET` devolve `modules` com `selected`. | `test_class_subjects.py` |
| `PATCH` aceita lista vazia, rejeita módulo de outra disciplina e repetidos. | `test_class_subjects.py` |
| `PATCH` com módulo de outra organização devolve 404. | `test_tenant_isolation_business.py` |
| `POST` e o CSV marcam todos os módulos. | `test_class_subjects.py`, `test_bulk_import.py` |
| A projeção cria requisitos só dos módulos marcados, com `sequence = order + 1`. | `test_scheduler_v1_projection.py` |
| Desmarcar sem créditos apaga o requisito. Com créditos fica `planned = false`. | `test_scheduler_v1_projection.py` |
| Ligação sem módulos levanta `CLASS_SUBJECT_WITHOUT_MODULES`. | `test_scheduler_v1_projection.py` |
| Desmarcar um módulo com sumários e gerar funciona. O horário não tem aulas desse módulo. O histórico fica intacto. | `test_scheduler_v1_progress.py` ou `test_scheduler_v1_adaptive_changes.py` |
| Um sumário novo depois de desmarcar credita o módulo marcado seguinte. | `test_scheduler_v1_operations.py` |
| Voltar a marcar retoma as horas registadas. | `test_scheduler_v1_progress.py` |
| Falta registada num módulo retirado: a recuperação adaptativa gera e aprova a proposta. | `test_scheduler_v1_recovery.py` |
| Desmarcar um módulo anterior e voltar a marcá-lo depois de o seguinte ter horas gera sem erro. | `test_scheduler_v1_progress.py` |
| A pré-validação devolve o bloqueio com a rota da turma. | `backend/tests/contracts/test_preflight_service.py` |
| A prontidão exige um módulo marcado. | `backend/tests/contracts/test_school_readiness_service.py` |
| A fingerprint muda quando a seleção muda. | `test_scheduler_fingerprint_service.py` |
| O progresso da turma e do professor mostra só os módulos marcados. | `test_module_progress.py` |

### Frontend

- `frontend/src/test/ClassSubjects.test.jsx`: contador, expansão, gravação ao clicar, bloqueio durante a gravação, aviso `Sem módulos` e modo só de leitura.
- `frontend/src/test/featureDataHooks.test.jsx`: o hook envia `module_ids` e invalida as consultas.
- `frontend/src/test/ClassDetails.test.jsx`: coluna `Módulos` e mensagem sem módulos.
- Novo `frontend/src/test/Subjects.test.jsx`: aviso ao acrescentar um módulo a uma disciplina existente. Hoje só existe `SubjectForm.test.jsx`.
- `frontend/src/test/tutorialApiAdapter.test.js`: `modules` na resposta do tutorial.

### E2E

Acrescente um percurso em `frontend/e2e/readiness/first-schedule.spec.js` ou num ficheiro novo na mesma pasta:
desmarque todos os módulos de uma disciplina, confirme o bloqueio na pré-validação e volte a marcar um módulo.

## Verification Procedure

Use os comandos da [Command Reference](../00_getting_started/COMMAND_REFERENCE.md#verification-by-change-type) para cada tipo de alteração:

1. Lógica pura do domínio: `fast --scope backend -- -k scheduler`.
2. Endpoint, serviço e consultas: `fast --scope backend`, depois `integration -- -k <área>`.
3. Migração e RLS: `integration` completo, depois as verificações de drift e de triggers.
4. Motor, propostas e API: `integration -- -k scheduler`. A CI não corre todos estes testes.
5. Frontend: `fast --scope frontend -- <ficheiro>`, depois `npm run verify:checks`.
6. Percurso: `e2e --project <nome>`, quando existirem as credenciais de teste do Clerk.
7. CI: `backend`, `frontend`, `e2e-runtime` e `e2e-browser` verdes antes do merge. Depois, `Deploy check` em `main`.

Verificação manual depois do PR 2:

1. Abra `/courses/:courseId/classes/:classId/subjects` como administrador.
2. Expanda uma disciplina e desmarque um módulo. Confirme o contador.
3. Desmarque todos os módulos. Confirme `Sem módulos` e o bloqueio em `/schedules`.
4. Volte a marcar um módulo e gere o horário. Confirme que o módulo desmarcado não aparece.

## Riscos e limitações

- Entre desmarcar e gerar, o horário publicado mantém as aulas antigas do módulo. Os sumários dessas aulas creditam o módulo marcado seguinte.
- O fecho de um módulo retirado depende dos minutos executados. Uma correção de um sumário antigo altera esse valor na geração seguinte.
- A FK não garante que o módulo pertence à disciplina da ligação. O serviço é o único ponto de escrita.
- Reordenar módulos de uma disciplina muda `sequence`. Este comportamento já existe hoje.

### Problema relacionado fora de âmbito

Remover uma disciplina inteira de uma turma com histórico parece não a retirar do horário seguinte.
O sync mantém a atribuição e os requisitos. `_load_assignments` carrega todas as atribuições do ano.
A correção exige tratar aulas publicadas, dívidas e reservas dessa atribuição.
Fica num pedido separado, que começa por um teste que reproduz o problema.

## Documentação a atualizar

| Documento | Alteração |
| :--- | :--- |
| [Professional Education](PROFESSIONAL_EDUCATION.md) | Regra da seleção por turma e ano, e do módulo retirado. |
| [Data Model](../01_system_architecture/DATA_MODEL.md) | Tabela `class_subject_module` e coluna `planned`. |
| [API Reference](../05_backend_api/API_REFERENCE.md) | `modules` e `module_ids` nas rotas da turma. |
| [Bulk Import CSV](../07_data_and_seed/BULK_IMPORT_CSV.md) | As Atribuições marcam todos os módulos. |
| [Scheduler Engine](../03_scheduler_engine/README.md) | Projeção a partir da seleção e fecho de módulos retirados. |
| [Feedback Message Matrix](../06_frontend_ux/FEEDBACK_MESSAGE_MATRIX.md) | Mensagens novas da checklist e da página Disciplinas. |
| [Repository Map](../00_getting_started/REPOSITORY_MAP.md) | A pasta `alembic` deixa de ter uma só baseline. |
| [Glossary](../00_getting_started/GLOSSARY.md) | Termos "módulo selecionado" e "módulo retirado", se o glossário os exigir. |

## Source Map

- Modelos: `backend/app/models.py`, `backend/app/scheduler/infrastructure/models.py`
- Projeção: `backend/app/scheduler/infrastructure/curriculum.py`
- Domínio: `backend/app/scheduler/domain/demand.py`, `candidate.py`, `projection.py`
- Snapshot: `backend/app/scheduler/infrastructure/snapshot.py`
- Serviços: `backend/app/services/class_service.py`, `preflight_service.py`, `school_readiness_service.py`, `scheduler_fingerprint_service.py`
- Ecrãs: `frontend/src/pages/ClassSubjects.jsx`, `ClassDetails.jsx`, `Subjects.jsx`

## Related Documents

- [Professional Education](PROFESSIONAL_EDUCATION.md)
- [Scheduler V1 Tech Spec](../03_scheduler_engine/SCHEDULER_V1_TECH_SPEC_V2.md)
- [Resource Removal](../05_backend_api/RESOURCE_REMOVAL.md)
- [Lesson Execution](../04_operational_features/LESSON_EXECUTION.md)
