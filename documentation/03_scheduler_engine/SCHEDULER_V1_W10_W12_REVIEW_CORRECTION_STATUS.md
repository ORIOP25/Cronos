# W10–W12 — Correção da revisão independente (registo as-built)

Data: 26 de setembro de 2026.
Branch: `codex/scheduler-v1-revamp`.
Estado: R10.1–R12.3 aplicados no âmbito corrigido. **O gate local de W12 permanece bloqueado**; W13 não foi iniciado.
Documentos de referência: [plano v2](SCHEDULER_V1_REVAMP_PLAN_V2.md), [WBS v2](SCHEDULER_V1_WBS_V2.md), [especificação v2](SCHEDULER_V1_TECH_SPEC_V2.md), [W10–W11](SCHEDULER_V1_W10_W11_STATUS.md), [W12](SCHEDULER_V1_W12_STATUS.md).

## 1. Decisão do gate

A candidate melhorou substancialmente: os defeitos F01–F05 e F10 têm correções com regressões permanentes, as campanhas foram repetidas com resultados completos e existe um holdout novo e congelado. Ainda assim:

- **E2E local (R12.2) está bloqueado pelo ambiente**: o runner exige uma chave Clerk `pk_test_`; o ambiente só tem chaves de produção e não existe adaptador local de autenticação. O percurso escolar de ponta a ponta não foi executado.
- **Política de paragem (R11.2)**: a calibração offline escolhe `eager` (sem perda, com paragem efetiva, poupança de ~228 s numa trajetória de 300 s), mas a avaliação online na família reservada **não confirmou** a poupança (o primeiro candidato completo chega ao limite do orçamento). A política fica como candidata não ativada; o orçamento de segurança mantém-se integral.
- A aceitação de horários concretos pelo proprietário continua pendente.

Consequência: W13 continua interdito. As condições 2, 7 e 10 do gate local (plano §17.1) permanecem abertas.

## 2. Correções por defeito

| ID | Correção aplicada | Regressão/evidência |
| :--- | :--- | :--- |
| F01 | `lab/longitudinal.py`: replay exige exatamente `event_count` passos aplicados, candidato final válido e conservação por módulo; consumir o ano antes dos eventos é incompleto; evento sem efeito é registado como tal (`applied`, `affected_lessons`). | `test_a_clock_that_consumes_the_year_before_events_is_incomplete`, `test_every_declared_event_must_be_applied_to_future_lessons`; replays 10/30/45/60 com 4/4 `VALID`, `completed`, `conserved` e eventos efetivos. |
| F02 | `lab/recovery.py`: `apply_event_with_effect` coloca a baixa docente apenas nas aulas futuras do docente (excluindo protegidas), nunca em períodos passados. | `test_scheduler_w10_future_events_v1`; ausências reais afetam 6 aulas por passo nos replays; bateria de oráculo W06 revalidada. |
| F03 | `lab/campaign.py`: `case_passes` falha fechado (`ERROR`, `OMITTED`, `INCONCLUSIVE`, `INVALID` não esperado bloqueiam mesmo com expectativa exploratória). `lab/matrix.py` separa cobertura executada de concluída e bloqueia com `blocking_cases`. | `test_an_error_blocks_a_campaign_even_with_an_exploratory_expectation`, `test_matrix_coverage_separates_executed_from_concluded_cases`; CLI devolve código 1. |
| F04 | `services/timesheet_service.py` e endpoints: com versão v1 ativa, a submissão semanal, os contadores e a revisão usam `SchedulerLessonV1`/`SchedulerLessonLogV1`; legado ignorado (sem dupla contagem); aula futura ou sem registo bloqueia. | `test_timesheets_v1.py` (4 testes, PostgreSQL real) + isolamento por organização; suíte de integração 299 verde. |
| F05 | `lab/reports.py`: comparação lexicográfica do vetor de produto com tolerâncias explícitas por família; `clean` inclui regressões de qualidade; diferenças métricas preservadas. | `test_a_worse_product_vector_is_not_clean_even_when_valid`, `test_an_explicit_family_tolerance_allows_a_declared_degradation`. |
| F06 | `lab/construct.py`: testemunhos construtivos independentes validados; matriz W10 com 10 eixos (procura 1h/10h/50h, crédito parcial, módulos cruzados, histórico executado, estabilidade, horizonte, eventos, docentes, salas, espaço); casos de pressão docente partilhada. | 236 pares válidos cobertos por 17 casos, `complete=True`; cada caso prepara testemunho construtivo validado; campanha 17/17 `VALID`. |
| F07 | `lab/performance.py`/`lab/baseline.py`: benchmark com quotas Docker (`--cpus=4 --memory=6g`), 10/30/45/60 turmas, 2 seeds, RSS (VmHWM), falhas e censura; escolha de workers por validade → qualidade → custo. | 40 amostras; 1/2/4 workers 8/8 válidos, 8 workers 7/8; `candidate_workers=2` (custo/qualidade); relatórios por família. |
| F08 | `lab/calibration.py`: candidatos explícitos, regra de adoção que exige paragem efetiva e ausência de perda; avaliação online com `--exploration` em família reservada. Defeito C19 corrigido: só incumbentes estritamente melhores entram na trajetória (guarda no campaign). | `w11_calibration_manifest.json` com `chosen=eager` (offline) e estado `candidate-unconfirmed`; online 120 s sem poupança; gate bloqueado com experiência necessária documentada. |
| F09 | Holdout novo (2 reparações + 1 replay anual) congelado por `code_identity` e digests; primeira versão do replay anual anulada por falha de desenho (3 eventos × 21 dias consumiam o plano), documentada antes de qualquer alteração de código. | `holdout_manifest.json`, `holdout_annual_manifest.json`; identidade final `4be18920a555fa4e`; reparações idênticas em duas execuções, anual `VALID`/`conserved`. |
| F10 | `lab/campaign.py`: `prepare_case` calcula o digest antes de qualquer solve; `--resume` não executa o solver; a proveniência de reparação usa o digest do snapshot perturbado. | `test_resume_does_not_run_the_solver_again`, `test_repair_provenance_includes_the_perturbed_snapshot_digest`. |

Correção adicional descoberta pela bateria de oráculo após F02: movimentos encadeados de 2 passos em `_stabilize_recovery`, aceites apenas com melhoria estrita do vetor completo (resolve o ótimo coordenado que a estabilização de 1 movimento não alcançava).

## 3. Campanhas repetidas (resultados completos)

| Campanha | Resultado final | Onde |
| :--- | :--- | :--- |
| `w06-w07-combined` (reparação, 18 casos) | 16 `VALID`, 2 `INFEASIBLE`, 0 inconclusivos | `.test-artifacts/w10r-final/repair` |
| `w10-combined` (matriz, 17 casos) | 17 `VALID`; 236/236 pares cobertos, sem bloqueios | `.test-artifacts/w10r-final/combined` |
| `w10-boundaries` (6 casos) | 3 `INFEASIBLE` (pressão provada), 3 `VALID` (reversão) | `.test-artifacts/w10r-final/boundaries` |
| `w10-annual-replay` (10/30/45/60) | 4/4 `VALID`, `completed`, `conserved`, eventos efetivos | `.test-artifacts/w10r/annual-replay` |
| Benchmark de workers (40 amostras) | 1/2/4 workers válidos em todas; 8 workers 7/8; custo CPU cresce com workers | `.test-artifacts/w11r/workers` |
| Trajetória longa (300 s) | 1 incumbente; `eager` poupa 228 s sem perda offline | `.test-artifacts/w11r/trajectory-long2` |
| Avaliação online (reservada, 120 s) | sem poupança confirmada; política não ativada | `.test-artifacts/w11r/online-*` |
| Holdout final | reparação 2/2 `VALID` (duas execuções idênticas) + anual `VALID`/`conserved` | `.test-artifacts/w12r/final-*` |

## 4. Checks de projeto (código final)

| Verificação | Resultado |
| :--- | :--- |
| `pytest tests/unit` | 713 passed |
| `node scripts/test.mjs integration` | 299 passed (PostgreSQL real, migrações a partir de base vazia) |
| Contratos | 47 passed |
| `ruff check` / `ruff format --check` | limpos |
| Frontend `npm run lint` / `npm run test` | verdes; 411 testes |
| E2E Playwright | **bloqueado**: `VITE_CLERK_PUBLISHABLE_KEY` não é `pk_test_` |

## 5. Limitações e experiências necessárias

1. E2E: fornecer um par de chaves Clerk de teste (`pk_test_`/`sk_test_`) ou aprovar um adaptador local de autenticação; repetir o percurso configurar → gerar → aprovar → registar aula/falta → reparar → submeter timesheet.
2. Política de paragem: repetir a avaliação online em pelo menos três famílias reservadas com orçamento longo (≥ 300 s), comparar poupança com o ganho perdido do vetor e obter aceitação explícita do proprietário antes de qualquer ativação.
3. Aceitação: revisão de horários concretos e do compromisso qualidade/tempo/custo pelo proprietário.
4. A identidade de código está congelada por digest (`4be18920a555fa4e`); o commit continua a ser decisão do proprietário.
