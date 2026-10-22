# Tech Spec — Prioridades do horário

## Purpose

Cada escola escolhe, de 0 a 4, a importância de 10 critérios do horário. "Acabar os módulos o mais cedo possível" é fixo no máximo (D19). O gerador equilibra os critérios segundo esses pesos, e nenhum critério ganha sempre aos outros.

**Estado:** pronto para implementação. Textos do ecrã, valores recomendados e D15 confirmados pelo responsável de produto a 19 de outubro de 2026.
**Base:** `main` em `3c312d17`, Alembic `0007_class_home_room`. Migração nova: `0008_schedule_priorities`.
**Origem:** item 8 dos pedidos da escola piloto (reunião de 13 de outubro de 2026). Decisões fechadas com o responsável de produto em 19 de outubro de 2026.
A execução vive no [WBS](SCHEDULE_PRIORITIES_WBS.md).

## Intended Reader

Agentes que implementam e o responsável de produto.

## Prerequisites

Nenhum pull request tem de entrar antes.
Leia o [AGENTS.md](../../AGENTS.md), o [Scheduler Engine](README.md), o [Scheduler V1 Tech Spec](SCHEDULER_V1_TECH_SPEC_V2.md), o [Tech Spec — Prioridade a quem tem pouca disponibilidade](AVAILABILITY_PRIORITY_TECH_SPEC.md) e a [Command Reference](../00_getting_started/COMMAND_REFERENCE.md).
Carregue `cronos-base`, `ponytail` (`full`), `cronos-backend`, `cronos-scheduler`, `cronos-frontend` e `cronos-frontend-designer`.

## What the System Does

### Problema

A ordem dos critérios é fixa e igual para todas as escolas. Foi escolhida para a escola piloto, e a própria escola piloto pede para a mudar.
Uma ordem fixa produz absurdos: acabar os módulos um dia mais cedo ganha sempre a evitar 3 horas de tempos livres.

### Comportamento atual observado

| Área | Comportamento | Fonte |
| :--- | :--- | :--- |
| Rota do motor | A construção rápida é a rota por omissão e para no primeiro horário completo. O modelo exato só corre se a construção falhar. | `search.py` `_joint_search`, `search_adaptive_schedule`; `SCHEDULER_V1_STOP_AT_FIRST_COMPLETE` em `backend/app/config.py` |
| Acabar cedo | Não é um critério: a construção percorre o ano hora a hora e enche todas as horas que pode. Nunca deixa uma hora vazia para ganhar noutro critério. | `constructive.py` `_construct_pass`, `_select_period` (`count_weight`) |
| Preferências escondidas | Ordem fixa: prioridade a quem tem pouca disponibilidade, Evitar, turma já começada, disciplina mais atrasada, presença aberta, aulas seguidas, padrão semanal, carga restante, salas. | `constructive.py` função `priority`; `recovery_construction.py` |
| Salas | As horas ficam fixas antes das salas. A sala nunca muda a hora de uma aula. | `room_assignment.py` `assign_rooms_by_period`; `search.py` `_room_pass` |
| Atualizações | Entre a reparação local e a reconstrução ganha o custo da T13, com os dias depois da data preferida dentro dele (T12). Sem pesos, ganha o vetor fixo: dias depois da data preferida, conclusão, perturbação, tempos livres. | `search.py` `search_adaptive_schedule`; `recovery.py` `recovery_vector` |
| Modelo exato | Etapas fixas: conclusão, tempos livres dos professores, das turmas, Evitar, salas. | `placement_model.py` `_solve_scope` |
| Proposta | Mostra aulas alteradas, perturbação, dias de margem, mudanças de sala evitáveis, aulas fora da sala da turma e horas em Evitar (professores, turmas e salas juntos). | `publishing.py` `_base_metrics`; `DraftPanel.jsx` |

### Decisões de produto

| ID | Decisão |
| :--- | :--- |
| D01 | O gerador deixa de ter preferências escondidas. Cada preferência do gerador passa a ser um dos critérios da D02, ou deixa de existir. A escola tem o controlo do que prioriza. |
| D02 | Lista fixa de 11 critérios, pela ordem do ecrã (o (1) é fixo desde a D19; o ecrã mostra 10): (1) Acabar os módulos o mais cedo possível; (2) Evitar tempos livres dos professores; (3) Evitar tempos livres das turmas; (4) Evitar que um professor venha à escola para uma só aula; (5) Evitar que uma turma venha à escola para uma só aula; (6) Respeitar Evitar e Preferencial dos professores; (7) Respeitar Evitar e Preferencial das turmas; (8) Manter a turma na mesma sala; (9) Manter o horário igual de semana para semana; (10) Avançar as disciplinas ao mesmo ritmo; (11) Nas atualizações, mexer pouco no horário publicado. O critério 5 foi pedido pelo responsável de produto a 19 de outubro de 2026: é a escola que declara a sua importância. |
| D03 | Escala de 0 a 4: Ignorar, Pouco importante, Importante, Muito importante, Prioridade máxima. Cada nível vale o dobro do anterior. Ignorar tira o critério da conta. |
| D04 | As regras obrigatórias não têm peso e nunca se quebram: Impossível, mínimo de presença e furo máximo, hora de almoço, tipo de sala e lugares, ordem dos módulos, janela de estabilidade, data preferida e data limite como hoje, e a prioridade a quem tem pouca disponibilidade (serve para o horário caber). |
| D05 | Cada critério mostra uma descrição e o impacto do valor mais baixo e do mais alto, com o que se ganha e o que se perde. Os textos estão em [Textos do ecrã](#textos-do-ecrã). |
| D06 | Os valores recomendados reproduzem o gerador de hoje: acabar cedo primeiro, dar o máximo de horas, conforto dos professores acima do das turmas, alguma estabilidade semanal sem abdicar de acabar cedo, disciplinas ao mesmo ritmo. Os valores estão em [Textos do ecrã](#textos-do-ecrã). Um botão repõe os valores recomendados. |
| D07 | Separador novo "Prioridades do horário" em Configuração, ao lado de "Grelha horária". |
| D08 | Cada critério usa 5 botões lado a lado com o nome do nível, não um slider de arrastar. |
| D09 | Só o administrador vê e edita. Os professores não veem. Os valores ficam de um ano letivo para o seguinte. |
| D10 | Alterar um valor deixa a proposta pendente desatualizada. Guardar os mesmos valores não muda nada. |
| D11 | Os valores aplicam-se às gerações e às atualizações ao longo do ano, só no futuro editável. |
| D12 | A proposta mostra um resumo por critério, comparado com o horário publicado. |
| D13 | O ecrã diz "tempos livres" para as horas sem aula entre aulas. "Furos" continua a querer dizer aulas não dadas por falta. |
| D14 | Superseded by D19. Antes, com "Acabar os módulos o mais cedo possível" em Ignorar, as aulas espalhavam-se até à data preferida. Revê a D10 do [Scheduler V1 Tech Spec](SCHEDULER_V1_TECH_SPEC_V2.md#binding-product-decisions) e a D11 do [spec de disponibilidade](AVAILABILITY_PRIORITY_TECH_SPEC.md). |
| D15 | Com "Manter a turma na mesma sala" acima de Ignorar, a sala pode mudar a hora de uma aula. Revê a regra "a sala nunca muda a hora" do [spec da sala da turma](../02_domain_model/CLASS_HOME_ROOM_TECH_SPEC.md). Em Ignorar, a sala da turma não é considerada. |
| D16 | O agente calibra quanto vale cada critério face aos outros com os dados da escola piloto e de uma escola piloto realista (`lab/realistic_pilot.py`, pedida pelo responsável de produto a 20 de outubro de 2026), e mostra horários de exemplo ao responsável de produto antes de fechar a calibração. A 20 de outubro de 2026 o responsável de produto aceitou, na escola realista, até mais 10% de minutos em Evitar dos professores em troca de muito menos tempos livres e dias com uma só aula. |
| D17 | Não há limite de tempo de geração antes dos testes. Um ciclo de medição (vários cenários, várias corridas, otimizar, repetir) propõe o limite no fim. |
| D18 | A escola realista tem 48 salas no total, incluindo salas especiais; algumas turmas partilham sala. A fixture associa salas próprias apenas às turmas cobertas pelas salas Normal disponíveis. A [fixture](../../backend/app/scheduler/lab/realistic_pilot.py) é a fonte dos detalhes. Decisão do responsável de produto, 20 de outubro de 2026. |
| D19 | "Acabar os módulos o mais cedo possível" deixa de ser configurável. O Cronos acaba sempre o mais cedo possível, para deixar margem para recuperar faltas e ocorrências, e a escola escolhe os outros 10 critérios. Com o critério fixo, as regras de Ignorar deste critério (D14, T07, T13, I05) deixam de se aplicar. Decisão do responsável de produto, 22 de outubro de 2026. |

### Decisões técnicas

| ID | Decisão |
| :--- | :--- |
| T01 | As regras puras vivem em três módulos novos do domínio: `priorities.py` (chaves, níveis, multiplicadores `(0, 1, 2, 4, 8)`, valores recomendados, validação e custos unitários), `priority_metrics.py` (métricas e custo de um horário) e `priority_value.py` (valor de uma opção). Três ficheiros deixam as slices correr em paralelo. |
| T02 | Chaves, pela ordem da D02: `finish_early`, `teacher_gaps`, `class_gaps`, `teacher_single_lessons`, `class_single_lessons`, `teacher_preferences`, `class_preferences`, `class_same_room`, `weekly_stability`, `subject_pace`, `update_stability`. A escola guarda só as 10 chaves das escolhas (`SCHOOL_CRITERION_KEYS`). `finish_early` fica fixo em 4 (`FIXED_LEVELS`, D19); uma chave `finish_early` já guardada é ignorada. |
| T03 | Guarda: coluna `organization_settings.schedule_priorities` JSONB, nula por omissão. Nula quer dizer os valores recomendados. Guardar grava as 11 chaves. O Soft-Reset do ano não mexe em `organization_settings` (`school_year_reset_service.py`), por isso a D09 já vale. |
| T04 | `PlanningSnapshot.priority_weights: PriorityWeights \| None = None`. `snapshot.py` preenche sempre o campo. `None` quer dizer a ordem de hoje e serve as fixtures, o laboratório e os testes atuais. `snapshot_to_dict` só escreve o campo quando não é `None`, para os digests atuais não mudarem. |
| T05 | `construct_schedule` e `construct_recovery` ganham `weights: PriorityWeights \| None = None`. Com `None` correm como hoje, sem mudança (I02). Com pesos, cada opção de um período recebe o valor da T06 em vez da posição na ordem de hoje. |
| T06 | Valor de uma opção (aula, período, sala): soma, por critério, de multiplicador × custo unitário × medida, com a medida em minutos de aula. Positivo: acabar cedo (os minutos da aula), aula seguida à anterior do professor ou da turma, segunda aula de um dia do professor ou da turma, repetir o padrão semanal, disciplina atrasada face às outras da turma. Padrão semanal: cada turma compara com a sua aula, nesse dia da semana e hora, no dia de aula anterior (data da grelha em que a turma não está bloqueada); a mesma disciplina dá crédito, outra disciplina dá 0, hora vazia nesse dia dá −crédito, e sem dia anterior não há medida. Negativo: tempo livre que a aula cria para o professor ou a turma, bloco Evitar ou fora do Preferencial, sala fora da sala da turma, hora que no padrão semanal é de outra disciplina, disciplina adiantada. Só inteiros. A primeira aula de um dia não é penalizada: a construção segue o calendário e não sabe se o dia vai ter uma segunda aula (decisão do responsável de produto, 19 de outubro de 2026). |
| T07 | Uma opção com valor ≤ 0 não é colocada, salvo se for necessária. A hora fica vazia. Isto é o que deixa a escola trocar acabar cedo por outros critérios. Na passagem relaxada (a estrita provou que algum Evitar é inevitável), o Evitar continua a ordenar as opções mas já não deixa a hora vazia, como na construção sem pesos. Escassez: a opção entra também quando `valor + 32 × minutos × tightness` é positivo, onde `tightness` (`AvailabilityLedger.tightness`) é a maior razão procura/capacidade restante dos seus recursos, no máximo 1. Uma hora vazia num calendário cheio não é gratuita, porque a aula ainda tem de ser dada depois. É uma regra do motor e não um critério: uma hora vazia num calendário apertado não é livre, porque a aula ainda tem de ser dada depois. Com `finish_early` em Ignorar, as aulas podem espalhar-se até à data preferida (D14): um calendário até meio ocupado espalha livremente, e o impulso para ensinar cresce até ao pleno à medida que enche. Com `finish_early` em Ignorar, a escassez usa `2t − 1` (com `t` a `tightness`, no mínimo 0), e os outros níveis usam `t`. Assim uma escola apertada ainda acaba. O valor de ordenação não muda. |
| T08 | Uma opção é necessária quando o professor ou uma turma da aula está atrasado no ritmo (`D(t) × C(0) > D(0) × C(t)`, a negação estrita de `on_pace`) ou quando, sem este período, a sua capacidade restante deixa de cobrir a sua procura. Num bloco Evitar desse recurso, é necessária quando a procura restante excede a capacidade neutra restante (o resto do tempo já não chega); enquanto um recurso da opção ainda puder manter o seu Evitar livre, o ritmo não torna a opção necessária, só a perda de capacidade. O Evitar só deixa de penalizar para o recurso que precisa dele (`AvailabilityLedger.needed_evitar`). |
| T09 | Seleção de um período: primeiro o maior número de opções necessárias, ordenadas pela urgência (`AvailabilityLedger.urgency`: a menor capacidade restante entre os recursos com, no máximo, um período de folga, por isso quem tem menos horas livres é servido primeiro, D04); depois a maior soma de valores. A urgência entra no modelo do período como posição (1.º, 2.º, ...), não em minutos, para os coeficientes caberem em inteiros de 64 bits em escolas grandes. A calibração (S7) mostrou que a chave `AvailabilityLedger.priority` deixava sem horário os professores com janelas curtas quando a disponibilidade não tem folga. `_select_period` recebe o valor por opção; com `None` usa a pontuação de hoje (`count_weight + len(options) - rank`), sem mudança. Com pesos, a passagem estrita só coloca aulas até `snapshot.preferred_end_date` (janela estrita); a relaxada e a de preenchimento usam todos os períodos. |
| T10 | Os critérios 4 e 5 contam dias inteiros: um professor ou uma turma "vem para uma só aula" num dia em que tem exatamente uma aula. Uma aula isolada de manhã ou de tarde num dia com aulas no outro turno não conta (responsável de produto, 21 de outubro de 2026). O critério 4 só conta professores sem mínimo de presença; o critério 5 conta todas as turmas. |
| T11 | Se a passagem com pesos (estrita e relaxada) devolve `None`, a construção tenta uma passagem de preenchimento: todas as horas que podem ter aula têm aula e as prioridades só escolhem qual (T07 não deixa horas vazias). Se também devolve `None` sem cancelamento nem fim de prazo, `search.py` repete a construção sem pesos (a de hoje, com as passagens estrita e relaxada). A proposta diz que não seguiu as prioridades (Failure Modes). Depois, `None` segue para o caminho exato, como hoje. A passagem estrita de cada tentativa respeita a janela da T09. |
| T12 | Na atualização, `search_adaptive_schedule` escolhe entre a reparação local e a reconstrução pelo custo da T13 e só por ele; empate: o vetor de hoje. O critério 11 entra aqui: o custo conta as aulas alteradas, e o atraso depois da data preferida entra no custo (T13, T15). |
| T13 | Custo de um horário: soma, por critério, de multiplicador × custo unitário × métrica da secção [Métricas](#métricas). Cada dia em que a última aula acaba depois de `preferred_end_date` soma o multiplicador de `finish_early` × `LATE_DAY_COST` (T15); dentro da data preferida o termo é zero. Serve a T12 e os testes do ciclo; não é mostrado no ecrã. |
| T14 | Com `class_same_room` em Ignorar, a passagem de salas não corre e as salas ficam as da construção. Acima de Ignorar corre como hoje. |
| T15 | Os custos unitários da T06 e da T13 são constantes em `priorities.py`; só a calibração (S7) os muda, e a S7 é a única slice depois da S1 que edita esse ficheiro. Não há configuração por escola além dos níveis. Começam em 4 (`dict.fromkeys(CRITERION_KEYS, 4)`) e os critérios calibrados mudam para `finish_early` 1, `teacher_gaps` 12, `teacher_single_lessons` 60, `class_single_lessons` 40, `teacher_preferences` 80, `class_preferences` 20, `weekly_stability` 8 e `subject_pace` 80 (escala do piloto real). `SCARCITY_UNIT_COST` = 32 (T07). `update_stability` custa 4800 por aula alterada na T13: uma aula movida em "Muito importante" (4 × 4800) vale uma hora de Evitar de professor no mesmo nível (4 × 80 × 60). Só a T13 usa este custo; não é medida de opção (T06). O atraso custa `LATE_DAY_COST` = 2 880 000 por dia depois da data preferida, vezes o multiplicador de `finish_early`: um dia pesa 600 aulas movidas com níveis iguais. Com `finish_early` em Ignorar, o atraso vale 0 (I05). |
| T16 | O caminho exato (`annual_model.py`, `placement_model.py`), o validador e `VALIDATOR_VERSION` não mudam. O caminho exato só corre quando as duas construções falham e mantém as etapas fixas. A proposta diz que não seguiu as prioridades. |
| T17 | O ciclo de medição vive em `backend/app/scheduler/lab/priority_bench.py`. Corre cenários × perfis × 3 repetições e escreve uma tabela com resultado, tempo, memória máxima e as 11 métricas. Um ficheiro exportado da produção entra por argumento e nunca entra no repositório. |

### Âmbito e fora de âmbito

Dentro: guarda e API dos níveis, separador novo, valor das opções nas duas construções, escolha nas atualizações, métricas e resumo da proposta, ciclo de medição e calibração, documentação.
Fora: o modelo exato (T16), critérios novos fora da D02, níveis por turma ou por professor, perfis com nome, notificações aos professores.

### Textos do ecrã

Níveis: 0 Ignorar · 1 Pouco importante · 2 Importante · 3 Muito importante · 4 Prioridade máxima.
O valor recomendado é o valor inicial e o do botão "Repor valores recomendados". Os valores vivem em [`priorities.py`](../../backend/app/scheduler/domain/priorities.py) (`SCHOOL_DEFAULT_LEVELS`).

Desde a D19 o critério 1 não aparece no ecrã: fica fixo em Prioridade máxima. O ecrã mostra os outros 10 critérios.

Os textos de cada critério vivem em [`schedulePriorities.js`](../../frontend/src/features/schoolConfig/schedulePriorities.js):

- título e descrição;
- o que acontece em Ignorar e em Prioridade máxima, com os impactos medidos na escola realista (campanha de 22 de outubro de 2026, no [registo de engenharia](SCHEDULE_PRIORITIES_ENGINEERING_LOG.md));
- um aviso opcional, discreto, com o mesmo estilo do nível recomendado, quando um extremo piora outros critérios de forma visível (responsável de produto, 22 de outubro de 2026).

O topo do separador diz que o Cronos equilibra os critérios, que as regras obrigatórias nunca se quebram e que acaba sempre os módulos o mais cedo possível, para deixar margem para recuperar faltas e ocorrências.
No resumo da proposta, a data do critério 1 chama-se "Data da última aula.".

## Why the Behavior Exists

Cada escola tem prioridades diferentes, e hoje as escolas usam várias aplicações, e até o ChatGPT, para afinar o horário.
Com pesos em vez de uma ordem fixa, uma escola pode trocar um dia de conclusão por menos tempos livres, e outra pode fazer o contrário.
Os valores recomendados mantêm o comportamento que a escola piloto já validou.

## Components and Ownership

### Inventário de leitores e escritores

| Ficheiro | Lê ou escreve | Slice |
| :--- | :--- | :--- |
| `backend/alembic/versions/0008_schedule_priorities.py` (novo) | coluna `schedule_priorities` | S1 |
| `backend/app/models.py` | `OrganizationSettings.schedule_priorities` | S1 |
| `backend/app/schemas.py` | `SchedulePrioritiesRead`, `SchedulePrioritiesUpdate` | S1 |
| `backend/app/scheduler/domain/priorities.py` (novo) | T01, T02, T15 | S1 |
| `backend/app/scheduler/domain/priority_metrics.py` (novo) | métricas e custo (T13) | S3 |
| `backend/app/scheduler/domain/priority_value.py` (novo) | valor de uma opção (T06) | S4 |
| `backend/app/scheduler/domain/candidate.py` | `PlanningSnapshot.priority_weights` | S1 |
| `backend/app/scheduler/domain/serialization.py` | `snapshot_to_dict`, `snapshot_from_dict` | S1 |
| `backend/app/services/settings_service.py` | `get_schedule_priorities`, `update_schedule_priorities`, `record_scheduler_change` com `entity_type="SCHEDULE_PRIORITIES"` | S2 |
| `backend/app/api/v1/endpoints/org_settings.py` | `GET` e `PUT /school/settings/schedule-priorities` (`deps.AdminActor`) | S2 |
| `backend/app/services/scheduler_fingerprint_service.py` | `generation_input_snapshot` junta os níveis resolvidos | S2 |
| `backend/app/scheduler/infrastructure/snapshot.py` | lê os níveis ao montar o snapshot, junto de `_stability_window` | S2 |
| `backend/app/scheduler/application/publishing.py` | `_base_metrics`: `priority_summary` e `priorities_followed` | S3 |
| `backend/app/scheduler/application/generation.py`, `application/recovery.py` | passam o horário publicado a `recovery_proposal_payload` | S3 |
| `backend/app/scheduler/infrastructure/constructive.py` | `construct_schedule(weights=)`, `_construct_pass`, `_select_period` | S4 |
| `backend/app/scheduler/infrastructure/recovery_construction.py` | `construct_recovery(weights=)` | S5 |
| `backend/app/scheduler/infrastructure/search.py` | passa `snapshot.priority_weights`, repetição sem pesos (T11), escolha T12, salas T14, `objective_scope` | S4, S5 |
| `backend/app/scheduler/infrastructure/room_assignment.py` | só é chamado; não muda | — |
| `backend/app/scheduler/lab/*.py`, `backend/tests/_support/scheduler_v1.py` | chamam as construções sem pesos; não mudam | — |
| `backend/app/scheduler/lab/priority_bench.py` (novo) | ciclo de medição (T17) | S6 |
| `frontend/src/pages/SchoolConfig.jsx` | separador novo | S8 |
| `frontend/src/features/schoolConfig/SchedulePrioritiesSection.jsx`, `schedulePriorities.js` (novos) | botões, textos, guardar, repor | S8 |
| `frontend/src/features/schoolConfig/data.js` | `useSchedulePriorities`, `useUpdateSchedulePriorities` | S8 |
| `frontend/src/components/schedules/DraftPanel.jsx` | resumo por critério e aviso de prioridades não seguidas | S9 |
| [School Configuration](../02_domain_model/SCHOOL_CONFIGURATION.md), [Scheduler Engine](README.md), [Scheduler V1 Tech Spec](SCHEDULER_V1_TECH_SPEC_V2.md), [Glossary](../00_getting_started/GLOSSARY.md), [Feedback Message Matrix](../06_frontend_ux/FEEDBACK_MESSAGE_MATRIX.md), [Command Reference](../00_getting_started/COMMAND_REFERENCE.md) | separador, ordem do motor (D10, D21, D33 revistas), termos, mensagens, comando do ciclo | S6, S9 |

## Data or Request Flow

### API

- `GET /api/v1/school/settings/schedule-priorities` devolve `{"levels": {chave: nível}, "defaults": {chave: nível}}`, com as 10 chaves escolhidas (D19). Sem valores guardados, `levels` é igual a `defaults`.
- `PUT /api/v1/school/settings/schedule-priorities` recebe `{"levels": {...}}` com as 10 chaves, inteiros de 0 a 4, sem chaves a mais. Uma chave `finish_early` ou uma chave em falta dá 422. Devolve o mesmo corpo do `GET`.
- O `PUT` regista a mudança com `record_scheduler_change` (`FUTURE_IMPACTING`). Valores iguais aos guardados dão `NO_OP` (D10).

### Geração e atualização

1. `snapshot.py` lê `schedule_priorities` e preenche `priority_weights`.
2. `search.py` chama a construção com `weights=snapshot.priority_weights`.
3. Em cada período, as opções recebem o valor da T06, as não necessárias com valor ≤ 0 saem (T07) e `_select_period` escolhe pela T09.
4. Se a construção com pesos falha, repete sem pesos (T11). Na atualização, a escolha entre reparação local e reconstrução segue a T12.
5. `publishing.py` mede as métricas da proposta e as do horário publicado, e grava `priority_summary`.

### Métricas

| Chave | Métrica do horário | Unidade no resumo |
| :--- | :--- | :--- |
| `finish_early` | data da última aula (`latest_completion_date`) | data |
| `teacher_gaps` | minutos de tempos livres dos professores (`_gap_minutes` de `quality.py`); a hora de almoço contínua dentro da janela não conta (`lunch_minutes_in`) | horas |
| `class_gaps` | minutos de tempos livres das turmas, sem a hora de almoço, como os professores | horas |
| `teacher_single_lessons` | dias (T10) com uma só aula, de professores sem mínimo de presença | dias |
| `class_single_lessons` | dias (T10) com uma só aula, de turmas | dias |
| `teacher_preferences` | minutos de aulas em Evitar dos professores, incluindo períodos fora de Preferencial | horas |
| `class_preferences` | minutos de aulas em Evitar das turmas, incluindo períodos fora de Preferencial | horas |
| `class_same_room` | `avoidable_room_changes` de `home_rooms.py` | mudanças |
| `weekly_stability` | posições (turma, dia da semana, início) cuja disciplina difere da semana letiva anterior, quando os dois dias são letivos para a turma | aulas |
| `subject_pace` | soma, por turma, dos dias entre a primeira e a última disciplina a acabar | dias (média por turma) |
| `update_stability` | `changed_lessons` | aulas |

`priority_summary` é `{"proposal": {chave: valor}, "published": {chave: valor} \| None}`. `published` só existe numa atualização.

## Contracts and Invariants

### Identificadores

| Campo | Aponta para |
| :--- | :--- |
| `organization_settings.organization_id` e o `organization_id` do pedido | `organizations.id` |
| chaves de `levels` | as 10 chaves escolhidas (T02, D19), nunca o texto do ecrã |
| `Assignment.teacher_id` nas métricas e no valor | `teachers.id` |
| `Assignment.class_ids` nas métricas e no valor | `classes.id` |
| sala da turma | `classes.home_room_id` → `rooms.id` |

### Invariantes

- I01: as regras obrigatórias da D04 não mudam. Todo o candidato devolvido passa em `validate_candidate`.
- I02: com `weights=None`, as duas construções produzem as mesmas aulas que em `main` em `3c312d17`.
- I03: os mesmos dados e os mesmos níveis dão o mesmo horário. Não há aleatoriedade nova. A reparação de cada período com pesos para em tempo determinístico; só um prazo global quase esgotado (tempo de relógio) pode cortá-la mais cedo.
- I04: os pesos nunca tornam impossível um horário que a construção de hoje encontra: a T11 repete sem pesos.
- I05: um critério em Ignorar não muda nenhuma escolha. Com "Manter a turma na mesma sala" em Ignorar, a passagem de salas não corre e as salas ficam as da construção (T14).
- I06: a leitura e a escrita dos níveis filtram por `organization_id`. Só o administrador as faz.
- I07: só inteiros no valor e no custo; nenhum `float` entra na comparação.

## Failure Modes

| Situação | Resposta | Texto visível |
| :--- | :--- | :--- |
| Nível fora de 0–4, chave em falta ou a mais | 422 `schedule_priorities_invalid` | "Escolha um nível de 0 a 4 em cada critério." |
| Configuração da escola por criar | 404 `settings_not_found` | a mensagem atual de configuração em falta |
| Professor a ler ou escrever | 403, como as outras rotas de administrador | a página de acesso negado atual |
| Construção com pesos sem saída | repetição sem pesos (T11); `priorities_followed = false` | "Não foi possível seguir as prioridades definidas pela escola nesta proposta. Experimente baixar alguns critérios e gerar outra proposta." |
| As duas construções falham | caminho exato, como hoje (T16); `priorities_followed = false` | o mesmo aviso; não afirma que a proposta segue valores recomendados |
| Proposta pendente quando os níveis mudam | proposta `STALE` | o texto atual de proposta desatualizada |
| Guardar com sucesso | 200 | "Prioridades guardadas. A próxima geração ou atualização usa estes valores." |

## Cenários de risco

Cada cenário é um teste que falha primeiro. Salvo indicação: grelha de 60 minutos às 9h e 10h, de segunda a sexta, data preferida no fim da última semana, níveis recomendados exceto os indicados.

| ID | Perigo | Cenário (teste que falha primeiro) | Resultado exato esperado | Ficheiro de teste |
| :--- | :--- | :--- | :--- | :--- |
| R01 | Validação (domínio) | `PriorityWeights` com as 11 chaves; depois com uma chave em falta, uma a mais, um 5 e um −1. | O primeiro é válido; os outros 4 dão `ValueError`. | `backend/tests/unit/test_scheduler_priorities_v1.py` (novo) |
| R02 | Valores recomendados | `DEFAULT_LEVELS`. | Igual à coluna "Recomendado": `4, 3, 2, 2, 2, 3, 2, 2, 2, 3, 3` pela ordem da T02. | `test_scheduler_priorities_v1.py` |
| R03 | Digest | `build_typology_fixture(12)` com `priority_weights=None`; depois com pesos. | Sem pesos, `snapshot_to_dict` não tem `priority_weights` e o digest é igual ao de `main`. Com pesos, `snapshot_from_dict(snapshot_to_dict(s)) == s`. | `backend/tests/unit/test_scheduler_candidate_contracts.py` |
| R04 | Valor (domínio) | Opção de 60 min que cria 60 min de tempo livre ao professor, com `finish_early=1` e `teacher_gaps=4`. | `option_value == 1×U_finish×60 − 8×U_teacher_gap×60` com os custos unitários de `priorities.py`, calculado por `priority_value.py`. Com `teacher_gaps=0`, o termo do professor é 0 (I05). | `test_scheduler_priorities_v1.py` |
| R05 | Ignorar tudo | 1 turma, 1 professor, 4 semanas, um só período por semana (segunda às 9h), 120 min. Os 11 níveis em 0. | Aulas nas semanas 2 e 4. Com `finish_early=4` e os outros em 0: semanas 1 e 2. | `backend/tests/unit/test_scheduler_weighted_construction_v1.py` (novo) |
| R06 | Hora vazia | 1 semana, 1 aula de 60 min, Evitar do professor às 9h de segunda; `finish_early=1`, `teacher_preferences=4`. | A aula fica às 10h de segunda. Com `teacher_preferences=0`: às 9h de segunda. | `test_scheduler_weighted_construction_v1.py` |
| R07 | Necessária | R06 com Impossível às 10h todos os dias e Evitar às 9h todos os dias. | A aula fica às 9h de segunda: o Evitar não penaliza uma opção necessária. | `test_scheduler_weighted_construction_v1.py` |
| R08 | Sem pesos | `build_typology_fixture(12)` e as fixtures de disponibilidade, de presença e de sala da turma dos testes atuais, com `weights=None`. | Os digests fixos (incluindo `TWELVE_CLASS_CONSTRUCTION_DIGEST`) e os testes atuais não mudam (I02). | `backend/tests/unit/test_scheduler_typology_v1.py` |
| R09 | Repetição sem pesos | `construct_schedule` com pesos devolve `None` (a passagem com pesos substituída por uma que devolve `None`). | `search_complete_schedule` devolve `COMPLETE` com o horário de `weights=None`, e `evidence.objective_scope == "CONSTRUCTIVE_INITIAL"`. Com pesos e sucesso: `"CONSTRUCTIVE_PRIORITIES"` (numa atualização, `"CONSTRUCTIVE_RECOVERY_PRIORITIES"`). | `backend/tests/unit/test_scheduler_search_fallback_v1.py` |
| R10 | Seleção | Período com 2 opções do mesmo professor: A necessária com valor −10 e B com valor 50. | Fica A. Sem A necessária, fica B. | `test_scheduler_weighted_construction_v1.py` |
| R11 | Turno | Professor sem mínimo, janela de almoço 12h–14h: aulas às 9h e às 15h; professor dispensado de almoço com as mesmas aulas. | `teacher_single_lessons == 2` no primeiro e `0` no segundo. Professor com mínimo de presença: `0`. Turma com as mesmas aulas: `class_single_lessons == 2`. | `test_scheduler_priorities_v1.py` |
| R12 | Estabilidade semanal | Turma com disciplina A às 9h de segunda na semana 1, B na semana 2, e segunda da semana 3 feriado. | `weekly_stability == 1`. A semana 3 não conta. | `test_scheduler_priorities_v1.py` |
| R13 | Ritmo | Turma com disciplinas a acabar aos dias 10 e 30 da origem. | `subject_pace == 20`. | `test_scheduler_priorities_v1.py` |
| R14 | Custo | `priority_cost` com os 11 níveis em 0; depois com `class_gaps` de 2 para 3. | 0; o termo `class_gaps` duplica e os outros ficam iguais. | `test_scheduler_priorities_v1.py` |
| R15 | Atualização | Horário publicado e duas reparações: uma com 40 aulas alteradas e 0 min de tempos livres, outra com 2 aulas alteradas e 120 min de tempos livres. `update_stability=4`, `teacher_gaps=0`, `class_gaps=0`; depois o inverso. | Primeiro ganha a de 2 aulas; depois a de 40. | `backend/tests/unit/test_scheduler_recovery_construction_v1.py` |
| R16 | Sala em Ignorar | Fixture de sala da turma do spec da feature 6 com `class_same_room=0`. | `assign_rooms_by_period` não é chamado e as salas são as da construção. | `test_scheduler_weighted_construction_v1.py` |
| R17 | API e permissões | `PUT` com níveis válidos; `GET`; `PUT` com um 5; professor a fazer `GET`; organização B a fazer `GET`. | 200 com os níveis; 422 `schedule_priorities_invalid`; 403; a organização B recebe os seus valores recomendados. | `backend/tests/integration/committed/test_schedule_priorities_api.py` (novo) |
| R18 | Proposta desatualizada | Proposta pendente; `PUT` com um nível diferente; depois `PUT` igual. | `is_stale` passa a `True` e `input_revision` sobe 1; o `PUT` igual regista `NO_OP` e a revisão não sobe. | `test_schedule_priorities_api.py` |
| R19 | Leitores do motor | Mudar `class_gaps` de 2 para 3. | `generation_input_snapshot` muda; o snapshot do motor tem `priority_weights.class_gaps == 3`. | `backend/tests/integration/committed/test_scheduler_fingerprint_service.py` |
| R20 | Mudança de ano | Gravar níveis; Soft-Reset do ano. | O `GET` devolve os mesmos níveis. | `test_schedule_priorities_api.py` |
| R21 | Resumo | `recovery_proposal_payload` com horário publicado; `initial_proposal_payload` sem publicado. | `priority_summary.published` com as 11 chaves e `priority_summary.proposal` com as 11 chaves; na geração inicial, `published is None`. | `backend/tests/unit/test_scheduler_publishing_v1.py` |
| R22 | Ecrã | Separador "Prioridades do horário" com os 10 critérios escolhidos; clicar "Muito importante" em "Evitar tempos livres das turmas"; "Guardar prioridades"; depois "Repor valores recomendados". | O `PUT` leva `class_gaps: 3`; os botões têm `role="radio"` com `aria-checked`; repor volta a `class_gaps: 2` antes de guardar. | `frontend/src/test/SchedulePrioritiesSection.test.jsx` (novo) |
| R23 | Painel | Proposta com `priority_summary` publicado e proposta, e outra com `priorities_followed: false`. | Uma linha por critério com os dois valores; o aviso da Failure Modes só na segunda. | `frontend/src/test/DraftPanel.test.jsx` |
| R24 | Calibração | Ciclo S7 nas fixtures de tipologia de 12 e 48 turmas, na de disponibilidade de 12 turmas e na escola piloto realista, com os valores recomendados. O ficheiro piloto original deixou de ser referência (responsável de produto, 21 de outubro de 2026). | Tipologia e disponibilidade: resultado `COMPLETE`; última aula não posterior à da construção sem pesos; minutos em Evitar dos professores não superiores. Escola realista: a construção sem pesos não a constrói (fica com horas por colocar), por isso exige-se horário completo e válido até à data preferida. | `backend/tests/unit/test_scheduler_typology_v1.py` e `test_scheduler_realistic_pilot_v1.py` (48 turmas e realista marcados `slow_solver`; a realista corre só localmente, cerca de 20 min) |
| R25 | Efeito visível | Para cada critério de 1 a 10, níveis recomendados com esse critério em 0 e depois em 4, na fixture de 12 turmas. | A métrica desse critério com 4 é estritamente melhor do que com 0. | `test_scheduler_typology_v1.py` |

## Coexistência

- Base: `main` em `3c312d17`. Última revisão Alembic: `0007_class_home_room`. Este spec cria `0008_schedule_priorities`.
- Pull requests abertos: #129, #130 e #142 só têm documentação noutras pastas; #138 a #140 são do Dependabot. Nenhum toca nestes ficheiros.
- O branch `fix/foundation-organization-onboarding` (dois commits, sem pull request) toca na Fundação e nos membros, não nestes ficheiros.
- Ordem de merge: PR 1, PR 2, PR 3. O PR 3 pode ser feito em paralelo com o PR 2, mas só entra depois dele: sem o PR 2, o separador guardaria valores sem efeito.
- Depois do deploy do PR 1, o snapshot de entrada passa a incluir os níveis. Uma proposta pendente nesse momento pode ficar desatualizada; gera-se outra.

## Verification Procedure

Cada slice tem a sua prova no [WBS](SCHEDULE_PRIORITIES_WBS.md). Use os perfis de [Verification by change type](../00_getting_started/COMMAND_REFERENCE.md#verification-by-change-type).

- PR 1: perfil de migração, perfil de endpoint e perfil de jobs do motor (`test_scheduler_v1_lifecycle.py` só corre localmente).
- PR 2: perfil do solver, com o teste `slow_solver` de 48 turmas adicionado ao `e2e-runtime` em `ci.yml`; o R24 da escola realista corre localmente. O pull request junta o relatório do ciclo (T17) e a escolha do responsável de produto (D16).
- PR 3: perfil de componente e de jornada no browser, e a stack local reconstruída na worktree.

Verificação manual depois do PR 3: pôr "Acabar os módulos o mais cedo possível" em Ignorar e "Evitar tempos livres das turmas" em Prioridade máxima; gerar; comparar o resumo da proposta com o horário publicado.

## Source Map

- Domínio: `backend/app/scheduler/domain/priorities.py`, `priority_metrics.py`, `priority_value.py`, `candidate.py`, `serialization.py`.
- Construção e pesquisa: `backend/app/scheduler/infrastructure/constructive.py`, `recovery_construction.py`, `search.py`.
- Guarda e API: `backend/app/models.py`, `backend/app/services/settings_service.py`, `backend/app/api/v1/endpoints/org_settings.py`.
- Proposta: `backend/app/scheduler/application/publishing.py`, `frontend/src/components/schedules/DraftPanel.jsx`.
- Ecrã: `frontend/src/features/schoolConfig/SchedulePrioritiesSection.jsx`.
- Ciclo: `backend/app/scheduler/lab/priority_bench.py`.

## Related Documents

- [WBS — Prioridades do horário](SCHEDULE_PRIORITIES_WBS.md)
- [Registo de engenharia — Gerador com prioridades](SCHEDULE_PRIORITIES_ENGINEERING_LOG.md)
- [Scheduler Engine](README.md)
- [Scheduler V1 Tech Spec](SCHEDULER_V1_TECH_SPEC_V2.md)
- [Tech Spec — Prioridade a quem tem pouca disponibilidade](AVAILABILITY_PRIORITY_TECH_SPEC.md)
- [Tech Spec — Presença dos professores](../02_domain_model/TEACHER_PRESENCE_TECH_SPEC.md)
