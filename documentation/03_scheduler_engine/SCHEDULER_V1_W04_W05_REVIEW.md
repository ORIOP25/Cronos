# Revisão independente — Scheduler v1, W04 e W05

Data: 24-09-2026. Branch: `codex/scheduler-v1-revamp`.
Base: `facd1d93bead7fc6ed481de6761644afd2e0be81`, incluindo alterações locais não commitadas.

**Conclusão: não aceitar o fecho de W04/W05 nem o gate G2.** Existe implementação útil e os testes existentes passam, mas foram reproduzidos erros de geração, desvios à prioridade das conclusões e certificação enganadora. As correções propostas estão no [WBS de correção](SCHEDULER_V1_W04_W05_CORRECTION_WBS.md).

## 1. Âmbito e evidência

Foram confrontados o plano, a tech spec (§§8–10, 16), W04/W05 do WBS, o registo de implementação, os modelos, a aplicação, o validador, o oráculo, os testes e os artefactos do laboratório. Esta revisão não recertifica toda a correção anterior W00–W03, nem funcionalidades futuras W06–W11.

| Verificação executada nesta revisão | Resultado |
|---|---|
| `node scripts/test.mjs fast --scope backend` | **591 passed**, 55,01 s de pytest; exit 0 |
| Campanha `generation_manifest.json`, modo generator, limite experimental 30 s | **26 casos: 20 VALID, 6 INFEASIBLE**, exit 0 |
| Contraexemplos adicionais em Docker sem rede | Falhas reproduzidas descritas abaixo; resultados completos guardados |

Artefactos desta execução:

- Unitários: `.test-artifacts/1790283295243-35876/backend-unit.xml`.
- Campanha: `.test-artifacts/1790283605216-3808/scheduler-lab/`; [cópia do relatório](review_evidence/2026-09-24-w04-w05/campaign_report.json).
- [Script dos contraexemplos](review_evidence/2026-09-24-w04-w05/probes.py), [resultados completos](review_evidence/2026-09-24-w04-w05/probes.json) e [manifesto de fontes/evidência](review_evidence/2026-09-24-w04-w05/source_manifest.json).

Os 321 testes de integração e 47 contratos constam da execução do implementador. **Não foram reexecutados nesta revisão**: os defeitos aqui isolados pertencem ao modelo, domínio e laboratório, sem alterações de persistência. Não foram alterados código de produção, testes existentes, volumes de dados, Railway ou Cloudflare.

Os probes são experiências diagnósticas: exit 0 significa que a experiência terminou, não que os comportamentos observados sejam aceitáveis. Os casos pequenos são comparados com enumeração e validação independente; a injeção de estado do solver é explicitamente identificada.

## 2. Defeitos reproduzidos

### F01 — P1 — Colisões dentro da mesma atribuição provocam FAILED

`placement_model.py:271` e `:284` ignoram pares quando `assignment_a == assignment_b`. Duas aulas da mesma disciplina/turma/professor também não podem sobrepor-se.

Probe `same_assignment_overlap`: procura de 120 minutos; segunda 09:00–10:00 e 09:30–10:30; terça 09:00–10:00. O modelo escolhe as duas aulas sobrepostas de segunda, declara conclusão ótima no dia 0 e o validador recusa colisões de turma, professor e sala. A aplicação devolve **FAILED**. O oráculo encontra solução válida concluída na terça.

O validador protege a aceitação do horário, mas não corrige o modelo nem procura a alternativa existente. Falha W04.4/W04.5.

### F02 — P1 — A ordem do input altera a validade do crédito parcial

`placement_model.py:217` define a última aula pela posição na lista `eligible`, sem ordenar cronologicamente. A materialização ordena depois, tornando visível a inconsistência.

Probes `period_order_sorted` / `period_order_reversed`: mesmos dois períodos de 60 minutos e procura de 90. Ordem cronológica dá **COMPLETE**; ordem inversa dá **FAILED / PARTIAL_CREDIT_VIOLATION**. Em ambos o oráculo encontra a mesma conclusão válida. Falha W04.5; não é aceitável depender da ordem acidental de leitura.

### F03 — P1 — Elegibilidade não respeita todo o contrato temporal

`capacity.py:105` filtra limites, feriados, disponibilidade e aulas fixas, mas não `protected_dates` nem `now_utc`.

Probes `protected_date` e `past_period`: dois dias com uma aula possível em cada; o primeiro está protegido ou já terminou. O modelo escolhe o primeiro, o validador rejeita e a aplicação devolve **FAILED**. Existe solução válida no segundo dia. A API de domínio aceita estes snapshots; se houver uma precondição que os exclua de CompleteGeneration, ela não está implementada. A preservação do passado já é requisito, independentemente de AdaptiveRecovery.

### F04 — P1 — O master sacrifica uma conclusão mais cedo e a pesquisa termina aí

`annual_model.py:219–238` minimiza a semana final e depois desperdício. `search.py:152` retorna na primeira distribuição realizável. Otimizar o detalhe condicionado por essa distribuição não otimiza o problema anual original.

Probe `annual_waste_delays_completion`: faltam 90 minutos; há segunda 09:00–11:00 e terça 09:00–10:30, na mesma semana. Segunda permite crédito final de 90 minutos num bloco físico de 120, válido pelas regras. O master prefere desperdício zero na terça. Resultado: **COMPLETE, dia 1, EXACT_MODEL/OPTIMAL**. Oráculo e detalhe sem quotas encontram **dia 0**.

Não se exige uma prova global em todos os problemas reais. Exige-se que desperdício não substitua a prioridade de concluir cedo e que uma prova condicionada não seja apresentada como global. Falha W05.1/W05.3.

### F05 — P1 — A prioridade coletiva é truncada já com sete turmas

`placement_model.py:58` limita a seis etapas de conclusão; `:518` elimina os níveis seguintes ao primeiro quando há mais de oito turmas. Depois otimiza furos e preferências.

Probes `completion_tail_7_classes` e `completion_tail_9_classes`: todas as turmas menos uma só podem terminar terça; a restante pode terminar segunda, mas prefere não ter essa aula. O gerador termina **todas na terça** para evitar a preferência. O oráculo mantém as restantes datas e termina essa turma segunda.

Vetores observados / ótimos:

- 7 turmas: `(1,1,1,1,1,1,1)` / `(1,1,1,1,1,1,0)`.
- 9 turmas: `(1,1,1,1,1,1,1,1,1)` / `(1,1,1,1,1,1,1,1,0)`.

Isto altera a política de produto, não apenas a qualidade da prova. A limitação documentada não autoriza trocar prioridades obrigatórias. Adiar esta correção para W11 não fecha W05.

### F06 — P1 — Prefixos e limites não representam corretamente a prova

`placement_model.py:628` fixa a igualdade também após **FEASIBLE**. `:626` conta etapas ótimas isoladas, em vez do prefixo contíguo certificado. `SearchEvidence` valida apenas o comprimento, não a consistência do prefixo.

Probe `controlled_unproven_prefix`: uma injeção controlada mantém soluções reais, mas devolve FEASIBLE na primeira etapa. A etapa seguinte é OPTIMAL condicionada à primeira. A evidência guarda `[false,true]` e **certified_stages=1**; o prefixo global certificado deveria ter comprimento **0**. Não se apresenta esta injeção como um timeout natural observado.

Além disso, `search.py:128` chama `relaxation_bound` ao `plan.latest_week`, que é o valor de uma solução do master. Quando a etapa não é ótima, esse valor não é necessariamente um limite inferior. Não é capturado o bound efetivo do solver. A semana da relaxação e o dia do detalhe também exigem unidades/âmbitos distintos. F04 demonstra concretamente a ambiguidade de `EXACT_MODEL` com quotas fixadas.

### F07 — P1 — O detalhe não concretiza exatamente a distribuição anual

`QuotaDistribution` transporta apenas contagens positivas; não transporta `f/u`. `placement_model.py:243` só impõe os grupos presentes, deixando os restantes livres. A tech spec §8.3 exige vincular quotas, grupo final, crédito parcial e cronologia.

Probe `detail_ignores_zero_quotas`: o master fornece uma aula de 60 minutos para a atribuição 1 e uma de 90 para a atribuição 2. O detalhe acrescenta **mais uma aula de 60 minutos na atribuição 2**, e reduz o crédito da aula de 90 para 30, para eliminar um furo do professor. O candidato é válido, mas a distribuição física e o desperdício diferem do que foi fornecido.

Esta experiência não demonstra por si só um falso INFEASIBLE: um detalhe mais permissivo pode continuar a fornecer cortes seguros quando prova impossibilidade. Demonstra a quebra do contrato usado para descrever a decomposição e as suas provas. É preciso definir exatamente o subproblema e alinhar quotas, cortes e evidência.

### F08 — P2 — O objetivo de preferências difere da métrica publicada

`placement_model.py:177` soma penalizações por indisponibilidade soft aplicável; `quality.py:165` usa `any` e contabiliza a duração uma única vez por aula.

Probe `preference_metric_disagreement`: aula de 60 minutos com preferência de professor e de sala. Etapa otimizada/certificada: **120**; qualidade recalculada: **60**. O laboratório não permite comparar de forma coerente a função otimizada e a qualidade anunciada. É necessária uma definição de domínio única e implementação independente mas equivalente no modelo.

### F09 — P2 — Margem de calendário é apresentada como recuperabilidade

`generation.py:56` define `recoverable = margin_days > 0`, sem analisar capacidade.

Probe `margin_without_recovery_capacity`: conclusão imediata, **20 dias de margem, recoverable=true**, mas todos os períodos posteriores são indisponíveis para o professor. Cancelar a única aula possível torna o problema comprovadamente impossível. Ter dias restantes não garante que exista um único bloco recuperável.

W05.4 deve distinguir margem, capacidade necessária e recuperabilidade demonstrada para um cenário definido. Não é possível prometer resistência a ocorrências arbitrárias.

## 3. Qualidade da evidência e arquitetura

### F10 — P1 para o gate — A campanha não sustenta as conclusões anuais

Os 20 VALID e 6 INFEASIBLE foram reproduzidos; não há motivo para contestar esses resultados nos inputs executados. O problema é o alcance:

- As fixtures de escala têm **cinco dias, 20 períodos, uma disciplina de quatro horas por turma, um módulo e uma sala dedicada por turma**. Para 60 turmas: 60 atribuições, 15 professores, 60 salas e 240 aulas. Não são 60 turmas durante um ano letivo.
- Nesta execução, o caso de 60 turmas mediu **6,207 s** no temporizador atual; isto não prevê o tempo de uma escola real nem estabelece p95.
- `scale.py:68` aplica a seed à posição do testemunho. O probe `scale_seed_diversity` confirma que seeds 1 e 2 produzem **snapshots e períodos iguais**, embora testemunhos diferentes. Variar a seed não garante diversidade do problema.
- `gen-c01-clean` e `gen-c01-partial` têm o mesmo `input_digest`. Existem 26 execuções, não 26 inputs distintos por esse identificador.
- Os JSON exportam métricas agregadas, mas não o candidato materializado, o vetor completo de conclusões, todas as etapas/provas ou o relatório integral de validação. Não permitem revalidar autonomamente o horário entregue.
- `wall_time_ms` deriva do temporizador da pesquisa, não de toda a operação incluindo pré-validação, materialização final/validação e relatório. Não mede CPU/RAM.

São bons smoke tests e regressões dirigidas; não demonstram o gate G2 de qualidade coletiva e geração anual. As campanhas longitudinais de recuperação continuam a pertencer a W06/W11, não são exigidas artificialmente nesta revisão.

### F11 — P2 — A decomposição e as dependências ainda divergem da arquitetura escolhida

`placement_model._build_state` cria variáveis para todos os períodos elegíveis do horizonte e escolhas de salas concretas. `_add_conflicts` percorre pares por recurso, inclusive entre dias diferentes, antes de verificar sobreposição. Não existe detalhe delimitado por semanas com resultados reutilizados; cada ronda reconstrói o detalhe anual inteiro. A campanha curta não mede este custo anual. Isto é observação estrutural, **não uma medição de falha/OOM em escola real**.

A tech spec prevê detalhe temporal reabrível e equivalência de salas quando válida. A implementação atual mantém o produto atribuição × período × sala elegível e comparações quadráticas por recurso; precisa de demonstração anual e alinhamento arquitetural antes de ser apresentada como a decomposição concluída.

`application/generation.py:16–17` importa diretamente implementação de capacidade e pesquisa de `infrastructure`. A aplicação deve depender do contrato de domínio e receber a operação concreta na composição. Basta uma fronteira pequena; não é necessário um framework de injeção.

## 4. O que está bem e o que deve mudar no estado de aceitação

Há separação de dados de domínio, projeção de módulos, validação independente, disponibilidade conjunta com salas, preferência soft distinta de proibição e realimentação que não corta simplesmente por timeout. Os contraexemplos de colisão e parcialidade mostram precisamente o valor do validador.

Contudo, detetar um horário inválido no fim não cumpre a geração correta quando existe alternativa, e um teste VALID não verifica a política de qualidade. Aumentar o número de testes sem alterar os critérios de observação não resolve estas lacunas.

Reabrir W04.1–W04.5 nos pontos identificados e W05.1–W05.4. Preservar a evidência anterior como registo histórico; acrescentar a revisão e o estado **não aceite**. Corrigir, executar os loops do WBS de correção e só então decidir o fecho de G2 e a continuação dependente para W06. Não alterar a tech spec para legitimar o truncamento das prioridades.
