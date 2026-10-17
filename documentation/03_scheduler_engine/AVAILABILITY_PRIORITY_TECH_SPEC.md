# Tech Spec — Prioridade a quem tem pouca disponibilidade

## Purpose

Quando um professor ou uma turma tem poucas horas disponíveis, o gerador passa a dar-lhe as horas disputadas primeiro.
O gerador passa também a respeitar os blocos Evitar e Preferencial, e avisa antes da pesquisa quando um professor não tem horas suficientes.

**Estado:** aprovado e em implementação.
**Base:** `main` em `01a011e9`, Alembic `0005_teacher_presence`. Não há migração.
**Origem:** item 7 dos pedidos da escola piloto (reunião de 13 de outubro de 2026). Decisões fechadas com o responsável de produto em 17 de outubro de 2026.
A execução vive no [WBS](AVAILABILITY_PRIORITY_WBS.md).

## Intended Reader

Agentes que implementam e o responsável de produto.

## Prerequisites

Nenhum pull request tem de entrar antes.
Leia o [AGENTS.md](../../AGENTS.md), o [Scheduler Engine](README.md), o [Scheduler V1 Tech Spec](SCHEDULER_V1_TECH_SPEC_V2.md) e a [Command Reference](../00_getting_started/COMMAND_REFERENCE.md).
Carregue `cronos-base`, `ponytail` (`full`), `cronos-backend`, `cronos-scheduler` e `cronos-frontend`.

## What the System Does

### Problema

A escola tem muitos professores disponíveis de manhã e poucos à tarde. Alguns só podem estar 2 a 3 horas por dia.
Se as poucas horas desses professores forem ocupadas por quem tinha alternativas, as aulas deles deixam de caber.

### Comportamento atual observado

| Área | Comportamento | Fonte |
| :--- | :--- | :--- |
| Rota do motor | A construção rápida é a rota por omissão e para no primeiro horário completo. O modelo exato só corre se a construção falhar. | `search.py` `_joint_search`, `search_adaptive_schedule`; `SCHEDULER_V1_STOP_AT_FIRST_COMPLETE` em `backend/app/config.py` |
| Ordem da construção | A disponibilidade não entra na ordem. No desempate ganha o professor com **mais** minutos por dar. | `constructive.py` `construct_schedule`, função `priority` |
| Evitar e Preferencial | A construção nunca lê `soft_unavailable`. O Preferencial chega ao motor como Evitar em todos os outros blocos, por isso também não tem efeito. | `constructive.py`; `snapshot.py` `_preference_unavailability` |
| Reparação | A reparação usa o Evitar só como desempate, depois do progresso. | `recovery_construction.py` `construct_recovery` |
| Prova de falta de horas | Existe por atribuição e por turma. Não existe por professor. | `capacity.py` `aggregate_capacity_check`; `diagnostics.py` `diagnose_capacity` |

Medição feita em 17 de outubro de 2026 com protótipos fora do repositório, sobre `construct_schedule` em `main`:

| Cenário | Hoje | Regra deste spec |
| :--- | :--- | :--- |
| 4 turmas, 12 semanas, professores de 2 h e 3 h por dia (R01) | A construção falha | Completo na semana 12 |
| 48 turmas da fixture deste spec (R13) | A construção falha em 28 s nas duas ordens de identificadores | Completo em 24 s, última aula a 15 de junho |
| 12 turmas, Evitar 16h–18h nos professores de dia inteiro | 2628 aulas em blocos Evitar | 0 aulas em blocos Evitar |

### Decisões de produto

| ID | Decisão |
| :--- | :--- |
| D01 | Quando duas aulas disputam a mesma hora, ganha a do professor ou turma com menos horas disponíveis no ano letivo. É a disponibilidade absoluta, não a folga. |
| D02 | A prioridade tem ritmo. Só vale enquanto esse professor ou turma está em dia ou atrasado no seu ritmo normal. Adiantado, perde a prioridade até o ritmo o apanhar. Nunca adianta aulas por causa da prioridade. |
| D03 | Na conta da disponibilidade, um bloco Evitar conta como hora disponível. Só os blocos Impossível e os dias bloqueados tiram horas. |
| D04 | As turmas com pouca disponibilidade têm a mesma prioridade e a mesma conta que os professores. |
| D05 | A prioridade está sempre ligada. Não há opção no ecrã. O item 8 (pesos ajustáveis) pode torná-la ajustável. |
| D06 | Ordem de força: regras obrigatórias; caber no prazo (esta prioridade); Evitar e Preferencial; conforto (progresso equilibrado, padrão semanal, aulas seguidas). |
| D07 | Mantêm-se os quatro níveis: Impossível, Evitar, Neutro e Preferencial. |
| D08 | A rota por omissão passa a respeitar o Evitar. Um bloco Evitar, ou um bloco fora do Preferencial, só recebe aulas quando, sem ele, as aulas desse professor ou turma não cabem até ao fim do ano letivo. |
| D09 | Se um professor não tem horas suficientes, a geração para antes da pesquisa e o painel diz quanto falta, com ligação para a disponibilidade dele. A verificação corre ao carregar em Gerar, no início da geração, e não na lista Verificar: a conta exata precisa do calendário do ano. |
| D10 | A regra vale também na atualização de um horário publicado, só no futuro editável. |
| D11 | O motor continua a acabar o mais cedo possível, como manda a D10 do [Scheduler V1 Tech Spec](SCHEDULER_V1_TECH_SPEC_V2.md#binding-product-decisions). As aulas não são distribuídas pelo ano. |
| D12 | Não há dados novos, ecrãs novos, nem alterações ao CSV ou às grelhas de disponibilidade. |

D11 aceita uma consequência conhecida. As disciplinas de professores de dia inteiro podem acabar mais cedo no ano, e as tardes desse fim de ano ficam vazias.

### Decisões técnicas

| ID | Decisão |
| :--- | :--- |
| T01 | As regras puras vivem num módulo novo, `backend/app/scheduler/domain/availability_priority.py`, com o contrato da secção [Módulo de prioridade](#módulo-de-prioridade). As duas construções usam o mesmo módulo. |
| T02 | A capacidade de um recurso (professor ou turma) é a união dos períodos elegíveis das suas atribuições com procura, dados por `capacity.eligible_periods`, em minutos. Um período partilhado por duas atribuições conta uma vez. O limite de datas é o de `eligible_periods`: a data preferida na geração completa e a data limite na atualização. |
| T03 | A capacidade neutra exclui os períodos dentro de um bloco Evitar do próprio recurso. O Evitar de outro recurso não conta. O Evitar de sala, que só existe em fixtures, fica como hoje. |
| T04 | A procura de um recurso é a soma dos minutos que faltam às suas atribuições no início da construção. Desce a cada aula colocada. Uma aula conjunta conta uma vez para o professor e uma vez para cada turma. |
| T05 | Em dia ou atrasado: `D(t) × C(0) ≥ D(0) × C(t)`, com `D` a procura e `C(t)` a capacidade dos períodos que começam em `t` ou depois. Conta só com inteiros. |
| T06 | Chave de prioridade de uma aula: o menor `C(0)` entre os seus recursos com `D(t) > 0` e em dia. Sem nenhum, vale o maior `C(0)` do snapshot. Um recurso com disponibilidade total empata com quem não tem prioridade. |
| T07 | Ordem em `construct_schedule`: chave de prioridade, depois "a hora é Evitar para algum recurso", depois as chaves de hoje sem mudança. Em `construct_recovery`: as duas primeiras chaves iguais, depois as de hoje; as duas chaves Evitar atuais saem, porque a segunda chave as cobre. |
| T08 | Uma aula numa hora Evitar do recurso `r` só é opção quando `D_r(t)` é maior do que a capacidade neutra de `r` a partir de `t`. |
| T09 | Se a passagem estrita devolve `None` sem cancelamento nem fim de prazo, e a T08 recusou pelo menos uma opção, a mesma função repete uma vez sem T08. O Evitar continua a ser a segunda chave da T07. Depois, `None` segue para o caminho exato, como hoje. |
| T10 | O caminho exato (`annual_model.py`, `placement_model.py`), o validador, o snapshot, o fingerprint e a API não mudam. O modelo exato já conta as preferências no objetivo, depois da conclusão e dos furos. `VALIDATOR_VERSION` mantém-se. Com `SCHEDULER_V1_STOP_AT_FIRST_COMPLETE` desligado, ou com `generate_schedule` sem `stop_at_first_complete`, a construção compete com o caminho exato e a D08 vale só na medida desse objetivo. |
| T11 | `CapacityCheck` ganha `teacher_deficits` com valor por omissão vazio, calculado na mesma passagem de elegibilidade. `proven_infeasible` passa a incluí-lo. A falta de um professor é a sua procura menos a união dos períodos elegíveis das suas atribuições. Só entra o professor cuja falta é maior do que a soma das faltas das suas próprias atribuições, para não repetir um `INSUFFICIENT_INTERSECTION`. |
| T12 | `diagnose_capacity` emite um `INSUFFICIENT_TEACHER_TIME` por entrada de `teacher_deficits`, depois das linhas de turma: âmbito `TEACHER:{id}`, `affected_teacher_ids=(id,)`, `affected_class_ids=()`, sem disciplina, e sugestões `REVIEW_AVAILABILITY` e `REVIEW_END_DATE`. A mensagem de `generate_complete` junta "teacher {id}: N minute(s)" aos detalhes. Sem `affected_class_ids`, `_job_diagnostics` nunca mostra o professor como turma. |
| T13 | A fixture nova `build_availability_typology_fixture` vive em `lab/typology.py`. As fixtures atuais e os seus testes ficam iguais. |
| T14 | Na reparação, o módulo nasce depois de conservar as posições publicadas. `D(0)` é o que falta depois delas. Os períodos que essas aulas ocupam saem da capacidade do professor e das turmas que ocupam. |

### Âmbito e fora de âmbito

Dentro: ordem das duas construções, Evitar e Preferencial na construção, repetição relaxada, prova de falta de horas por professor, linha no painel da geração, fixture e documentação.
Fora: distribuir as aulas pelo ano (D11), pesos ajustáveis (item 8), lista Verificar (D09), modelo exato, substituições.

### Exemplos

Grelha de 8 aulas de 60 minutos, das 9h às 13h e das 14h às 18h.

| Situação | Hoje | Depois |
| :--- | :--- | :--- |
| O professor R (só 9h–11h) e o professor F (dia inteiro) disputam a aula das 9h de uma turma. | Ganha F, que tem mais horas por dar. | Ganha R enquanto estiver em dia. F vai para a tarde. |
| O professor L está 10 h por semana e só dá 2 h. | — | L ganha enquanto está em dia. Adiantado, perde a vez e não dá a disciplina toda em outubro. |
| Uma turma com estágio todas as tardes partilha um professor com outra turma. | A turma do estágio pode perder manhãs. | A turma do estágio ganha as manhãs. |
| Um professor tem Evitar às 16h e às 17h e horas de sobra no resto. | Recebe aulas nesses blocos. | Não recebe aulas nesses blocos. |
| O mesmo professor precisa de 34 h numa semana e só tem 30 h fora do Evitar. | Usa 8 blocos Evitar. | Usa exatamente 4 blocos Evitar. |
| Um professor marca Preferencial das 9h às 11h e dá 8 h por semana. | Só 2 aulas nos blocos Preferencial. | As 8 aulas nos blocos Preferencial. |
| Um professor tem 5 h possíveis e precisa de 6 h. | A pesquisa corre até falhar. | A geração para antes da pesquisa: "faltam pelo menos 1 h". |

## Why the Behavior Exists

Uma hora dada a quem tinha alternativas é uma hora que um professor de horário curto não recupera.
O responsável de produto escolheu a disponibilidade absoluta porque um professor de 30 h pode ceder horas e um de 10 h não.
O ritmo impede que essa prioridade concentre as aulas de quem tem pouca carga no início do ano.
O Evitar e o Preferencial já eram promessas dos ecrãs de disponibilidade. Este spec cumpre-as na rota por omissão.

## Components and Ownership

### Inventário de leitores e escritores

| Ficheiro | Lê ou escreve | Slice |
| :--- | :--- | :--- |
| `backend/app/scheduler/domain/availability_priority.py` (novo) | capacidade, procura, ritmo, chave de prioridade, regra do Evitar | S1 |
| `backend/app/scheduler/infrastructure/constructive.py` | `construct_schedule`: função `priority`, filtro de opções, repetição relaxada | S2 |
| `backend/app/scheduler/infrastructure/recovery_construction.py` | `construct_recovery`: ordem das opções, filtro, repetição relaxada | S3 |
| `backend/app/scheduler/infrastructure/search.py` | só chama `construct_schedule` (geração e `RECOVERY_REBUILD` da atualização) e `construct_recovery`; não muda. A D10 vale também pela reconstrução. | S2, S3 |
| `backend/app/scheduler/lab/recovery.py`, `lab/typology.py` `build_joint_typology_fixture`, `backend/tests/_support/scheduler_v1.py` `seed_published_baseline` | chamam `construct_schedule`; não mudam. O `seed_published_baseline` serve os testes de integração da atualização. | S2 |
| `backend/app/scheduler/lab/typology.py` | `build_availability_typology_fixture` (novo) | S4 |
| `backend/app/scheduler/domain/capacity.py` | `CapacityCheck.teacher_deficits`, `aggregate_capacity_check` | S5 |
| `backend/app/scheduler/domain/diagnostics.py` | `DiagnosisCode.INSUFFICIENT_TEACHER_TIME`, `diagnose_capacity` | S5 |
| `backend/app/scheduler/application/generation.py` | detalhe da mensagem de falta em `generate_complete` | S5 |
| `backend/app/scheduler/application/recovery.py` | só chama `aggregate_capacity_check` e `diagnose_capacity`; não muda | — |
| `backend/app/scheduler/application/publishing.py` | já serializa `affected_teacher_ids` e `minimum_missing_minutes`; não muda | — |
| `backend/app/scheduler/infrastructure/jobs.py` | já guarda `diagnostics_json` em `INFEASIBLE`; não muda | — |
| `backend/app/scheduler/infrastructure/queries.py` | `_job_diagnostics`: uma linha por professor de `INSUFFICIENT_TEACHER_TIME` | S6 |
| `frontend/src/components/schedules/GenerationStatusPanel.jsx` | lista "Professores sem tempo suficiente" | S6 |
| [Scheduler Engine](README.md) | ordem da construção, Evitar, prova por professor | S2, S5 |
| [Scheduler V1 Tech Spec](SCHEDULER_V1_TECH_SPEC_V2.md) | decisões D32 e D33, texto da construção e das preferências | S2, S5 |
| [School Configuration](../02_domain_model/SCHOOL_CONFIGURATION.md) | o que o Evitar e o Preferencial fazem na geração | S2 |
| [Feedback Message Matrix](../06_frontend_ux/FEEDBACK_MESSAGE_MATRIX.md) | mensagem nova do painel | S6 |

Os testes que leem a construção e que têm de continuar verdes estão no [WBS](AVAILABILITY_PRIORITY_WBS.md#testes-existentes-que-guardam-o-comportamento).

## Data or Request Flow

### Módulo de prioridade

O módulo T01 expõe uma classe com estado, `AvailabilityLedger`. Cada passagem de construção cria a sua.

| Operação | Entrada | Resultado |
| :--- | :--- | :--- |
| `AvailabilityLedger.build` | snapshot; períodos elegíveis por atribuição; minutos que faltam por atribuição | o livro com `C(0)`, capacidade neutra e `D(0)` por professor e por turma (T02–T04) |
| `priority(assignment, period)` | uma opção | a chave inteira da T06; a menor ganha |
| `unfavorable(assignment, period)` | uma opção | `True` quando o período cai num Evitar do professor ou de uma turma da aula |
| `allows(assignment, period)` | uma opção | `False` quando a T08 recusa a opção |
| `refused` | — | número de opções recusadas pela T08 nesta passagem (T09) |
| `place(assignment, minutes)` | uma aula colocada | desce `D` do professor e de cada turma da aula |

Os recursos são chaves `("teacher", teacher.id)` e `("class", class.id)`.

### Construção

1. A construção calcula os períodos elegíveis de cada atribuição, como hoje.
2. O módulo T01 recebe esses períodos, os minutos que faltam e o snapshot. Calcula por professor e por turma `C(0)`, a capacidade neutra e `D(0)`.
3. Em cada período, as opções passam o filtro T08 e ordenam-se pela T07.
4. Cada aula colocada desce `D` do professor e de cada turma da aula.
5. Se a passagem estrita falha, a função repete pela T09.

### Prova de falta de horas

1. `generate_complete` e a reparação chamam `aggregate_capacity_check` antes da pesquisa, como hoje.
2. Uma falta de professor torna o resultado `INFEASIBLE` com `INSUFFICIENT_TEACHER_TIME`.
3. O job guarda o diagnóstico. `GET /api/v1/scheduler/jobs/{job_id}` devolve uma linha com `teacher_id`, `teacher_name` e `minimum_missing_minutes`.
4. O painel mostra a lista, com o nome ligado a `/members?teacher_id={teacher_id}&panel=availability`.

`SchedulerV1JobDiagnosticRead` já tem `teacher_id` e `teacher_name`. O contrato HTTP não muda.

## Contracts and Invariants

### Identificadores

| Campo | Aponta para |
| :--- | :--- |
| `Assignment.teacher_id`, chave de professor no módulo T01, `CapacityCheck.teacher_deficits` | `teacher.id` |
| `Assignment.class_ids`, chave de turma no módulo T01 | `class.id` |
| `Diagnosis.affected_teacher_ids` e âmbito `TEACHER:{id}` | `teacher.id` |
| `teacher_id` na linha do job e na ligação do painel | `teacher.id`, nunca `organization_membership.id` |

### Invariantes

- I01: as regras obrigatórias não mudam. Todo o candidato devolvido passa em `validate_candidate`.
- I02: sem diferenças de disponibilidade, sem blocos Evitar e sem aulas protegidas, a construção produz as mesmas aulas que hoje (T06).
- I03: a ordem e o filtro dependem só do snapshot e dos períodos. Duas execuções iguais dão o mesmo horário.
- I04: o Evitar nunca torna impossível um horário que hoje a construção encontra: a repetição T09 trata o Evitar como hoje.
- I05: a reparação mantém as aulas protegidas, as aulas dadas e as posições publicadas que conserva.
- I06: `teacher_deficits` é um limite inferior provado. Ignora almoço, presença e salas ocupadas, por isso nunca bloqueia um caso possível.
- I07: a leitura do nome do professor filtra por `organization_id`.

## Failure Modes

| Situação | Resposta | Texto visível |
| :--- | :--- | :--- |
| Professor sem horas suficientes | job `INFEASIBLE` com `INSUFFICIENT_TEACHER_TIME` antes da pesquisa | "Professores sem tempo suficiente:" e, por professor, "{nome}: faltam pelo menos {duração}." Depois: "Reveja a disponibilidade destes professores, das suas turmas ou as atribuições." |
| Professor apagado ou de outra organização | a linha sai sem `teacher_name` e o painel não a mostra | a mensagem genérica de `INFEASIBLE` |
| Professor e turma sem horas | as duas listas aparecem, primeiro as turmas | as duas listas |
| Sala sem compatibilidade, aula protegida em conflito ou aula conjunta sem horas comuns | a mensagem atual tem precedência | a mensagem atual |
| Construção estrita sem saída | repetição relaxada (T09) | nenhum |
| As duas passagens falham | caminho exato, como hoje | o painel atual da pesquisa |
| Cancelamento ou fim de prazo na construção | `None` sem repetição, como hoje | o painel atual |

A duração usa `formatDurationMinutes`, como a lista das turmas.

## Cenários de risco

Cada cenário é um teste que falha primeiro, salvo indicação. Salvo indicação, a grelha é a dos Exemplos e uma semana tem 40 períodos.

| ID | Perigo | Cenário (teste que falha primeiro) | Resultado exato esperado | Ficheiro de teste |
| :--- | :--- | :--- | :--- | :--- |
| R01 | Prioridade | 4 turmas, 12 semanas de prazo. R1 e R2 só 9h–11h, 5 h por semana em 2 turmas cada. R3 só 9h–12h, 3,5 h em 4 turmas. M1 e M2 só 9h–13h, 6 h em 2 turmas. F1 a F4 dia inteiro, 21,5 h numa turma. | Hoje `construct_schedule` devolve `None`. Depois devolve um candidato válido e a última aula fica na semana 12. | `backend/tests/unit/test_scheduler_availability_priority_v1.py` (novo) |
| R02 | Ritmo | R01 com o professor L (9h–11h) a dar 2 h por semana à turma 1, e F1 com 19,5 h. | Candidato válido até à semana 12. A última aula de L fica na semana 10 ou depois. Sem ritmo ficava na semana 5. | `test_scheduler_availability_priority_v1.py` |
| R03 | Turma | 1 semana. Um professor dá 20 h à turma 1 (dia inteiro) e 20 h à turma 2 (Impossível das 13h às 18h). A atribuição da turma 1 tem o identificador menor. | Hoje `None`. Depois candidato válido com 40 aulas, e as 20 aulas da turma 2 de manhã. | `test_scheduler_availability_priority_v1.py` |
| R04 | Ritmo (domínio) | `D(0)=600`, `C(0)=1200`; em `t`, `C(t)=600`, `D(t)=300` e depois `D(t)=290`. | Em dia com 300; adiantado com 290. | `test_scheduler_availability_priority_v1.py` |
| R18 | Capacidade (domínio) | Um professor com 2 atribuições nos mesmos 5 períodos de 60 minutos. Evitar do professor em 2 desses períodos e Evitar de uma turma noutro. | `C(0)=300` para o professor (não 600) e capacidade neutra 180. | `test_scheduler_availability_priority_v1.py` |
| R19 | Aula conjunta (domínio) | Uma atribuição conjunta de 2 turmas com 120 minutos em falta. | `D(0)=120` para o professor e 120 para cada turma. | `test_scheduler_availability_priority_v1.py` |
| R20 | Chave (domínio) | Professor em dia com `C(0)=600` e turma adiantada com `C(0)=300`; o maior `C(0)` do snapshot é 2400. Depois os dois adiantados. | Chave 600; depois 2400. | `test_scheduler_availability_priority_v1.py` |
| R21 | Regra do Evitar (domínio) | Opção num Evitar do professor com `D(t)=240` e capacidade neutra 240; depois `D(t)=300`. | `allows` dá `False` e `refused == 1`; depois `True`. | `test_scheduler_availability_priority_v1.py` |
| R05 | Evitar necessário | 1 turma, 1 professor, 1 semana, 34 h. Evitar das 16h às 18h todos os dias. | Hoje 8 aulas em Evitar. Depois candidato válido com 34 aulas e exatamente 4 em Evitar. | `test_scheduler_availability_priority_v1.py` |
| R06 | Preferencial | 1 turma, 1 professor, 1 semana, 8 h. Evitar em todos os blocos fora das 9h–11h, como `_preference_unavailability` produz. | Hoje 6 aulas fora. Depois as 8 aulas nas 9h–11h. | `test_scheduler_availability_priority_v1.py` |
| R07 | Repetição relaxada | 1 turma, 1 semana. T1 com Evitar segunda e terça, e Impossível de quarta a sexta exceto às 9h. T2 só às 9h de quarta a sexta. 3 h cada. | Candidato válido: as 3 aulas de T1 na segunda e as de T2 de quarta a sexta. Passa em `main`, falha no S2 depois da T08 e volta a passar com a T09. | `test_scheduler_availability_priority_v1.py` |
| R08 | Prova por professor | 1 semana. Um professor só às 9h, 3 h a cada uma de 2 turmas. | `teacher_deficits == {id: 60}`, sem faltas por atribuição nem por turma. `generate_schedule` dá `INFEASIBLE` com um único `INSUFFICIENT_TEACHER_TIME`, âmbito `TEACHER:{id}`, `affected_class_ids == ()` e `minimum_missing_minutes == 60`. | `backend/tests/unit/test_scheduler_teacher_capacity_v1.py` (novo) |
| R09 | Aula conjunta | Uma aula conjunta de 2 turmas com 300 minutos e um professor com 300 minutos possíveis. | `teacher_deficits == {}`. | `test_scheduler_teacher_capacity_v1.py` |
| R10 | Diagnóstico repetido | Um professor com uma só atribuição sem horas suficientes. | `teacher_deficits == {}`. O teste existente `test_a_proven_capacity_deficit_carries_a_minimum_only_when_demonstrated` continua com exatamente 2 diagnósticos. | `test_scheduler_teacher_capacity_v1.py`; `backend/tests/unit/test_scheduler_w07_diagnostics_v1.py` |
| R11 | Reparação | R03 com estratégia `ADAPTIVE_RECOVERY` e sem aulas publicadas, em `construct_recovery`. | Hoje `None`. Depois candidato válido com 40 aulas. | `backend/tests/unit/test_scheduler_recovery_construction_v1.py` |
| R12 | Reparação com Evitar | R07 em `construct_recovery`. | Candidato válido com as aulas de T1 na segunda. | `test_scheduler_recovery_construction_v1.py` |
| R13 | Cenário da escola | `build_availability_typology_fixture(12)` no perfil `fast`; `build_availability_typology_fixture(48)` marcado `slow_solver`. | Hoje `None` nos dois tamanhos. Depois candidato válido de `construct_schedule` com a última aula até `PREFERRED_END`. Com 48 turmas o teste imprime o tempo da construção. | `backend/tests/unit/test_scheduler_typology_v1.py` |
| R14 | Sem mudança | `build_typology_fixture(12)`: disponibilidade igual e sem Evitar. | O digest das aulas ordenadas (atribuição, início em UTC, sala) é igual ao de `main` em `01a011e9`. A fixture usa a sua grelha de 5 aulas por dia. O teste passa antes e depois da mudança. | `test_scheduler_typology_v1.py` |
| R15 | Linha do job | Um job `INFEASIBLE` com `INSUFFICIENT_TEACHER_TIME` de um professor da organização e outro de outra organização. | Uma linha com `teacher_id`, `teacher_name` e `minimum_missing_minutes == 60`; a de outra organização sai com `teacher_name = None`. Nenhuma linha de turma. | `backend/tests/integration/committed/test_scheduler_v1_lifecycle.py` |
| R16 | Painel | Job `INFEASIBLE` com a linha de R15, outra sem nome e outra com 0 minutos. | O texto "Professores sem tempo suficiente:", o nome ligado a `/members?teacher_id=7&panel=availability` e "faltam pelo menos 1 h". As outras duas linhas não aparecem. | `frontend/src/test/GenerationStatusPanel.test.jsx` |
| R17 | Precedência | Job com `NO_ELIGIBLE_ROOM` e uma linha de professor. | Só a mensagem das salas. | `GenerationStatusPanel.test.jsx` |

## Coexistência

- Base: `main` em `01a011e9`. Última revisão Alembic: `0005_teacher_presence`. Este spec não cria migração.
- Os pull requests abertos #129, #130, #142 e #143 só têm documentação, noutras pastas.
- O item 6 (sala da turma) está em curso localmente no branch `feat/school-room-types`. As slices seguintes do item 6 vão mudar a escolha de sala em `constructive.py` e `recovery_construction.py`. Este spec muda só a ordem e o filtro das opções. Quem entrar depois faz rebase.
- Os pull requests do Dependabot (#138 a #140) não tocam nestes ficheiros.
- Ordem de merge: PR 1 e PR 2 podem entrar em qualquer ordem. Quem entrar depois resolve os dois guias do motor.

## Verification Procedure

Cada slice tem a sua prova no [WBS](AVAILABILITY_PRIORITY_WBS.md). Use os perfis de [Verification by change type](../00_getting_started/COMMAND_REFERENCE.md#verification-by-change-type).

- PR 1: perfil do solver, incluindo o teste `slow_solver` das 48 turmas no CI.
- PR 2: perfil do solver, perfil de jobs do motor (o `test_scheduler_v1_lifecycle.py` só corre localmente), perfil de componente frontend e a stack local reconstruída na worktree.

O PR 1 regista no pull request o tempo de construção das 48 turmas, antes e depois.
Verificação manual depois do PR 2: dar a um professor só 1 hora possível por semana e 2 horas de aulas; carregar em Gerar; confirmar a lista e a ligação no painel.

## Source Map

- Domínio: `backend/app/scheduler/domain/availability_priority.py`, `capacity.py`, `diagnostics.py`.
- Construção: `backend/app/scheduler/infrastructure/constructive.py`, `recovery_construction.py`.
- Leitura do job: `backend/app/scheduler/infrastructure/queries.py`.
- Interface: `frontend/src/components/schedules/GenerationStatusPanel.jsx`.
- Fixture: `backend/app/scheduler/lab/typology.py`.

## Related Documents

- [WBS — Prioridade a quem tem pouca disponibilidade](AVAILABILITY_PRIORITY_WBS.md)
- [Scheduler Engine](README.md)
- [Scheduler V1 Tech Spec](SCHEDULER_V1_TECH_SPEC_V2.md)
- [Tech Spec — Disponibilidade das Turmas](../02_domain_model/CLASS_AVAILABILITY_TECH_SPEC.md)
- [Tech Spec — Presença dos professores](../02_domain_model/TEACHER_PRESENCE_TECH_SPEC.md)
