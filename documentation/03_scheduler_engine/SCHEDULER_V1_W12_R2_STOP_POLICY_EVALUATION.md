# W12.R2 — avaliação reservada da política de paragem

Data: 27 de setembro de 2026. Branch: `codex/scheduler-v1-revamp`. Commit de referência: `9582ff4`.

Este registo fecha a avaliação reservada pedida em W12.R2. Não ativa nenhuma política nova: o orçamento de segurança completo permanece ativo.

## 1. Método

Método: `app.scheduler.lab.performance`, modo `repair`, 2 workers internos, orçamento de 300 s, quotas Docker `--cpus=4 --memory=6g`. Cada família foi executada duas vezes: braço conservador (sem política) e braço `eager` (paragem na primeira solução completa). Os artefactos ficam em `.test-artifacts/w12r2/`.

Famílias reservadas usadas (nunca usadas na calibração offline):

| Família | Origem | Escala |
| :--- | :--- | :--- |
| `w12-reserved-annual-20` | `reserved_annual_manifest.json` | 20 turmas, 3 eventos |
| `w12-reserved-annual-15-connected` | `reserved_annual_manifest.json` | 15 turmas, 2 eventos |
| `w12r-holdout-annual-15` | `holdout_annual_manifest.json` | 15 turmas, 2 eventos |
| `w12-reserved-01/02/03` | `reserved_manifest.json` | especificação pequena |

O vetor de produto é o par (custo de perturbação, aulas alteradas) mais os dias em excesso; `excess_days` ficou a zero em todas as execuções.

## 2. Evidência

| Família | Conservador (busca) | `eager` (busca) | Ganho perdido pelo `eager` |
| :--- | :--- | :--- | :--- |
| `w12-reserved-annual-20` | 298,033 s; 38040 / 3804 aulas | 298,978 s; 38040 / 3804 aulas | nenhum |
| `w12-reserved-annual-15-connected` | 298,202 s; 28490 / 2849 aulas | 298,868 s; 28510 / 2851 aulas | +20 de custo; +2 aulas |
| `w12r-holdout-annual-15` | 299,099 s; 28550 / 2855 aulas | 298,673 s; 28550 / 2855 aulas | nenhum |
| `w12-reserved-01` | 0,505 s; 20 / 2 aulas | 0,086 s; 30 / 3 aulas | +10 de custo; +1 aula |
| `w12-reserved-02` | 0,075 s; 10 / 1 aula | 0,041 s; 10 / 1 aula | nenhum |
| `w12-reserved-03` | 0,117 s; 10 / 1 aula | 0,032 s; 10 / 1 aula | nenhum |

Todas as execuções terminaram `COMPLETE`, `valid=True`. Nos orçamentos longos, o `eager` não poupou tempo relevante: a primeira solução completa chega ao limite do orçamento, como já registado na revisão R11.2. Nas famílias pequenas, o tempo poupado é irrelevante e duas execuções perderam ganho.

## 3. Decisão

Decisão explícita: **manter a política conservadora**. O candidato `eager` não confirma poupança sem perda nas famílias reservadas; a ativação exigiria aceitação explícita do proprietário para um compromisso qualidade/tempo. O orçamento de segurança completo mantém-se.

O manifesto versionado `backend/tests/scheduler_lab/w11_calibration_manifest.json` registra a avaliação (`online_evaluation`), o estado `not-activated` e a razão.

## 4. Seguimento

- W12.R3: submeter ao proprietário os horários concretos e o compromisso qualidade/tempo/custo, incluindo esta decisão e a experiência necessária caso se pretenda ativar a paragem antecipada.
