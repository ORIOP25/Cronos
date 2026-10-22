# Tech Spec — Refatoração da construção do scheduler

## Purpose

Reduzir a complexidade da construção anual e da recuperação adaptativa sem alterar o horário produzido, as regras de negócio, os contratos públicos ou o comportamento do solver.
**Estado:** pronto para implementação. **Base:** `origin/main` em `5a4fd7d369062eefaf08446f6adb5fa1398e5af6`, Alembic `0008_schedule_priorities`. Este trabalho não cria migração.

## Intended Reader

Agentes que implementam a refatoração, revisores técnicos e o responsável de produto.
O responsável de produto decide apenas o que este documento não consegue provar contra o código.

## Prerequisites

Atualizar `origin/main` e rever PRs abertos antes do primeiro *slice*.
O diff do PR #186 foi lido: altera FastAPI, Pydantic Settings e *hashes* de dependências; não altera o *pin* de OR-Tools nem ficheiros do scheduler.
Essa leitura prova apenas o diff revisto, não o comportamento futuro de todo o PR.
O `origin/main` de referência é `5a4fd7d3`; o `main` local de outras *worktrees* está em `feee8deb` e não é a base.
A fonte Alembic é `0008_schedule_priorities`; o seu `down_revision` é `0007_class_home_room`.

## What the System Does

`_construct_pass` (`constructive.py`, 733–1260), `_select_period` (516–659) e `_construct_recovery` (`recovery_construction.py`, 117–550) misturam orquestração, estado mutável, presença, *ledger*, salas, prioridades, orçamento, cancelamento e candidato.
A refatoração separa responsabilidades sem mudar resultados.

### Decisões fechadas

| ID | Decisão |
| :--- | :--- |
| D01 | O comportamento observável não muda: candidato, ordem, crédito, salas, recusas, cancelamento e desempates. |
| D02 | Não se calibram prioridades, não se altera o modelo CP-SAT, os custos ou os limites de pesquisa. |
| D03 | Cálculos puros por opção entram em `domain/priority_value.py`, reutilizando `option_value` e `weekly_stability_measure`. |
| D04 | No máximo um módulo partilhado novo: `infrastructure/construction_support.py` `(novo)`, sem OR-Tools. |
| D05 | `_select_period` e `_flow_selection` ficam em `constructive.py`; modelo, coeficientes, *hints* e leitura do solver não saem. |
| D06 | Cada rota tem um detentor concreto privado: `_ConstructionPass` e `_RecoveryPass`; não há superclasse, protocolo, fábrica ou *callback* genérico. |
| D07 | As diferenças de presença, histórico, desempates, cancelamento, identidade e crédito ficam explícitas; não se unificam. |
| D08 | As assinaturas públicas de `construct_schedule`, `construct_recovery`, `_construct_pass`, `_construct_recovery` e `_select_period` não mudam. |
| D09 | `search.py`, `placement_model.py`, composição, aplicação, propostas e publicação são apenas lidos e verificados; a tabela de chamadas é obrigatória. |
| D10 | Não há alteração de base de dados, API, interface, migração, configuração, dependências ou versões de validador. |
| D11 | O sucesso exige igualdade exata do candidato tipado; o modelo exige igualdade byte a byte na campanha e os quatro *digests* são guarda unitária, não prova única. |
| D12 | O *oracle* rápido é autónomo num *checkout* limpo; as referências lentas, incluindo o modelo, ficam em artefactos fora do Git com `hash` e proveniência. |
| D13 | A campanha usa os 23 perfis C01–C23 definidos neste documento; não se afirma recuperar o script histórico em falta. |
| D14 | Os seis SHA16 históricos são contexto; não são prova sem o script e a escala antigos. |
| D15 | Nenhum comportamento latente é corrigido; uma correção futura exige spec e testes próprios. |
| D16 | A entrega são três PRs seriais e dez *slices*; os três ficheiros quentes têm uma única lane de escrita. |
| D17 | A métrica é complexidade cognitiva SonarCloud Python S3776, máxima 15, nas três funções alvo e em todas as novas/extraídas. Ruff C901 mede complexidade ciclomática e não substitui S3776. |
| D18 | Não se move um bloco de centenas de linhas para `__init__`, `run` ou `score` para baixar uma métrica. |
| D19 | Se a caracterização falhar, a extração pára; nunca se regenera a referência a partir do código alterado. |
| D20 | A campanha completa é evidência manual obrigatória no PR final; `.github/workflows/ci.yml` não é alterado e o CI não prova sozinho a equivalência. |

### Âmbito

- Extrair cálculos puros e heurísticas existentes.
- Criar detentores de estado privados por rota.
- Reduzir as três funções a coordenadores de fases.
- Preservar os percursos estrito, relaxado e preenchimento da geração, e retenção/reconstrução da recuperação.
- Provar igualdade antes/depois nos seis casos nomeados, nos 23 perfis e em dois cenários de atualização.

### Fora de âmbito

- Alterar horário preferido, qualidade, prioridades, pesos ou calibração.
- Alterar solver, OR-Tools, modelo de colocação ou `digest` do modelo.
- Alterar `candidate_validation.py`, versões de regras, diagnóstico ou API.
- Alterar fila, *worker*, aplicação, publicação ou interface.
- Alterar `finish_early`; `finish_early0` não volta.
- Alterar ordem de módulos, precedências, conjuntos ou reservas de dívida.
- Adicionar *frameworks*, dependências, configuração ou interruptores.
- Manter uma segunda implementação antiga depois da prova.

## Why the Behavior Exists

O horário tem regras duras de recursos, presença, almoço, progresso, disponibilidade e estabilidade.
A construção tenta satisfazê-las; a recuperação preserva posições publicadas e corrige apenas o futuro editável.
Uma regressão silenciosa pode produzir um horário válido mas diferente, alterar estabilidade ou esconder recusas.
A refatoração é conservadora e prova igualdade física, de identidade e de modelo.

## Components and Ownership

| Componente | Responsabilidade alvo | Escrita |
| :--- | :--- | :--- |
| `domain/priority_value.py` | Medidas puras, valor de sala e admissão ponderada | Sim |
| `infrastructure/construction_support.py` `(novo)` | Heurísticas sem OR-Tools; verificações exatas de recursos/precedências | Sim |
| `infrastructure/constructive.py` | `_ConstructionPass`, `_select_period`, fases e candidato | Sim |
| `infrastructure/recovery_construction.py` | `_RecoveryPass`, retenção, reversão, presença e crédito | Sim |
| `placement_model.py` / `candidate_validation.py` | `_build_candidate` e validador independente | Leitura |
| `search.py`, composição, aplicação, propostas, publicação | Chamadas e efeitos a jusante | Leitura |

### Propriedade de estado

| Estado | `_ConstructionPass` | `_RecoveryPass` |
| :--- | :--- | :--- |
| *Ledger* | Cria, coloca e lê recusas | Cria depois da retenção; coloca crédito |
| Ocupação comprometida | Sim: `busy`/`occupancy` de colocados e protegidos | Sim: `_Booking` |
| Ocupação pendente/planeada | Sim, *preview* não comitado | Não |
| Retenção e reversão | Não | Sim, em ordem inversa |
| Salas abertas | Por período | A partir da ocupação comprometida |
| Presença | *Preview* antes da seleção e execução do *run* | Retém o *run*; reverte se falhar |
| Histórico semanal | Padrão semanal; com pesos também dia letivo anterior | Protegido e *baseline* |
| Crédito e último fim | Atualiza ao colocar | Atualiza ao reter/desfazer |
| Normalização | Não | Por período crescente; só última editável parcial |
| Candidato | Protegido + lições novas | `_build_candidate(snapshot, selections)` |

### Extrações nomeadas

| Extração | Entrada | Saída / efeito |
| :--- | :--- | :--- |
| Medidas por opção e intervalo | `snapshot`, unidade, período, crédito, ocupação, referências, atraso | Mapa inteiro; nenhum efeito |
| Valor/admissão de sala | Medidas, sala, sala habitual, necessidade, preenchimento | Valor e salas; nenhum efeito |
| Presença diária | Ocupação, slots, regra, dia | Booleano; nenhum efeito |
| Slots/intervalos/chaves | `snapshot`, períodos | Índices puros; nenhum efeito |
| `_gives_up` e precedência | *Ledger*, período, unidades | Booleano; nenhum efeito |
| Seletor ganancioso/modelo/solver | Opções, salas, *scores*, limite | Seleção; o modelo é construído, sem mutar a passagem |
| `occupy`/`ready`/`place` | Estado da passagem | Estado mutado; dono `_ConstructionPass` |
| `retain`/`undo`/`book`/`normalize` | `_Booking`, seleções, residual | Estado mutado; dono `_RecoveryPass` |

## Data or Request Flow

Geração: `composition.generate_schedule` → `application.generation.generate_complete` → `search.search_complete_schedule` → `_joint_search` → `construct_schedule` → `_construct_pass` → `_select_period`.

Recuperação: `composition.repair_published_schedule` → `application.recovery.repair_schedule` → `search.search_adaptive_schedule` → `construct_recovery` (1002/1016) e `construct_schedule` com `weekly_reference=baseline` (1028/1047) → `_room_pass` → custo vetorial/ponderado → `_constructive_outcome`.

`search_adaptive_schedule(stop_at_first_complete=True)` é o ramo direto acima; `_joint_search` só corre no ramo `false` (1139).
`recovery_assessment` pertence a `application.generation.generate_complete` (295), depois da geração inicial; não está no fluxo de recuperação.
O candidato continua a passar por `validate_candidate` e pelas mesmas medidas de qualidade; a ordem não muda.

## Contracts and Invariants

### I01–I04 — Contratos, fases e modelo

- **I01** `construct_schedule`/`construct_recovery` conservam argumentos e retorno; `_construct_pass` conserva `(candidate, refused, paced_out)` e `_construct_recovery` conserva `(candidate, refused)`.
- **I02** A geração conserva estrito → relaxado → preenchimento. Estrito exige `weights` nulo ou preferência de professor/turma; relaxado exige recusa, `paced_out` ou janela diferente; preenchimento exige pesos. Na recuperação, relaxado exige recusa ou janela diferente.
- **I03** Igualdade exata de candidato, `lessons`, `slices`, identidade, período, sala, origem, substituições, crédito e minutos; o `digest` é adicional.
- **I04** O modelo conserva ordem de variáveis, nomes, *hints*, coeficientes, limites, objetivo e restrições. Os quatro *digests* existentes continuam a passar; S2 guarda a *baseline* `str(model.Proto())` e S3+ compara-a nas mesmas quatro opções.

### I05–I08 — Tempo, cancelamento e seletor

- **I05** O não ponderado conserva o limite de parede de 0,1 s; o ponderado conserva `PERIOD_REPAIR_DETERMINISTIC_TIME` e nunca usa tempo de parede como qualidade.
- **I06** A geração avalia `should_cancel` antes do `deadline`; a recuperação avalia o `deadline` primeiro. O número/ordem de chamadas por atribuição e período não muda.
- **I07** Opções `[(Assignment, tuple[room])]`; `_select_period` conserva ganancioso, fluxo, modelo e leitura. Sem `scores`, ganancioso devolve cedo e o fluxo segue; com `scores`, calcula seleção inicial/*hints*, não devolve cedo e não há fluxo.
- **I08** Com solução, a seleção segue a ordem de `choices`; sem FEASIBLE/OPTIMAL, volta à seleção gananciosa. `fill_admitted` só entra com `scores` e passagem não estrita.

### I09–I12 — Presença, histórico, salas e crédito

- **I09** A construção pré-visualiza presença sem comitar e filtra opções incompletas antes da seleção. A recuperação retém/reverte em ordem inversa, liberta dias quebrados e normaliza do período mais cedo para o mais tarde.
- **I10** Sem pesos, o padrão semanal legado é a referência. Com pesos, esse padrão conserva-se e o dia letivo anterior entra na medida T06. A recuperação semeia protegido/*baseline*, incluindo posições descartadas, e conserva `patterns.setdefault` antes da elegibilidade.
- **I11** A geração ordena salas por `(not preferred, pressure, id)`; a recuperação conserva a sua ordem. Não se trocam.
- **I12** A recuperação conserva `_Booking`, `refresh_last_end`, `_build_candidate` e identidade; a geração junta protegido e lições novas. Só a última lição **editável** de cada unidade fica parcial; histórico protegido parcial preserva-se.

### I13–I16 — Módulos, fronteiras, consumidores e artefactos

- **I13** Módulos, precedências, unidades conjuntas e reserva de dívida não mudam; não se limpam conjuntos/listas/dicionários nem se corrige ordem latente.
- **I14** `priority_value.py` não importa infraestrutura, OR-Tools, HTTP, ORM ou relógio. `construction_support.py` não importa OR-Tools nem conhece `_Booking`. `constructive.py` conserva CP-SAT/modelo.
- **I15** Não há superclasse, protocolo, fábrica, *callback* de presença ou configuração. Os detentores são concretos e privados; os coordenadores ficam pequenos.
- **I16** Nomes privados, `_select_period` e `cp_model` mantêm o *binding*. Importações mecânicas só no *slice* indicado. Cada artefacto regista *commit*, *snapshot*, pesos, períodos, semente, trabalhadores, perfil e tempo; cada repetição corre em processo separado.

## States and Transitions

A refatoração não altera estado de produto, persistência, API ou estados públicos.
As fases continuam iguais; os coordenadores apenas as ordenam.
Geração: estrito, relaxado e preenchimento, com os contratos de I02.
Recuperação: retenção, reversão, normalização e preenchimento; o `deadline` precede o cancelamento.
Não há estado novo, transição nova ou escrita fora de `_ConstructionPass`/`_RecoveryPass`.

## Failure Modes

| ID | Falha / entrada pequena | Teste e resultado exato |
| :--- | :--- | :--- |
| R01 | Ordem de lições/slices muda | Caracterização ordenada; igualdade posição a posição; guarda `test_projector_detects_slice_order_only_difference`. |
| R02 | Modelo muda | `test_period_repair_models_keep_their_variables_hints_and_objective`; quatro *digests* iguais; S2 guarda a *baseline* `str(model.Proto())` e S3+ compara byte a byte; o teste atual não prova essa igualdade. |
| R03 | Ponderado passa pelo ganancioso | `test_period_selection_uses_value_when_no_option_is_necessary`; seleção e coeficientes iguais; *hints* conservadas. |
| R04 | Cancelamento muda | `test_r07_the_strict_pass_gives_up_once_class_1_has_more_hours_than_periods_left` continua a provar 17 chamadas de desistência, não a ordem de interrupção; o teste planeado `test_construction_and_recovery_keep_interruption_short_circuit_order` fixa a ordem de `monotonic`/`should_cancel`. |
| R05 | Limite de tempo muda | `test_period_repair_is_bounded_by_deterministic_time_so_the_schedule_repeats` regista `(inf, PERIOD_REPAIR_DETERMINISTIC_TIME)`; não ponderado `(0.1, inf)`. |
| R06 | *Preview* comita ou não filtra | `test_a_presence_lesson_that_cannot_complete_does_not_block_its_class_mates`; segunda 09h = atribuição 2, candidato válido, atribuição 1 em terça 09h e 3 em terça 10h. |
| R07 | Retenção/reversão perde lição | `test_rr1_a_retained_short_presence_is_rebuilt_into_full_presences`, `test_rr3_a_published_compliant_presence_is_kept`, `test_rr4_a_retained_presence_is_never_stranded_below_the_minimum`; posições/crédito iguais. |
| R08 | Semente semanal muda | `test_weekly_stability_measure_of_one_class_follows_its_previous_teaching_day` e `test_weekly_history_compares_with_the_previous_teaching_day_not_an_older_lesson`; referências iguais. |
| R09 | Desempate de sala muda | `test_uniform_class_rooms_fill_a_teacher_matching_without_sat_search` e `test_different_subject_rooms_use_flow_when_selected_subjects_fit`; salas/ordem iguais. |
| R10 | Precedência/módulo muda | `test_a_successor_unit_never_starts_before_its_predecessor_ends`; candidato válido e igual. |
| R11 | Crédito muda | Plano com módulos 75+75, executado M1=50, lições futuras 60+40: lição 1 `[(M1,50,25),(M2,0,35)]`, lição 2 `[(M2,35,40)]`; futuro 100 + executado 50 = 150. Offsets são locais ao módulo; teste planeado `test_construction_and_recovery_keep_cross_module_slice_offsets` no ficheiro de recuperação existente, dono S6, sem teste existente para esta sequência. |
| R12 | Aplicação recebe outro resultado | `test_scheduler_generation_v1.py` e `test_scheduler_recovery_v1.py`; estado, relatório e qualidade iguais. |
| R13 | Import privado quebra | Testes diretos acima; `binding` e assinatura iguais. |
| R14 | Permutação de entrada altera saída | `test_construction_is_independent_of_input_assignment_and_period_order`; candidato igual, sem alargar a garantia. |
| R15 | Complexidade cognitiva >15 | Relatório SonarCloud S3776 do PR, funções alvo e novas/extraídas, máximo 15; Ruff C901 não conta. |
| R16 | Atualização escolhe outro horário | Cenários A/B; 10 pares base/cabeça e métricas semânticas iguais. |

### Boundary conditions

O plano aplica-se a *snapshots* preparados que já passam a validação; entradas vazias, zero demanda e limites de data mantêm o comportamento existente.
Histórico e créditos dos cenários vêm do *baseline* capturado, não de valores inventados.
Tenant/RLS, leitores do scheduler e migrações não mudam; não se inventam testes de BD. A migração é N/A.
Complexidade e camadas são revistas no código e no SonarCloud; neste documento não há medição numérica.

## Safety Net

### Fast oracle (autónomo)

`test_scheduler_construction_characterization_v1.py` `(novo)` contém constantes compactas congeladas de uma projeção tipada e ordenada.
O ficheiro crítico não lê `.test-artifacts` nem o sistema de ficheiros; funciona num *checkout* limpo.
`candidate_digest` usa a projeção completa, retém data/início/fim/fuso, preserva a ordem de entrada das lições e ordena apenas *slices*; `lesson_to_dict` também ordena apenas *slices*.
O primeiro teste planeado é `test_construction_candidate_matches_base_fixture`.
Define localmente um `FixtureSpec` com os valores de `BASE_SPEC`: origem 2026-09-21, preferida 2026-10-30, limite 2026-11-30, `Europe/Lisbon`, grelha segunda/quarta 09–10, períodos 21 e 23 de setembro, `AssignmentSpec(1, 100, (100,), (500, 501))`; os campos opcionais ficam vazios.
Usa `build_snapshot(spec)` e `normalize_period`; não usa `build_fixture` nem o *oracle*; não importa `BASE_SPEC` do teste laboratorial.
Executa `construct_schedule(snapshot, periods, weights=None, deadline=None)` e repete com `PriorityWeights(DEFAULT_LEVELS)`.
A constante congelada exige duas lições ordenadas: IDs `1000001`/`1000002` por `allocate_lesson_identity`, atribuição 1, sala 500 sem pesos e sala 501 com `PriorityWeights(DEFAULT_LEVELS)`, 21 e 23 de setembro, créditos 60/40, *slices* `(1,0,60)`/`(1,60,40)`, `source_lesson_id`, `teacher_id` e `class_ids` nulos.
Esta distinção foi confirmada no código base `5a4fd7d3`, com OR-Tools `9.15.6755`, e autorizada pelo responsável. As salas empatam em pontuação e coeficientes; o *hint* para 500 não obriga o solver, que escolhe 501 com estado `OPTIMAL`. Preserva-se esse comportamento.
Valida o resultado no *commit* base antes de produção; uma diferença pára e exige inspeção, sem regenerar a constante a partir da saída atual.
O teste existente só fixa créditos `[60,40]`; não se afirma que já correu este *oracle* completo.
`test_projector_detects_slice_order_only_difference` usa uma lição sintética de 50 créditos com dois `ModuleSlice` de módulos diferentes; não precisa de *solver*.
`test_construction_and_recovery_keep_interruption_short_circuit_order` fecha a ordem: falsos/futuro geração `['cancel','clock']`, recuperação `['clock','cancel']`; cancelamento `['cancel']`/`['clock','cancel']`; `deadline` expirado `['cancel','clock']`/`['clock']`.
O teste faz *monkeypatch* aos `monotonic` locais, usa uma lista de eventos e fixa a primeira passagem bem-sucedida; os `_interrupted` privados de cada módulo são *bindings* locais testáveis. O teste R07 continua separado com 17 verificações.
O `digest` de entrada tem de coincidir; cabeçalhos de evidência podem variar. Versão, semente, trabalhadores e *defaults* ficam explícitos.

### Slow references and staging

`backend/tests/unit/test_scheduler_construction_campaign_v1.py` `(novo)` é `slow_solver` e não entra no manifesto crítico.
`backend/tests/_support/construction_snapshot.py` `(novo)` gera artefactos lentos com `hash`, *commit* de código e *commit* do *harness*.
O *harness* é aplicado ao *commit* base como *overlay* só de testes ou *commit* separado; o código de produção referenciado é o do *commit* base, nunca o código alterado.
Uma referência lenta pode ser lida do artefacto; a comparação rápida não depende dele.
Os quatro *digests* de modelo continuam guarda unitária; não provam igualdade de `Proto()`.
S2 captura a *baseline* `str(model.Proto())` nas mesmas quatro opções de `test_period_repair_models_keep_their_variables_hints_and_objective`, guarda a ordem e a versão OR-Tools; S3 e cada PR comparam as *strings* byte a byte.
S1 usa só os quatro *digests* e o *oracle* rápido; S3 e cada PR de implementação correm a comparação byte a byte desse artefacto, além dos quatro *digests*; o *fast* diário não o lê.

### Characterization and history

A projeção guarda *commit*, `snapshot`, pesos, períodos, candidato ordenado, lições com período/sala/origem/substituições/crédito e *slices* ordenadas.
A comparação em processo usa igualdade de objetos; entre *commits*, o artefacto ordenado e o `digest`.
O registo histórico menciona seis SHA16: `teacher_gaps4`, `weekly_stability4`, `class_gaps0+class_same_room4`, recomendado 70%, `subject_pace0` e base.
O script e a escala antigos não existem; a matriz atual é uma substituição técnica, não certificação histórica.
A mutação inverte um desempate, uma ordem de *slice*, uma sala e um valor; fica vermelha e volta a verde quando restaurada.

### Matriz C01–C23

Todos os perfis usam o *snapshot*/períodos de `build_realistic_pilot()`; todos os pesos não indicados partem de `DEFAULT_LEVELS` (`domain/priorities.py`).
`finish_early` permanece sempre 4; C20 também o fixa em 4.

| ID | Perfil | Caso nomeado |
| :--- | :--- | :--- |
| C01 | `DEFAULT_LEVELS` recomendado | base |
| C02 | `teacher_gaps=0` | |
| C03 | `teacher_gaps=4` | `teacher_gaps4` |
| C04 | `class_gaps=0` | |
| C05 | `class_gaps=4` | |
| C06 | `teacher_single_lessons=0` | |
| C07 | `teacher_single_lessons=4` | |
| C08 | `class_single_lessons=0` | |
| C09 | `class_single_lessons=4` | |
| C10 | `teacher_preferences=0` | |
| C11 | `teacher_preferences=4` | |
| C12 | `class_preferences=0` | |
| C13 | `class_preferences=4` | |
| C14 | `class_same_room=0` | |
| C15 | `class_same_room=4` | |
| C16 | `weekly_stability=0` | |
| C17 | `weekly_stability=4` | `weekly_stability4` |
| C18 | `subject_pace=0` | `subject_pace0` |
| C19 | `subject_pace=4` | |
| C20 | Todos os `SCHOOL_CRITERION_KEYS=2`, `finish_early=4` | |
| C21 | `class_gaps=0,class_same_room=4` | composto histórico |
| C22 | `teacher_gaps=0,class_gaps=4` | |
| C23 | `DEFAULT_LEVELS` com módulos a 70% | `70% hours` |

A ordem C02–C19 é a de `SCHOOL_CRITERION_KEYS` em `domain/priorities.py`; não se copiam os 11 mapas.
C23 aplica `max(1, (minutos * 70) // 100)` a cada requisito, preservando minutos positivos e a identidade da unidade partilhada, sem vírgula flutuante.

### Update scenarios A and B

Fixture fixa: `SCHOOL_YEAR_START=2026-09-14`, `HARD_END=2027-07-30`, referência 2027-02-22; as 5 primeiras datas de `grid_dates` vão até 2027-02-26.
A baseline C01 é gerada uma vez; o cenário sintético não representa execução real nem usa um *loader* de BD.
`now_utc=2027-02-22T00:00:00+00:00`; `end_utc <= now_utc` forma histórico concluído, agregado por módulo e unidade, uma vez por unidade conjunta, nunca por turma.
O histórico é mantido no artefacto de comparação e não entra no crédito de pesquisa.
As *slices* executadas têm de ser o prefixo exato; não se reprojetam módulos porque o catálogo não muda.
A baseline ativa contém apenas lições com `start_utc > now_utc`; uma lição que atravessa o instante falha o fixture.
As protegidas são as lições ativas em datas protegidas; as lições passadas consumidas não ficam planeadas nem protegidas, para não haver crédito duplo.
O *snapshot* ativo conserva origem/calendário/grelha e define `ADAPTIVE_RECOVERY`, `now_utc`, executado, `baseline_lessons=active`, protegidas e pesos; `reserved_lesson_ids` contém todos os IDs originais C01.
`reservations`, dívida e *claims* ficam vazios; `prior_changes` fica vazio; a política é `laboratory_policy(active_snapshot)`.
A pesquisa recebe `CandidateSchedule(active_lessons)` apenas, igual na base e na cabeça; o candidato C01 completo fica no artefacto de proveniência.
Cada unidade mantém `required = executed + protected + residual`; `validate_candidate` passa antes de acrescentar indisponibilidade e falha só nas lições editáveis afetadas depois, sem conflito protegido.
A: indisponível de 2027-03-01 a 2027-03-12. B: quartas desde 2027-03-03 até `HARD_END`; escolhe-se e regista-se o primeiro `teacher_id` ordenado sem mínimo, afetado e sem conflito protegido, ou falha.
Cada cenário corre níveis 0–4: **10 pares base/cabeça** no total. Há 4 pares locais/reconstruídos (8 chamadas de topo, 2 eventos × base/cabeça); os custos nos 5 níveis reutilizam esses pares após provar que as medidas puras não leem `update_stability`; 10 comparações/vencedores pequenos cobrem os níveis. Não se afirma que os 10 níveis correram pesquisa real.
Comparam-se ambos os candidatos, seleção, qualidade, custo, disrupção, estado, `objective_scope` e `priorities_followed`, ignorando tempos; local/reconstrução são diagnósticos extra.
`test_construction_updates_do_not_double_count_completed_or_protected_credit` usa 180 = executado 60 + protegido 60 + residual 60, com três períodos de 60; é guarda rápido no ficheiro de caracterização (S2), que entra inteiro no crítico, e o teste lento seguinte fica na campanha.
`test_construction_updates_match_frozen_base` é `slow_solver`, parametrizado A/B e 0–4, selecionado por `construction_updates`; S2 captura o fixture de atualização sem alterar produção.
O limite realista é `time_limit_seconds=3600`; o caso pequeno usa relógio controlado; um `deadline` quase zero testa cancelamento sem prometer candidato.
O histórico é idêntico nos dois *snapshots*; a consistência conjunta R10 não muda.

### Campaign and CI

A base B0 é capturada no *commit* base, em três lotes de 8/8/7 perfis, antes de S3.
A campanha completa de 23 perfis pareados demora cerca de 4 h; com base/cabeça em cache, cerca de 2 h mais referências.
Cada execução realista demora cerca de 340 s; lotes param aos 80 min e retomam do perfil pendente, sem saltar.
O PR final corre 23/23 e 10/10 pares, zero *skips*, `None`, `timedout` ou omissões.

O manifesto crítico seleciona o ficheiro rápido inteiro, sem filtro `-m`; por isso o ficheiro lento é separado.
`e2e-runtime` continua a correr três testes de tipologia e a recuperação da *worker*; os quatro jobs obrigatórios (`backend`, `frontend`, `e2e-runtime`, `e2e-browser`) mantêm-se verdes.
A decisão de CI é fechada: **evidência manual obrigatória anexada ao PR**, sem alterações a `.github/workflows/ci.yml`.
O revisor confirma o manifesto de evidência com 23 IDs e 10 pares, sem omissões nem *skips*.
Não se afirma que o CI impõe a campanha; CI futuro é explicitamente fora de âmbito e não há novo E2E de browser.
Cada PR corre o *fast* focado e os testes de integração de fronteira; o PR1 (seletor partilhado), o PR2 e o PR3 correm também os casos nomeados/atualizações aplicáveis, fora do *timebox* de engenharia.
As horas são estimativa, não objetivo de desempenho.

## Coexistence

A base é `origin/main` `5a4fd7d3`; não se faz *fetch* neste trabalho.
A fonte Alembic é `0008_schedule_priorities`, cujo `down_revision` é `0007_class_home_room`; não há migração nova.
Os PRs #177, #129, #130, #142 e Dependabot #138, #139, #184, #185, #186, #187, #188 estão abertos a 22 de outubro de 2026.
O #186 mexe apenas em requisitos/lock: FastAPI/Pydantic Settings; não altera o *pin* `ortools==9.15.6755` nem ficheiros do scheduler.
As *branches* `chore/scheduler-cleanup`, `perf/construction-exact-speedups`, `fix/priorities-update-choice` e `fix/schedule-priorities-recovery-review` são históricas/pendentes, não bloqueios.
O código atual vence qualquer spec antiga; atualizar `origin/main` antes de implementar.

## Verification Procedure

Neste PR documental: verificar ligações relativas, `git diff --check`, `git diff`, `git status` e *trailing whitespace* nos ficheiros novos, que o `git diff --check` não cobre.
A verificação SonarCloud S3776 aplica-se apenas aos PRs de implementação futuros e exige o relatório para as três funções alvo e todas as novas/extraídas, com URL e pontuação por função; este PR documental não faz essa alegação.
O ficheiro `.sonarcloud.properties` define o âmbito de análise automática; a presença da análise é pré-requisito operacional a confirmar, não um facto verificado aqui.
Se o relatório não existir, a afirmação numérica de complexidade fica **não verificada** e bloqueia a prova; não se substitui por Ruff C901, AST aproximado ou configuração nova.
Na fase de implementação, a Command Reference passa a indicar como inspecionar esse relatório SonarCloud existente, sem *scanner*, plugin ou configuração nova.
Para os testes futuros, usar o *runner* existente documentado na Command Reference; caminhos são relativos a `backend/`. O perfil `critical` é o job CI, não prova de BD local em Windows.
A campanha lenta usa os argumentos `-m slow_solver` e o perfil de atualização documentados em S2; não se cria marcador, *runner* ou subcomando adicional.
Cada PR regista comando, perfil, filtro, código de saída e saída relevante; uma execução sem casos não é prova.

## Source Map

Caminhos relativos a `backend/`. “Dono” é o *slice* que pode alterar o ficheiro; os restantes são leitura/regressão.

| Fonte | Chamadas/importações | Dono | Estado |
| :--- | :--- | :--- | :--- |
| [`constructive.py`](../../backend/app/scheduler/infrastructure/constructive.py) | Escritor de `_construct_pass` e `_select_period` | S3–S5 | Escrita |
| [`recovery_construction.py`](../../backend/app/scheduler/infrastructure/recovery_construction.py) | Importa 20 nomes privados de `constructive` (29–50) | S6–S7 | Escrita |
| [`search.py`](../../backend/app/scheduler/infrastructure/search.py) | `_joint_search` 460/482; `search_adaptive_schedule` 1002/1016, 1028/1047, 1062, 1125, 1139 | — | Leitura |
| [`lab/recovery.py`](../../backend/app/scheduler/lab/recovery.py) | `construct_schedule` 229/234 | — | Leitura |
| [`lab/typology.py`](../../backend/app/scheduler/lab/typology.py) | `construct_schedule` 195/434 | — | Leitura |
| [`lab/priority_bench.py`](../../backend/app/scheduler/lab/priority_bench.py) | `search_complete_schedule` 241; `search_adaptive_schedule` 249 | — | Leitura |
| [`composition.py`](../../backend/app/scheduler/composition.py) | `generate_complete` / `repair_schedule`; search injetado | — | Leitura |
| [`endpoints/scheduler.py`](../../backend/app/api/v1/endpoints/scheduler.py) | `enqueue_generation` e `dispatcher.dispatch`; sem alteração | — | Leitura |
| [`scheduler_v1_worker.py`](../../backend/app/scheduler_v1_worker.py) | `_run_search` chama `composition.generate_schedule`/`repair_published_schedule` | — | Leitura |
| [`jobs.py`](../../backend/app/scheduler/infrastructure/jobs.py) / [`task_dispatcher.py`](../../backend/app/scheduler/infrastructure/task_dispatcher.py) | Fila e despacho; sem alteração | — | Leitura |
| [`generation.py`](../../backend/app/scheduler/application/generation.py) | Valida, qualidade e `recovery_assessment` 295 | — | Leitura |
| [`recovery.py`](../../backend/app/scheduler/application/recovery.py) | Avalia, orçamenta, chama `search` e valida | — | Leitura |
| [`placement_model.py`](../../backend/app/scheduler/infrastructure/placement_model.py) / [`candidate_validation.py`](../../backend/app/scheduler/domain/candidate_validation.py) | `_build_candidate` e validador independente | — | Leitura |
| [`publishing.py`](../../backend/app/scheduler/application/publishing.py) / [`proposals.py`](../../backend/app/scheduler/infrastructure/proposals.py) | Proposta, aprovação, rejeição e escrita por `unit_accounting` | — | Leitura |
| [`tests/_support/scheduler_v1.py`](../../backend/tests/_support/scheduler_v1.py) | `construct_schedule` 428 | — | Leitura |
| [`test_scheduler_weighted_construction_v1.py`](../../backend/tests/unit/test_scheduler_weighted_construction_v1.py) | Helpers, `_select_period`, `construct_schedule`; *patch* | S3–S5 | Regressão |
| [`test_scheduler_availability_priority_v1.py`](../../backend/tests/unit/test_scheduler_availability_priority_v1.py) | `construct_schedule`; `_construct_pass` 437; `_construct_recovery` 450 | S4–S6 | Regressão |
| [`test_scheduler_recovery_construction_v1.py`](../../backend/tests/unit/test_scheduler_recovery_construction_v1.py) | `construct_recovery`; *patch*; teste R11 planeado | S6–S7 | Regressão |
| [`test_scheduler_constructive_progress_v1.py`](../../backend/tests/unit/test_scheduler_constructive_progress_v1.py) | Helpers, `_select_period`, `cp_model` | S1/S3–S4 | Regressão |
| [`test_scheduler_constructive_presence_v1.py`](../../backend/tests/unit/test_scheduler_constructive_presence_v1.py) | `construct_schedule` e `search_adaptive_schedule` | S4–S6 | Regressão |
| [`test_scheduler_lab_fixtures.py`](../../backend/tests/unit/test_scheduler_lab_fixtures.py) / [`test_scheduler_search_fallback_v1.py`](../../backend/tests/unit/test_scheduler_search_fallback_v1.py) | Fixture `BASE_SPEC` e ordem de *fallback* | S1/S8 | Regressão |
| [`test_scheduler_generation_v1.py`](../../backend/tests/unit/test_scheduler_generation_v1.py) / [`test_scheduler_recovery_v1.py`](../../backend/tests/unit/test_scheduler_recovery_v1.py) | Consumidores de geração e recuperação | S5/S7 | Regressão |
| [`domain/`](../../backend/app/scheduler/domain/) / [`infrastructure/`](../../backend/app/scheduler/infrastructure/) | `priority_value.py`; `construction_support.py` planeado | S3–S7 | Novo |
| [`tests/unit/`](../../backend/tests/unit/) | Caracterização e campanha planeadas | S1–S2 | Novo |

### Identidade e contabilidade

| Identificador | Significado verificado |
| :--- | :--- |
| [`Assignment.assignment_id`](../../backend/app/scheduler/infrastructure/snapshot.py) 1227 | `TeachingUnit.unit_id`, chave lógica da unidade; pode ser sintética e não é uma FK de `curricular_assignment`. |
| `SnapshotBundle.unit_accounting` | `unit_id` → ids de contabilidade (`curricular_assignment.id`) por turma. |
| `SnapshotBundle.accounting_classes` | id de contabilidade → `class_id`; `proposals.py` usa estes mapas para as FKs escritas. |
| `module_id`, `class_id`, `teacher_id`, `room_id` | `module.id`, `class.id`, `teacher.id`, `room.id`. |
| `ScheduledLesson.lesson_id` | Identidade lógica estável do candidato; não é a PK de uma nova linha; `base_lesson_ids`/`base_lesson_classes` ligam à BD. |
| `subject_id` | `subject.id`. |

Não se copiam nomes plurais de uma spec antiga: a fonte é o código acima.

## Related Documents

- [WBS da refatoração](CONSTRUCTION_REFACTOR_WBS.md)
- [Especificação técnica do scheduler v1](SCHEDULER_V1_TECH_SPEC_V2.md)
- [Prioridades escolares](SCHEDULE_PRIORITIES_TECH_SPEC.md)
- [Prioridade de disponibilidade](AVAILABILITY_PRIORITY_TECH_SPEC.md)
- [Registo de engenharia de prioridades](SCHEDULE_PRIORITIES_ENGINEERING_LOG.md)
- [Command Reference](../00_getting_started/COMMAND_REFERENCE.md)
- [Testing and CI](../08_security_quality/TESTING_AND_CI.md)
