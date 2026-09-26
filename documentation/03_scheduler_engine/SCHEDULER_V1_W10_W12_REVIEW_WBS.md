# WBS de correção — revisão independente de W10–W12

Data: 26 de setembro de 2026. Branch analisada: `codex/scheduler-v1-revamp`.

## Decisão

**Não aprovar ainda o gate local de W12 nem iniciar W13.** A evidência atual não demonstra qualidade suficiente para uso escolar.

A revisão encontrou erros no próprio laboratório e uma integração operacional incompleta. Também encontrou critérios obrigatórios sem evidência conclusiva.

Esta conclusão não invalida os resultados verdes já obtidos. Limita o que esses resultados conseguem demonstrar.

## Âmbito e verificação

Foram confrontados o [plano v2](SCHEDULER_V1_REVAMP_PLAN_V2.md), o [WBS v2](SCHEDULER_V1_WBS_V2.md), a [especificação v2](SCHEDULER_V1_TECH_SPEC_V2.md) e os [registos W10–W11](SCHEDULER_V1_W10_W11_STATUS.md) e [W12](SCHEDULER_V1_W12_STATUS.md).

Foram inspecionados manifestos, relatórios em `.test-artifacts`, código do gerador, laboratório, publicação e consumidores escolares. Passaram 35 testes unitários focados no Docker existente.

Sondas adicionais reproduziram os defeitos F01–F03 e F05. Não foi repetida a suite completa de 687/295/47 testes nesta revisão.

## Problemas identificados

| ID | Prioridade | Problema e evidência | Consequência |
| :--- | :--- | :--- | :--- |
| F01 | P0 | `lab/longitudinal.py:142–145,204` declara conclusão quando o último avanço do relógio consome todas as aulas. `_conservation_problems` aceita candidato ausente. Sonda: `event_count=1`, `step_days=400` → `completed=True`, `conserved=True`, `steps=0`, `final_candidate=None`. | `campaign.py:607–609` classifica como `VALID` um replay sem evento aplicado nem proposta final. |
| F02 | P0 | `lab/recovery.py:113–121` coloca a baixa docente nos primeiros dias de todos os períodos. O replay já avançou o relógio (`lab/longitudinal.py:135–148`). Sonda com relógio em 5/10: 12 indisponibilidades em 21–22/9, zero interseções com 768 aulas futuras. | As cinco baixas docentes dos replays W10/W12 não exercitam essa perturbação no horizonte editável. |
| F03 | P0 | `lab/campaign.py:803–810,932–940` trata `ERROR` de `EXPLORATORY_UNKNOWN` como sucesso. `lab/matrix.py:284–299` conta resultados por ID, independentemente do resultado. Sonda: `case_passes` devolve `True` para `ERROR`. | Uma campanha pode sair com código zero e matriz completa apesar de erros reais. |
| F04 | P0 | `services/timesheet_service.py:53–75,103–131` consulta só `ActiveScheduleBlock` e `LessonLog`. A publicação v1 grava `SchedulerLessonV1`; o mapa v1 usa `SchedulerLessonLogV1`. A UI continua a chamar `/timesheets/me/{week}/submit`. | Numa instalação limpa com horário v1, a submissão semanal responde “Sem aulas planeadas nesta semana”. Os contadores de timesheet omitem aulas v1. |
| F05 | P1 | `lab/reports.py:156–190` regista diferenças métricas, mas `ReportComparison.clean` ignora-as (`:78–87`). Sonda: `objective_days` de 5 para 50 mantém `clean=True`. | Uma candidate válida, mas muito pior, atravessa a comparação de regressões sem bloquear o gate. |
| F06 | P1 | A matriz W10 tem cinco eixos e 14 reparações pequenas, cada uma com duas atribuições e 3–5 períodos. Os replays anuais têm 2–3 eventos. Não provam as interações obrigatórias do WBS §8. | Faltam provas integradas para procura de 50h, crédito parcial, módulos cruzados, substituição, correções retroativas, aprovação atrasada e falha de worker combinada. |
| F07 | P1 | W11 comparou uma fixture de 10 turmas duas vezes e outra de 30 turmas uma vez, sempre com seed 1. Não mediu reparação, 45/60 turmas, quotas reais ou RSS nativo. `baseline.py:40–60` escolhe workers por contagem válida e mediana, sem custo CPU ou qualidade por família. | `candidate_workers=4` é apenas uma hipótese local. No caso de 30 turmas, quatro workers foram mais lentos e consumiram mais CPU que um. |
| F08 | P1 | A calibração W11 tem trajetórias de um ponto, `chosen=null` e nenhuma avaliação online reservada. O próprio dossier W12 marca o critério 7 bloqueado. | Os parâmetros da política adaptativa e da paragem não satisfazem a especificação §17.4 e §18. |
| F09 | P1 | W12.3 exige E2E local verde; o dossier declara Playwright com Clerk por executar. W12.4 exige candidate congelada no mesmo commit; os relatórios usam rótulos `worktree-w12`/`w12`, com alterações não committed. O caso reservado 03 influenciou uma correção. | O gate de ponta a ponta não está cumprido e a avaliação reservada deixou de ser uma validação independente da candidate final. |
| F10 | P2 | `lab/campaign.py:855–870` executa o caso antes de consultar `--resume`. Em reparação, a proveniência usa `input_digest=None` (`:738–745`). | Retoma consome o custo integral e pode reutilizar resultados antigos se a fixture mudar com o mesmo rótulo de código. |

As provas do oráculo em microcasos e a validação independente de candidatos são boas bases. Os defeitos acima estão na seleção, execução e interpretação das campanhas.

## Pacotes de correção

| Pacote | Dependência | Entrega mínima | Critério de fecho |
| :--- | :--- | :--- | :--- |
| R10.1 — Replay honesto | Nenhuma | Escrever testes vermelhos para F01 e F02. Aplicar eventos apenas a aulas futuras afetadas. Registar evento sem efeito como tal. Exigir exatamente `event_count` passos aplicados, candidato final válido e conservação por módulo. | O caso de 400 dias falha como incompleto. Cada baixa ensaiada intersecta aulas futuras do docente pretendido. Replays W10/W12 repetidos com evidência por passo. |
| R10.2 — Runner que falha fechado | R10.1 | Corrigir F03. `ERROR`, `INVALID`, `OMITTED` e `INCONCLUSIVE` bloqueiam campanhas obrigatórias, mesmo com expectativa exploratória. Separar cobertura executada de cobertura concluída. | Testes com erro, timeout e omissão impedem código zero e `complete=True`. Relatórios apresentam contagens por resultado e oráculo. |
| R10.3 — Variedade e qualidade | R10.2 | Completar níveis isolados, pares e interações do WBS §8. Construir testemunhos independentes para casos viáveis. Incluir casos onde a solução fácil bloqueia semanas finais. | Manifesto aprovado cobre todos os níveis obrigatórios e exclusões justificadas. Oráculos pequenos confirmam ótimo; casos grandes comparam vetores, margem e estabilidade por família. |
| R10.4 — Regressões de qualidade | R10.3 | Corrigir F05 com comparação lexicográfica do vetor de produto e tolerâncias explícitas por família. Preservar diferenças métricas no relatório. | Uma candidate válida com conclusão pior, menos margem ou mais perturbação relevante não obtém `clean=True` sem decisão explícita. |
| R11.1 — Benchmark representativo | R10.3 | Repetir workers 1/2/4/8 em geração e reparação. Incluir 10/30/45/60 turmas, várias seeds, casos difíceis, quotas CPU/RAM e pico RSS. Guardar falhas e censura. | Relatório por família mostra validade, vetor, tempo, CPU, RSS e incerteza. A escolha de workers usa custo e qualidade, não só mediana global. |
| R11.2 — Política de pesquisa | R10.3, R11.1 | Produzir trajetórias longas com melhoria precoce, estagnação e melhoria tardia. Avaliar candidatos offline e depois online em famílias reservadas. | Política, limites de segurança e reserva de finalização explícitos. Se a evidência continuar inconclusiva, manter o gate bloqueado e documentar a experiência necessária. |
| R12.1 — Timesheet v1 | Nenhuma | Criar integração falhada após publicação v1. Adaptar submissão, contadores e revisão semanal para `SchedulerLessonV1` e `SchedulerLessonLogV1`, sem dupla contagem com legado. | Docente submete semana v1 concluída; aulas pendentes/futuras impedem submissão; administração vê contagens corretas. Isolamento por organização e ano permanece testado. |
| R12.2 — Percurso escolar | R12.1 | Executar E2E Docker com adaptador local de autenticação ou Clerk funcional. Cobrir configurar, gerar, aprovar, registar aula e falta, reparar e submeter timesheet. | E2E verde, incluindo refresh, duplo clique, sessão sem permissão, aprovação stale e resposta atrasada. Evidência da UI concorda com a ledger v1. |
| R12.3 — Candidate e reserva novas | R10.1–R12.2 | Congelar commit, digests de fixture e política. Criar casos reservados novos após as correções. Corrigir `--resume` e a proveniência de reparação. | Repetição no mesmo commit produz resultados comparáveis. Holdout novo passa sem ajuste posterior da candidate. Qualquer nova correção exige novo holdout. |

## Ordem e gate

1. Fechar F01–F04 antes de confiar em qualquer relatório W10–W12.
2. Repetir as campanhas afetadas e comparar resultados completos, não apenas resultados válidos.
3. Fechar F05–F09 antes de aceitar W12. F10 entra antes da repetição ampla com `--resume`.
4. Reexecutar os checks de projeto, incluindo integração PostgreSQL, contratos, frontend e E2E.
5. Rever horários concretos com o proprietário. Só depois decidir a passagem para W13.

O gate exige zero violações de integridade e isolamento. Exige também qualidade demonstrada por cenário, sem compensar uma escola falhada com médias favoráveis.
