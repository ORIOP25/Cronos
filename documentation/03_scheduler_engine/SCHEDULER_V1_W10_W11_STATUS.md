# W10–W11 — Campanhas integradas e calibração (registo as-built)

> Revisão independente e correções: [SCHEDULER_V1_W10_W12_REVIEW_CORRECTION_STATUS.md](SCHEDULER_V1_W10_W12_REVIEW_CORRECTION_STATUS.md). Os números finais de matriz, benchmark, trajetórias e calibração são os do registo de correção; este documento permanece como o registo original de W10–W11.

Data: 26 de setembro de 2026.
Branch: `codex/scheduler-v1-revamp`.
Estado: W10.1–W10.5 e W11.1–W11.4 executados. W12 em curso no registo próprio. Nenhum push, reset remoto ou ensaio Railway/Cloudflare foi executado.
Documentos de referência: [plano v2](SCHEDULER_V1_REVAMP_PLAN_V2.md), [WBS v2](SCHEDULER_V1_WBS_V2.md), [especificação v2](SCHEDULER_V1_TECH_SPEC_V2.md).

## 1. Resultado

- A matriz semântica está declarada nos manifestos e a cobertura por pares é calculada a partir dos relatórios de campanha, não da simples enumeração de casos.
- As interações críticas de três ou mais fatores têm campanha própria (`w10-combined`), com oito pares de eixos e 56 pares válidos cobertos.
- As fronteiras de viabilidade são demonstradas pela verificação de capacidade necessária (défice mínimo provado), nunca por timeout; a reversão restaura exatamente os dados originais.
- Os replays anuais acumulam execução simulada e eventos, validam cada passo e conservam minutos de ponta a ponta (executado + planeado = requisito).
- O perfil de fases revelou que a elegibilidade conjunta dominava o custo; a duplicação de cálculo no planeamento anual foi removida com regressões verdes.
- A calibração da paragem ficou explicitamente inconclusiva: as trajetórias disponíveis têm um único ponto e nenhuma política pouparia tempo com ganho zero. Não foi ativado nenhum default silencioso.

## 2. W10 — Campanhas integradas

| ID | Entrega | Evidência |
| :--- | :--- | :--- |
| W10.1 | Matriz de fatores e combinações por pares. | `lab/matrix.py` (cobertura por pares, exclusões justificadas, array de cobertura determinista); `combined_manifest.json` (5 eixos, 56 pares); relatórios `matrix_report.json` com `complete=True problems=0`. |
| W10.2 | Interações críticas de três ou mais fatores. | Casos explícitos `w10-c08-teacher-room-calendar`, `w10-c10-recovery-after-preferred`, `w10-c11-stability-margin`, `w10-c12-accumulated-events` e 10 casos de cobertura por pares; campanha `w10-combined` 14 casos {VALID 12, INFEASIBLE 2}. |
| W10.3 | Replays anuais com eventos acumulados. | `lab/longitudinal.py` (relógio simulado, consumo de execução, reparação e adoção do candidato validado); campanha `w10-annual-replay` 10/30/45/60 turmas, 4/4 `VALID`, `completed=True`, `conserved=True`; passo a passo com validação independente. |
| W10.4 | Fronteiras de viabilidade e reversão de pressão. | `lab/boundaries.py` (`block_resource`, `remove_eligible_rooms`, `remove_grid_slot`, `prove_pressure`); campanha `w10-boundaries` 6 casos {INFEASIBLE 3 (removido), VALID 3 (restaurado)}, matriz completa. |
| W10.5 | Redução de falhas a casos mínimos. | `lab/reduce.py` (redução gulosas determinística com predicado); `reduced_case` gera regressões permanentes; teste de minimalidade por segunda passagem. A falha da fixture reservada `w12-reserved-03` foi reduzida e corrigida no gerador, não escondida. |

Ficheiros novos: `app/scheduler/lab/matrix.py`, `lab/boundaries.py`, `lab/longitudinal.py`, `lab/reduce.py`, `lab/combined.py`.
Manifestos novos (versionados): `combined_manifest.json`, `boundary_manifest.json`, `annual_replay_manifest.json`, `reserved_manifest.json`, `reserved_annual_manifest.json`.
Regressões novas: `test_scheduler_lab_matrix`, `test_scheduler_w10_combined_events`, `test_scheduler_w10_longitudinal_v1`, `test_scheduler_w10_boundaries_v1`, `test_scheduler_w10_reduce_v1`, `test_scheduler_w10_manifests_v1`.

## 3. W11 — Desempenho e calibração

| ID | Entrega | Evidência |
| :--- | :--- | :--- |
| W11.1 | Comparar workers 1/2/4/8 no hardware local. | `lab/performance.py` (intercalação, CPU, pico de memória Python, fases); Docker `cronos-backend-test:local`; relatórios em `.test-artifacts/w11/workers`. 10 turmas (2 repetições, 30 s): medianas 30.4/29.4/24.3/30.7 s; 30 turmas (45 s): 46.5/46.1/48.2/49.2 s, CPU 46.5→64.8 s. Todas as configurações produziram candidatos válidos. |
| W11.2 | Perfilar construção, procura, solver e persistência. | Perfil `cProfile` mostrou `capacity.eligible_periods` a dominar (~74% do tempo medido) por recomputação duplicada no planeamento anual; `_availability_minutes` reutiliza agora as elegibilidades já calculadas. Regressões das nove otimizações verdes; orçamento de fases passa a acumular construção e solve de todas as rondas de feedback. |
| W11.3 | Calibrar política adaptativa e paragem. | `lab/calibration.py` (5 candidatos explícitos, regra de seleção declarada, treino separado da avaliação reservada); trajetórias de treino e anual registadas. Resultado honesto: todas as trajetórias têm um ponto; nenhum candidato poupa tempo (`chosen=None`). Mantém-se a exploração completa dentro do orçamento de segurança. |
| W11.4 | Fixar baseline e parâmetros candidatos. | `lab/baseline.py`; `w11_baseline_manifest.json` (versionado): `w11-baseline-1`, `candidate_workers=4`, `stop_policy=null`, `target_p95=null` (p90 apenas observado), decisão explícita de não agrupar salas equivalentes com a razão. |

Ficheiros novos: `app/scheduler/lab/performance.py`, `lab/calibration.py`, `lab/baseline.py`.
Regressões novas: `test_scheduler_w11_performance_v1`, `test_scheduler_w11_calibration_v1`, `test_scheduler_w11_baseline_v1`, `test_scheduler_w11_profile_accounting`, `test_scheduler_w11_trajectory_v1`, `test_scheduler_w11_manifests_v1`.

## 4. Cobertura da matriz obrigatória (WBS §8)

| Eixo | Níveis cobertos | Onde |
| :--- | :--- | :--- |
| Escala | 10/20/30/45/60 turmas | `annual_manifest`, `annual_replay_manifest`, `reserved_annual_manifest` |
| Procura de reparação | eventos únicos e combinados, pressão e fronteira exata | `combined_manifest`, `boundary_manifest`, `reserved_manifest` |
| Espaço efetivo | apertado viável, amplo, sem interseção provada | `combined_manifest`, `boundary_manifest` |
| Docentes | independentes, partilhados, indisponibilidade prolongada | `combined_manifest`, `reserved_manifest`, `repair_manifest` |
| Salas | alternativas, específicas, removidas e restauradas | `combined_manifest`, `boundary_manifest`, `reserved_manifest` |
| Horizonte | curto, médio, longo | `combined_manifest`, `repair_manifest` |
| Calendário | grelhas 3/4/5/6, bloqueios, feriados | `annual_manifest`, `generation_manifest` |
| Estabilidade | fronteira editável (`now_utc`), datas protegidas | `w10-c11`, `repair_manifest` |
| Datas finais | preferencial, além da preferencial, limite absoluto | `w10-c10`, `annual_manifest`, `repair_manifest` |
| Histórico | poucos e muitos eventos acumulados | `w10-c12`, `annual_replay_manifest` |
| Operação | sucesso, cancelamento, falha, lock perdido, stale | `test_scheduler_v1_lifecycle`, `test_scheduler_v1_operations` (W08) |
| Hardware | 1/2/4/8 workers internos | `.test-artifacts/w11/workers` |

Limitações declaradas: o eixo de operação é exercido pela integração PostgreSQL (W08), não pelo laboratório CP-SAT; as quotas Docker de CPU/RAM foram representadas pelo hardware local de 8 processadores lógicos e 32 GB (o ensaio remoto é da W13).

## 5. Relatórios

- W10: `.test-artifacts/w10/combined`, `.test-artifacts/w10/boundaries`, `.test-artifacts/w10/annual-replay-full` (relatório e `matrix_report.json`).
- W11: `.test-artifacts/w11/workers/annual-10.json`, `annual-30.json`, `.test-artifacts/w11/calibration`, `.test-artifacts/w11/baseline_manifest.json`.
- Versionados: `backend/tests/scheduler_lab/w11_baseline_manifest.json`, `w11_calibration_manifest.json` e os manifestos de campanha.

Os artefactos de execução não são versionados por tamanho; as receitas e manifestos são.
