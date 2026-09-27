# W06–W07 — revisão independente e WBS de correção

Data: 25 de setembro de 2026. Branch: `codex/scheduler-v1-revamp`.

Referências: [plano v2](SCHEDULER_V1_REVAMP_PLAN_V2.md), [WBS v2](SCHEDULER_V1_WBS_V2.md), [especificação v2](SCHEDULER_V1_TECH_SPEC_V2.md) e [registo as-built](SCHEDULER_V1_W06_W07_STATUS.md).

## Decisão

**Não aceitar o gate G3 no estado atual.** Há contraexemplos em que uma reparação completa piora o horário publicado válido. Há também perdas de identidade, diagnósticos incorretos e falhas no controlo de paragem.

Esta revisão analisa W06/W07. A fila, a aprovação e os replays anuais continuam nos pacotes W08–W12. O fecho desses pacotes não substitui as correções abaixo.

## Evidência reproduzida

Os 502 testes unitários de scheduler passaram nesta revisão (`pytest -q tests/unit -k scheduler`). Passaram também 47 testes dirigidos de recuperação, paragem e diagnóstico. Os contraexemplos abaixo usaram os modelos reais e `repair_published_schedule`, sem alterar o código.

| ID | Cenário e resultado observado | Impacto |
| :--- | :--- | :--- |
| E01 | Uma turma tem uma aula de 60 minutos em 22/09, antes da preferência. O baseline válido tem vetor progressivo `(1,)` e custo de perturbação `0`. A reparação devolve 21/09, vetor `(27,)`, custo `27`, com `PROPOSALS_EXHAUSTED`. | O produto troca uma solução válida por outra estritamente pior, segundo a sua própria política. |
| E02 | Duas turmas partilham duas salas. Cada uma tem uma aula protegida e uma aula futura. O baseline passa `validate_candidate` e tem perturbação `0`. A reparação troca ambas as salas para reduzir continuidade; devolve perturbação `6`. | O matching de salas pode piorar a prioridade adaptativa. Uma estabilização aula a aula não desfaz a troca simultânea. |
| E03 | Uma indisponibilidade obriga a mover uma aula de 21/09 para 22/09. A proposta tem `source_lesson_id=None`. A alteração é contabilizada como `REMOVED(15) + INSERTED(12)`, em vez de `MOVED(10)`. | Perde-se a identidade publicada e o custo usado nas decisões fica errado. |
| E04 | Um baseline de duas aulas de 60 minutos inclui uma aula protegida. O residual editável é 60 minutos. `assess_baseline` declara 60 minutos de excesso. | Um horário publicado correto é diagnosticado como obsoleto. |
| E05 | Duas aulas do mesmo professor sobrepõem-se. `assess_baseline.valid=True`, mas `validate_candidate.valid=False` por `RESOURCE_CONFLICT`. | Um baseline fisicamente inválido pode ser apresentado como válido. |
| E06 | Numa execução completa, o tempo de parede foi cerca de `0,047 s`; o orçamento registou cerca de `0,094 s`. A fase `FINALIZATION` recebeu o tempo desde o início da execução. | O orçamento soma duas vezes construção e pesquisa; a avaliação posterior fica fora da conta. |
| E07 | O cancelamento tornou-se verdadeiro entre a resposta da pesquisa e a finalização. `repair_schedule` devolveu `COMPLETE` com proposta. | A corrida de cancelamento não é respeitada na fronteira de finalização. |
| E08 | `ExecutionBudget(float("inf"))` e `ExecutionBudget(float("nan"))` são aceites. | O limite de segurança não é garantidamente finito. |

## Causas localizadas

| Evidência | Código a rever |
| :--- | :--- |
| E01 | `infrastructure/annual_model.py:391-395`, `infrastructure/placement_model.py:841-869`, `infrastructure/search.py:259-318` |
| E02 | `infrastructure/placement_model.py:977-1077`, `infrastructure/search.py:127-188` |
| E03 | `infrastructure/placement_model.py:200-260`, `domain/recovery.py:303-330`, `composition.py:39-52` |
| E04–E05 | `domain/recovery.py:125-176`, `domain/candidate_validation.py:471-489` e `:559-583` |
| E06–E07 | `application/recovery.py:124-240` |
| E08 | `domain/stop.py:38-59` |
| Paragem e cobertura | `infrastructure/search.py:319-329`, `domain/stop.py:114-210`, `tests/unit/test_scheduler_recovery_solver_v1.py:172-203` |

## WBS de correção

Prioridade P0 bloqueia decisões de qualidade e integridade. Prioridade P1 bloqueia o gate G3. Escrever primeiro o teste que reproduz cada falha. Corrigir a menor causa comum e voltar a executar o teste.

| ID | Prioridade | Dependência | Trabalho e correção | Critério de aceitação |
| :--- | :--- | :--- | :--- | :--- |
| R67.01 | P0 | — | Alinhar master, detalhe e poda com `AdaptiveQualityVector`. Usar o baseline validado como incumbente inicial. Retirar qualquer poda por semana sem limite inferior seguro para o vetor adaptativo. Procurar também distribuições de semanas posteriores quando puderem reduzir perturbação sem gerar excesso. | E01 passa. Toda reparação de baseline válido é igual ou melhor pelo vetor completo. Um oráculo enumerativo confirma ótimos em casos pequenos, na mesma semana e entre semanas. |
| R67.02 | P0 | R67.01 | Fazer o matching global de salas respeitar o vetor adaptativo. Incluir o custo face à sala publicada e permitir trocas coordenadas. Aceitar um refinamento apenas se melhorar estritamente o vetor completo. | E02 passa. Duas ou mais aulas podem trocar salas conjuntamente. Continuidade e preferências só decidem quando as prioridades superiores empatam. |
| R67.03 | P0 | — | Unificar a origem do baseline: o argumento da API deve alimentar a associação de identidades no solver. Associar aulas mantidas ou movidas à ocorrência publicada correta. Distinguir movimentos de remoções e inserções reais. | E03 passa. `source_lesson_id` mantém-se em movimentos. Cada transformação é contada uma vez; o custo coincide com um oráculo de correspondência em casos pequenos. |
| R67.04 | P1 | R67.03 | Avaliar cobertura editável sem voltar a contar aulas protegidas. Reutilizar as verificações de conflito, cronologia, currículo, duplicados e proteção aplicáveis ao baseline, mantendo o diagnóstico de falta/excesso. | E04 e E05 passam. Um baseline completo só é `valid` quando também satisfaz o validador independente. Baselines incompletos conservam diagnósticos específicos. |
| R67.05 | P1 | — | Corrigir a contabilidade por deltas monotónicos de fase. Medir validação, qualidade, resumo e serialização antes de fechar o orçamento. Rejeitar limites não finitos. Preparar a mesma medição para persistência em W08. | E06 e E08 passam. A soma das fases aproxima o tempo real sem dupla contagem. Uma finalização lenta marca excesso e retira certificados indevidos; `inf` e `nan` falham na entrada. |
| R67.06 | P1 | R67.05 | Consultar cancelamento antes da finalização e antes de entregar uma proposta. Em W08, condicionar a persistência e a promoção ao mesmo estado de cancelamento e versão. | E07 devolve `CANCELLED`, sem proposta. Uma corrida durante validação, serialização ou persistência não cria proposta publicável. |
| R67.07 | P1 | R67.01 | Basear a trajetória de paragem no **incumbente adaptativo completo**, não na data máxima de cada candidato. Exigir exploração mínima após a primeira solução e cobrir objetivos superiores, conflitos e bairros relevantes. Tratar famílias sem calibração conservadoramente. | Um único primeiro candidato não produz `LOW_EXPECTED_RETURN`. Ganhos em excesso, perturbação ou segunda conclusão são reconhecidos mesmo com a data máxima igual. O replay C19 mede ganho perdido pelo vetor completo. |
| R67.08 | P1 | R67.01–R67.07 | Ampliar a bateria W06/W07 com oráculos e cenários escolares variados. Corrigir o gerador aleatório atual: os seis seeds só variam indisponibilidade de turma; usam professor `2`, mas os docentes são `7` e `8`. Nenhum seed testa sala. | Incluir urgência, reincidência, dívida, créditos parciais, professores e salas escassos, turma adiantada a ceder capacidade, meta ultrapassada, hard end, semanas distantes, aulas protegidas e cancelamento. Comparar o vetor completo com oráculos pequenos. |
| R67.09 | P1 | R67.08 | Executar campanhas combinadas C02–C15, C16 e C19, incluindo mutações múltiplas e casos reservados. Medir qualidade e tempo com limites reais antes de calibrar parâmetros em W11. | G3 tem relatório por cenário, contraprova ou certificado com âmbito correto, qualidade face ao baseline e análise dos ganhos perdidos. Casos inconclusivos ficam identificados. |

## Ordem e gates

1. Corrigir R67.01–R67.03. Bloquear propostas que piorem um baseline válido enquanto a correção não estiver demonstrada.
2. Corrigir R67.04–R67.07 com testes vermelho-primeiro e verificação independente.
3. Executar R67.08–R67.09. Usar dados de calibração separados dos casos reservados.
4. Reexecutar regressões W04/W05 e W06/W07, lint e campanhas. Só então reconsiderar G3 e atualizar o registo as-built.

**Condição mínima de aceitação:** cada contraexemplo E01–E08 tem regressão permanente; nenhum resultado `COMPLETE` piora um baseline válido; identidades, diagnósticos, orçamento e cancelamento concordam com o estado observado.

## Estado da correção (25 de setembro de 2026)

R67.01–R67.09 concluídos com os testes E01–E08 vermelho-primeiro, bateria de oráculo alargada e campanhas combinadas. Evidência e decisão do gate em [SCHEDULER_V1_W06_W07_G3_REPORT.md](SCHEDULER_V1_W06_W07_G3_REPORT.md) e registo atualizado em [SCHEDULER_V1_W06_W07_STATUS.md](SCHEDULER_V1_W06_W07_STATUS.md). G3 reconsiderado como aceite no âmbito corrigido, com os limites declarados no relatório.
