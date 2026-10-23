# WBS — Refatoração da construção do scheduler

## Purpose

Decompõe o [tech spec](CONSTRUCTION_REFACTOR_TECH_SPEC.md) em dez *slices* seriais e três PRs; decisões, invariantes, inventário e riscos ficam no spec, aqui a ordem, escrita, prova e orçamento.

## Regras de Execução

- Nenhum *slice* altera comportamento observável.
- C01–C22 e atualizações exigem candidato completo; C23 preserva exatamente o `INCONCLUSIVE` da base, com candidato/qualidade `None`, conforme revisão autorizada no tech spec. Não se altera o solver ou os limites.
- Engenharia em 90 minutos; campanha em lotes de 80 minutos com retoma do perfil pendente.
- Uma lane de escrita de produção em S3–S7; S1/S2 preparam prova sem alterar produção.
- Ficheiros quentes não cabem em S1: uma lane serial em S3–S7, extrações limitadas/inalteradas e sem escrita concorrente; não criar um mega-S3.
- Teste vermelho de caracterização/unitário antes da extração; a mutação é revertida antes de extrair.
- Uma diferença de candidato, ordem, crédito, sala, modelo, recusa ou `binding` pára o *slice*.
- Não se aumenta limite, enfraquece teste, muda dependência ou corrige comportamento latente para passar.
- Depois de S7 só se alteram testes, artefactos e documentação de prova.
- Caminhos são relativos a `backend/`; `critical` é o job CI, não prova de BD local. O *fast* é local; CI, `.github/` e browser E2E não mudam.

## Write Set

| Área | Ficheiros | Slice |
| :--- | :--- | :--- |
| Domínio | `backend/app/scheduler/domain/priority_value.py` | S3 |
| Infraestrutura partilhada | `backend/app/scheduler/infrastructure/construction_support.py` `(novo)` | S3–S4, S6–S7 |
| Construção | `backend/app/scheduler/infrastructure/constructive.py` | S3–S5 |
| Recuperação | `backend/app/scheduler/infrastructure/recovery_construction.py` | S6–S7 |
| *Harness* lento | `backend/tests/_support/construction_snapshot.py` `(novo)` | S2, S8–S10 |
| Oracle rápido | `backend/tests/unit/test_scheduler_construction_characterization_v1.py` `(novo)` | S1–S2 |
| Campanha lenta | `backend/tests/unit/test_scheduler_construction_campaign_v1.py` `(novo)` | S2, S8–S10 |
| Testes focados | `test_scheduler_weighted_construction_v1.py`, `test_scheduler_availability_priority_v1.py`, `test_scheduler_recovery_construction_v1.py`, `test_scheduler_constructive_progress_v1.py` | S1, S3–S7 |
| Manifesto e comandos | `backend/tests/critical_selection.py`, `backend/tests/critical_manifest.json`, `documentation/00_getting_started/COMMAND_REFERENCE.md` | S2 |
| Leitura apenas | `search.py`, `placement_model.py`, aplicação, composição, propostas, publicação, laboratório, CI | — |

O ficheiro lento é separado do rápido: o manifesto crítico corre o ficheiro rápido **inteiro**, sem filtro `-m`. O manifesto não inclui o ficheiro `slow_solver`.

## Slices

| ID | PR | Comportamento | Primeiro teste | Prova / filtro | Dep. | Caixa |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| S1 | 1 | Oracle rápido autónomo e projeção ordenada | `test_construction_candidate_matches_base_fixture`; guarda de ordem de *slice* | `-k "construction_characterization or projector or period_repair_models"` | — | 90 min |
| S2 | 1 | *Harness* lento, modelo, C01–C23, manifesto, comandos e B0; sem produção | `test_construction_campaign_profiles_cover_c01_to_c23` | `-m slow_solver -k construction_campaign`; B0 23/23; manifesto contém o ficheiro rápido | S1 | 90 min + 3 lotes |
| S3 | 1 | Medidas puras, `construction_support`, seletor e aliases transitórios | Quatro *digests*; limites exatos | `-k "period_selection or period_repair or uniform_class_rooms or different_subject_rooms"` | S2 | 90 min |
| S4 | 2 | Estado de `_ConstructionPass`: *ledger*, ocupação, presença, salas | Presença, slots, R06 | `-k "r07 or constructive or weighted_construction"` | S3 | 90 min |
| S5 | 2 | Prioridade, admissão, fases, candidato e seis casos | Caracterização; 17 verificações | `-k "generation or recovery_construction or publishing"`; integração de fronteira; 6/6 | S4 | 90 min |
| S6 | 3 | Estado de `_RecoveryPass`, retenção/reversão e importações mecânicas | R11 75+75/50; `rr1`–`rr3` | `-k "recovery_construction or rr1 or rr2 or rr3"` | S5 | 90 min |
| S7 | 3 | Presença, planeamento, fases, normalização e fim | `rr4`; crédito parcial; cancelamento | `-k "recovery_construction or rr4"` | S6 | 90 min |
| S8 | 3 | Cenários A/B, 5 níveis, 10 pares | Independência de `update_stability`; 10/10 | `-k "construction_updates"`; `slow_solver` | S7 | 90 min + lotes |
| S9 | 3 | Matriz C01–C12 | Pares C01–C12 | 12/12; zero *skips* | S8 | 80 min/lote |
| S10 | 3 | C13–C23, Sonar e fecho | Pares C13–C23 | 23/23; 10/10; S3776 | S9 | 80 min/lote |

## Detalhe dos Slices

### S1 — Oracle rápido

- Congelar fixture local e candidato tipado/ordenado; sem `.test-artifacts`, `build_fixture` ou importar `BASE_SPEC`; valores exatos no spec.
- `test_construction_candidate_matches_base_fixture` valida o *commit* base; diferença exige inspeção, nunca regenerar a constante da saída.
- `test_projector_detects_slice_order_only_difference` e `candidate_digest`; quatro *digests* são guarda, S2 guarda a *baseline* `Proto()`.
- Provar mutações de desempate, *slice*, sala e valor; vermelho com mutação, verde restaurado.
- Prova: *oracle*, projetor e quatro *digests* passam no *commit* base.

### S2 — Harness lento, manifesto e B0

- Criar `construction_snapshot.py`: projeção, `hash`, proveniência, C01–C23, *fixture* de atualização materializada e candidato C01 completo.
- Criar `test_scheduler_construction_campaign_v1.py` com `slow_solver`; não o incluir no crítico.
- Escrever no ficheiro rápido o guarda de atualização 180 e promovê-lo inteiro ao crítico, sem retirar testes.
- S2 captura a *baseline* `str(model.Proto())` das mesmas quatro opções, ordem e versão OR-Tools; sem *proto* gigante no repositório.
- Registar na Command Reference a inspeção do Sonar existente e a exceção `-m slow_solver`; sem *runner*, subcomando, *scanner* ou configuração.
- Capturar B0 em três jobs de 8/8/7 perfis no *commit* base, com *overlay* só de testes; nunca correr código alterado para referência.
- Prova: 23 IDs de base (22 candidatos completos e o resultado terminal de C23); manifesto só com testes rápidos; *fixture* de atualização capturado; zero omissões.

### S3 — Helpers puros e seletor

- Mover medidas puras, valor/admissão de sala e verificações exatas para `priority_value.py`/`construction_support.py`; sem OR-Tools.
- Dividir o ganancioso, modelo/coeficientes e solver/leitura de `_select_period`, no mesmo ficheiro.
- Manter `_select_period`, `cp_model` e o *binding*; reexportar só *aliases* usados por produção/testes; remover apenas os sem consumidor.
- R05: igualdade registada com `PERIOD_REPAIR_DETERMINISTIC_TIME` e `(0.1, inf)` sem pesos; não basta `>0`.
- Prova: quatro *digests*, ganancioso/fluxo e salas; S3 e cada PR comparam byte a byte o artefacto *baseline* das mesmas quatro opções.

### S4 — Estado de construção

- Criar `_ConstructionPass` com `_ledger`, `busy`/`occupancy` de colocados/protegidos, *preview* de presença, slots, índices de recursos e salas.
- Manter a ocupação pendente não comitada; a construção tem ocupação comprometida e *preview*.
- Conservar `occupy`, `ready`, `place`, `defaultdict`, `_gives_up` e a ordem de cancelamento.
- Manter reexports transitórios e a ordem de `_select_period`; não remover nomes que testes importam.
- Prova: presença/slots, R06 e R04 passam; nenhum candidato muda.

### S5 — Decisões e seis casos

- Mover prioridade, desempate, histórico, medidas ponderadas, admissão, `fill_admitted`, execução do *run* e junção do candidato.
- `_construct_pass` fica coordenador de fases; conserva estrito/relaxado/preenchimento, recusas, `paced_out` e cancelamento.
- Correr C01 (base), C03, C17, C21, C23 e C18; correspondem aos seis perfis nomeados, não certificam o script antigo nem a escala; C20 fixa `SCHOOL_CRITERION_KEYS=2` e `finish_early=4`.
- Prova: 6/6 (cinco candidatos e o resultado terminal de C23), R07 com 17 verificações e consumidores de geração iguais; unitário de publicação no *fast* `-k publishing`.
- Integração: `-k "scheduler_v1_api or scheduler_v1_lifecycle or joint_lesson_engine"`.

### S6 — Estado de recuperação

- Criar `_RecoveryPass` com histórico protegido/*baseline*, `patterns.setdefault`, índices, ocupação, `_Booking`, retenção, reverção inversa, dias quebrados e `refresh_last_end`.
- Mover importações de recuperação de `constructive` para `priority_value`/`construction_support` mecanicamente; sem ciclos.
- R11: módulos 75+75, executado M1=50, lições futuras 60+40 → `[(M1,50,25),(M2,0,35)]` e `[(M2,35,40)]`, futuro 100 + executado 50 = 150; *offsets* locais ao módulo, só a última editável parcial.
- `test_construction_and_recovery_keep_cross_module_slice_offsets` no ficheiro de recuperação; não há teste existente; *aliases* usados ficam, sem limpeza total; prova `rr1`–`rr3`, R11 e reversão.

### S7 — Planeamento de recuperação

- Mover opções, ordenação, `plan_presence_run`, `book`, fases, normalização e `_build_candidate`.
- `_construct_recovery` fica coordenador; `construct_recovery` não muda.
- Conservar `deadline` antes de `should_cancel`, recusas, preenchimento e apenas a última editável parcial.
- S7 não escreve `constructive.py`; mantém *aliases* e o *binding* `_select_period`/`cp_model`; limpar só *alias* sem consumidor num passo mecânico autorizado após testes, ou adiar.
- Prova: `rr4`, crédito, ausência de *pacing* na recuperação e consumidores iguais.

### S8 — Atualizações

- Fixture fixa: `SCHOOL_YEAR_START=2026-09-14`, `HARD_END=2027-07-30`, referência e `now_utc=2027-02-22T00:00:00+00:00`; 5 datas protegidas de `grid_dates`, até 2027-02-26; baseline C01 uma vez, sem *loader* de BD.
- Histórico concluído tem `end_utc <= now_utc`, agregado uma vez por módulo e unidade conjunta; baseline ativa só `start_utc > now_utc`, sem lição a atravessar; passadas consumidas não ficam planeadas/protegidas.
- Snapshot ativo: `ADAPTIVE_RECOVERY`, executado, `baseline_lessons=active`, protegidas, pesos, IDs originais reservados; reservations/dívida/claims/`prior_changes` vazios; `laboratory_policy`; a pesquisa recebe só o candidato ativo, igual base/cabeça, e o C01 completo fica no artefacto.
- Invariante `required = executed + protected + residual`; `validate_candidate` passa antes de acrescentar indisponibilidade e falha só nas editáveis afetadas depois, sem conflito protegido.
- A: 2027-03-01 a 2027-03-12. B: quartas desde 2027-03-03 até `HARD_END`; primeiro `teacher_id` ordenado sem mínimo, afetado e sem conflito protegido, ou falha, nunca *skip*.
- 2 cenários × 5 níveis = **10 pares**; 4 pares locais/reconstruídos (2 eventos × base/cabeça; 8 chamadas de topo); custos nos 5 níveis reutilizam pares; 10 comparações/vencedores pequenos; nunca 10 pesquisas reais.
- Envolver *bindings*/custo com encaminhamento transparente; não alterar `search`; limite 3600 s, caso pequeno com relógio controlado e `deadline` quase zero testa cancelamento sem prometer candidato.
- `test_construction_updates_do_not_double_count_completed_or_protected_credit`: guarda rápido no ficheiro de caracterização (S2), crítico inteiro; 180 = executado 60 + protegido 60 + residual 60; o lento fica na campanha.
- `test_construction_updates_match_frozen_base`: `slow_solver`, A/B × 0–4, filtro `construction_updates`; S2 captura o *fixture* sem alterar produção.
- Prova: 10/10 candidatos/estado/qualidade/custo/disrupção/`objective_scope`/`priorities_followed`; diagnósticos local/reconstrução extra; históricos base/cabeça idênticos.
- `search_fallback` sem pesos passa antes/depois; se a independência falhar, sublotes limitados sem abandonar níveis.

### S9 — Matriz C01–C12

- 12 perfis contra base/cabeça; lotes de 80 min; retomar perfil pendente.
- `-k "C01 or C02 or C03 or C04 or C05 or C06 or C07 or C08 or C09 or C10 or C11 or C12"`.
- Não prometer que todos cabem num lote quando o diff real for maior; registar checkpoint.
- Prova: 12/12, zero *skips*.

### S10 — C13–C23 e fecho

- 11 perfis; 23/23 no total (22 candidatos e C23 `INCONCLUSIVE`); 10/10 atualizações completas; zero `None` inesperado, `timedout` ou omissões.
- `-k "C13 or C14 or C15 or C16 or C17 or C18 or C19 or C20 or C21 or C22 or C23"`.
- Rever assinaturas, imports privados, consumidores, reexports, `git diff` e ausência de segunda implementação.
- Abrir o relatório SonarCloud S3776 do PR de implementação: URL, pontuação por função, exatamente as três funções alvo e novas/extraídas, máximo 15. Sem relatório, a prova numérica fica não verificada.
- Anexar manifesto de evidência; revisor confirma 23 IDs/10 pares; CI não é alterado.

## Campanha

| Lote | Conteúdo | Saída |
| :--- | :--- | :--- |
| B0a/B0b/B0c | Base C01–C08/C09–C16/C17–C23 no *commit* base | 23 referências, `hash` e proveniência |
| B1 | Seis casos nomeados | 6/6 resultados iguais: cinco candidatos e C23 terminal |
| B2 | Cenários A/B, 5 níveis | 10 pares |
| S9 | Cabeça C01–C12 | 12 comparações |
| S10 | Cabeça C13–C23 | 11 comparações |

B0 são 3 jobs de computação, não a *suite*; matriz pareada ~4 h, cache ~2 h.
Cada lote regista comando, perfil, filtro, código, tempo, IDs e contagem; lote sem casos não é prova; base capturada uma vez.

## Lanes and Pull Requests

| PR | Slices | Barreira |
| :--- | :--- | :--- |
| PR 1 | S1–S3 | Merge após S3; testes rápidos, seletor e reexports verdes |
| PR 2 | S4–S5 | Merge após S5; seis casos, R07 e integração |
| PR 3 | S6–S10 | Um ramo; sem merge entre S6–S10; campanha no fecho |

A lane 0 (S1–S3) corre sozinha; C (S4–S5) após PR1; R (S6–S10) após PR2, com **um** ramo. Sem novo ramo ou merge interno; barreiras só PR1/S3 e PR2/S5.
Cada PR corre o *fast* focado e a integração de fronteira; PR1/PR2/PR3 correm os casos/atualizações aplicáveis fora do *timebox*.

## Rastreabilidade

| IDs | Slices |
| :--- | :--- |
| D01–D02 | S5, S7, S8 |
| D03, D05, D08, D17 | S3 |
| D04, D06, D07 | S4, S6 |
| D09 | S3–S7 (inventário e regressão) |
| D10, D15, D18 | S5, S7, S10 |
| D11, D12, D14, D19 | S1, S2, S10 |
| D13, D16, D20 | S2, S8, S9, S10 |
| I01–I03 | S1, S2, S3, S5, S7, S8 |
| I04–I08 | S1, S3, S4, S10 |
| I09–I12 | S4, S6, S7, S8 |
| I13–I16 | S1, S2, S3, S4, S5, S6, S7, S10 |
| R01, R02, R05, R08, R09, R13, R14 | S1, S3, S4, S6, S9, S10 |
| R03, R04, R06, R07 | S2, S4, S5, S6, S7 |
| R10, R11, R12, R16 | S5, S6, S7, S8 |
| R15 | S10 |

## Critério de Paragem

Parar e devolver ao responsável se:

- a caracterização falhar no *commit* base;
- uma referência tiver de ser regenerada para passar;
- um *slice* de engenharia precisar de mais de 90 minutos;
- uma diferença exigir mudar comportamento latente;
- OR-Tools, dependência ou PR aberto invalidar os *digests*;
- a campanha não tiver 23 IDs e 10 pares, ou tiver *skips*;
- o relatório Sonar S3776 não existir ou exceder 15.

## Related Documents

- [Tech Spec](CONSTRUCTION_REFACTOR_TECH_SPEC.md)
- [Command Reference](../00_getting_started/COMMAND_REFERENCE.md)
- [Testing and CI](../08_security_quality/TESTING_AND_CI.md)
- [Registo de engenharia de prioridades](SCHEDULE_PRIORITIES_ENGINEERING_LOG.md)
