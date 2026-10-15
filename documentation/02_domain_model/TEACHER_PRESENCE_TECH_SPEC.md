# Tech Spec — Presença dos professores

## Purpose

O administrador define, por professor, se ele tem de ter hora de almoço, um mínimo de horas por presença e um furo máximo.
O motor nunca gera nem repara um horário que quebre estas regras.

**Estado:** aprovado pelo responsável de produto (pedido de implementação de 15 de outubro de 2026).
**Base:** `main` em `e787aa5`, Alembic `0004_joint_lesson_groups`.
**Origem:** item 5 dos pedidos da escola piloto (reunião de 13 de outubro de 2026). Decisões fechadas com o responsável de produto em 15 de outubro de 2026.
A execução vive no [WBS](TEACHER_PRESENCE_WBS.md).

## Intended Reader

Agentes que implementam e o responsável de produto.

## Prerequisites

Nenhum pull request tem de entrar antes.
Leia o [AGENTS.md](../../AGENTS.md), o [Scheduler V1 Tech Spec](../03_scheduler_engine/SCHEDULER_V1_TECH_SPEC_V2.md), a [School Configuration](SCHOOL_CONFIGURATION.md), a [Importação CSV](../07_data_and_seed/BULK_IMPORT_CSV.md) e a [Command Reference](../00_getting_started/COMMAND_REFERENCE.md).
Carregue `cronos-base`, `ponytail` (`full`), `cronos-backend`, `cronos-scheduler`, `cronos-frontend` e `cronos-frontend-designer`.

## What the System Does

### Problema

Os professores efetivos estão na escola o dia todo. Os contratados vêm só para algumas aulas.
Hoje o horário pode dar a um contratado aulas às 9h, às 10h e às 17h, ou uma única hora num dia.
Um contratado não se desloca para uma ou duas horas, nem espera a tarde inteira. Um horário assim não serve.

### Comportamento atual observado

| Área | Comportamento | Fonte |
| :--- | :--- | :--- |
| Almoço | Cada turma e cada professor precisa de um intervalo contínuo dentro da janela de almoço. A regra é igual para todos. | `placement_model.py` `_add_lunch`; `candidate_validation.py` `_check_lunch` |
| Carga diária | A decisão D19 proíbe limites diários implícitos. | [Scheduler V1 Tech Spec](../03_scheduler_engine/SCHEDULER_V1_TECH_SPEC_V2.md#binding-product-decisions) |
| Prioridades | A data de conclusão domina os furos (objetivo lexicográfico). | `placement_model.py` `_solve_scope` |
| Professor | O modelo `Teacher` não tem campos de presença nem de almoço. | `backend/app/models.py` |
| Rota do motor | A construção rápida é a rota principal: `SCHEDULER_V1_STOP_AT_FIRST_COMPLETE` vale `True`. O caminho exato (plano anual e colocação) é a alternativa. | `backend/app/config.py`; `search.py` `search_complete_schedule` |
| Grelha por defeito | O assistente inicial propõe 08:30–17:30, aulas de 50 minutos, intervalos de 10 e almoço 12:30–14:00 com 60 minutos. | `frontend/src/features/foundation/foundationModel.js` |

### Decisões de produto

| ID | Decisão |
| :--- | :--- |
| D01 | A regra é opcional em qualquer professor. Não há tipos de professor. Um professor novo começa sem regra. |
| D02 | A unidade é a hora inteira. O campo chama-se "Mínimo de horas por presença". |
| D03 | Uma presença é a manhã ou a tarde, separadas pela hora de almoço que o motor escolhe para esse professor nesse dia. Sem hora de almoço, o dia inteiro é uma presença. |
| D04 | Cada presença tem 0 horas ou pelo menos o mínimo. As aulas podem ser de turmas diferentes. |
| D05 | O furo máximo só existe com um mínimo. Vem preenchido com 1 hora e aceita qualquer número inteiro. O produto não impõe limite pedagógico; a escola é responsável pelo valor. |
| D06 | O interruptor "Tem de ter hora de almoço? Sim / Não" existe em qualquer professor, vale Sim por defeito e é independente do mínimo. Com Não, o professor fica dispensado da regra do almoço. As turmas têm sempre almoço. |
| D07 | A regra é obrigatória. O motor nunca a quebra. |
| D08 | Antes de gerar, a pré-verificação bloqueia e nomeia o professor que não tem nenhuma presença possível com o mínimo. |
| D09 | Se a geração falhar, a mensagem lista os professores com mínimo e sugere baixar o mínimo, aumentar o furo máximo ou alargar a disponibilidade. A lista é uma pista, não uma prova. |
| D10 | Um professor com pouca carga semanal recebe aulas concentradas, por exemplo 3 horas numa semana e nenhuma na seguinte. |
| D11 | A regra fica na secção "Presença na escola", por cima da grelha, no modal "Editar disponibilidade" da Equipa. A lista da Equipa mostra etiquetas. |
| D12 | Há um só mínimo para a manhã e para a tarde. |
| D13 | O professor vê a regra só em leitura em "Minhas Preferências". |
| D14 | Só o administrador define a regra. A regra é do professor e mantém-se entre anos letivos e versões da grelha. |
| D15 | Alterar a regra conta como alteração de disponibilidade: uma proposta pendente fica desatualizada. |
| D16 | Num horário publicado, só o futuro editável muda. Os dias protegidos e as aulas dadas ficam iguais. |
| D17 | As substituições ficam fora de âmbito. A lista de sugestões de substituto não muda. |
| D18 | A importação em massa usa um modelo CSV novo, "Presença dos professores". O formato está em [Importação CSV](#importação-csv). |
| D19 | A grelha por defeito do assistente inicial passa a 09:00–18:00, aulas de 60 minutos, intervalos de 5 minutos e almoço 12:00–14:00 com 60 minutos. O responsável de produto não sabia se o intervalo é de 5 ou de 10 minutos; o agente escolheu 5, que dá 8 aulas por dia. |

### Decisões técnicas

| ID | Decisão |
| :--- | :--- |
| T01 | Guardar a regra em três colunas de `teacher`, em horas inteiras. Não há tabela nova. |
| T02 | Gravar com `PUT /api/v1/teachers/{teacher_id}/presence`. O modal lê com `GET /api/v1/teachers/{teacher_id}/presence`, ligado ao `teacher.id`, como a leitura da disponibilidade. O professor lê com `GET /api/v1/teachers/me/presence`. `MemberRead.teacher_presence` serve só para as etiquetas da lista. |
| T03 | As regras puras vivem num módulo novo, `backend/app/scheduler/domain/teacher_presence.py`. O validador, a construção rápida, a reparação e a pré-verificação usam o mesmo módulo. O S3 move `_lunch_options` de `placement_model.py` para este módulo, porque o domínio não importa a infraestrutura. |
| T04 | Uma presença só com aulas protegidas fica isenta. Uma presença com pelo menos uma aula editável cumpre a regra contando também as protegidas. As reservas operacionais (substituições planeadas) continuam a ser indisponibilidade, não aulas. |
| T05 | No plano anual, a carga semanal editável de um professor com mínimo é 0 ou pelo menos o mínimo, nas semanas sem aulas protegidas desse professor. É uma condição necessária e evita cortes de realimentação inúteis. |
| T06 | A D19 do motor passa a: "A grelha define a capacidade máxima. O motor não inventa limites de carga; aplica só as regras de presença que a escola define por professor." |
| T07 | `VALIDATOR_VERSION` passa de `v5` a `v6`. Não há migração de dados: não existem dados reais de produção. |
| T08 | No modal, o botão "Guardar disponibilidade" grava cada parte alterada no seu pedido (presença e grelha). Se uma parte falhar, a mensagem diz qual. A parte gravada deixa de estar por guardar. A secção fica desativada até a leitura da presença terminar, para nunca gravar valores por defeito por cima da regra guardada. |
| T09 | O diagnóstico de falha aparece nos estados terminais sem horário: `INFEASIBLE`, `FAILED` e `INCONCLUSIVE`. Não aparece em `CANCELLED` nem em `STALE`. |
| T10 | A fixture de 48 turmas ganha um parâmetro opcional com regras de presença. A fixture atual e o seu teste lento ficam iguais. |

### Âmbito e fora de âmbito

Dentro: grelha por defeito, dados e API, motor (geração, reparação, validação), pré-verificação, mensagem de falha, modal e etiquetas da Equipa, vista do professor e importação CSV.
Fora: substituições (D17), cópia da regra entre professores, regras por dia da semana e mínimos diferentes para a manhã e a tarde (D12).

### Exemplos

Grelha de exemplo com aulas de 60 minutos seguidas, sem intervalos, das 9h às 18h; almoço entre 12h e 14h com 60 minutos; mínimo de 3 horas e furo máximo de 1 hora.
Na grelha por defeito da D19, os intervalos de 5 minutos deixam a aula das 12:15 sempre como almoço de quem o tem obrigatório.

| Almoço | Aulas | Resultado |
| :--- | :--- | :--- |
| Sim | 9h, 10h, 11h e 13h, 14h, 15h | Aceite: almoço às 12h, duas presenças de 3 horas. |
| Sim | 10h, 11h, 12h | Aceite: o almoço passa para as 13h. |
| Sim | 10h, 11h e 17h | Recusado: manhã com 2 horas e tarde com 1. |
| Não | 11h, 12h, 13h, 14h | Aceite: uma presença de 4 horas sem almoço. |
| Não | 9h, 10h e 17h | Recusado: furo de 6 horas. |

## Why the Behavior Exists

A escola piloto só usa o Cronos se o horário de um contratado for praticável.
A regra é explícita e configurada pela escola. Por isso não contradiz a intenção da D19, que proibia limites inventados pelo motor.

## Components and Ownership

### Inventário de leitores e escritores

| Ficheiro | Lê ou escreve | Slice |
| :--- | :--- | :--- |
| `frontend/src/features/foundation/foundationModel.js` | `initialFoundationDraftValues` | S1 |
| `frontend/src/features/foundation/components/OpeningStep.jsx`, `LunchStep.jsx`, `SlotDurationStep.jsx` | valores de recurso (`08:30`, `17:30`, `12:30`, `14:00`, `50`) | S1 |
| `frontend/src/features/timetable/breakTimeline.js` | recurso `50` e `10` quando o valor falta | S1 |
| `backend/alembic/versions/0005_teacher_presence.py` (novo) | colunas e verificações | S2 |
| `backend/app/models.py` | `Teacher` | S2 |
| `backend/app/schemas.py` | `TeacherPresence` e `MemberRead` (S2); `SchedulerV1JobDiagnosticRead` (S7); `BulkImportFiles` e `require_a_file` (S10) | S2, S7, S10 |
| `backend/app/services/teacher_service.py` | `get_teacher_presence`, `set_teacher_presence` (novos), `_teacher_is_scheduled` | S2, S10 |
| `backend/app/api/v1/endpoints/teachers.py` | `PUT /{teacher_id}/presence`, `GET /{teacher_id}/presence`, `GET /me/presence` | S2 |
| `backend/app/services/member_service.py` | `_to_read` | S2 |
| `backend/app/services/scheduler_state_service.py` | `record_scheduler_change` com `entity_type="TEACHER_PRESENCE"` (só chamado) | S2, S10 |
| `backend/app/services/scheduler_fingerprint_service.py` | lista `teachers` de `generation_input_snapshot` | S2 |
| `backend/app/scheduler/domain/candidate.py` | `TeacherPresenceRule` (novo), `PlanningSnapshot.teacher_presence` | S3 |
| `backend/app/scheduler/domain/teacher_presence.py` (novo) | `lunch_options` (movida), divisão em presenças, verificação (S3); capacidade possível (S7); o S6 só importa | S3, S7 |
| `backend/app/scheduler/domain/candidate_validation.py` | `_check_lunch`, `_check_teacher_presence` (novo), `ValidationViolationCode`, `VALIDATOR_VERSION` | S3 |
| `backend/tests/critical_manifest.json` | regista o teste novo no grupo crítico; o limite de 90% de `candidate_validation.py` mantém-se | S3 |
| `backend/app/scheduler/domain/serialization.py` | `snapshot_to_dict` e `snapshot_from_dict` | S3 |
| `backend/app/scheduler/infrastructure/snapshot.py` | `_load_teacher_presence` (novo), montagem do `PlanningSnapshot` | S3 |
| `backend/app/scheduler/infrastructure/placement_model.py` | importa `lunch_options` do domínio (S3); `_lunch_resource_rows`, `_add_lunch` (S4); `_add_teacher_presence` (novo), `_lunch_cache_salt` (S5) | S3, S4, S5 |
| `backend/app/scheduler/infrastructure/annual_model.py` | `_add_quota_variables` (carga semanal do professor) | S5 |
| `backend/app/scheduler/infrastructure/constructive.py` | `_select_period`, `construct_schedule` | S4, S6 |
| `backend/app/scheduler/infrastructure/recovery_construction.py` | `construct_recovery` | S4, S6 |
| `backend/app/scheduler/lab/typology.py` | fixture de 48 turmas com regras de presença | S6 |
| `backend/app/services/preflight_service.py` | bloqueio `TEACHER_PRESENCE_IMPOSSIBLE` | S7 |
| `backend/app/scheduler/domain/diagnostics.py` | `DiagnosisCode.TEACHER_PRESENCE_RULES`, `Diagnosis.affected_teacher_ids` | S7 |
| `backend/app/scheduler/application/generation.py` | resultados sem candidato | S7 |
| `backend/app/scheduler/application/recovery.py` | resultados sem candidato | S7 |
| `backend/app/scheduler/application/publishing.py` | serialização do diagnóstico | S7 |
| `backend/app/scheduler/infrastructure/queries.py` | `_job_diagnostics`: hoje descarta diagnósticos sem `affected_class_ids`; passa a devolver uma linha por professor de `TEACHER_PRESENCE_RULES` | S7 |
| `backend/app/scheduler/infrastructure/jobs.py` | `finish_job` guarda `diagnostics_json` também em `FAILED` e `INCONCLUSIVE` (nunca em `CANCELLED`/`STALE`) | S7 |
| `frontend/src/components/schedules/GenerationStatusPanel.jsx` | mensagem de falha | S7 |
| `frontend/src/components/AvailabilityEditorModal.jsx` | ranhura para a secção e gravação combinada | S8 |
| `frontend/src/components/TeacherAvailabilityModal.jsx` | secção "Presença na escola" | S8 |
| `frontend/src/components/TeacherPresenceSection.jsx` (novo) | campos da secção | S8 |
| `frontend/src/features/operations/data.js` | `useTeacherPresence`, `useSaveTeacherPresence` (S8, invalida a Equipa e as consultas de preparação como a gravação da disponibilidade), `useMyPresence` (S9) | S8, S9 |
| `frontend/src/pages/Members.jsx` | etiquetas na lista | S8 |
| `frontend/src/pages/MyAvailability.jsx` | cartão só de leitura | S9 |
| `frontend/src/features/tutorial/tutorialApiAdapter.js` | `GET /teachers/me/presence` no tutorial | S9 |
| `backend/app/services/bulk_import_policy.py` | recurso `teacher_presence`: modelo, leitura e validação | S10 |
| `backend/app/services/bulk_import_service.py` | modelo dinâmico e `commit_import` | S10 |
| `frontend/src/features/imports/data.js`, `frontend/src/pages/BulkImport.jsx` | secção de importação | S10 |
| `frontend/src/test/importFiles.test.js` | fixa os nomes dos modelos | S10 |

A `ClassAvailabilityModal.jsx` usa o mesmo `AvailabilityEditorModal`. O S8 tem de a manter igual.
O `quality.py` não muda: a métrica de furos já conta o dia inteiro.

## Data or Request Flow

### Modelo de dados e migração

A migração `0005_teacher_presence` tem `down_revision = "0004_joint_lesson_groups"` e acrescenta a `teacher`:

| Coluna | Tipo | Regra |
| :--- | :--- | :--- |
| `lunch_required` | `BOOLEAN NOT NULL DEFAULT true` | D06 |
| `minimum_presence_hours` | `SMALLINT NULL` | `CHECK` entre 1 e 12 |
| `maximum_presence_gap_hours` | `SMALLINT NULL` | `CHECK` entre 0 e 12 |

Um `CHECK` garante que as duas colunas numéricas estão ambas vazias ou ambas preenchidas (D05).
O limite de 12 horas é técnico: o dia escolar fica entre as 08:00 e as 20:00 (`LunchRule`). Não é um limite de produto.

### Contrato HTTP

| Pedido | Quem | Resposta |
| :--- | :--- | :--- |
| `PUT /api/v1/teachers/{teacher_id}/presence` | `AdminActor` | `200` com `TeacherPresence` |
| `GET /api/v1/teachers/{teacher_id}/presence` | administrador, ou o próprio professor | `200` com `TeacherPresence`; `403` para outro professor |
| `GET /api/v1/teachers/me/presence` | professor autenticado | `200` com `TeacherPresence`; `403` sem perfil de professor |
| `GET /api/v1/members` | administrador | cada `MemberRead` traz `teacher_presence`, ou `null` sem perfil de professor |

`TeacherPresence` tem `lunch_required` (booleano), `minimum_hours` (inteiro de 1 a 12, ou `null`) e `max_gap_hours` (inteiro de 0 a 12, ou `null`).
Os dois números são ambos `null` ou ambos preenchidos.
A gravação regista `record_scheduler_change` com `entity_type="TEACHER_PRESENCE"`, valores antes e depois, e `active_resource` igual a `_teacher_is_scheduled`.
Uma gravação sem alterações devolve os valores e não chama `record_scheduler_change`, porque essa função regista um evento `NO_OP` mesmo sem mudança.

### Fluxo da interface

1. Na Equipa, o administrador abre "Editar disponibilidade" de um professor.
2. A secção "Presença na escola" lê `GET /teachers/{teacher_id}/presence` e fica desativada até a leitura terminar (T08). O modal pode abrir pela ligação da pré-verificação antes de a lista da Equipa carregar. Mostra:
   - "Tem de ter hora de almoço?" com Sim e Não;
   - "Mínimo de horas por presença", com a ajuda "Vazio = sem mínimo. Uma presença é a manhã ou a tarde, separadas pelo almoço. Sem hora de almoço, o dia inteiro conta como uma presença.";
   - "Furo máximo dentro da presença", visível só com mínimo; ao preencher o mínimo pela primeira vez, o furo fica com 1;
   - a nota "Vale para todas as grelhas e anos letivos."
3. "Guardar disponibilidade" grava as partes alteradas (T08). Depois invalida a lista da Equipa.
4. A lista da Equipa mostra, ao lado da etiqueta Professor, "Sem almoço" e "Mín. {N}h · furo {M}h" quando se aplicam.
5. Em "Minhas Preferências", o professor vê um cartão só de leitura quando a regra difere do padrão: "A direção definiu: hora de almoço {obrigatória|dispensada}; mínimo de {N} horas por presença; furo máximo de {M} horas."

### Importação CSV

O recurso `teacher_presence` usa o ficheiro `Cronos_PresencaProfessores_Template.csv`, com estes cabeçalhos exatos:
`Nome do professor;Email do professor;Hora de almoço;Mínimo de horas por presença;Furo máximo (horas)`.

- O modelo é dinâmico e vem preenchido com os professores ativos, por nome, e os valores atuais.
- O email identifica o professor, com a mesma procura da secção Professores; pode existir ou vir no mesmo lote, no ficheiro de Professores. O nome serve só para leitura.
- O pedido aceita o ficheiro novo em `BulkImportFiles` (`schemas.py`), incluído na verificação `require_a_file`.
- "Hora de almoço" aceita `Sim` ou `Não`, sem distinguir maiúsculas ou acentos. Vazio vale Sim.
- Mínimo vazio quer dizer sem regra. Furo vazio com mínimo vale 1 hora.
- Cada linha substitui os três valores desse professor. Os professores ausentes ficam iguais.
- Qualquer erro recusa todos os ficheiros, com a linha e a coluna, como nas outras secções.
- O `commit` aplica a presença depois de criar professores e regista uma alteração do motor por professor alterado.
- `created_counts["teacher_presence"]` conta os professores alterados.

### Motor

Definições, a partir de `TeacherPresenceRule` (minutos = horas × 60):

- Com almoço obrigatório e uma janela de almoço configurada, o dia divide-se numa opção de almoço livre. As opções são as de `lunch_options`, movida para o domínio (T03). A manhã tem as aulas que acabam até ao início da opção; a tarde tem as que começam depois do fim.
- O dia cumpre a regra se alguma opção de almoço livre faz as duas presenças cumprir. O CP-SAT escolhe uma opção designada entre as livres; o validador aceita se existir uma.
- Sem almoço obrigatório, ou sem janela de almoço configurada, o dia inteiro é uma presença.
- Minutos da presença: soma das durações físicas das aulas do professor. Uma aula conjunta é uma só aula.
- Furo da presença: soma das durações dos blocos da grelha sem aula entre a primeira e a última aula. Os intervalos entre blocos não contam, como na métrica de furos atual.

Aplicação por rota:

- `placement_model.py`: `_add_lunch` ignora professores com `lunch_required=False`. `_add_teacher_presence` reutiliza a ocupação por posição de `_gap_resource_rows` e as opções de `_add_resource_lunch`. Impõe, condicionado à opção designada, minutos de 0 ou pelo menos o mínimo, e furo até ao máximo. A chave de cache das janelas inclui as regras.
- `annual_model.py`: aplica a T05.
- `constructive.py` e `recovery_construction.py`: ignoram o almoço de quem está dispensado. Preferem continuar uma presença aberta de um professor com mínimo e nunca devolvem um candidato inválido. Se não conseguirem, devolvem `None` e a pesquisa segue pelo caminho exato.
- `candidate_validation.py`: `_check_teacher_presence` devolve `TEACHER_PRESENCE_VIOLATION` com `resource_type="teacher"`. `_check_lunch` ignora professores dispensados.

## Contracts and Invariants

### Identificadores

| Campo | Aponta para |
| :--- | :--- |
| `teacher_id` no caminho de `PUT /teachers/{teacher_id}/presence` | `teacher.id`, nunca `organization_membership.id` |
| `MemberRead.teacher_id` e `MemberRead.teacher_presence` | o `teacher` do membro (`teacher_profile`) |
| `TeacherPresenceRule.teacher_id` e `Diagnosis.affected_teacher_ids` | `teacher.id` |
| `Email do professor` no CSV | email da conta (`user`) do membro com perfil de professor na mesma organização |

### Invariantes

- I01: as colunas numéricas estão ambas vazias ou ambas preenchidas; os limites estão no `CHECK`.
- I02: todas as leituras e escritas filtram por `organization_id`.
- I03: a regra é do professor; nenhuma versão da grelha nem nenhum ano letivo a copia ou apaga.
- I04: `PlanningSnapshot.teacher_presence` contém só regras diferentes do padrão, ordenadas por `teacher_id`, sem repetições. `snapshot_to_dict` só escreve a chave quando a lista não está vazia, como `precedences`; os digests atuais ficam iguais. O digest muda quando uma regra muda.
- I05: `_load_teacher_presence` usa o mesmo filtro de professores do fingerprint: membro ativo, `can_teach` e presente nas atribuições. O fingerprint de prontidão muda quando uma dessas regras muda (D15). Mudar a regra de um professor sem atribuições não desatualiza propostas.
- I06: um candidato que quebre a regra nunca é persistido; o validador é a última barreira.
- I07: as turmas e os professores sem regra têm o comportamento atual.
- I08: as aulas protegidas e as aulas dadas nunca mudam por causa da regra (D16, T04).

## Failure Modes

| Situação | Resposta | Texto visível |
| :--- | :--- | :--- |
| Mínimo fora de 1–12 ou furo fora de 0–12 | `422` | "O mínimo tem de estar entre 1 e 12 horas." / "O furo máximo tem de estar entre 0 e 12 horas." |
| Só um dos números preenchido | `422` | "Indique o mínimo e o furo máximo, ou deixe os dois vazios." |
| Professor de outra organização ou inexistente | `404 resource_not_found` | "Professor não encontrado." |
| Professor sem perfil lê `/me/presence` | `403 access_forbidden` | "Professor sem perfil associado" |
| Nenhuma presença possível | pré-verificação `TEACHER_PRESENCE_IMPOSSIBLE`, `BLOCKER`, rota `/members?teacher_id={id}&panel=availability` | "O professor {nome} não tem nenhuma presença com {N} h disponíveis. Baixe o mínimo, aumente o furo máximo ou reveja a disponibilidade." |
| Geração ou reparação sem candidato, com professores com mínimo | diagnóstico `TEACHER_PRESENCE_RULES` (`ESTIMATE`, com `affected_teacher_ids`); `SchedulerV1JobDiagnosticRead` ganha `teacher_id` e `teacher_name`; estados da T09 | "Não foi possível cumprir as regras de presença. Professores com mínimo de horas: {nomes}. Experimente baixar o mínimo, aumentar o furo máximo ou alargar a disponibilidade." com a ligação "Abrir Equipa" |
| Candidato que quebra a regra | `TEACHER_PRESENCE_VIOLATION`; geração `FAILED` | mensagem técnica no resultado; nada é persistido |
| CSV: valor de almoço inválido | erro de validação | "Escreva Sim ou Não." |
| CSV: mínimo ou furo inválido | erro de validação | "Escreva um número inteiro de horas entre 1 e 12." / "... entre 0 e 12." |
| CSV: furo sem mínimo | erro de validação | "O furo máximo só se aplica com um mínimo de horas." |
| CSV: email desconhecido ou repetido | erro de validação | "Professor não encontrado." / "Este email aparece em mais de uma linha." |

A pré-verificação usa a grelha visível e os blocos Impossível do professor.
Há uma presença possível se algum dia tem um troço de blocos seguidos com pelo menos o mínimo em blocos possíveis, no máximo o furo em blocos Impossível e, com almoço obrigatório, sem sobrepor uma opção de almoço.
O diagnóstico de falha não aparece em cancelamentos, em propostas desatualizadas nem em erros de dados (`INVALID_INPUT`).

## Cenários de risco

Cada cenário é um teste que falha primeiro.

| ID | Perigo | Cenário (teste que falha primeiro) | Ficheiro de teste |
| :--- | :--- | :--- | :--- |
| R01 | Identificadores | `PUT` com o `id` do membro em vez do `teacher.id` não altera outro professor e devolve `404`. | `backend/tests/integration/committed/test_teacher_presence.py` (novo) |
| R02 | Isolamento | `PUT` e CSV com um professor de outra organização devolvem `404` ou erro de validação. | `test_teacher_presence.py`; `backend/tests/integration/committed/test_bulk_import.py` |
| R03 | Almoço dispensado | O motor coloca uma aula de um professor dispensado na janela de almoço; a turma mantém o almoço; o mesmo horário com almoço obrigatório é recusado. | `backend/tests/unit/test_scheduler_lunch_solver_v1.py`; `test_scheduler_lunch_break_v1.py` |
| R04 | Divisão pelo almoço | O validador aceita 10h, 11h, 12h e 14h, 15h, 16h com almoço às 13h (janela 12h–14h). | `backend/tests/unit/test_scheduler_teacher_presence_v1.py` (novo) |
| R05 | Mínimo | 10h, 11h e 17h com mínimo 3 dá `TEACHER_PRESENCE_VIOLATION`; o mesmo horário sem regra é válido. | `test_scheduler_teacher_presence_v1.py` |
| R06 | Furo | Sem almoço, mínimo 3: 9h, 10h, 12h é válido com furo 1; 9h, 10h, 13h é recusado com furo 1 e aceite com furo 2. | `test_scheduler_teacher_presence_v1.py` |
| R07 | Aula conjunta | Uma aula conjunta de duas turmas conta 60 minutos, não 120. | `test_scheduler_teacher_presence_v1.py` |
| R08 | Protegidas | Uma presença só com uma aula protegida de 1 hora não dá violação. A reparação não lhe junta aulas que deixem a presença abaixo do mínimo. | `test_scheduler_teacher_presence_v1.py`; `test_scheduler_recovery_solver_v1.py` |
| R09 | Leitores do motor | Alterar a regra muda o digest, o fingerprint e o `input_revision`; uma proposta pendente fica `STALE`. | `test_teacher_presence.py`; `backend/tests/integration/committed/test_scheduler_fingerprint_service.py` |
| R10 | Escrita múltipla | Um CSV com dois professores altera os dois; um terceiro, ausente, fica igual. | `backend/tests/unit/test_bulk_import_policy.py`; `test_bulk_import.py` |
| R11 | Reversão | Definir o mínimo, apagá-lo e voltar a definir deixa o furo em 1; apagar o mínimo apaga o furo. | `test_teacher_presence.py`; `frontend/src/test/TeacherAvailabilityModal.test.jsx` |
| R12 | Limites | Mínimo 12 e furo 0 são aceites; mínimo 13, furo 13 e números soltos dão `422`. | `test_teacher_presence.py` |
| R13 | Construção rápida | Com professores com regra, `construct_schedule` devolve um candidato válido ou `None`; com `None`, `search_complete_schedule` termina pelo caminho exato. | `test_scheduler_constructive_progress_v1.py`; `test_scheduler_search_fallback_v1.py` |
| R14 | Plano anual | Um professor com 2 horas semanais e mínimo 3 recebe semanas de 0 ou de pelo menos 3 horas, e a geração termina. | `test_scheduler_annual_planning_v1.py` |
| R15 | Pré-verificação | Mínimo 4 com só 3 horas possíveis por presença em todos os dias dá `TEACHER_PRESENCE_IMPOSSIBLE` com o nome; um dia com 4 horas tira o bloqueio. | `backend/tests/contracts/test_preflight_service.py` |
| R16 | Mensagem de falha | Uma geração ou reparação sem candidato com professores com mínimo traz `TEACHER_PRESENCE_RULES` com os nomes, também em `FAILED` e `INCONCLUSIVE`; sem regras, cancelada ou `STALE`, não traz. | `test_scheduler_diagnostics_v1.py`; `test_scheduler_generation_v1.py`; `test_scheduler_recovery_v1.py`; `frontend/src/test/GenerationStatusPanel.test.jsx` |
| R17 | Cadeia de migrações | `0005_teacher_presence` sobe, desce para `0004_joint_lesson_groups` e sobe de novo sem drift. | provas de migração da [Command Reference](../00_getting_started/COMMAND_REFERENCE.md#backend-checks-outside-the-runner) |
| R18 | Histórico | Com um horário publicado, uma regra nova não altera aulas protegidas nem dadas. | `test_scheduler_recovery_solver_v1.py` |
| R19 | Versão da grelha | Gravar a disponibilidade com `on_date` de outra grelha não altera a presença. | `test_teacher_presence.py` |
| R20 | Vista do professor | O professor lê `/me/presence`; o `PUT` de um professor sem perfil de administrador devolve `403`. | `test_teacher_presence.py` |
| R21 | Grelha por defeito | Um rascunho novo do assistente propõe 09:00, 18:00, 60, 5 e almoço 12:00–14:00/60, e gera 8 aulas. | `frontend/src/test/foundationModel.test.js` |
| R22 | Oráculo | Em instâncias mínimas com regra, o ótimo do motor exato é igual ao do oráculo enumerativo. | `test_scheduler_teacher_presence_v1.py` |
| R23 | Falha parcial | No modal, a presença grava, a grelha falha: a mensagem diz que a grelha não foi guardada e a presença deixa de estar por guardar. | `TeacherAvailabilityModal.test.jsx` |
| R24 | Perda de dados | O modal abre pela ligação da pré-verificação antes de a Equipa carregar: a secção fica desativada até ler a regra guardada e nunca grava valores por defeito por cima dela. | `TeacherAvailabilityModal.test.jsx` |
| R25 | Digest | Um snapshot sem regras tem o mesmo digest fixado de hoje; um professor sem atribuições com regra não muda o digest nem o fingerprint. | `test_scheduler_candidate_contracts.py`; `test_teacher_presence.py` |

## Coexistência

- Base: `main` em `e787aa5`. Última revisão Alembic: `0004_joint_lesson_groups`. Nova: `0005_teacher_presence`.
- Os pull requests abertos #129 e #130 só têm documentação. Podem chocar no índice `documentation/02_domain_model/README.md`; quem entrar depois resolve.
- Os pull requests do Dependabot (#138 a #140) não tocam nestes ficheiros.
- O item 4 dos pedidos (CSV de preferências dos professores) ainda não começou. Vai tocar em `bulk_import_policy.py`, `features/imports/data.js`, `BulkImport.jsx` e no modal do professor. Quem entrar depois faz rebase.
- Ordem de merge: PR 1 sozinho; PR 2; depois PR 3 e PR 4 em paralelo (ver o [WBS](TEACHER_PRESENCE_WBS.md)).

## Verification Procedure

Cada slice tem a sua prova no [WBS](TEACHER_PRESENCE_WBS.md). Use os perfis de [Verification by change type](../00_getting_started/COMMAND_REFERENCE.md#verification-by-change-type).

- PR 1: perfil de componente frontend e reconstrução do contentor do frontend.
- PR 2: perfis de solver (incluindo `slow_solver`), de endpoint, de migração e de jobs do motor; perfil de componente frontend e reconstrução do contentor do frontend, por causa do painel do S7.
- PR 3: perfil de componente frontend e reconstrução do contentor do frontend.
- PR 4: perfis de endpoint e de componente frontend.

O PR 2 regista no pull request a medição da fixture de 48 turmas com regras: rota usada (construção rápida ou caminho exato) e tempo.
Verificação manual depois do PR 3: dar a um professor mínimo 3, furo 1 e sem almoço; gerar; confirmar no horário que cada dia dele tem 0 ou pelo menos 3 horas seguidas, com furos de até 1 hora.

### Documentação a atualizar

| Guia | O que muda | Slice |
| :--- | :--- | :--- |
| [Scheduler V1 Tech Spec](../03_scheduler_engine/SCHEDULER_V1_TECH_SPEC_V2.md) | D19 (T06), almoço dispensado, regra de presença, código de validação e diagnóstico | S3, S4, S5, S7 |
| [School Configuration](SCHOOL_CONFIGURATION.md) | secção "Presença dos professores" e grelha por defeito | S1, S2, S8 |
| [API Reference](../05_backend_api/API_REFERENCE.md) | rotas de presença e `MemberRead.teacher_presence` (S2); recurso de importação `teacher_presence` (S10) | S2, S10 |
| [Glossary](../00_getting_started/GLOSSARY.md) | Presença e Furo máximo | S2 |
| [Feedback Message Matrix](../06_frontend_ux/FEEDBACK_MESSAGE_MATRIX.md) | mensagens do modal, da pré-verificação e da falha | S7, S8 |
| [Importação CSV](../07_data_and_seed/BULK_IMPORT_CSV.md) | secção "Presença dos professores" | S10 |

## Source Map

- Dados e API: `backend/app/models.py`, `backend/app/schemas.py`, `backend/app/services/teacher_service.py`, `backend/app/api/v1/endpoints/teachers.py`.
- Motor: `backend/app/scheduler/domain/teacher_presence.py`, `candidate_validation.py`, `placement_model.py`, `annual_model.py`, `constructive.py`, `recovery_construction.py`.
- Interface: `frontend/src/components/TeacherAvailabilityModal.jsx`, `frontend/src/pages/Members.jsx`, `frontend/src/pages/MyAvailability.jsx`.
- CSV: `backend/app/services/bulk_import_policy.py`, `backend/app/services/bulk_import_service.py`.

## Related Documents

- [WBS — Presença dos professores](TEACHER_PRESENCE_WBS.md)
- [Scheduler V1 Tech Spec](../03_scheduler_engine/SCHEDULER_V1_TECH_SPEC_V2.md)
- [Tech Spec — Disponibilidade das Turmas](CLASS_AVAILABILITY_TECH_SPEC.md)
- [Importação CSV](../07_data_and_seed/BULK_IMPORT_CSV.md)
