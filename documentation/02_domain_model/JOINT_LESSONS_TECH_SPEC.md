# Tech Spec — Aulas Conjuntas

## Purpose

Este documento especifica as aulas conjuntas: turmas diferentes que têm alguns módulos de uma disciplina juntas, com o mesmo professor, na mesma sala e à mesma hora.
Define as decisões de produto, o modelo de dados, as regras do motor de horários, a operação diária, o plano TDD e os critérios de aceitação.

**Estado:** em implementação. A implementação local e a verificação de app estão concluídas; a aceitação completa e a entrega estão pendentes.
**Data:** 14 de outubro de 2026.
**Base observada:** branch `main` no commit `4773d76`.
**Origem:** item 2 dos pedidos da escola piloto, reunião de 13 de outubro de 2026.
**Depende de:** item 1, Módulos por Turma. O spec desse item está em revisão em `documentation/02_domain_model/CLASS_MODULE_SELECTION_TECH_SPEC.md`.

Depois da implementação, os guias da secção [Documentação a atualizar](#documentação-a-atualizar) descrevem o comportamento.
Este documento fica como registo das decisões.

## Intended Reader

Este documento destina-se a engenheiros backend, frontend e do motor de horários, e a revisores.

## Prerequisites

Leia estes documentos antes da implementação:

- [Repository Agent Instructions](../../AGENTS.md).
- [Documentation Standard](../00_getting_started/DOCUMENTATION_STANDARD.md).
- [Professional Education](PROFESSIONAL_EDUCATION.md).
- O tech spec de Módulos por Turma (ver **Depende de**).
- [Scheduler Engine](../03_scheduler_engine/README.md) e [Scheduler V1 Tech Spec](../03_scheduler_engine/SCHEDULER_V1_TECH_SPEC_V2.md).
- [Lesson Execution](../04_operational_features/LESSON_EXECUTION.md), [Occurrences and Substitutions](../04_operational_features/OCCURRENCES_AND_SUBSTITUTIONS.md) e [Timesheets and Progress](../04_operational_features/TIMESHEETS_AND_PROGRESS.md).
- [Security and Tenant Isolation](../08_security_quality/SECURITY_AND_TENANT_ISOLATION.md).
- [Command Reference](../00_getting_started/COMMAND_REFERENCE.md).

Carregue os skills `cronos-base`, `ponytail` (`full`), `cronos-domain`, `cronos-backend`, `cronos-scheduler`, `cronos-operations` e `cronos-frontend`.
Aplique as quatro práticas obrigatórias do `AGENTS.md`: clean code, Clean Architecture, TDD e Ponytail.

## What the System Does

### Problema

Turmas de cursos diferentes, por exemplo Marketing e Massagem, têm as disciplinas gerais juntas.
Português e Matemática são dados à mesma hora, na mesma sala, pelo mesmo professor.
As disciplinas técnicas são dadas a cada turma em separado.
Hoje, a aplicação trata cada turma sozinha. O professor fica com aulas a dobrar e ocupam-se salas a mais.

A junção não se faz pela disciplina inteira.
Duas turmas podem ter juntas os módulos 1 a 4, e só uma ter o módulo 5 e só a outra o módulo 6.

### Comportamento atual observado

| Área | Comportamento | Fonte |
| :--- | :--- | :--- |
| Unidade de planeamento | Cada atribuição tem uma turma, uma disciplina e um professor. | `backend/app/scheduler/domain/candidate.py` (`Assignment`) |
| Atribuição persistida | Uma linha por turma, disciplina e ano letivo. | `backend/app/scheduler/infrastructure/models.py` (`CurricularAssignment`) |
| Aula publicada | Cada linha pertence a uma atribuição, logo a uma turma. | `SchedulerLessonV1.assignment_id` |
| Identidade da aula | `stable_key` é único por versão. | `uq_scheduler_lesson_v1_stable_key` |
| Exclusividade | Turma, professor e sala nunca estão em duas aulas ao mesmo tempo. | `candidate_validation.py`, `placement_model.py` (`_add_conflicts`) |
| Sala | A lotação tem de cobrir o número de alunos da turma. | `snapshot.py` (`_build_assignments`) |
| Sequência | Os minutos de uma atribuição seguem a ordem dos módulos. Uma aula pode acabar um módulo e começar o seguinte. | `domain/projection.py` (`project_module_slices`) |
| Crédito do sumário | Concluir uma aula credita os slices guardados nessa linha. | `operations.py` (`record_lesson_log`) |
| Liquidação de dívida | Um crédito positivo liquida primeiro a dívida aberta mais antiga. | `progress.py` (`_execution_settlements`) |
| Reservas de reposição | Os minutos reservados numa aula não excedem o crédito da aula. | `application/publishing.py` (`plan_recovery_allocations`) |
| Rota de produção | A construção cronológica é a rota normal. Os modelos anual e de colocação são o recurso. | `config.py` (`SCHEDULER_V1_STOP_AT_FIRST_COMPLETE`), `search.py` (`_joint_search`) |
| Substitutos | O candidato dá outra disciplina à mesma turma e está livre. | `occurrences.py` (`get_substitute_recommendations`) |
| Folha semanal | Conta uma linha de aula por registo. | `backend/app/services/timesheet_service.py` |
| Estágio | Retira as aulas da turma e regista `GAP` em cada uma. | `backend/app/services/internship_flow_service.py` |

Não existe hoje nenhum conceito de aula com várias turmas.
A sobreposição de turma, professor e sala é validada em código. A base de dados não tem restrições de exclusão.

### Decisões de produto fechadas

O responsável de produto aprovou estas decisões em 14 de outubro de 2026.

| ID | Decisão | Requisito |
| :--- | :--- | :--- |
| J01 | O diretor indica que turmas partilham que módulos de cada disciplina. | Uma **junção** tem uma disciplina, duas ou mais turmas e um conjunto de módulos conjuntos. |
| J02 | A junção configura-se na página "Disciplinas e Professores" da turma. | Na linha da disciplina, junto à checklist de módulos do item 1. A junção aparece em todas as turmas envolvidas. |
| J03 | Uma junção pode ter qualquer número de turmas, de qualquer curso e de qualquer ano. | A escola decide. A aplicação não limita. |
| J04 | Uma turma está, no máximo, numa junção por disciplina. | As aulas conjuntas têm sempre todas as turmas da junção. Não há subgrupos. |
| J05 | Os módulos conjuntos têm de estar marcados em todas as turmas da junção. | Ao criar, a aplicação marca os módulos comuns a todas. O diretor pode desmarcar. |
| J06 | O professor da disciplina é o mesmo em todas as turmas da junção. | Inclui os módulos separados. Mudar o professor numa turma muda-o nas outras, com aviso. |
| J07 | Sequência estrita por horas em cada turma. | Uma turma nunca recebe minutos de um módulo antes de acabar os anteriores. A exceção é a reposição de ausências (J12). |
| J08 | As turmas esperam umas pelas outras. | A parte conjunta só começa quando todas as turmas acabarem os módulos separados anteriores. |
| J09 | Uma aula nunca mistura parte conjunta e parte separada. | Se a parte conjunta não encher a última aula, sobram minutos nessa aula. |
| J10 | A sala tem o tipo da disciplina e lugares para a soma dos alunos. | Nenhuma sala serve: a pré-validação bloqueia antes da geração. |
| J11 | A aula conjunta só é marcada quando todas as turmas estão livres. | Inclui dias bloqueados, indisponibilidades e almoço de cada turma. |
| J12 | Um só sumário por aula conjunta. O professor marca as turmas presentes. | A turma ausente fica com uma ocorrência só para ela. Uma falta decidida cria dívida só nessa turma. A turma repõe os minutos numa aula sua, com o mesmo professor, antes de começar o segmento seguinte. |
| J13 | A falta do professor vale para todas as turmas. | A decisão `GAP` ou `SUBSTITUTED` aplica-se a todas. A reposição é uma aula conjunta. |
| J14 | O substituto de uma aula conjunta dá outra disciplina em conjunto às mesmas turmas. | As turmas têm de estar na parte conjunta dessa disciplina. Os minutos contam nessa disciplina, para cada turma presente. |
| J15 | Numa aula de uma só turma, o substituto não pode dar uma disciplina que a turma está a ter em conjunto. | Senão essa turma avançava e as outras não. |
| J16 | A aula conjunta conta uma só vez nas horas do professor. | Sumários, progresso e dívida contam por turma. |
| J17 | Vista da turma: "Português · em conjunto com 10.º MAS". Vista do professor: um só bloco com todas as turmas. | Aplica-se a todas as vistas semanais. |
| J18 | Se uma turma fica bloqueada num dia com aula conjunta publicada, a aula sai para todas as turmas. | Fica `GAP` em todas. A reposição é conjunta. |
| J19 | Um módulo já começado não entra nem sai de uma junção. | Também não entra nem sai uma turma com módulos conjuntos começados. |
| J20 | Desmarcar na checklist um módulo conjunto não é permitido. | Mensagem: "Retire primeiro este módulo da aula conjunta." É uma exceção à decisão D06 do item 1. |
| J21 | Mudar uma junção depois de publicar exige nova geração. | Usa o mecanismo atual de revisões de planeamento. |
| J22 | A importação CSV de junções fica fora desta versão. | O CSV de Atribuições não muda. |

### Exemplo de referência

O exemplo usa a disciplina Português com seis módulos de 25 horas.

| Turma | Módulos marcados (item 1) |
| :--- | :--- |
| 10.º MKT (Marketing) | M1, M2, M3, M4, M5 |
| 10.º MAS (Massagem) | M1, M2, M3, M4, M6 |

A junção tem as duas turmas e os módulos conjuntos M1 a M4.

- As aulas de M1 a M4 são conjuntas: 100 horas, um professor, uma sala com lugares para as duas turmas.
- A MKT só começa o M5 depois de acabar o M4 conjunto. A MAS só começa o M6 depois do M4 conjunto.
- Se a MAS falta a uma aula conjunta de 50 minutos (visita de estudo), a MKT recebe os 50 minutos e a MAS não.
  A MAS fica com 50 minutos em falta na parte conjunta. Recebe-os numa aula só dela, antes de começar o M6.

### Âmbito

Incluído:

- Modelo de dados, migração e isolamento por organização.
- API de configuração das junções e bloqueios nas rotas existentes.
- Unidades de ensino, sequência estrita e défice por turma no motor de horários.
- Construção cronológica, recuperação adaptativa, modelos anual e de colocação, salas, qualidade e validador.
- Persistência das aulas conjuntas, propostas, diferenças e aprovação.
- Sumário com presenças, ocorrências, substituições, dívida, folha semanal e estágio.
- Pré-validação, prontidão e fingerprint de geração.
- Ecrãs: Disciplinas e Professores, página da turma, horários, sumário e Faltas e Ocorrências.

Excluído:

- Importação CSV de junções (J22).
- Subgrupos de uma junção (J04).
- Reposição conjunta de turmas que faltaram à mesma aula. Cada turma repõe sozinha. Ver [Riscos e limitações](#riscos-e-limitações).
- Alterar a política atual de liquidação de dívida.

## Why the Behavior Exists

A escola precisa de representar o funcionamento real: um professor, uma sala e várias turmas ao mesmo tempo.
Sem isto, o horário gerado gasta horas de professor e salas que a escola não tem, e muitas vezes não cabe na grelha.

A sequência estrita (J07) segue a regra do Ensino Profissional: as horas de uma disciplina contam por ordem.
A hora 51 de uma disciplina só pode pertencer ao módulo seguinte quando os anteriores somam 50 horas.

A contabilidade continua por turma, porque o progresso, a dívida e os sumários têm de responder por turma.
O motor planeia por unidade de ensino. Uma unidade pode ter várias turmas.
Esta separação mantém intacto o ledger append-only e o Scheduler V1 Tech Spec (D16, D17 e D18).

## Vocabulário

| Termo | Definição |
| :--- | :--- |
| Junção | Disciplina, turmas membro e módulos conjuntos. Na interface: "Aula conjunta". |
| Turma membro | Uma ligação turma–disciplina (`class_subject_link`) que pertence à junção. |
| Módulo conjunto | Um módulo da junção. É dado a todas as turmas ao mesmo tempo. |
| Segmento | Sequência máxima de módulos consecutivos de uma turma que são todos conjuntos ou todos separados. |
| Unidade de ensino | O que o motor planeia: turmas, disciplina, professor, módulos e minutos em falta. Substitui o papel atual de `Assignment`. |
| Progresso conjunto | Por módulo conjunto, o maior número de minutos executados entre as turmas membro. |
| Défice | Por turma e módulo conjunto, o progresso conjunto menos os minutos executados dessa turma. |
| Aula irmã | Cada linha de `scheduler_lesson_v1` de uma aula conjunta. Há uma por turma membro. |

## Components and Ownership

| Responsabilidade | Implementação |
| :--- | :--- |
| Tabelas da junção e coluna da unidade | Nova migração em `backend/alembic/versions/`, `backend/app/models.py`, `backend/app/scheduler/infrastructure/models.py` |
| Regras puras da junção | Novo `backend/app/services/joint_lesson_policy.py` |
| Serviço e API da junção | Novo `backend/app/services/joint_lesson_service.py`, novo `backend/app/api/v1/endpoints/joint_lesson_groups.py`, `backend/app/schemas.py` |
| Bloqueios nas rotas existentes | `backend/app/services/class_service.py`, `subject_service.py`, `resource_removal.py` |
| Unidades de ensino (puro) | Novo `backend/app/scheduler/domain/teaching_units.py` |
| Contratos do domínio | `backend/app/scheduler/domain/candidate.py`, `capacity.py`, `candidate_validation.py`, `quality.py`, `recovery.py`, `oracle.py`, `serialization.py`, `demand.py` |
| Snapshot e mapeamento das aulas | `backend/app/scheduler/infrastructure/snapshot.py` |
| Construção e recuperação | `backend/app/scheduler/infrastructure/constructive.py`, `recovery_construction.py` |
| Modelos CP-SAT | `backend/app/scheduler/infrastructure/annual_model.py`, `placement_model.py`, `search.py` |
| Propostas e aprovação | `backend/app/scheduler/infrastructure/proposals.py`, `backend/app/scheduler/application/publishing.py` |
| Sumário e vista semanal | `backend/app/scheduler/infrastructure/operations.py`, `backend/app/api/v1/endpoints/schedule.py` |
| Ocorrências e substitutos | `backend/app/scheduler/infrastructure/occurrences.py`, `backend/app/api/v1/endpoints/occurrences.py` |
| Folha semanal | `backend/app/services/timesheet_service.py` |
| Estágio | `backend/app/services/internship_flow_service.py` |
| Pré-validação, prontidão e fingerprint | `preflight_service.py`, `school_readiness_service.py`, `scheduler_fingerprint_service.py` em `backend/app/services/` |
| Privacidade | `backend/scripts/privacy.py` |
| Fixtures do laboratório | `backend/app/scheduler/lab/typology.py`, `backend/tests/_support/scheduler_v1.py` |
| Hooks de dados | `frontend/src/features/catalog/data.js`, `frontend/src/features/operations/data.js` |
| Ecrãs | `frontend/src/pages/ClassSubjects.jsx`, `ClassDetails.jsx`, `Occurrences.jsx`, `Schedules.jsx`, `MySchedules.jsx` |
| Componentes | `frontend/src/components/WeekGrid.jsx`, `LessonLogModal.jsx` |

## Data or Request Flow

### Visão geral

1. O diretor cria a junção na página "Disciplinas e Professores" de uma turma.
2. O serviço valida as regras J03 a J06 e J19, grava a junção e regista uma alteração de planeamento.
3. Na geração, `sync_curricular_projection` mantém as atribuições por turma, como hoje.
4. O snapshot constrói as unidades de ensino a partir das atribuições, da execução e das junções.
5. O motor planeia as unidades com sequência estrita e grava cada aula conjunta como aulas irmãs.
6. O administrador aprova a proposta, como hoje.
7. O professor regista um sumário com as turmas presentes. Cada turma presente recebe o crédito.
8. A direção decide as ocorrências. A recuperação adaptativa repõe o défice e a dívida.

### Modelo de dados

#### Tabela `joint_lesson_group`

| Coluna | Tipo | Regra |
| :--- | :--- | :--- |
| `id` | `serial` | Chave primária. |
| `organization_id` | `integer NOT NULL` | FK para `organization(id)` com `ON DELETE CASCADE`. |
| `subject_id` | `integer NOT NULL` | FK composta `(organization_id, subject_id)` para `subject(organization_id, id)`. |

Restrição única `(organization_id, id)` para as FKs compostas.

#### Tabela `joint_lesson_group_member`

| Coluna | Tipo | Regra |
| :--- | :--- | :--- |
| `organization_id` | `integer NOT NULL` | FK para `organization(id)` com `ON DELETE CASCADE`. |
| `group_id` | `integer NOT NULL` | FK composta para `joint_lesson_group(organization_id, id)` com `ON DELETE CASCADE`. |
| `class_subject_link_id` | `integer NOT NULL` | FK composta para `class_subject_link(organization_id, id)`, sem `ON DELETE CASCADE`. |

- Chave primária `(organization_id, class_subject_link_id)`. Garante J04: uma ligação está no máximo numa junção.
- A ligação tem chave `grade_level`. A junção pertence ao ano escolar atual das turmas, como a seleção do item 1.
- A FK sem cascata faz a base de dados recusar a remoção de uma ligação membro. O serviço responde antes com `409`.

#### Tabela `joint_lesson_group_module`

| Coluna | Tipo | Regra |
| :--- | :--- | :--- |
| `organization_id` | `integer NOT NULL` | FK para `organization(id)` com `ON DELETE CASCADE`. |
| `group_id` | `integer NOT NULL` | FK composta para `joint_lesson_group(organization_id, id)` com `ON DELETE CASCADE`. |
| `module_id` | `integer NOT NULL` | FK composta para `module(organization_id, id)`, sem `ON DELETE CASCADE`. |

Chave primária `(organization_id, group_id, module_id)`.

O serviço valida que todas as ligações e módulos pertencem à disciplina da junção.
A base de dados não cobre esta regra, como no item 1.
O professor não fica na junção. Fica em `class_subject_link.teacher_id`, igual em todos os membros (J06).

#### Coluna `scheduler_lesson_v1.teaching_unit_key`

Acrescente `teaching_unit_key varchar(80) NOT NULL`. Identifica a unidade de ensino que planeou a aula.

| Formato | Unidade |
| :--- | :--- |
| `A:{assignment_id}` | Atribuição sem junção. É o valor de todas as linhas existentes. |
| `S:{assignment_id}:{module_id}` | Segmento separado de uma atribuição em junção. `module_id` é o primeiro módulo do segmento. |
| `J:{group_id}:{module_id}` | Segmento conjunto. `module_id` é o primeiro módulo do segmento. |
| `D:{assignment_id}:{module_id}` | Reposição do défice de uma turma num segmento conjunto. `module_id` é o primeiro módulo desse segmento. |

As chaves usam módulos, não posições. Uma alteração da configuração não reaproveita uma chave antiga por engano.

#### Identidade das aulas irmãs

Substitua `uq_scheduler_lesson_v1_stable_key (version_id, stable_key)` por `(version_id, stable_key, assignment_id)`.
As aulas irmãs partilham `stable_key`, `school_date`, `starts_at`, `ends_at`, `room_id`, `physical_minutes`, `credit_minutes` e `teaching_unit_key`.
Cada aula irmã tem os mesmos slices.
O código valida esta igualdade ao gravar e ao carregar. A base de dados não a cobre.

### Migração

Crie `0003_joint_lesson_groups` com `down_revision` igual à migração do item 1.

1. Crie as três tabelas, as FKs, os índices e as chaves primárias.
2. Ative `ENABLE ROW LEVEL SECURITY` e `FORCE ROW LEVEL SECURITY` nas três tabelas.
3. Crie a política `tenant_isolation` para `cronos_app`, igual à de `class_subject_link`.
4. Conceda `SELECT, INSERT, UPDATE, DELETE` a `cronos_app`.
5. Acrescente `teaching_unit_key` a `scheduler_lesson_v1` e preencha com `'A:' || assignment_id`.
6. Substitua a restrição única de `stable_key`.
7. O `downgrade` repõe a restrição antiga e remove a coluna e as tabelas. Recusa se existirem aulas irmãs.

Acrescente as três tabelas a `backend/scripts/privacy.py` com a ação `delete`.

### Contrato HTTP

#### Rotas novas

Todas exigem a capacidade `admin`, como as rotas do catálogo.

| Método e rota | Efeito |
| :--- | :--- |
| `GET /api/v1/subjects/{subject_id}/joint-candidates?class_id={id}` | Turmas que podem entrar numa junção com a turma indicada. |
| `POST /api/v1/joint-lesson-groups` | Cria uma junção. |
| `PUT /api/v1/joint-lesson-groups/{group_id}` | Substitui turmas, módulos e professor. |
| `DELETE /api/v1/joint-lesson-groups/{group_id}` | Desfaz a junção. As turmas ficam com os mesmos módulos, todos separados. |

Esquema `JointLessonGroupWrite`:

| Campo | Tipo | Regra |
| :--- | :--- | :--- |
| `subject_id` | `int` | Só no `POST`. |
| `class_ids` | `list[int]` | Duas ou mais turmas distintas. |
| `module_ids` | `list[int]` | Um ou mais módulos distintos. |
| `teacher_id` | `int` | Professor com competência na disciplina. |

Esquema `JointLessonGroupRead`: `id`, `subject_id`, `subject_name`, `teacher_id`, `classes` (`class_id`, `class_name`, `course_abbreviation`, `grade_level`) e `module_ids` por ordem.

Esquema `JointCandidateRead`: `class_id`, `class_name`, `course_abbreviation`, `grade_level`, `teacher_id`, `selected_module_ids` e `started_module_ids`.
O frontend usa estas listas para calcular os módulos comuns e os módulos bloqueados.

#### Alterações em rotas existentes

| Método e rota | Alteração |
| :--- | :--- |
| `GET /api/v1/classes/{class_id}/subjects` | Cada disciplina inclui `joint_group: JointLessonGroupRead \| null`. |
| `PATCH /api/v1/classes/{class_id}/subjects/{subject_id}` com `teacher_id` | Numa junção, muda o professor em todas as ligações membro, na mesma transação. |
| `PATCH /api/v1/classes/{class_id}/subjects/{subject_id}` com `module_ids` | Recusa retirar um módulo conjunto: `409 JOINT_MODULE_LOCKED` (J20). |
| `DELETE /api/v1/classes/{class_id}/subjects/{subject_id}` | Recusa uma ligação membro: `409 resource_in_use`. |
| Arquivar uma turma | Recusa uma turma membro: `409 resource_in_use`. |
| Remover um módulo da disciplina | Recusa um módulo conjunto: `409 resource_in_use`, pelas regras de [Resource Removal](../05_backend_api/RESOURCE_REMOVAL.md). |
| `GET /api/v1/readiness/prevalidation` | Acrescenta os bloqueios `JOINT_ROOM_CAPACITY` e `JOINT_GROUP_INCOMPLETE`. |
| Sumário, ocorrências e vista semanal | Ver [Operação](#operação). |

### Regras de configuração

Crie funções puras em `joint_lesson_policy.py`. O serviço carrega os dados e chama as funções.
Cada regra devolve um código e uma mensagem em português. O serviço traduz para `400` ou `409`.

| Código | Regra | Mensagem |
| :--- | :--- | :--- |
| `JOINT_TOO_FEW_CLASSES` | Menos de duas turmas distintas. | "Escolha pelo menos duas turmas." |
| `JOINT_CLASS_WITHOUT_SUBJECT` | Uma turma não tem a disciplina no ano escolar atual, ou está arquivada. | "A turma {turma} não tem {disciplina} este ano." |
| `JOINT_CLASS_ALREADY_JOINED` | Uma turma já está noutra junção desta disciplina (J04). | "A turma {turma} já tem {disciplina} em conjunto com outras turmas." |
| `JOINT_NO_MODULES` | Lista de módulos vazia. | "Escolha pelo menos um módulo conjunto." |
| `JOINT_MODULE_NOT_SELECTED` | Um módulo não está marcado numa das turmas (J05). | "O módulo {módulo} não está marcado na turma {turma}." |
| `JOINT_TEACHER_NOT_ELIGIBLE` | O professor não tem competência na disciplina. | Mensagem atual de professor sem competência. |
| `JOINT_MODULE_STARTED` | Entra ou sai um módulo com minutos executados em alguma turma (J19). | "O módulo {módulo} já começou e não pode entrar nem sair da aula conjunta." |
| `JOINT_CLASS_STARTED` | Entra ou sai uma turma, e algum módulo conjunto já tem minutos executados (J19). | "A aula conjunta já começou. Não pode juntar nem retirar turmas." |

Um módulo começou quando a soma dos créditos de execução dessa atribuição e desse módulo é positiva.
Um módulo com minutos executados que fica na junção, com as mesmas turmas, é permitido.

Fluxo de gravação:

1. O serviço bloqueia as ligações membro antigas e novas com `with_for_update`, por ordem de `id`.
2. O serviço chama as regras puras.
3. O serviço grava a junção e muda `teacher_id` em todas as ligações membro.
4. O serviço chama `record_scheduler_change` com `entity_type="JOINT_LESSON_GROUP"`.
5. O instantâneo da alteração inclui a disciplina, as turmas, os módulos e o professor, por ordem.

### Do plano curricular às unidades de ensino

Crie uma função pura em `teaching_units.py`:

```python
def build_teaching_units(
    assignments: Sequence[AssignmentPlan],
    groups: Sequence[JointGroupPlan],
    published_unit_keys: AbstractSet[str],
) -> TeachingUnitPlan:
    """Split class assignments into planning units with strict precedence."""
```

`AssignmentPlan` traz, por atribuição: identificador, turma, disciplina, professor, alunos, módulos marcados por ordem e minutos executados por módulo.
Os módulos vêm da visão de planeamento do item 1. Um módulo retirado e fechado não entra na segmentação.
`JointGroupPlan` traz o identificador, a disciplina, as atribuições membro e os módulos conjuntos.

#### Segmentação

Para cada junção `G`, com módulos conjuntos `J`:

1. Ordene `J` pela ordem da disciplina.
2. Entre dois módulos conjuntos consecutivos `j` e `j'`, crie uma fronteira quando alguma turma membro tem um módulo separado marcado entre `j` e `j'`.
3. As fronteiras dividem `J` nos segmentos conjuntos `J1`, `J2`, ..., `Jn`.
4. Cada turma membro fica com a sequência `S0, J1, S1, J2, ..., Jn, Sn`. `Sk` são os módulos separados da turma entre `Jk` e `Jk+1`. Um `Sk` pode estar vazio.

Exemplo: a MKT tem M1, M2 e M3. A MAS tem M1 e M3. A junção tem M1 e M3.
A MKT tem M2 entre M1 e M3, por isso há uma fronteira. Os segmentos conjuntos são `J1 = {M1}` e `J2 = {M3}`.
A MAS espera que a MKT acabe o M2 antes de começar o `J2`.

#### Unidades

| Unidade | Chave | Turmas | Módulos e minutos executados |
| :--- | :--- | :--- | :--- |
| Atribuição sem junção | `A:{a}` | A turma | Todos os módulos marcados e os minutos da atribuição. Igual a hoje. |
| Segmento separado | `S:{a}:{m}` | A turma | Os módulos de `Sk` e os minutos da atribuição nesses módulos. |
| Segmento conjunto | `J:{g}:{m}` | Todas as turmas membro | Os módulos de `Jk`. Os minutos executados de cada módulo são o progresso conjunto. |
| Défice | `D:{a}:{m}` | A turma | Os módulos de `Jk` com progresso conjunto positivo. O requisito de cada módulo é o progresso conjunto. Os minutos executados são os da turma. |

- As unidades `A`, `S` e `J` existem sempre. A unidade `D` existe quando o défice da turma no segmento é positivo, ou quando uma aula publicada usa a sua chave.
- O professor de todas as unidades da disciplina é o da ligação. Professores diferentes numa junção levantam `JOINT_TEACHER_MISMATCH`.
- As salas elegíveis de uma unidade `J` exigem o tipo da disciplina e lotação maior ou igual à soma dos alunos (J10).
- As salas específicas por turma e disciplina aplicam-se a todas as turmas da unidade. Para `J`, use a interseção. Uma interseção vazia é um problema de sala.

#### Identificadores

O motor exige identificadores inteiros positivos.

- Uma unidade `A:{a}` usa o identificador `a`. As escolas sem junções ficam exatamente como hoje.
- As outras unidades recebem identificadores acima do maior identificador de atribuição, pela ordem das chaves.
- Os identificadores só precisam de ser estáveis dentro de um snapshot. As aulas publicadas guardam a chave, não o identificador.

#### Progresso conjunto e défice

Para cada módulo conjunto `m` e turma membro `c`:

```text
conjunto[m] = max(executado[c][m] para c em G)
défice[c][m] = conjunto[m] - executado[c][m]
residual(J) = soma(requisito[m] - conjunto[m])
residual(D de c) = soma(défice[c][m])
```

- Uma aula conjunta credita o mesmo módulo e os mesmos minutos a todas as turmas presentes. As turmas presentes ficam alinhadas.
- Uma turma ausente fica com défice. As aulas conjuntas seguintes continuam no progresso conjunto.
- A reposição do défice (unidade `D`) preenche os módulos em falta da turma, por ordem.
- Uma correção manual que põe uma turma à frente cria défice nas outras. O motor trata-o da mesma forma.

#### Precedência

A sequência estrita (J07 e J08) torna-se uma relação de precedência entre unidades.
Para cada turma, as etapas são `S0`, `{J1, D1}`, `S1`, `{J2, D2}`, ..., pela ordem da sequência.

1. Ignore as unidades sem minutos em falta.
2. Ligue cada etapa restante à etapa restante seguinte: cada unidade da primeira precede cada unidade da segunda.
3. `Jk` e `Dk` da mesma turma não têm precedência entre si. O défice pode ser reposto enquanto a parte conjunta continua.

Precedência `u → v`: cada aula nova de `v` começa depois de acabar a última aula de `u`, protegida ou nova.
As aulas protegidas de `v` são factos e não ficam sujeitas à regra.

A função devolve as unidades, as precedências, o mapa de cada unidade para as atribuições contabilísticas e o mapa de cada chave para o identificador.

### Motor de horários

#### Contratos do domínio

| Contrato | Alteração |
| :--- | :--- |
| `Assignment` | `class_id: int` passa a `class_ids: tuple[int, ...]`, ordenado, com pelo menos uma turma. O nome fica. A docstring explica que é uma unidade de ensino. |
| `ScheduledLesson` | `class_id` passa a `class_ids`. |
| `PlanningSnapshot` | Acrescenta `precedences: tuple[tuple[int, int], ...]`. Valida unidades conhecidas, sem ciclos e sem `u → u`. |
| `PlanningSnapshot` | Acrescenta `claim_classes: Mapping[int, int]`, a turma de cada dívida aberta. |
| `RecoveryAllocation` | Sem alteração. O limite passa a ser por aula e turma (ver abaixo). |

Cada leitura de `assignment.class_id` passa a iterar `class_ids`.
Os pontos principais são:

| Ficheiro | Regra por turma membro |
| :--- | :--- |
| `capacity.py` | Indisponibilidade, dias bloqueados (`blocked_on`) e ocupação fixa de qualquer turma excluem o período. |
| `candidate_validation.py` | Ocupação, almoço, dias bloqueados, indisponibilidade e datas de conclusão contam em cada turma. |
| `quality.py` | Datas de conclusão, furos de turma, continuidade de sala por turma e disciplina, e progresso por turma. |
| `recovery.py` | Datas de conclusão por turma. |
| `serialization.py` | Uma unidade com uma turma serializa `class_id`, como hoje. `class_ids`, `precedences` e `claim_classes` só aparecem com junções. Assim, a digest de uma escola sem junções não muda e nenhuma proposta pendente fica desatualizada no deploy. |
| `oracle.py` | O oráculo enumerativo aceita `class_ids` e precedências. Continua a ser a referência dos testes. |

#### Validador independente

Suba `VALIDATOR_VERSION` para `v5` e acrescente um código:

| Código | Violação |
| :--- | :--- |
| `PRECEDENCE_VIOLATION` | Uma aula nova de `v` começa antes de acabar uma aula de `u`, com `u → v`. |

`RESOURCE_CONFLICT` passa a incluir as turmas membro.
`RESERVATION_OVERFLOW` passa a contar por aula e turma.
`RESERVATION_ASSIGNMENT_MISMATCH` passa a exigir que a turma da dívida pertença à aula e que a dívida aponte para a unidade da aula.

#### Construção cronológica

É a rota normal de produção. Altere `construct_schedule`:

1. Uma unidade só fica ativa num período quando todas as suas antecessoras têm zero minutos em falta e a última aula delas acabou antes do início do período.
2. A ocupação, o almoço e os furos contam em todas as turmas da unidade.
3. `_select_period` verifica todas as turmas no passo guloso.
4. `_flow_selection` só corre quando todas as opções têm uma turma. Com uma unidade conjunta, o período usa o modelo CP-SAT pequeno que já existe, com uma restrição por turma.
5. A prioridade usa o progresso da unidade. `started_classes` e `class_remaining` contam em cada turma membro.
6. O padrão semanal guarda a unidade em cada turma membro.

#### Recuperação adaptativa

`construct_recovery` aplica as mesmas regras de ocupação e precedência.
A unidade `D` tem a mesma prioridade da dívida atual. O motor tenta repô-la no primeiro espaço livre.

#### Modelo anual

Em `plan_annual_quotas`:

- `load_terms` e `_availability_minutes` contam cada unidade em todas as turmas membro.
- Para cada precedência `u → v`, uma quota de `v` numa semana anterior a `last_week[u]` é zero.
  Use a mesma construção do booleano `after` que já existe.

#### Modelo de colocação

Em `placement_model.py`:

- Exclusividade, almoço, medida de conclusão e furos contam em cada turma membro.
- Para cada precedência `u → v` dentro de uma janela, crie `last_end[u]` e `first_start[v]`:

```text
last_end[u] >= fim(p) * x[u,p]              para cada período p de u
last_end[u] >= fim(l)                       para cada aula protegida l de u
first_start[v] <= início(p) + H * (1 - x[v,p])   para cada período p de v
last_end[u] <= first_start[v]
```

`H` é o fim do horizonte em minutos. A formulação é linear no número de períodos.
Não use restrições por pares de períodos: no modo sem distribuição, o horizonte é o ano inteiro.

#### Salas

`_optimize_rooms` atribui uma sala por aula conjunta.
A continuidade de sala conta a aula em cada par turma e disciplina das turmas membro.

#### Diagnóstico

`_build_assignments` acrescenta problemas de sala para unidades conjuntas, com `required_capacity` igual à soma dos alunos.
Uma inviabilidade comprovada em que só uma unidade conjunta fica sem períodos indica `JOINT_NO_COMMON_TIME`.
A mensagem diz: "As turmas {turmas} não têm horas livres em comum para {disciplina}."

### Persistência das aulas

#### Snapshot

Em `load_snapshot`:

1. Carregue as junções ativas com membros na projeção curricular do ano.
2. Carregue os minutos executados por atribuição, como hoje.
3. Chame `build_teaching_units` e construa um `Assignment` por unidade.
4. Agrupe as linhas publicadas por `(version_id, stable_key)`. Cada grupo é uma aula do domínio.
5. Associe cada aula à unidade da sua `teaching_unit_key`. As turmas das linhas têm de ser as turmas da unidade.
6. Uma aula protegida sem unidade correspondente levanta `JOINT_PUBLISHED_LESSONS_CONFLICT`.
7. Uma aula futura editável sem unidade correspondente só serve para emparelhar identidades.
8. Associe cada dívida aberta a uma unidade e a uma turma:
   - A dívida de uma aula com `GAP` em todas as aulas irmãs vai para a unidade da aula (`J` ou `A`).
   - A dívida de uma turma ausente vai para a unidade `D` dessa turma e desse segmento.
   - Se essa unidade não tiver minutos em falta, vai para a primeira unidade da turma com minutos em falta.

`split_version_history` e `_reproject_baseline` trabalham por unidade.
As aulas registadas de uma aula conjunta ocupam todas as turmas, o professor e a sala.

#### Propostas

`persist_proposal` grava cada aula do domínio como uma linha por atribuição contabilística da unidade.

- Uma unidade `A`, `S` ou `D` grava uma linha.
- Uma unidade `J` grava uma linha por turma membro, com a mesma `stable_key` e os mesmos slices.
- `source_lesson_id` de cada aula irmã aponta para a aula irmã da mesma turma na versão anterior.
- As reservas de reposição apontam para a aula irmã da turma da dívida.

`build_diff` devolve uma entrada por aula e turma. Cada entrada traz `joint_class_ids` quando a aula é conjunta.
`plan_recovery_allocations` limita as reservas por aula e por turma, não por aula.

A aprovação, `_carry_consumed_lessons` e `_repoint_lesson_logs` tratam cada aula irmã pela sua turma.

### Operação

#### Sumário com presenças

`PUT /api/v1/schedule/lessons/{lesson_id}/log` aceita `absent_class_ids: list[int]`, por omissão vazio.
O `lesson_id` pode ser o de qualquer aula irmã.

| Pedido | Efeito |
| :--- | :--- |
| `COMPLETED` sem ausências | Todas as aulas irmãs ficam `COMPLETED`. Cada turma recebe os slices da sua linha. |
| `COMPLETED` com ausências | As turmas presentes ficam `COMPLETED`. As ausentes ficam `OCCURRENCE`, sem resumo e com a nota "Turma ausente". |
| `OCCURRENCE` | Todas as aulas irmãs ficam `OCCURRENCE`. É o caso do professor que faltou (J13). |

- `absent_class_ids` só se aplica a aulas conjuntas. Tem de ser um subconjunto próprio das turmas da aula.
- O serviço bloqueia todas as aulas irmãs por ordem de `id` e aplica tudo numa transação.
- O professor escreve o resumo uma vez (J12). As turmas presentes recebem o mesmo resumo e as mesmas notas.
- Uma correção posterior das presenças segue as regras atuais por linha. Passar de `COMPLETED` a `OCCURRENCE` reverte a execução dessa turma.
- A resposta acrescenta `classes`, com `class_id`, `status` e `credited_minutes` por turma.

A ocorrência de uma turma ausente fica pendente até à decisão da direção, como qualquer ocorrência.
`GAP` cria dívida só nessa turma. `GIVEN` credita a turma.

#### Ocorrências

- A lista agrupa as aulas irmãs. Cada item traz `joint_lesson` com as turmas e o estado de cada uma.
- `PATCH /api/v1/occurrences/{id}` aceita `class_ids`. A decisão aplica-se, numa transação, a essas aulas irmãs. Por omissão, aplica-se só à linha indicada.
- `GIVEN` e `GAP` podem ser decididos por turma.
- `SUBSTITUTED` exige todas as aulas irmãs com ocorrência pendente e aplica-se a todas (J13).
- A reversão continua por linha.

#### Substitutos

Para uma aula conjunta, um candidato tem de cumprir todas as regras atuais e estas (J14):

- Dá uma disciplina `s'` que tem uma junção com exatamente as mesmas turmas.
- Em `s'`, a próxima unidade com minutos em falta de cada turma é a mesma unidade `J`.
- A unidade `J` tem minutos em falta suficientes para o crédito da aula.

Para uma aula de uma só turma, exclua a disciplina `s'` quando a próxima unidade da turma em `s'` é conjunta (J15).

| Código de exclusão | Mensagem |
| :--- | :--- |
| `joint_classes_mismatch` | "O docente não dá esta disciplina em conjunto a estas turmas." |
| `joint_not_in_progress` | "As turmas não estão na parte conjunta desta disciplina." |
| `joint_in_progress` | "A turma tem esta disciplina em conjunto. A substituição deixaria as outras turmas para trás." |

A deteção de conflitos do candidato conta cada aula conjunta uma vez.

Planear uma substituição conjunta cria um bloco operacional por aula irmã, com o mesmo professor, disciplina, hora e sala.
Concluir um desses blocos conclui todos. O pedido aceita `absent_class_ids`. O bloco de uma turma ausente é cancelado, sem crédito.
O crédito de cada turma presente usa uma função pura nova em `demand.py`:

```python
def joint_frontier_credit(
    modules: Sequence[ModuleRequirement],
    completed_by_class: Mapping[int, Mapping[int, int]],
    minutes: int,
) -> tuple[ModuleCredit, ...]:
    """Sequential credit over the joint progress, equal for every class."""
```

#### Dívida e reposição

- A política de liquidação não muda: o crédito positivo de uma turma liquida a sua dívida mais antiga.
- `GAP` em todas as aulas irmãs cria uma dívida por turma. O motor repõe-na numa aula conjunta.
- `GAP` numa só turma cria dívida nessa turma. O motor repõe o défice na unidade `D`.
- O invariante "dívida aberta menor ou igual ao residual" continua por atribuição contabilística.

#### Folha semanal e totais do professor

- `timesheet_service.py` agrupa as aulas irmãs por `(version_id, stable_key)`. A aula conjunta conta uma vez (J16).
- A aula conjunta está registada quando todas as aulas irmãs têm registo.
- Os blocos operacionais de uma substituição conjunta contam uma vez.
- Qualquer total de horas por professor ou por sala conta uma aula conjunta uma vez.
- O progresso por turma não muda.

#### Estágio

Ao retirar as aulas de uma turma, `internship_flow_service.py` retira também as aulas irmãs das aulas conjuntas (J18).
Regista `GAP` em todas, com a razão "Turma em estágio" na turma bloqueada e "Aula conjunta retirada por estágio de {turma}" nas outras.
O carregamento recusa um grupo de aulas irmãs com retirada parcial.

#### Vista semanal

`week_schedule`:

- Na vista da turma, cada aula conjunta traz `joint_classes` com `id` e `name` das outras turmas.
- Na vista do professor, as aulas irmãs formam um só item. O item traz `class_infos` com todas as turmas e o estado do registo de cada uma.
- `class_info` fica igual nas aulas de uma só turma.

### Pré-validação, prontidão e fingerprint

| Código | Severidade | Mensagem | Rota |
| :--- | :--- | :--- | :--- |
| `JOINT_ROOM_CAPACITY` | `BLOCKER` | "A aula conjunta de {disciplina} ({turmas}) precisa de uma sala de {tipo} com pelo menos {n} lugares." | `/rooms` |
| `JOINT_GROUP_INCOMPLETE` | `BLOCKER` | "A aula conjunta de {disciplina} tem menos de duas turmas ativas. Edite ou desfaça a junção." | Página de disciplinas da turma |

O snapshot repete as duas verificações e levanta `SnapshotConfigurationError` com os mesmos códigos.

Prontidão: uma junção conta como válida quando todas as ligações membro são válidas.

Fingerprint: `generation_input_snapshot` acrescenta `joint_lesson_groups`.
Cada entrada tem `subject_id`, `class_ids` e `module_ids`, por ordem.

### Interface

#### Disciplinas e Professores (`ClassSubjects.jsx`)

Na linha expansível da disciplina do item 1, abaixo da checklist de módulos:

- Sem junção: botão secundário "Dar em conjunto com…".
- Com junção: o texto "Em conjunto com {turmas} · Módulos {lista}" e os botões "Editar" e "Desfazer".
- Na checklist, um módulo conjunto mostra o ícone de ligação e fica desativado. O texto de ajuda diz "Retire primeiro este módulo da aula conjunta."
- No tutorial e em `readOnly`, a junção é só de leitura.

Modal "Aula conjunta · {disciplina}":

1. Lista de turmas candidatas com caixas de seleção: turma, curso, ano e professor.
2. Lista de módulos. Só ficam ativos os módulos marcados em todas as turmas escolhidas. Ao criar, todos os comuns ficam marcados.
3. Um módulo já começado fica desativado, com o texto "Já começou".
4. Se as turmas têm professores diferentes, aparece a escolha obrigatória do professor.
5. Antes de gravar: "Esta alteração também muda {turmas}."
6. Os erros da API aparecem junto ao campo, como `teacherBlock`.

"Desfazer" abre uma confirmação: "As turmas {turmas} passam a ter {disciplina} em separado. É preciso gerar o horário de novo."

Mudar o professor de uma disciplina conjunta abre uma confirmação: "O professor muda também em {turmas} (aula conjunta)."

#### Página da turma (`ClassDetails.jsx`)

A tabela "Disciplinas & Professores" mostra a etiqueta "Conjunta" na disciplina, com as outras turmas na dica.

#### Horários (`WeekGrid.jsx`, `Schedules.jsx`, `MySchedules.jsx`)

- Vista da turma: "Português · em conjunto com 10.º MAS".
- Vista do professor: um só bloco com "10.º MKT + 10.º MAS".
- A dica e o `aria-label` incluem todas as turmas.
- A diferença da proposta assinala as aulas conjuntas.

#### Sumário (`LessonLogModal.jsx`)

Numa aula conjunta:

- Um só campo de sumário.
- A secção "Turmas presentes", com uma caixa por turma, todas marcadas.
- Desmarcar uma turma mostra: "A turma fica com uma ocorrência pendente. A direção decide a falta."
- Pelo menos uma turma fica marcada. Para uma aula que não aconteceu, o professor usa "Registar ocorrência".

#### Faltas e Ocorrências (`Occurrences.jsx`)

- Um cartão por aula conjunta: "Aula conjunta · {disciplina} · {turmas}", com o estado de cada turma.
- Ações "Decidir para todas" (`GIVEN`, `GAP`, `SUBSTITUTED`) e ações por turma (`GIVEN`, `GAP`).
- As recomendações e o diagnóstico de substitutos mostram os códigos novos.

#### Hooks

- `useJointCandidates`, `useCreateJointGroup`, `useUpdateJointGroup` e `useDeleteJointGroup` em `catalog/data.js`.
- O sucesso invalida `class-subjects` de todas as turmas membro, `classes`, `readiness` e `invalidatePreparationQueries`.
- O hook do sumário envia `absent_class_ids`. O hook da decisão envia `class_ids`.

## Contracts and Invariants

- Toda a consulta às junções filtra por `organization_id`. A RLS forçada protege as três tabelas.
- Uma ligação turma–disciplina pertence no máximo a uma junção.
- Os módulos conjuntos estão marcados em todas as turmas membro.
- As ligações membro têm o mesmo professor.
- Uma aula nunca mistura módulos conjuntos e separados.
- As aulas irmãs têm o mesmo intervalo, sala, crédito, slices e chave de unidade.
- Uma aula conjunta ocupa todas as turmas membro, um professor e uma sala.
- A sala de uma aula conjunta tem lotação para a soma dos alunos.
- Cada aula nova de uma unidade respeita as precedências da unidade.
- A execução, a dívida e o progresso continuam por atribuição contabilística, ou seja, por turma.
- O ledger continua append-only. Nenhuma regra nova apaga ou reescreve execução.
- Uma escola sem junções produz o mesmo snapshot, a mesma digest e o mesmo horário que hoje.

## States and Transitions

### Junção

| De | Para | Efeito |
| :--- | :--- | :--- |
| Sem junção | Junção criada | Nova revisão de planeamento. A geração seguinte usa as unidades novas. |
| Junção | Junção editada | Igual. As regras J19 limitam módulos e turmas já começados. |
| Junção | Sem junção | Igual. As turmas ficam com unidades `A`. |

### Aula conjunta registada

| Situação | Turmas presentes | Turma ausente |
| :--- | :--- | :--- |
| Sumário com ausência | `COMPLETED`, crédito | `OCCURRENCE` pendente |
| Direção decide `GAP` na ausente | Sem mudança | Dívida e défice. Reposição na unidade `D`. |
| Direção decide `GIVEN` na ausente | Sem mudança | Crédito |
| Professor faltou e direção decide `GAP` para todas | Dívida em todas | Dívida em todas |
| Direção decide `SUBSTITUTED` | Dívida em todas, mais o crédito da disciplina do substituto | Igual |

## Failure Modes

| Falha | Comportamento |
| :--- | :--- |
| Regra de configuração violada | `400` com o código e a mensagem da tabela de regras. Nada muda. |
| Módulo ou turma já começados | `409 JOINT_MODULE_STARTED` ou `JOINT_CLASS_STARTED`. |
| Desmarcar um módulo conjunto | `409 JOINT_MODULE_LOCKED`. |
| Remover uma ligação, turma ou módulo em uso | `409 resource_in_use`. |
| Junção de outra organização | `404 resource_not_found`. |
| Nenhuma sala para a soma dos alunos | `BLOCKER` na pré-validação. A geração devolve `JOINT_ROOM_CAPACITY`. |
| Junção com menos de duas turmas ativas | `BLOCKER`. A geração devolve `JOINT_GROUP_INCOMPLETE`. |
| Professores diferentes nas ligações membro | A geração devolve `JOINT_TEACHER_MISMATCH`. Só acontece com dados escritos fora do serviço. |
| Aula protegida sem unidade depois de mudar a junção | A geração devolve `JOINT_PUBLISHED_LESSONS_CONFLICT` com as turmas e as datas. |
| Aulas irmãs diferentes ou retiradas em parte | O carregamento levanta `JOINT_LESSON_INCONSISTENT`. Nunca repara em silêncio. |
| Turmas sem horas livres em comum | A geração termina `INFEASIBLE` com `JOINT_NO_COMMON_TIME`. |
| Sumário com todas as turmas ausentes | `422`. A mensagem pede "Registar ocorrência". |

## Plano de implementação

Entregue em cinco pull requests a partir de `main`, depois de o item 1 estar integrado.
Cada passo começa com um teste que falha. Cada PR mantém o comportamento das escolas sem junções.

| PR | Conteúdo | O utilizador vê |
| :--- | :--- | :--- |
| 1 — Base de dados e domínio | Migração `0003`, modelos, privacidade, `teaching_units.py`, `class_ids`, precedências, validador `v5`, oráculo e serialização. | Nada. Todas as aulas ficam `A:{a}`. |
| 2 — Motor | Snapshot com unidades, construção, recuperação, modelos anual e de colocação, salas, qualidade, propostas, diferença e aprovação. Família de laboratório com junções. | Nada. Só os testes criam junções. |
| 3 — Configuração | Regras puras, serviço, rotas novas, bloqueios nas rotas existentes, pré-validação, prontidão e fingerprint. | Nada no ecrã. A API aceita junções. |
| 4 — Operação | Sumário com presenças, ocorrências, substitutos, folha semanal, estágio, vista semanal e totais do professor. | Nada no ecrã. |
| 5 — Ecrãs | Disciplinas e Professores, página da turma, horários, sumário e Faltas e Ocorrências. | A funcionalidade completa. |

Os PR 2 e 3 podem ser desenvolvidos em paralelo. O PR 3 só é integrado depois do PR 2.
Sem o motor novo, uma junção criada pela API seria planeada como turmas separadas, sem aviso.
Depois de cada merge, siga o `Deploy check` em `main`, como manda o `AGENTS.md`.

O [WBS — Aulas Conjuntas](JOINT_LESSONS_WBS.md) é dono da decomposição do trabalho.
Define os pacotes, as dependências, o caminho crítico e os critérios de conclusão.

## Testes

### Domínio (unitários)

| Cenário | Ficheiro sugerido |
| :--- | :--- |
| Atribuição sem junção produz uma unidade `A` com o identificador da atribuição. | Novo `backend/tests/unit/test_scheduler_teaching_units.py` |
| Exemplo de referência: `J1 = M1..M4`, `S` com M5 na MKT e M6 na MAS, e as precedências. | Igual |
| Módulo separado entre dois conjuntos cria uma fronteira e duas unidades `J`. | Igual |
| Ausência de uma turma cria a unidade `D` com o défice exato. | Igual |
| Correção que põe uma turma à frente cria défice nas outras. | Igual |
| Unidade sem minutos em falta não cria precedência e mantém a cadeia. | Igual |
| Sala de unidade `J` exige a soma dos alunos. Interseção vazia de salas específicas. | `test_scheduler_room_eligibility.py` |
| `PlanningSnapshot` recusa ciclos, unidades desconhecidas e `u → u`. | `test_scheduler_candidate_contracts.py` |
| Validador: conflito numa turma membro, `PRECEDENCE_VIOLATION`, almoço por turma e reservas por turma. | `test_scheduler_candidate_validation.py`, `test_scheduler_lunch_break_v1.py` |
| `joint_frontier_credit` dá o mesmo crédito a todas as turmas. | `test_scheduler_progress_domain.py` |
| O oráculo e o CP-SAT concordam em instâncias pequenas com junções e precedências. | `test_scheduler_oracle.py` |
| A digest de um snapshot sem junções não muda. | `test_scheduler_candidate_contracts.py` |
| Regras de configuração: uma por código da tabela. | Novo `backend/tests/unit/test_joint_lesson_policy.py` |

### Motor (solver)

| Cenário | Ficheiro sugerido |
| :--- | :--- |
| A construção coloca a unidade conjunta com todas as turmas livres e respeita as precedências. | `test_scheduler_constructive_progress_v1.py` |
| O período com uma unidade conjunta usa o modelo CP-SAT e não o fluxo. | Igual |
| O modelo anual anula quotas antes da última semana da antecessora. | `test_scheduler_annual_planning_v1.py` |
| A colocação ordena antecessora e sucessora na mesma semana. | `test_scheduler_search_v1.py` |
| A recuperação repõe o défice antes do segmento seguinte. | `test_scheduler_recovery_construction_v1.py` |
| A família de laboratório com junções gera um candidato válido. Registe os tempos. | `test_scheduler_typology_v1.py` |

### Servidor e operação (integração)

| Cenário | Ficheiro sugerido |
| :--- | :--- |
| A migração preenche `A:{a}` e a nova restrição única aceita aulas irmãs. | `test_scheduler_v1_baseline.py` |
| RLS das três tabelas novas. | `backend/tests/contracts/test_rls_database_policies.py` |
| Criar, editar e desfazer junções. Professor propagado. Junção de outra organização devolve 404. | Novo `backend/tests/integration/committed/test_joint_lesson_groups.py` |
| Bloqueios: desmarcar módulo conjunto, remover ligação, arquivar turma, remover módulo. | Igual e `test_class_subjects.py` |
| Gerar e aprovar com uma junção: aulas irmãs, uma sala, lotação somada. | `test_scheduler_v1_projection.py` |
| Sumário com uma turma ausente: crédito nas presentes, ocorrência na ausente. | `test_scheduler_v1_operations.py` |
| `GAP` na ausente e recuperação adaptativa: aula `D` antes do segmento seguinte. | `test_scheduler_v1_recovery.py` |
| Professor falta: `GAP` em todas e reposição conjunta. | `test_scheduler_v1_occurrences.py` |
| Substituto conjunto válido e as três exclusões novas. | `test_scheduler_v1_occurrences.py` |
| Folha semanal conta a aula conjunta uma vez e exige todos os registos. | `test_timesheets_v1.py` |
| Estágio de uma turma retira as aulas irmãs e regista `GAP` em todas. | `test_internship_flows.py` |
| Alterar uma junção com aulas protegidas devolve `JOINT_PUBLISHED_LESSONS_CONFLICT`. | `test_scheduler_v1_adaptive_changes.py` |
| A pré-validação e o snapshot devolvem `JOINT_ROOM_CAPACITY`. | `backend/tests/contracts/test_preflight_service.py` |
| A fingerprint muda quando a junção muda. | `test_scheduler_fingerprint_service.py` |

### Frontend

- `ClassSubjects.test.jsx`: botão, modal, módulos comuns, módulo começado, escolha do professor, aviso de outras turmas, módulo conjunto bloqueado na checklist, desfazer.
- `ClassDetails.test.jsx`: etiqueta "Conjunta".
- `WeekGrid.test.jsx`: texto da vista da turma, bloco único na vista do professor, `aria-label`.
- `LessonLogModal.test.jsx`: turmas presentes, aviso, pelo menos uma turma, envio de `absent_class_ids`.
- `OccurrencesTabs.test.jsx`: cartão conjunto, decisão para todas e por turma.
- `featureDataHooks.test.jsx`: hooks novos e invalidações.

### E2E

Acrescente um percurso em `frontend/e2e/readiness/` ou numa pasta nova:
crie uma junção entre duas turmas, gere o horário e confirme o bloco único na vista do professor.

## Verification Procedure

Use os comandos da [Command Reference](../00_getting_started/COMMAND_REFERENCE.md#verification-by-change-type) para cada tipo de alteração:

1. Lógica pura: `fast --scope backend -- -k "scheduler or joint"`.
2. Solver: `fast --scope backend -- -k scheduler`. Espere execuções reais do CP-SAT de vários minutos.
3. Endpoint, serviço e consultas: `fast --scope backend`, depois `integration -- -k <área>`.
4. Migração e RLS: `integration` completo, depois as verificações de drift e de triggers.
5. Motor, propostas e API: `integration -- -k scheduler`. A CI não corre `test_scheduler_v1_api.py` nem `test_scheduler_v1_lifecycle.py`.
6. Frontend: `fast --scope frontend -- <ficheiro>`, depois `npm run verify:checks`.
7. Percurso: `e2e --project <nome>`, quando existirem as credenciais de teste do Clerk.
8. CI: `backend`, `frontend`, `e2e-runtime` e `e2e-browser` verdes antes do merge. Depois, `Deploy check` em `main`.

Verificação manual depois do PR 5:

1. Abra `/courses/:courseId/classes/:classId/subjects` como administrador.
2. Crie uma junção de Português entre duas turmas com os módulos 1 a 4.
3. Confirme a junção na outra turma e o bloqueio do módulo 2 na checklist.
4. Gere e aprove o horário. Confirme o bloco único na vista do professor e o texto na vista da turma.
5. Registe um sumário com uma turma ausente. Decida `GAP` em Faltas e Ocorrências.
6. Repare o horário. Confirme a aula de reposição só dessa turma, antes do módulo separado seguinte.

## Riscos e limitações

- **Desempenho.** A sequência estrita e as unidades conjuntas mudam o problema. Não há meta de p95 (D05 do Scheduler V1). Meça com a família de laboratório nova antes de cada merge do PR 2.
- **Construção mais difícil.** A precedência pode levar a construção cronológica a um beco sem saída mais vezes. O recurso continua a ser a pesquisa completa. Registe a taxa de recurso na família de laboratório.
- **Minutos perdidos.** Cada unidade pode acabar numa aula parcial (J09). Mais unidades significam mais minutos sem uso.
- **Mudar a junção a meio do ano.** Aulas protegidas planeadas com a configuração antiga bloqueiam a geração até a janela de estabilidade passar. Melhoria futura: associar essas aulas pelo conteúdo, quando a escola precisar.
- **Reposição de várias turmas ausentes.** Se duas turmas faltam à mesma aula conjunta, cada uma repõe sozinha. Melhoria futura: unidades de défice partilhadas, quando a escola o pedir.
- **Liquidação de dívida.** A política atual liquida a dívida de uma turma com o crédito seguinte, mesmo de uma aula conjunta. O défice continua planeado pelo residual. A vista de dívida pode mostrar zero enquanto a aula `D` está por dar, como já acontece hoje numa turma sozinha.
- **Dados escritos fora do serviço.** As FKs não garantem a disciplina dos membros e dos módulos. O serviço é o único ponto de escrita. O snapshot volta a validar.

## Documentação a atualizar

| Documento | Alteração |
| :--- | :--- |
| [Professional Education](PROFESSIONAL_EDUCATION.md) | Junções, módulos conjuntos e sequência estrita por turma. |
| [Scheduler V1 Tech Spec](../03_scheduler_engine/SCHEDULER_V1_TECH_SPEC_V2.md) | Unidades de ensino, precedência, validador `v5` e decisões J07 a J11. |
| [Scheduler Engine](../03_scheduler_engine/README.md) | Unidades conjuntas na construção, recuperação e modelos. |
| [Data Model](../01_system_architecture/DATA_MODEL.md) | Três tabelas novas, `teaching_unit_key` e a restrição de `stable_key`. |
| [API Reference](../05_backend_api/API_REFERENCE.md) | Rotas novas e campos novos nas rotas existentes. |
| [Lesson Execution](../04_operational_features/LESSON_EXECUTION.md) | Sumário com presenças. |
| [Occurrences and Substitutions](../04_operational_features/OCCURRENCES_AND_SUBSTITUTIONS.md) | Decisões por turma, `SUBSTITUTED` conjunto e regras de substitutos. |
| [Timesheets and Progress](../04_operational_features/TIMESHEETS_AND_PROGRESS.md) | Aula conjunta conta uma vez. |
| [Resource Removal](../05_backend_api/RESOURCE_REMOVAL.md) | Bloqueios de ligação, turma e módulo em junção. |
| [Feedback Message Matrix](../06_frontend_ux/FEEDBACK_MESSAGE_MATRIX.md) | Mensagens novas. |
| [Glossary](../00_getting_started/GLOSSARY.md) | "Aula conjunta" e "Junção". |

## Source Map

- Modelos: `backend/app/models.py`, `backend/app/scheduler/infrastructure/models.py`
- Domínio: `backend/app/scheduler/domain/candidate.py`, `capacity.py`, `candidate_validation.py`, `projection.py`, `demand.py`, `quality.py`
- Snapshot e propostas: `backend/app/scheduler/infrastructure/snapshot.py`, `proposals.py`, `backend/app/scheduler/application/publishing.py`
- Solver: `backend/app/scheduler/infrastructure/constructive.py`, `recovery_construction.py`, `annual_model.py`, `placement_model.py`, `search.py`
- Operação: `backend/app/scheduler/infrastructure/operations.py`, `occurrences.py`, `progress.py`
- Serviços: `backend/app/services/class_service.py`, `timesheet_service.py`, `internship_flow_service.py`, `preflight_service.py`, `scheduler_fingerprint_service.py`
- Ecrãs: `frontend/src/pages/ClassSubjects.jsx`, `ClassDetails.jsx`, `Occurrences.jsx`, `Schedules.jsx`, `MySchedules.jsx`
- Componentes: `frontend/src/components/WeekGrid.jsx`, `LessonLogModal.jsx`

## Related Documents

- [Professional Education](PROFESSIONAL_EDUCATION.md)
- [Scheduler V1 Tech Spec](../03_scheduler_engine/SCHEDULER_V1_TECH_SPEC_V2.md)
- [Lesson Execution](../04_operational_features/LESSON_EXECUTION.md)
- [Occurrences and Substitutions](../04_operational_features/OCCURRENCES_AND_SUBSTITUTIONS.md)
- [Resource Removal](../05_backend_api/RESOURCE_REMOVAL.md)
