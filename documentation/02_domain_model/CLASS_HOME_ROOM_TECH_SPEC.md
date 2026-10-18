# Tech Spec — Sala da turma e tipos de sala

## Purpose

Cada turma passa a maior parte do dia na sua sala. Só muda quando a aula precisa de uma sala própria.
A escola cria os seus próprios tipos de sala, em vez de ficar presa a Normal, Laboratório, Ginásio e Artes.

**Estado:** aprovado pelo responsável de produto e entregue em 18 de outubro de 2026 ([#155](https://github.com/ORIOP25/Cronos/pull/155), [#157](https://github.com/ORIOP25/Cronos/pull/157), [#161](https://github.com/ORIOP25/Cronos/pull/161), [#162](https://github.com/ORIOP25/Cronos/pull/162)).
**Base:** `main` em `e787aa5`, Alembic `0004_joint_lesson_groups`.
**Origem:** item 6 dos pedidos da escola piloto (reunião de 13 de outubro de 2026). Decisões fechadas com o responsável de produto em 15 de outubro de 2026.
A execução vive no [WBS](CLASS_HOME_ROOM_WBS.md).

## Intended Reader

Agentes que implementam e o responsável de produto.

## Prerequisites

O PR 2 do [Tech Spec — Presença dos professores](https://github.com/ORIOP25/Cronos/pull/142) (motor) deve estar em `main`: toca nos mesmos ficheiros do motor. Ver [Coexistência](#coexistência).
Leia o [AGENTS.md](../../AGENTS.md), o [Scheduler V1 Tech Spec](../03_scheduler_engine/SCHEDULER_V1_TECH_SPEC_V2.md), a [School Configuration](SCHOOL_CONFIGURATION.md), a [Importação CSV](../07_data_and_seed/BULK_IMPORT_CSV.md) e a [Command Reference](../00_getting_started/COMMAND_REFERENCE.md).
Carregue `cronos-base`, `ponytail` (`full`), `cronos-backend`, `cronos-scheduler`, `cronos-frontend` e `cronos-frontend-designer`.

## What the System Does

### Problema

A turma muda de sala ao longo do dia. Isso incomoda alunos e professores. A diretora pediu que cada turma fique na sua sala.
A escola também precisa de distinguir salas próprias diferentes, por exemplo uma oficina, um laboratório de Química e uma sala de Informática.

### Comportamento atual observado

| Área | Comportamento | Fonte |
| :--- | :--- | :--- |
| Rota de produção | `SCHEDULER_V1_STOP_AT_FIRST_COMPLETE` vale `True`. A construção rápida devolve o primeiro horário completo, sem otimizar salas. | `backend/app/config.py`; `search.py` `search_complete_schedule` |
| Escolha da sala | Para cada aula, a construção prefere a sala da mesma hora na semana de referência; senão, a sala do tipo certo com menos procura. | `constructive.py` `construct_schedule` (`weekly_pattern`, `room_pressure`) |
| Continuidade | A "mesma sala por turma e disciplina" só existe no caminho exato, e é o último critério. | `placement_model.py` `_optimize_rooms`, `_room_continuity_expression`; `quality.py` `room_change_cost` |
| Sala da turma | Não existe. | `backend/app/models.py` `Class` |
| Tipos de sala | Enum fixo `normal`, `lab`, `gym`, `art`. Uma disciplina pede um tipo; uma sala elegível tem esse tipo e lugares para os alunos. | `models.py` `RoomType`; `constraint_policy.py` `assess_room_eligibility` |
| Salas específicas | A regra `specific_room` (turma + disciplina) existe só na API, sem ecrã. Fica como está. | `constraint_policy.py`; `schedule_service.py` |

### Decisões de produto

| ID | Decisão |
| :--- | :--- |
| D01 | A turma tem um campo opcional "Sala da turma". O valor inicial é "Automática (o Cronos escolhe)". Sem sala definida, o Cronos mantém a turma o mais possível numa sala. |
| D02 | O administrador pode escolher qualquer sala ativa. O Cronos, sozinho, só usa salas do tipo Normal para as disciplinas Normais. |
| D03 | A sala nunca muda a hora de uma aula. O motor decide as horas como hoje e só depois a sala: primeiro a sala da turma; se estiver ocupada, outra sala, de preferência a mesma alternativa nesse dia. |
| D04 | Enquanto a turma tem uma aula que cabe na sua sala, nenhuma outra turma a ocupa. Quando a turma está fora, outras turmas podem usá-la. |
| D05 | Duas turmas podem ter a mesma sala da turma. A lista indica "também é sala da turma X". Se coincidirem, uma vai para outra sala. Não há bloqueio. |
| D06 | Uma aula conjunta vai para a sala da turma de uma das turmas, se couberem todos os alunos; senão, para outra sala com lugares. |
| D07 | As disciplinas com sala própria vão para uma sala do seu tipo. A mesma disciplina da mesma turma fica, se possível, sempre na mesma sala. A regra passa a valer também na rota de produção. |
| D08 | O campo fica na página da turma, no botão "Editar". O cabeçalho mostra "Sala {nome}" ou "Sala automática". Só o administrador o altera. Mantém-se entre anos letivos. |
| D09 | Arquivar ou apagar uma sala que é sala de turma deixa essas turmas em Automática. A confirmação diz quais são. |
| D10 | Mudar a sala da turma deixa desatualizada uma proposta pendente. Na atualização seguinte, só as aulas futuras fora da janela de estabilidade mudam de sala. |
| D11 | A proposta mostra "Mudanças de sala evitáveis: N": vezes em que uma turma mudou de sala entre duas aulas seguidas do mesmo dia sem que nenhuma das duas precisasse de sala própria. Não há lista por turma. |
| D12 | Uma sala da turma que não é Normal recebe as disciplinas Normais dessa turma e as disciplinas do seu tipo. As outras vão para salas do seu tipo. |
| D13 | A lotação conta: a lista só mostra salas com lugares para a turma. Se a turma crescer acima da lotação, a página da turma mostra um aviso e o Cronos trata a turma como Automática até alguém corrigir. |
| D14 | Cada escola cria os seus tipos de sala. Os tipos entram neste spec e são entregues primeiro. |
| D15 | "Normal" existe em todas as escolas e não se apaga nem muda de nome. Laboratório, Ginásio e Artes são tipos iniciais: a escola pode mudar-lhes o nome ou removê-los. |
| D16 | Os tipos gerem-se na página Salas, no botão "Tipos de sala": lista com quantas salas e disciplinas usam cada tipo, criar, mudar o nome e remover. |
| D17 | Remover um tipo segue a regra das salas e disciplinas: bloqueado se uma sala ou disciplina ativa o usa (a mensagem diz quais); arquivado se só objetos arquivados o usam; apagado se ninguém o usa. |
| D18 | Na importação CSV, um tipo desconhecido é criado. A pré-visualização lista "Tipos de sala novos". Maiúsculas e acentos não contam. |
| D19 | Cada disciplina tem um só tipo. Os tipos são de cada escola. As escolas atuais mantêm os 4 tipos e as escolas novas começam com eles. Não há dois tipos com o mesmo nome. Todos os tipos usam a mesma etiqueta neutra. Só o administrador os gere. Mudar o tipo de uma sala ou disciplina desatualiza uma proposta pendente. |
| D20 | O ficheiro "Cursos e turmas" ganha a coluna opcional "Sala da turma" (vazio = Automática). Só serve para turmas novas; depois altera-se na página da turma. |

### Decisões técnicas

| ID | Decisão |
| :--- | :--- |
| T01 | Tabela nova `room_type` (modelo `SchoolRoomType`): `id`, `organization_id`, `name` até 60 caracteres, `is_normal`, `is_archived`. RLS forçado, `UNIQUE (organization_id, id)`, índice único em `(organization_id, lower(name))` e índice único parcial em `organization_id` com `is_normal`. `room.room_type_id` e `subject.room_type_id` com chave composta para `room_type (organization_id, id)`. No fim do PR 1 são `NOT NULL` e o enum `RoomType`, `room.type` e `subject.required_room_type` saem. |
| T02 | A migração `0006_room_types` é feita em dois tempos dentro do PR 1, antes do merge. O S1 cria a tabela, cria os 4 tipos em cada escola e preenche `room_type_id` a partir do enum, ainda nulo. O S4 edita a mesma migração: `NOT NULL` e remoção do enum. Cada slice fica verde sozinho. |
| T03 | Uma só função, `ensure_initial_room_types`, cria os 4 tipos de forma idempotente (por `is_normal` e pelo nome dobrado). Usam-na `complete_foundation` e a fixture `create_org_and_user` de `backend/tests/_support/db_fixtures.py`, que cria escolas já com a fundação concluída. As rotas de recursos exigem a fundação concluída (`deps.py`). A tabela entra em `PRIVACY_TABLES` de `backend/scripts/privacy.py`. |
| T04 | A comparação de nomes ignora maiúsculas e acentos com o `_fold` de `bulk_import_policy.py`, tornado público como `fold_text`. Criar um nome igual ao de um tipo arquivado restaura esse tipo. |
| T05 | A migração `0007_class_home_room` acrescenta `class.home_room_id` (nulo), com chave composta para `room (organization_id, id)` (`uq_room_org_id` já existe na migração base). Sem ação em cascata: `resource_removal.remove_room_configuration` limpa a coluna na mesma transação. |
| T06 | `assess_room_eligibility` recebe `home_room_ids`: as salas da turma das turmas da unidade com lugares para a soma dos alunos. Se o tipo da disciplina é Normal, juntam-se às salas do tipo (D12). Uma restrição `specific_room` continua a cortar o conjunto. O snapshot, a pré-verificação e a verificação de substituições usam esta função; a prontidão (`COMPATIBLE_ROOM`) reproduz a regra em SQL. |
| T07 | `PlanningSnapshot.home_rooms` lista pares (`class_id`, `room_id`) só das salas válidas: ativas e com lugares para a turma (D13). `Assignment.needs_special_room` é verdadeiro quando o tipo da disciplina não é Normal. `snapshot_to_dict` só escreve `home_rooms` com pares e `needs_special_room` quando é verdadeiro, como `precedences`. |
| T08 | `home_room_misses` e `avoidable_room_changes` são medidas de `backend/app/scheduler/domain/home_rooms.py`, publicadas nas métricas da proposta. Não entram nos vetores de qualidade: `quality.py`, `QUALITY_POLICY_VERSION` e os testes de oráculo de `test_scheduler_w05_audit.py` ficam iguais. A política de salas aplica-se no passo de salas (T10, T11). |
| T09 | Uma mudança de sala justificada pela sala da turma custa 0 na perturbação adaptativa (`measure_recovery_quality`): a aula entra na sala da turma de uma das suas turmas, ou sai da sala da turma de outra turma. O diff continua a mostrá-la como "Sala alterada". Sem isto, a guarda do caminho exato recusaria sempre a D10. |
| T10 | Um passe de salas novo, `assign_rooms_by_period` em `backend/app/scheduler/infrastructure/room_assignment.py`, reatribui só `room_id` das aulas editáveis, período a período e por ordem cronológica, com o `min_cost_flow` do OR-Tools que `constructive.py` já usa. As horas e as identidades nunca mudam. |
| T11 | Rotas de produção (paragem no primeiro completo), passe sem guarda: o candidato da construção na geração, os dois candidatos da recuperação antes do `min` do vetor, e a colocação do recurso `_unrestricted_fallback`. Caminho exato, passe com guarda (só fica se o vetor de qualidade não piorar): depois de `_optimize_rooms` ou do estágio de salas no modelo, depois de `_stabilize_recovery`, e sobre o incumbente publicado de `_baseline_incumbent`. |
| T12 | No caminho exato (desligado em produção), `_optimize_rooms`, `_room_continuity_expression` e `_refine_room_positions` não mudam. Escolhem, entre horários com os mesmos critérios de tempo, o que poupa salas por turma e disciplina; nunca trocam tempo por sala. ponytail: teto conhecido — aí, a sala da turma só ganha quando não piora o vetor certificado. |
| T13 | Datas em que aulas editáveis se sobrepõem só em parte mantêm as salas da construção. ponytail: teto conhecido; só grelhas irregulares o atingem. |
| T14 | `RoomRead.home_classes` lista as turmas ativas que têm a sala como sala da turma. Serve a lista de escolha (D05) e a confirmação de remoção (D09). Alterar a turma invalida também a lista de salas no frontend. |
| T15 | O validador não muda (`VALIDATOR_VERSION` igual): a elegibilidade já vem de `eligible_room_ids`. Não há dados reais em produção: as conversões da migração não precisam de cuidados de dados. |

### Âmbito e fora de âmbito

Dentro: tipos de sala (dados, API, ecrã, CSV), sala da turma (dados, API, ecrã, CSV), elegibilidade, motor nas três rotas, métrica na proposta.
Fora: ecrã para `specific_room`, lista por turma das mudanças de sala, vários tipos por disciplina, cores por tipo e mudança da sala da turma na criação de turma pela API.

### Exemplos

Turma A com sala da turma N1 (Normal). Um dia: 9h Português em N1, 10h Matemática em N2, 11h Educação Física no Ginásio, 12h Inglês em N1.

| Métrica | Valor | Porquê |
| :--- | :--- | :--- |
| `home_room_misses` | 1 | Matemática podia estar em N1 e está em N2. Educação Física não cabe em N1. |
| `avoidable_room_changes` | 1 | Português → Matemática muda de sala sem precisar. As trocas com Educação Física não contam. |

Turma TGPSI 10 com sala da turma L-03 (Laboratório). Português pode ser em L-03 (D12). Programação (Laboratório) em L-05 conta uma falha de sala da turma, porque L-03 servia. A troca Programação → Português não conta como evitável, porque Programação precisa de sala própria.

## Why the Behavior Exists

O horário só serve à escola se as turmas não andarem de sala em sala sem motivo.
A sala da turma é uma preferência, não uma regra: nunca atrasa o fim das turmas, nunca cria furos e nunca torna um horário impossível.
Os tipos próprios evitam que uma aula de Química vá parar a uma sala de Informática por ambas serem "Laboratório".

## Components and Ownership

### Inventário de leitores e escritores

| Ficheiro | Lê ou escreve | Slice |
| :--- | :--- | :--- |
| `backend/alembic/versions/0006_room_types.py` (novo) | tabela, RLS, tipos iniciais, `room_type_id` preenchido (S1); `NOT NULL` e remoção do enum (S4) | S1, S4 |
| `backend/app/models.py` | `SchoolRoomType`, `room_type_id` nulos (S1); enum sai (S4); `Class.home_room_id` (S8) | S1, S4, S8 |
| `backend/app/schemas.py` | `RoomTypeRead`, `RoomTypeRef` (S1); as nove utilizações do enum: a importação, `SubjectBase`, `SubjectUpdate`, `RoomBase`, `RoomUpdate`, `SubjectSimple`, `SubjectProgressRead`, `ClassSubjectRead`, `TeacherSubjectProgressRead` (S2); `ClassUpdateInCourse`, `ClassRead`, `ClassFullDetailRead`, `RoomRead.home_classes` (S8) | S1, S2, S8 |
| `backend/app/services/room_type_service.py` (novo) | listar, criar, mudar o nome, remover, `ensure_initial_room_types` | S1 |
| `backend/app/api/v1/endpoints/room_types.py` (novo), `backend/app/api/api.py` | rotas `/room-types` | S1 |
| `backend/app/services/foundation_service.py` | `complete_foundation` chama `ensure_initial_room_types` | S1 |
| `backend/scripts/privacy.py` | `PRIVACY_TABLES` com `room_type` | S1 |
| `backend/tests/_support/db_fixtures.py` | `create_org_and_user` cria os tipos iniciais | S1 |
| `backend/app/services/resource_removal.py` | referências de tipos (S1); `remove_room_configuration` limpa `home_room_id` (S8) | S1, S8 |
| `backend/app/services/bulk_import_policy.py` | `fold_text` (S1); tipo por nome (S2); tipos novos e coluna "Sala da turma" (S14) | S1, S2, S14 |
| `backend/app/services/bulk_import_service.py` | `load_snapshot` com tipos, escrita de `room_type_id` (S2); criação de tipos e `home_room_id` (S14) | S2, S14 |
| `backend/app/services/room_service.py` | `_room_snapshot`, escrita com `room_type_id` (S2); `home_classes` (S8) | S2, S8 |
| `backend/app/services/subject_service.py` | snapshot e escrita com `room_type_id` | S2 |
| `backend/app/services/class_service.py` | `room_type` nas disciplinas da turma (S2); `update_class_in_course`, `_class_demand_snapshot`, `get_class_full_details` (S8) | S2, S8 |
| `backend/app/services/course_service.py`, `backend/app/services/teacher_service.py` | carregamento antecipado do tipo da disciplina (`SubjectSimple`, `get_teacher_progress`) | S2 |
| `backend/app/services/dashboard_service.py` | salas por nome de tipo | S2 |
| `backend/tests/factories.py`, `backend/tests/_support/scheduler_v1.py`, `backend/tests/integration/committed/joint_lesson_support.py` | salas e disciplinas com `room_type_id` | S2, S4 |
| `backend/app/scheduler/infrastructure/snapshot.py` | `_build_assignments` por id e nome (S3); salas da turma e `needs_special_room` (S9) | S3, S9 |
| `backend/app/services/preflight_service.py` | elegibilidade por id, mensagem com nome (S3); salas da turma (S9) | S3, S9 |
| `backend/app/services/school_readiness_service.py` | `COMPATIBLE_ROOM` por id (S3); ramo da sala da turma (S9) | S3, S9 |
| `backend/app/services/scheduler_fingerprint_service.py` | `room_type_id` em salas e disciplinas (S3); `home_room_id` em turmas (S8) | S3, S8 |
| `backend/app/scheduler/infrastructure/occurrences.py` | `room_mismatch` das substituições por id (S3) e com sala da turma (S9) | S3, S9 |
| `backend/app/services/schedule_service.py` | validação de `specific_room` por id | S3 |
| `backend/app/scheduler/domain/constraint_policy.py` | `assess_room_eligibility` com `home_room_ids` | S9 |
| `backend/app/scheduler/domain/candidate.py`, `serialization.py` | `HomeRoom`, `PlanningSnapshot.home_rooms`, `Assignment.needs_special_room` | S9 |
| `backend/app/scheduler/domain/home_rooms.py` (novo) | medidas, mudança justificada, chave de escolha de sala | S10 |
| `backend/app/scheduler/domain/recovery.py` | custo 0 da mudança justificada (T09) | S10 |
| `backend/app/scheduler/application/publishing.py` | `metrics` com as duas medidas | S10 |
| `backend/app/scheduler/infrastructure/room_assignment.py` (novo) | `assign_rooms_by_period` | S11 |
| `backend/app/scheduler/infrastructure/search.py` | passe nas rotas de produção (S11); guarda no caminho exato, depois de `_stabilize_recovery` e no incumbente publicado (S12) | S11, S12 |
| `backend/app/scheduler/infrastructure/placement_model.py` | passe na colocação com paragem no primeiro completo (S11) e com guarda numa só janela (S12) | S11, S12 |
| `frontend/src/features/catalog/data.js` | `useRoomTypes` (S5); mutações de tipos (S7); alterar a turma invalida as salas (S13) | S5, S7, S13 |
| `frontend/src/components/Forms/RoomForm.jsx`, `SubjectForm.jsx` | escolha do tipo da escola | S5 |
| `frontend/src/components/RoomTypeBadge.jsx`, `frontend/src/utils/presentation.js` | etiqueta neutra com o nome; `ROOM_TYPES` sai | S5 |
| `frontend/src/pages/Rooms.jsx` | coluna Tipo (S5); botão "Tipos de sala" (S7); confirmação com turmas (S13) | S5, S7, S13 |
| `frontend/src/pages/Subjects.jsx`, `ClassSubjects.jsx`, `ClassDetails.jsx` | etiqueta do tipo (S5); campo e cabeçalho da sala da turma em `ClassDetails.jsx` (S13) | S5, S13 |
| `frontend/src/components/dashboard/ResourceCounts.jsx` | nomes dos tipos | S6 |
| `frontend/src/utils/apiErrors.js` | `required_room_type_name` (S6); erros dos tipos (S7) | S6, S7 |
| `frontend/src/features/imports/data.js` | ajuda dos tipos (S6); "Tipos de sala novos" e "Sala da turma" (S14) | S6, S14 |
| `frontend/src/features/tutorial/tutorialApiAdapter.js`, `tutorialScenario.js` | dados fictícios no contrato novo | S6 |
| `frontend/e2e/utils/scheduler-fixtures.js`, `frontend/e2e/scheduler/generation.spec.js`, `frontend/e2e/readiness/class-module-selection.spec.js` | tiram `type` e `required_room_type` | S6 |
| `frontend/src/components/RoomTypesModal.jsx` (novo) | janela "Tipos de sala" | S7 |
| `frontend/src/components/SmartTable.jsx` | `deleteMessage` aceita uma função da linha | S13 |
| `frontend/src/components/schedules/DraftPanel.jsx` | "Mudanças de sala evitáveis" | S13 |
| `documentation/07_data_and_seed/sample_import_48_classes/Cronos_CursosETurmas_Template.csv` | coluna nova vazia | S14 |

`constructive.py`, `recovery_construction.py` e `quality.py` não mudam: o passe de salas corre depois da construção (T11) e as medidas novas ficam fora do vetor (T08).
`candidate_validation.py` não muda (T15).

## Data or Request Flow

### Contrato HTTP

| Pedido | Quem | Resposta |
| :--- | :--- | :--- |
| `GET /api/v1/room-types/` | administrador | `200` com os tipos ativos: `id`, `name`, `is_normal`, `room_count`, `subject_count` (só objetos ativos) |
| `POST /api/v1/room-types/` | administrador | `201` com o tipo; restaura um arquivado com o mesmo nome (T04) |
| `PATCH /api/v1/room-types/{room_type_id}` | administrador | `200` com o tipo; só muda `name` |
| `DELETE /api/v1/room-types/{room_type_id}` | administrador | `200` com `remove_effect` `archive` ou `hard_delete`, como `DELETE /rooms/{id}` |
| `POST` e `PATCH /api/v1/rooms/` | administrador | `room_type_id` opcional; sem ele vale o tipo Normal |
| `GET /api/v1/rooms/` | membro ativo | cada sala traz `room_type` (`id`, `name`, `is_normal`) e `home_classes` (`id`, `name`) |
| `POST` e `PATCH /api/v1/subjects/` | administrador | `room_type_id` opcional; sem ele vale o tipo Normal |
| leituras de disciplinas | como hoje | `room_type` em vez de `required_room_type` |
| `PATCH /api/v1/courses/{course_id}/classes/{class_id}` | administrador | aceita `home_room_id` (inteiro ou `null` = Automática; ausente = sem mudança) |
| `GET /api/v1/classes/{class_id}` | administrador | `home_room` (`id`, `name`, `capacity`, `room_type`) ou `null` |
| pré-verificação | como hoje | as falhas de sala trazem `required_room_type_name` em vez de `required_room_type` |
| proposta | como hoje | `metrics.home_room_misses` e `metrics.avoidable_room_changes` |

A gravação da sala da turma regista `CLASS_DEMAND`: `_class_demand_snapshot` passa a incluir `home_room_id` (D10).
Criar ou mudar o nome de um tipo não regista alteração do motor: o motor só vê ids.

### Fluxo da interface

1. Salas: o botão "Tipos de sala" abre a janela com Nome, Salas, Disciplinas e ações. A linha Normal mostra "Fixo" e não tem ações. "Novo tipo" cria pelo nome.
2. Formulários de Sala e de Disciplina: lista dos tipos ativos da escola, Normal por defeito.
3. Página da turma, "Editar": campo "Sala da turma" com "Automática (o Cronos escolhe)" e as salas ativas com lugares para a turma, no formato "{nome} · {tipo} · {lugares} lugares", mais " · também é sala da turma {turmas}" quando se aplica (D05, D13).
4. Cabeçalho da turma: "Sala {nome}" ou "Sala automática". Com lotação insuficiente: "A sala {nome} tem {c} lugares e a turma tem {n} alunos. Até corrigir, o Cronos escolhe a sala."
5. Remover uma sala com `home_classes`: a confirmação acrescenta "É a sala da turma de {turmas}. Essas turmas passam a Automática." (D09).
6. Proposta pendente: "{N} mudanças de sala evitáveis" ao lado das outras métricas (D11).

### Importação CSV

- "Tipo de sala" (salas e disciplinas) aceita qualquer nome até 60 caracteres. Vazio dá erro.
- Um nome conhecido usa esse tipo; um arquivado é restaurado; um desconhecido é criado uma só vez, mesmo que apareça nos dois ficheiros com grafias diferentes.
- A pré-visualização conta `room_types` e lista os nomes novos como "Tipos de sala novos".
- O modelo "Cursos e turmas" passa a ter 8 colunas, a última "Sala da turma". O cabeçalho continua exato: só o novo modelo é aceite.
- "Sala da turma" procura uma sala ativa existente ou do ficheiro de salas do mesmo lote, sem distinguir maiúsculas ou acentos. Tem de ter lugares para os alunos da turma.
- O `commit` cria os tipos antes das salas e disciplinas, e define `home_room_id` depois de criar salas e turmas.

### Motor

Definições:

- **Turma com sala:** tem par em `PlanningSnapshot.home_rooms`.
- **Aula flexível:** `needs_special_room` falso.
- **Falha de sala da turma:** por aula e por turma da unidade com sala `h`, quando `h` está em `eligible_room_ids` e a aula não está em `h`.
- **Mudança evitável:** por turma e por dia, nas aulas ordenadas pelo início, cada par seguido de aulas flexíveis em salas diferentes.
- **Mudança justificada (T09):** a aula entra na sala de uma das suas turmas, ou sai da sala de uma turma que não é sua.

O passe `assign_rooms_by_period` (T10):

- Mantém as salas das aulas protegidas e respeita a ocupação fixa (`available_rooms`).
- Para cada grupo de aulas com o mesmo dia, início e fim, faz um emparelhamento de custo mínimo entre aulas e salas livres. A sala atual de cada aula está sempre no domínio, por isso há sempre solução.
- O custo segue uma chave lexicográfica exata, com base maior do que a soma máxima do componente seguinte no grupo:
  1. falhas de sala da turma (D04);
  2. mudança evitável em relação à aula anterior da turma nesse dia (D03);
  3. ocupar a sala de outra turma com sala (D04);
  4. sala habitual: numa aula flexível de turma sem sala, a sala flexível mais usada pela turma até ali; numa aula com sala própria, a sala mais usada pela turma nessa disciplina (D07);
  5. só na recuperação: custo de sair da sala publicada (`_room_cost_for_profile`), exceto mudança justificada.
- Desde 2026-10-18 (decisão do dono, B1), na atualização a sala publicada só desempata. Uma aula com horário publicado pode mudar de sala para a turma ficar numa sala só. As aulas protegidas e as dadas nunca mudam (I06).
- Desempate pelo `room_id`, para ser determinístico.

No caminho exato, o passe só fica se o vetor de qualidade não piorar (T11, T12).

## Contracts and Invariants

### Identificadores

| Campo | Aponta para |
| :--- | :--- |
| `room_type_id` (sala, disciplina, rota `/room-types/{room_type_id}`) | `room_type.id` |
| `home_room_id`, `HomeRoom.room_id` | `room.id`, nunca `room_type.id` |
| `HomeRoom.class_id`, `home_classes[].id` | `class.id` |
| `Assignment.assignment_id` no passe de salas | unidade de ensino do snapshot, nunca `class_subject_link.id` |

### Invariantes

- I01: cada escola com a fundação concluída tem exatamente um tipo Normal ativo.
- I02: todas as leituras e escritas filtram por `organization_id`; `room_type` tem RLS forçado; as chaves compostas impedem referências entre escolas.
- I03: nenhuma sala ou disciplina ativa aponta para um tipo arquivado.
- I04: `home_room_id` aponta sempre para uma sala ativa da mesma escola.
- I05: o passe de salas e os estágios de sala só mudam `room_id`. Datas, horas, identidades e créditos ficam iguais (D03).
- I06: as aulas protegidas e as aulas dadas nunca mudam de sala. Uma aula protegida também mantém a sala quando uma mudança posterior (tipo de sala ou capacidade) a torna inelegível; a validação não a acusa (B2, 2026-10-18).
- I07: um snapshot sem salas da turma e sem disciplinas de sala própria tem o digest de hoje (T07).
- I08: snapshot, pré-verificação, prontidão e substituições usam a mesma regra de elegibilidade (T06).
- I09: um horário de turmas sem sala e só com disciplinas Normais nunca piora em mudanças evitáveis por causa do passe.

## States and Transitions

Um tipo de sala está ativo ou arquivado. Arquivar só acontece pela remoção (D17); criar com o mesmo nome restaura-o (T04).

## Failure Modes

| Situação | Resposta | Texto visível |
| :--- | :--- | :--- |
| Nome de tipo vazio ou com mais de 60 caracteres | `422` | "Escreva um nome de tipo com até 60 caracteres." |
| Nome repetido (sem contar maiúsculas e acentos) | `409 room_type_name_taken` | "Já existe um tipo de sala com este nome." |
| Mudar o nome ou remover Normal | `409 room_type_fixed` | "O tipo Normal é fixo: não pode mudar de nome nem ser removido." |
| Remover um tipo em uso | `409 resource_in_use`, `public_context` com `rooms` e `subjects` | "Este tipo é usado por: {salas e disciplinas}. Mude-lhes o tipo primeiro." |
| Tipo de outra escola, inexistente ou arquivado numa escrita | `404 resource_not_found` | "Tipo de sala não encontrado." |
| Sala da turma de outra escola, inexistente ou arquivada | `404 resource_not_found` | "Sala não encontrada." |
| Sala da turma sem lugares | `422 home_room_capacity` | "A sala {nome} tem {c} lugares e a turma tem {n} alunos." |
| CSV: tipo vazio | erro de validação | "Escreva o tipo de sala." |
| CSV: sala da turma desconhecida | erro de validação | "Sala não encontrada. Escreva o nome de uma sala existente ou do ficheiro de salas." |
| CSV: sala da turma sem lugares | erro de validação | "A sala {nome} não tem lugares para os {n} alunos da turma." |

A turma que cresce acima da lotação da sua sala não dá erro (D13): o aviso aparece na página e o snapshot ignora a sala.

## Cenários de risco

Cada cenário é um teste que falha primeiro. Os caminhos sem pasta estão em `backend/tests/unit/`; `committed/` é `backend/tests/integration/committed/`.

| ID | Perigo | Cenário (teste que falha primeiro) | Ficheiro de teste |
| :--- | :--- | :--- | :--- |
| R01 | Identificadores | `PATCH` da turma com o id de um tipo em vez de uma sala, ou com sala de outra escola, devolve `404` e não grava. | `committed/test_classes_crud.py` |
| R02 | Isolamento | Duas escolas: cada uma só lista os seus tipos; `room_type_id` de outra escola em sala ou disciplina dá `404`; o CSV não encontra tipos nem salas de outra escola. | `committed/test_room_types.py` (novo); `committed/test_bulk_import.py` |
| R03 | Cadeia de migrações | `0006` converte `normal`, `lab`, `gym` e `art` em duas escolas, desce e sobe sem drift; `0007` sobe, desce e sobe. | `committed/test_room_type_migration.py` (novo); provas de migração |
| R04 | Normal fixo | Mudar o nome ou remover Normal dá `409`. A migração cria os tipos numa escola ainda sem fundação; concluir depois a fundação deixa 4 tipos e um só Normal; a escola da fixture de teste tem os 4 tipos. | `test_room_types.py`; `backend/tests/contracts/test_foundation_service.py`; `test_room_type_migration.py` |
| R05 | Reversão | Remover um tipo só usado por uma sala arquivada arquiva-o; criar o mesmo nome restaura o mesmo id; um tipo sem uso é apagado; um tipo usado por uma sala ativa dá `409` com o nome. | `test_room_types.py` |
| R06 | Nomes | "laboratorio" colide com "Laboratório"; mudar o nome para outro já existente dá `409`. | `test_room_types.py` |
| R07 | Leitores do motor (tipos) | Uma disciplina "Oficina" com só salas "Oficina": snapshot, pré-verificação e prontidão concordam; mudar o tipo de uma sala muda o fingerprint e desatualiza a proposta. | `backend/tests/contracts/test_preflight_service.py`; `backend/tests/contracts/test_school_readiness_service.py`; `committed/test_scheduler_fingerprint_service.py` |
| R08 | Substituições | Uma disciplina substituta Normal é aceite na sala da turma do tipo Laboratório e recusada noutro laboratório. | `committed/test_scheduler_v1_occurrences.py` |
| R09 | Limites | Sala da turma com menos lugares que a turma dá `422`; aumentar depois a turma é aceite, o detalhe da turma mostra a sala e o snapshot não a usa. | `test_classes_crud.py`; `committed/test_scheduler_home_room_snapshot.py` (novo) |
| R10 | Escrita | Definir a sala, voltar a Automática e definir outra regista três alterações `CLASS_DEMAND` com `home_room_id` e muda o fingerprint. | `test_classes_crud.py`; `test_scheduler_fingerprint_service.py` |
| R11 | Remoção | Arquivar e apagar uma sala de duas turmas deixa as duas em Automática, na mesma transação; `home_classes` lista-as antes. | `committed/test_resource_removal.py`; `committed/test_rooms_crud.py` |
| R12 | Elegibilidade (D12) | Português da turma com sala L-03 pode ir para L-03; Português de outra turma não; Educação Física da turma não; uma unidade conjunta só usa a sala de uma turma se couberem todos. | `test_scheduler_room_eligibility.py` |
| R13 | Restrição específica | Com `specific_room` para outra sala, a sala da turma não entra no conjunto. | `test_scheduler_room_eligibility.py` |
| R14 | Digest | Sem salas da turma e sem disciplinas de sala própria, o digest fixado não muda; com uma sala da turma, muda. | `test_scheduler_candidate_contracts.py` |
| R15 | Métricas | Os dois exemplos de [Exemplos](#exemplos) dão os valores da tabela; uma aula conjunta conta para cada turma. | `test_scheduler_home_rooms_v1.py` (novo) |
| R16 | Ordem (D03) | No caminho exato, um passe que piora o vetor de qualidade é recusado e o resultado certificado fica. Os testes de oráculo de `test_scheduler_w05_audit.py` ficam iguais e verdes. | `test_scheduler_room_assignment_v1.py`; `test_scheduler_w05_audit.py` (sem alterações) |
| R17 | Prioridade (D04) | A tem sala N1; B sem sala usou N1 de manhã; ambas com aula Normal à mesma hora: A fica em N1. Com A no Ginásio, B pode usar N1. | `test_scheduler_room_assignment_v1.py` (novo) |
| R18 | Partilha (D05, D03) | A e B com N1 em aula ao mesmo tempo: uma fica em N1 e a outra usa a mesma alternativa nas aulas seguintes desse dia. | `test_scheduler_room_assignment_v1.py` |
| R19 | Aula conjunta (D06) | A+B conjunta com N1 de A com lugares para todos: vai para N1; sem lugares: vai para outra sala. | `test_scheduler_room_assignment_v1.py` |
| R20 | Sala própria (D07) | Programação da turma A fica no mesmo laboratório em todas as aulas quando está livre. | `test_scheduler_room_assignment_v1.py` |
| R21 | Histórico (D10) | Com horário publicado, mudar a sala de A: a atualização muda as aulas futuras editáveis para a sala nova; as protegidas e as dadas ficam; a perturbação de sala vale 0 e o diff mostra "Sala alterada". Sem mudanças, a atualização mantém as salas publicadas. No caminho exato, o incumbente publicado também recebe a sala nova. | `test_scheduler_home_rooms_v1.py` (medida); `test_scheduler_recovery_construction_v1.py`, `test_scheduler_search_v1.py` (rotas) |
| R22 | Horas intocáveis | O passe devolve as mesmas aulas, datas e horas; numa data com sobreposição parcial mantém as salas; o validador aceita o resultado. | `test_scheduler_room_assignment_v1.py` |
| R23 | Rotas | Numa instância pequena com solução sem mudanças evitáveis: geração, recuperação e colocação com paragem no primeiro completo chegam a 0; o passe corre depois de `_stabilize_recovery`. | `test_scheduler_search_fallback_v1.py`; `test_scheduler_generation_quality_v1.py`; `test_scheduler_search_v1.py` |
| R24 | Desempenho | A fixture de 48 turmas gera com o passe; o tempo do passe fica registado no pull request. | `test_scheduler_typology_v1.py` (`slow_solver`) |
| R25 | CSV de tipos | "oficina" nas salas e "Oficina" nas disciplinas criam um só tipo; a pré-visualização lista-o; um nome arquivado é restaurado. | `test_bulk_import_policy.py`; `test_bulk_import.py` |
| R26 | CSV da sala da turma | Sala do mesmo lote é aceite; desconhecida ou sem lugares dá erro com linha e coluna; vazia fica Automática. | `test_bulk_import_policy.py`; `test_bulk_import.py` |
| R27 | Ecrã da turma | A lista só mostra salas com lugares, indica "também é sala da turma", grava `null` para Automática e mostra o aviso de lotação. | `frontend/src/test/ClassDetails.test.jsx` |
| R28 | Proposta | O painel mostra "{N} mudanças de sala evitáveis" quando a métrica existe e esconde-a numa proposta desatualizada. | `frontend/src/test/DraftPanel.test.jsx` |
| R29 | Orçamento de consultas | `GET /rooms/` com `home_classes` mantém o número de consultas fixado. | `committed/test_query_budgets.py` |
| R30 | Janela de tipos | Normal sem ações; criar, mudar o nome e remover mostram as mensagens da tabela de falhas. | `frontend/src/test/RoomTypesModal.test.jsx` (novo) |
| R31 | Isolamento | O registo de privacidade classifica `room_type`. | `test_rgpd_contracts.py` |
| R32 | Isolamento | O teste de RLS insere uma sala com `room_type_id` de outra escola e continua a ser recusado pela política, não pela falta da coluna. | `backend/tests/contracts/test_rls_database_policies.py` |

## Coexistência

- Base: `main` em `e787aa5`. Última revisão Alembic: `0004_joint_lesson_groups`. O [spec da presença dos professores](https://github.com/ORIOP25/Cronos/pull/142) reserva `0005_teacher_presence`. Este spec usa `0006_room_types` e `0007_class_home_room`. Se a `0005` não estiver em `main` quando o S1 começar, use o número livre seguinte e ajuste `down_revision`.
- O item 5 (presença) muda `candidate.py`, `serialization.py`, `snapshot.py`, `placement_model.py`, `constructive.py`, `recovery_construction.py` e `schemas.py`. Comece o PR 3 depois do PR 2 dele entrar.
- O item 4 ([CSV de preferências](https://github.com/ORIOP25/Cronos/pull/141)) e o item 5 mudam `bulk_import_policy.py`, `bulk_import_service.py`, `features/imports/data.js` e `BulkImport.jsx`. O S2 e o S14 fazem rebase depois deles.
- Os pull requests #129 e #130 só têm documentação e podem chocar no índice `documentation/02_domain_model/README.md`; quem entra depois resolve.
- Ordem: PR 1; depois PR 2 e PR 3 em paralelo; depois PR 4 (ver o [WBS](CLASS_HOME_ROOM_WBS.md)).

## Verification Procedure

Cada slice tem a sua prova no [WBS](CLASS_HOME_ROOM_WBS.md). Use os perfis de [Verification by change type](../00_getting_started/COMMAND_REFERENCE.md#verification-by-change-type).

- PR 1: perfis de migração, de endpoint, de RLS e de componente frontend; reconstrução do contentor do frontend; `e2e --project app` quando houver entradas Clerk de teste.
- PR 2: perfil de componente frontend e reconstrução do contentor do frontend.
- PR 3: perfis de migração, de endpoint, de solver (com `slow_solver`) e de jobs do motor.
- PR 4: perfis de endpoint e de componente frontend; reconstrução do contentor do frontend.

Verificação manual depois do PR 4: dar a uma turma uma sala Normal e a outra uma sala Laboratório, gerar, e confirmar em Horários, com "Proposta pendente" selecionada, que as aulas Normais ficam nessas salas e que a proposta mostra as mudanças evitáveis.

### Documentação a atualizar

| Guia | O que muda | Slice |
| :--- | :--- | :--- |
| [Scheduler V1 Tech Spec](../03_scheduler_engine/SCHEDULER_V1_TECH_SPEC_V2.md) | elegibilidade com sala da turma, medidas de sala, passe de salas, mudança justificada | S9, S10, S11, S12 |
| [Scheduler Engine](../03_scheduler_engine/README.md) | parágrafo "Weekly pattern" e passe de salas | S11 |
| [School Configuration](SCHOOL_CONFIGURATION.md) | tipos de sala da escola e sala da turma | S1, S8 |
| [Data Model](../01_system_architecture/DATA_MODEL.md) | `room_type` e `class.home_room_id` | S1, S8 |
| [API Reference](../05_backend_api/API_REFERENCE.md) | rotas `/room-types`, campos novos | S1, S2, S8 |
| [Importação CSV](../07_data_and_seed/BULK_IMPORT_CSV.md) | secção "Tipos de sala" e coluna "Sala da turma" | S2, S14 |
| [Glossary](../00_getting_started/GLOSSARY.md) | Tipo de sala, Sala da turma, Mudança de sala evitável | S1, S10 |
| [Feedback Message Matrix](../06_frontend_ux/FEEDBACK_MESSAGE_MATRIX.md) | mensagens da tabela de falhas | S7, S13 |

## Source Map

- Dados e API: `backend/app/models.py`, `backend/app/schemas.py`, `backend/app/services/room_type_service.py`, `room_service.py`, `subject_service.py`, `class_service.py`.
- Motor: `backend/app/scheduler/domain/constraint_policy.py`, `home_rooms.py`, `quality.py`, `recovery.py`; `backend/app/scheduler/infrastructure/snapshot.py`, `room_assignment.py`, `search.py`, `placement_model.py`.
- Interface: `frontend/src/pages/Rooms.jsx`, `frontend/src/components/RoomTypesModal.jsx`, `frontend/src/pages/ClassDetails.jsx`, `frontend/src/components/schedules/DraftPanel.jsx`.
- CSV: `backend/app/services/bulk_import_policy.py`, `backend/app/services/bulk_import_service.py`.

## Related Documents

- [WBS — Sala da turma e tipos de sala](CLASS_HOME_ROOM_WBS.md)
- [Scheduler V1 Tech Spec](../03_scheduler_engine/SCHEDULER_V1_TECH_SPEC_V2.md)
- [Tech Spec — Aulas conjuntas](JOINT_LESSONS_TECH_SPEC.md)
- [Importação CSV](../07_data_and_seed/BULK_IMPORT_CSV.md)
