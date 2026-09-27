# W10–W12 — Correção da revisão independente (registo as-built)

Data: 26 de setembro de 2026 (atualizado a 27 de setembro de 2026 com W12.R1–W12.R3).
Branch: `codex/scheduler-v1-revamp`. Commit da revisão mais recente: `9582ff4`.
Estado: R10.1–R12.3 aplicados no âmbito corrigido. O gate local de W12 tem as condições 2, 7 e 10 atualizadas por W12.R1–R12.3; a aceitação do proprietário (condição 10) é o último ato antes de W13. W13 não foi iniciado.
Documentos de referência: [plano v2](SCHEDULER_V1_REVAMP_PLAN_V2.md), [WBS v2](SCHEDULER_V1_WBS_V2.md), [especificação v2](SCHEDULER_V1_TECH_SPEC_V2.md), [W10–W11](SCHEDULER_V1_W10_W11_STATUS.md), [W12](SCHEDULER_V1_W12_STATUS.md), [avaliação da paragem](SCHEDULER_V1_W12_R2_STOP_POLICY_EVALUATION.md), [remediação CI #509](SCHEDULER_V1_CI_509_REMEDIATION_STATUS.md).

## 1. Decisão do gate

A candidate melhorou substancialmente: os defeitos F01–F05 e F10 têm correções com regressões permanentes, as campanhas foram repetidas com resultados completos e existe um holdout novo e congelado. Estado atual das condições em falta:

- **Condição 2 (domínio, validação independente, integração e E2E locais)**: fechada. Os três cenários E2E que falhavam na CI #509 foram corrigidos e passam localmente e na CI; o commit `9582ff4` tem backend, frontend, E2E e capacity smoke verdes ([execução](https://github.com/ORIOP25/Cronos/actions/runs/36325073140)).
- **Condição 7 (política de paragem com referências longas e dados reservados)**: fechada com decisão explícita. A avaliação reservada com orçamento de 300 s não confirmou poupança do candidato `eager` e registou perda de vetor numa família; a política conservadora mantém-se e o orçamento de segurança fica integral ([avaliação](SCHEDULER_V1_W12_R2_STOP_POLICY_EVALUATION.md)).
- **W12.R1 (percurso de produto)**: fechado. A data preferencial configura-se pelo produto e a projeção curricular é materializada a partir das atribuições escolares no pedido de geração; o E2E deixou de depender do seed de teste.
- **Condição 10 (aceitação do proprietário)**: pronta para decisão. Os horários concretos, o vetor de qualidade e o compromisso tempo/custo estão resumidos na secção 6; falta a aceitação explícita.

Consequência: W13 permanece interdito até à aceitação explícita da condição 10 pelo proprietário.

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

1. E2E: resolvido. O percurso configurar → gerar → aprovar → registar aula/falta → reparar corre localmente e na CI com chaves Clerk de teste; ver [remediação CI #509](SCHEDULER_V1_CI_509_REMEDIATION_STATUS.md).
2. Política de paragem: avaliação reservada concluída com orçamento de 300 s em três famílias longas e três pequenas; decisão de manter a política conservadora. Uma ativação futura exige nova evidência com poupança sem perda e aceitação explícita do proprietário.
3. Aceitação: revisão de horários concretos e do compromisso qualidade/tempo/custo pelo proprietário — ver secção 6.
4. A identidade de código da candidate congelada (`4be18920a555fa4e`) foi seguida das correções de remediação no commit `9582ff4`; a identidade final é a do commit aceite pelo proprietário.

## 6. Submissão ao proprietário (condição 10)

### 6.1 Horários concretos

| Origem | O que é | Onde observar |
| :--- | :--- | :--- |
| Instalação local (Docker) | Organização E2E com horário anual publicado, aulas registadas, ocorrência e dívida | Aplicação em `http://localhost:5173` (organização E2E preparada) |
| Holdout congelado | Reparação 2/2 `VALID` e replay anual `VALID`/`conserved` | `.test-artifacts/w12r/final-*` |
| Reservado anual | 20 turmas/3 eventos e 15 turmas/2 eventos, `COMPLETE`/`valid` | `.test-artifacts/w12r2/online-reserved-annual-*.json` |
| Reservado por reparação | 3 casos, 1 `VALID` e 2 impossibilidades provadas | `.test-artifacts/w12r2/online-reserved-*.json` |

### 6.2 Compromisso qualidade/tempo/custo

| Dimensão | Evidência | Valor |
| :--- | :--- | :--- |
| Qualidade | Vetor de produto por cenário; holdout e reservado sem regressões prioritárias | Vetores registados por família nos relatórios; `excess_days=0` nas famílias anuais reservadas |
| Tempo | Mediana e p90 por família, 10/30/45/60 turmas | Famílias de 10 turmas: 30,7–43,4 s de mediana; anuais de 15–30 turmas fecham no orçamento de 300 s com candidato completo |
| Custo | CPU e memória por família; workers internos | `candidate_workers=2` (1/2/4 workers válidos em 8/8; 8 workers 7/8; CPU cresce com workers) |
| Paragem | Avaliação reservada com 300 s | Conservadora; sem poupança confirmada com perda zero |

### 6.3 Decisão pedida

O proprietário deve aceitar expressamente as condições 2, 7 e 10 do gate local (plano §17.1) para autorizar o início de W13 (Railway/Cloudflare). Sem essa aceitação, W13 permanece interdito.
