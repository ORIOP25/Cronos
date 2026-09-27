# WBS técnico de correção — W04 e W05

Data: 24-09-2026. Estado: **por implementar; G2 não aceite**.

Autoridade: [plano](SCHEDULER_V1_REVAMP_PLAN.md), [tech spec](SCHEDULER_V1_TECH_SPEC.md) e [WBS principal](SCHEDULER_V1_WBS.md). Fundamentação: [revisão com contraexemplos](SCHEDULER_V1_W04_W05_REVIEW.md). Este documento complementa o WBS principal; não substitui W06–W14 nem o WBS anterior de correção W00–W04.

## 1. Objetivo, responsabilidade e limites

| Pergunta | Resposta |
|---|---|
| O quê? | Corrigir a geração inicial, a prioridade coletiva, as provas e a evidência de teste de W04/W05. |
| Porquê? | Existem soluções inválidas rejeitadas no fim, soluções desnecessariamente tardias e certificação que não corresponde ao problema original. |
| Quem? | O implementador executa TDD e documenta evidência; o revisor verifica os resultados; o proprietário decide a aceitação. Não pressupor nova equipa. |
| Onde? | Branch de revamp, Docker local e laboratório existente. Sem Railway/Cloudflare nesta correção. |
| Quando? | Antes de fechar G2 e de usar esta implementação como base validada de W06. A sequência é determinada pelas dependências abaixo. |
| Como? | Contraexemplo mínimo → teste vermelho de comportamento → correção da causa → testes dirigidos → campanha com artefactos auditáveis → revisão. |

Mantêm-se: um horário em geração de cada vez; paralelismo interno medido separadamente; nenhum p95 imposto agora; minutos exatos; professores atribuídos fixos; crédito parcial apenas na última aula; datas e prioridades já aprovadas. Não acrescentar motores legados, caminhos alternativos de produção ou relaxações silenciosas para obter testes verdes.

Uma solução válida sem prova global pode ser aceitável com qualidade e âmbito honestamente reportados. Uma solução impossível deve ser distinguida de pesquisa inconclusiva e de erro interno. Nenhum teste finito garante ausência absoluta de defeitos; o gate exige evidência concreta e ausência das falhas conhecidas.

## 2. Pacotes e dependências

| Pacote | Entrega | Defeitos | Dependências |
|---|---|---|---|
| R45.00 | Registo de aceitação e regressões mínimas | F01–F11 | Nenhuma |
| R45.01 | Elegibilidade, cronologia e exclusão física corretas | F01–F03 | .00 |
| R45.02 | Contrato anual/detalhe exato e realimentação válida | F07 | .01 |
| R45.03 | Qualidade anual com vetor completo | F04–F05 | .02 |
| R45.04 | Provas, prefixos e limites com âmbito rigoroso | F06, F04 | .02–.03 |
| R45.05 | Métricas coerentes e relatório de margem | F08–F09 | .01; integração final .03–.04 |
| R45.06 | Arquitetura temporal e fronteira da aplicação | F11 | .02–.04 |
| R45.07 | Output revalidável e critérios de laboratório | F10 | .00; integração final .04–.05 |
| R45.08 | Loops adversariais e demonstração anual | F01–F11 | .01–.07 |
| R45.09 | Fecho documentado de W04/W05/G2 | Todos | .08 |

R45.07 pode começar cedo para suportar as experiências. R45.06 deve ser considerada ao desenhar .02/.03, evitando refazer duas vezes o mesmo motor. Entregar fatias pequenas sem marcar como concluídas as integrações ainda pendentes.

## 3. R45.00 — Fixar a baseline de revisão

1. Registar commit, dirty-tree digest, hashes dos ficheiros, imagem Docker, versões Python/OR-Tools e limites de hardware. Preservar o trabalho existente.
2. Acrescentar ao registo W04/W05 que a declaração anterior de conclusão foi contestada por esta revisão. Não apagar a execução histórica verde.
3. Transformar os probes em testes de aceitação do comportamento **esperado**, nos testes de scheduler existentes. Não copiar assertions que validem o bug atual.
4. Guardar uma execução vermelha legível por defeito, incluindo esperado/observado. Manter o oráculo pequeno e a validação independente da formulação CP-SAT.

**Aceitação:** os testes identificam os defeitos desta revisão no código anterior e passam apenas após as respetivas correções. A comparação refere-se à mesma identidade de código; mocks não são apresentados como experiências naturais de performance.

## 4. R45.01 — Correção física e temporal

### R45.01.1 — Normalizar o domínio de períodos

- Canonicalizar e ordenar por instantes cronológicos antes de construir `last`, quotas e projeção. Definir deduplicação ou rejeição de períodos repetidos explicitamente.
- Aplicar a mesma elegibilidade temporal necessária ao precheck, master e detalhe: passado, fronteira protegida, calendário, professor, turma, salas e limites.
- Preservar ocupações protegidas; não as tornar editáveis por terem sido excluídas da procura residual.
- Evitar alterar o validador para aceitar uma proposta que viola as regras.

**TDD:** 90 minutos em dois blocos de 60; entrada normal, inversa e permutada; primeiro dia no passado/protegido; fronteira exata de `now_utc`; alternativa no dia seguinte; ausência de qualquer alternativa.

**Aceitação:** permutations dão a mesma viabilidade e vetor ótimo nas instâncias certificáveis, sem exigir a mesma identidade física em empates. Crédito parcial apenas na última aula cronológica. Casos sem alternativa são comprovadamente impossíveis ou explicitamente inválidos segundo contrato, nunca um falso sucesso.

### R45.01.2 — Excluir conflitos entre aulas da mesma atribuição

- Eliminar o atalho que ignora todos os pares com o mesmo `assignment_id`.
- Excluir todas as escolhas físicas incompatíveis, independentemente da disciplina ser igual ou diferente. Não criar autoconflito de uma variável consigo mesma.
- Usar índices temporais/sweep ou restrições nativas adequadas; não multiplicar comparações de períodos que nunca podem sobrepor-se.

**TDD:** 09:00–10:00 e 09:30–10:30; mesma atribuição e atribuições diferentes; salas iguais/diferentes; períodos contíguos; alternativa no dia seguinte; caso realmente impossível.

**Aceitação:** `same_assignment_overlap` produz COMPLETE válido no dia 1; os casos impossíveis coincidem com o oráculo. Zero candidatos rejeitados por colisão nos casos válidos da campanha dirigida.

## 5. R45.02 — Contrato anual/detalhe e cortes

### R45.02.1 — Materializar exatamente o plano transportado

- Vincular todos os grupos relevantes de quotas, incluindo zeros implícitos, e o grupo final/desperdício de §8.3.
- A representação pode ser esparsa; ausência tem significado único e testado. A assinatura de distribuição inclui todos os parâmetros que condicionam o subproblema.
- Depois de materializar, recalcular as contagens, o crédito final e o desperdício e confrontar com a distribuição vinculada.
- Não usar períodos adicionais fora das quotas para melhorar furos silenciosamente. Uma alteração dessas exige rever o plano, com nova avaliação global.

**TDD:** `detail_ignores_zero_quotas`; durações 45/50/60/90/120; resíduos exatos e parciais; zero procura; última aula noutra semana; quota de grupo inexistente.

**Aceitação:** o detalhe realiza exatamente a distribuição declarada ou reporta resultado coerente. A projeção modular continua independente das identidades físicas das aulas.

### R45.02.2 — Reabrir escolhas e justificar cortes

- Manter no-good da combinação completa como opção inicial simples. Não introduzir cortes generalizados sem necessidade demonstrada.
- Só excluir depois de prova de impossibilidade do subproblema identificado. Incluir condições externas fixadas que participaram nessa prova; invalidar cortes quando o snapshot muda.
- Reabrir semanas e escolhas anteriores necessárias. Timeout/UNKNOWN/interrupção não produzem corte.

**TDD:** T10/T11/T12; duas distribuições com q igual e créditos finais diferentes; conflito de sala criado por escolha anterior reabrível; mock de timeout; alteração de snapshot.

**Aceitação:** para corpus enumerável, nenhuma solução válida é eliminada e nenhum INFEASIBLE contradiz o oráculo. Log identifica a distribuição, condições e prova de cada corte.

## 6. R45.03 — Otimizar a política anual aprovada

### R45.03.1 — Não terminar a qualidade na primeira distribuição viável

- Manter incumbente anual completo avaliado pelo vetor de domínio.
- O master fornece relaxações e propostas; desperdício não pode impedir procurar uma conclusão diária melhor na mesma semana.
- Separar obtenção de viabilidade de melhoria de qualidade. O detalhe condicional não certifica o conjunto de todas as distribuições.
- Usar limites válidos, pesquisa entre distribuições e reabertura temporal para melhorar a solução. Não adicionar uma enumeração cega de todas as distribuições como solução de produção.
- Manter o modelo exato/oráculo pequeno como referência de teste, sem fallback legado na aplicação.

**TDD:** 90 minutos em segunda de 120 ou terça de 90: escolher segunda. Acrescentar um segundo professor/turma concorrente, inverter durações e cruzar semanas para impedir uma correção específica ao exemplo.

### R45.03.2 — Preservar todo o vetor de conclusões

- Remover a mudança de política associada a 6/8 turmas. A comparação global considera todas as turmas, independentemente da formulação escolhida para a pesquisa.
- Nunca aceitar uma melhoria de furos/preferências/salas que piore uma componente superior do vetor global.
- Se uma fase preserva um vetor apenas heuristicamente, declarar o âmbito e não alegar ótimo global. Falta de prova não autoriza descartar a prioridade desse vetor.
- Escolher formulação sequencial, progressiva ou equivalente verificada; não pesos enormes sem prova e limites numéricos.

**TDD:** 1/2/6/7/8/9 turmas; exemplos dos probes; turma já adiantada e turma atrasada a disputar professor; empates; IDs e ordem das atribuições permutados. Para 10/30/45/60 incluir testemunho estritamente melhor que o caso de regressão, mesmo quando enumeração não é viável.

**Aceitação:** vetores ótimos completos iguais ao oráculo no corpus pequeno; todos os probes corrigidos; nenhuma regressão do vetor superior para ganhar estética. W05 não exige prova universal em instâncias grandes, mas exige esta política invariável.

## 7. R45.04 — Evidência matemática honesta

1. Distinguir: solução viável, ótimo do subproblema condicionado, ótimo da relaxação, prefixo global certificado e ótimo global do objetivo completo.
2. Registar condições e unidades: quotas fixas, semanas/dias, objetivo e versão. `EXACT_MODEL` sozinho não basta.
3. Calcular o prefixo certificado **contíguo**. Depois de uma etapa superior não provada, etapas posteriores ótimas sob igualdade herdada não prolongam o prefixo global.
4. Fixar igualdade como prova apenas após prova. Uma fixação heurística permitida por §9.2 deve ser rotulada como tal e não perder essa condição em etapas posteriores.
5. Capturar separadamente valor do incumbente e limite inferior real do master. Não chamar bound ao objetivo de uma solução FEASIBLE. Combinar limites apenas com o mesmo âmbito e unidades; conservar a validade após cortes.
6. Não chamar OPTIMAL ao objetivo de negócio completo se foram omitidas componentes ou restringidas distribuições sem prova suficiente.

**TDD:** sequências controladas OPTIMAL→OPTIMAL, FEASIBLE→OPTIMAL, UNKNOWN, interrupção entre etapas; limite melhorado após corte; master FEASIBLE com incumbente diferente do bound; caso F04.

**Aceitação:** `[false,true]` nunca certifica prefixo global 1; as provas publicadas são verificáveis contra os resultados conhecidos dos casos pequenos. Inconclusivo nunca se converte em impossível por falta de tempo.

## 8. R45.05 — Métricas e significado de recuperabilidade

### R45.05.1 — Uma política de preferências, duas implementações equivalentes

- Formalizar no domínio como contam preferências simultâneas, sobreposições, duplicados e duração parcial. Preservar a prioridade professor antes de objetivos inferiores.
- Derivar coeficientes/modelação da mesma definição, mas recalcular a qualidade do candidato sem ler variáveis CP-SAT.
- Testar igualdade entre cada objetivo otimizado e a componente correspondente do candidato. Incluir furos e salas, não só preferências.

**TDD:** uma aula e preferências de professor+sala, turma+professor, duplicadas e parcialmente sobrepostas; várias durações; duas soluções que ordenem diferentemente quando se soma vs se une penalizações.

**Aceitação:** nunca publicar simultaneamente custo 120 como objetivo e 60 como a mesma métrica; vetor recalculado determina a comparação real das soluções.

### R45.05.2 — Não inferir capacidade a partir de dias livres

- Manter `margin_days` como distância no calendário.
- Substituir o booleano ambíguo por informação explícita: margem existente, análise de capacidade necessária e resultado de cenários de recuperabilidade definidos, com âmbito/estado desconhecido quando não calculados.
- Para concluir W05.4, acrescentar testes de perturbação da geração inicial: retirar blocos futuros e verificar se existe recomposição até à preferência/limite aplicável. Não exigir já estabilidade/ledger de AdaptiveRecovery, que pertencem a W06.
- Capacidade agregada suficiente não prova recuperação. Uma recuperabilidade demonstrada vale para a perturbação e condições testadas, não para qualquer baixa futura.

**TDD:** 20 dias de margem sem disponibilidade; zero margem com alternativas no mesmo dia; margem e capacidade conjunta real; docente/sala únicos; cancelamento que atravessa a preferência.

**Aceitação:** F09 deixa de prometer recuperação; relatório distingue quantidade de dias, capacidade e evidência de recomposição.

## 9. R45.06 — Arquitetura e custos de construção

### R45.06.1 — Alinhar a decomposição temporal

- Implementar o detalhe temporal delimitado e reabrível previsto na tech spec, reutilizando resultados por semana/janela quando válidos.
- Evitar reconstruir a cada ronda o produto anual completo atribuição × período × sala. Indexar sobreposições por componentes temporais e recurso.
- Agrupar salas só quando elegibilidade, disponibilidade e restrições forem realmente equivalentes; matching completo deve atribuir salas concretas e tratar sobreposições reais.
- Preservar restrições entre janelas, professor partilhado, crédito final e comparação anual. A fronteira de uma janela não pode ocultar uma colisão nem fabricar um ótimo global.
- Medir construção separadamente de resolução. Um solver rápido depois de uma construção excessiva não é uma execução rápida.

**Aceitação:** testes metamórficos e contraexemplos anteriores continuam corretos; perfis mostram dimensões reais do modelo por janela e memória/tempo de construção. Não aceitar a fixture de cinco dias como demonstração anual. Não se impõe um orçamento p95 de produto nesta tarefa.

### R45.06.2 — Inverter a dependência da aplicação

- Retirar os imports de implementações de `infrastructure` de `application/generation.py`.
- Colocar a composição concreta na fronteira apropriada; injetar a operação de pesquisa através de uma assinatura pequena e explícita. Não adicionar contentor DI, classes vazias ou factories de uma implementação.
- Separar cálculo puro de procura/resultado das escolhas de OR-Tools.

**TDD/aceitação:** teste arquitetural de dependências e teste da aplicação com resultado de pesquisa controlado; domínio/aplicação importáveis sem inicializar o solver; geração integrada mantém o comportamento.

## 10. R45.07 — Artefactos e critérios de aprovação do laboratório

### R45.07.1 — Guardar o resultado que se está a aprovar

Por execução, guardar no formato JSON existente, versionado:

- Snapshot normalizado e períodos, com identidade matemática separada do testemunho e das seeds do solver.
- Candidato completo: aulas, períodos/UTC, docente/turma/sala, minutos, slices modulares e referências protegidas.
- Relatório integral do validador e vetor completo de qualidade recalculado, incluindo conclusão por turma.
- Etapas, valores, estado de prova, prefixos, âmbitos, limites, condições/cortes e motivo de paragem.
- Comando, código, versões, hardware/limites Docker, seeds e número de workers internos.
- Tempo total e fases, CPU, pico RAM e dimensões do modelo; ausência de medição deve ser explícita.

**Aceitação:** um comando revalida um candidato guardado sem correr o solver, confirma crédito/salas/cronologia/qualidade e falha se o candidato for adulterado. Resultados incompletos não são aprovados só por terem `VALID` no JSON.

### R45.07.2 — Avaliar qualidade, não apenas outcome

- Declarar expectativas por caso: viabilidade, violações esperadas, vetor ótimo quando conhecido, propriedades metamórficas e âmbito de prova permitido.
- Comparar candidatos pequenos com oráculo; casos grandes com testemunhos, limites e regressões de qualidade explicitamente definidas.
- Separar testes de validade de testes de qualidade: COMPLETE válido mas pior que um ótimo conhecido faz falhar o teste de qualidade.
- Manter o teste de erro/inconclusivo distinguível de impossibilidade provada; uma campanha deve conservar os outputs por caso, incluindo falhas.
- Corrigir a diversidade: seed de fixture altera topologia, procura, calendários e/ou restrições do problema. Seed do solver mede variância de pesquisa; seed do testemunho não conta como novo problema.

**Aceitação:** os casos F04/F05 fariam falhar a campanha anterior; inputs iguais são identificados como repetições, sem inflacionar cobertura.

## 11. R45.08 — Loops de validação e demonstração anual

### Protocolo por loop

1. Executar X e guardar candidato, métricas e diagnóstico.
2. Verificar contra oráculo/testemunho/expectativa **antes** de mudar cenário.
3. Alterar uma dimensão para Y; explicar diferenças e procurar regressões.
4. Alterar outra dimensão para Z, incluindo fronteira impossível ou adversarial.
5. Se falhar, reduzir a instância, fixar regressão vermelha, corrigir a causa e repetir X/Y/Z.
6. Só depois aumentar escala ou combinar dimensões. Não ajustar expectativas para acomodar a saída atual.

| Loop | X → Y → Z | Observação obrigatória |
|---|---|---|
| L01 — Crédito/ordem | 90 em 2×60 → permutar períodos → várias durações/módulos | Mesma viabilidade/qualidade, crédito exato e parcial final |
| L02 — Colisões | Períodos disjuntos → sobrepostos com alternativa → sem alternativa | COMPLETE/INFEASIBLE conforme oráculo; nenhum FAILED indevido |
| L03 — Fronteira temporal | Primeiro bloco livre → passado/protegido → todo o futuro protegido | Preservação do contrato e diagnóstico correto |
| L04 — Quotas/qualidade | 120 cedo vs 90 tarde → concorrência de professor → outra semana/crédito final | Conclusão prevalece; quotas realizadas; cortes válidos |
| L05 — Vetor coletivo | 2/6 turmas → 7/8/9 → 10/30/45/60 | Todas as conclusões avaliadas antes de preferências |
| L06 — Espaço/procura | Poucas horas/muito espaço → muitas/pouco → poucas/pouco | Interseção efetiva de recursos, não soma abstrata de minutos |
| L07 — Recursos | Docentes/salas abundantes → gargalo partilhado → falta estrutural | Sala concreta, docente atribuído, prova necessária e alternativas |
| L08 — Soft/métricas | Uma preferência → várias coincidentes → alternativas de durações distintas | Métrica recalculada igual à otimizada e ordenação correta |
| L09 — Provas | Ótimo pequeno → FEASIBLE controlado → timeout/UNKNOWN | Prefixos/âmbitos honestos; nunca corte por timeout |
| L10 — Margem | Dias com capacidade → dias sem capacidade → retirar único bloco viável | Margem não implica recuperabilidade |
| L11 — Horizonte | Semana curta → período letivo → ano setembro–junho | Calendário completo, múltiplas disciplinas/módulos e custos de construção |
| L12 — Metamórfico | IDs/ordem originais → renomear/permutar → adicionar opção elegível | Ótimo certificado não piora pela expansão de opções; prova distingue resultados heurísticos |

Não impor monotonicidade do resultado heurístico de duas execuções com tempo limitado como se fosse um teorema do solver. Nos casos enumeráveis comparar ótimos; nos grandes registar e analisar a regressão observada face ao incumbente/testemunho conhecido.

### Corpus mínimo de fecho desta correção

- Todos os probes desta revisão convertidos em regressões de comportamento.
- Campanha atual preservada e reforçada, sem apagar os seis impossíveis esperados.
- Corpus pequeno determinístico cruzando durações, recursos, ordens, fronteiras e 1–9 turmas, com enumeração dentro do orçamento do oráculo. Excesso de orçamento é inconclusivo para o oráculo, não prova de impossibilidade.
- Instâncias anuais de **10/30/45/60 turmas**, com **pelo menos três seeds de problema diferentes por dimensão**: uma família folgada, uma com professor partilhado crítico e uma com salas/interseções escassas. O relatório demonstra que os snapshots diferem.
- Cada turma anual tem múltiplas disciplinas e módulos, procura distribuída no ano, calendário e indisponibilidades concretas. Publicar os totais reais; não reduzir a procura a quatro horas por turma para cumprir a etiqueta anual.
- Construir testemunhos válidos para positivos e variantes impossíveis demonstráveis; acrescentar topologias independentes do método de construção dos testemunhos. Rever datas de fim e carga real antes de correr a campanha pesada.
- Correr primeiro com um worker interno, de forma sequencial. Comparar 1/2/4/8 numa seleção representativa, conforme capacidade local, com três seeds de solver por configuração suportada; fixar quotas CPU/RAM e guardar qualidade vs custo. Não fazer várias gerações concorrentes para simular esse paralelismo.
- Configurações que o hardware local não suporta ficam explicitamente não medidas; não extrapolar vencedores. A seleção final de hardware/paragem e a campanha extensa continuam em W07/W11.

Os números acima são tamanhos de amostra de teste, não SLOs. Limites de segurança laboratoriais devem ser declarados. Atingi-los produz estado honesto e trabalho pendente; não prova uma duração de produção aceitável. Se as instâncias anuais só terminarem em erro/inconclusivo, G2 não está demonstrado.

## 12. R45.09 — Gate final e passagem ao plano principal

Para fechar a correção:

1. F01–F09 corrigidos, com regressões e comparação independente. Nenhum caso conhecido com testemunho válido falha pelo modelo.
2. Nenhuma divergência do vetor ótimo completo no corpus enumerável; nenhum objetivo inferior troca uma prioridade superior.
3. Quotas, crédito final, cortes e evidência descrevem o mesmo problema; prefixos e bounds corretos nas interrupções controladas.
4. Campanha atual e corpus anual produzem artefactos completos, revalidáveis e resultados explicados. Lista explícita de cenários corridos/não corridos, sem os misturar.
5. Executar os testes dirigidos após cada correção; no fecho, unitários backend, integração/contratos pertinentes, testes do runner se alterado e Ruff. Guardar comandos, exits e identidade do código final.
6. Atualizar `SCHEDULER_V1_W04_W05_STATUS.md` por subitem, com ligações à nova evidência. Preservar este relatório como histórico; não declarar a revisão antiga inválida por os bugs já estarem corrigidos.
7. Revisor executa novamente contraexemplos e uma amostra anual, verifica o output materializado e decide G2. Entregar também limitações reais ainda abertas, sem chamar otimização futura a desvios de política.

**Não antecipar:** AdaptiveRecovery completo e seus loops longitudinais (W06), controlador final qualidade/tempo (W07), fila/persistência/publicação (W08), UI (W09), restante migração e qualificação/produção do WBS principal. A correção deve preparar uma base confiável para essas etapas, sem afirmar que elas já foram validadas.

**Pacote a entregar ao implementador:** este WBS, a revisão, os probes/outputs e a tech spec/WBS principais. A ordem das prioridades e os contratos de produto mantêm-se; o implementador escolhe a solução técnica mais pequena que cumpra os critérios, não a que apenas faça desaparecer os exemplos.
