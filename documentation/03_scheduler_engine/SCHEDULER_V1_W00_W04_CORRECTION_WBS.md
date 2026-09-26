# WBS de correção e fecho — Scheduler v1 até W04

Data: 24 de setembro de 2026.
Origem: [revisão independente](SCHEDULER_V1_W00_W04_REVIEW.md).
Autoridade de produto: [plano](SCHEDULER_V1_REVAMP_PLAN.md) e [tech spec](SCHEDULER_V1_TECH_SPEC.md).
Este documento complementa o [WBS principal](SCHEDULER_V1_WBS.md); não o substitui.

## 1. Resultado exigido

Corrigir as falhas reproduzidas e tornar demonstráveis os fundamentos de W00–W03.
Implementar e validar W04, que ainda não foi iniciado no estado revisto.
Só depois continuar para W05 e seguintes.

Não alterar prioridades escolares para acomodar a implementação atual.
Não executar produção, publicar, fazer merge ou limpar desenvolvimento como parte automática desta correção.
Todos os ensaios seguintes são locais, em Docker e bases temporárias verificadas.

Responsável técnico: implementador.
Responsável pela aceitação funcional: proprietário.
Estado inicial de todos os itens: por iniciar.
Não há estimativas temporais nem p95 fixos neste WBS.

## 2. Ordem e dependências

| Pacote | Tipo | Corrige/fecha | Depende de |
| :--- | :--- | :--- | :--- |
| RC00 | Proveniência | Limites W00 e evidência de revisão | Leitura dos documentos |
| RC01 | Correção de contratos | F02, F03, F05 | RC00 |
| RC02 | Correção do validador | F01–F03 | RC01 |
| RC03 | Correção do oráculo | F04 | RC02 |
| RC04 | Correção do laboratório | F06–F08 | RC00; integração com RC02–RC03 |
| RC05 | Fecho curricular persistido | L01–L02 | RC01–RC02 |
| RC06 | Fecho estrutural e laboratório W04 | L03–L05 | RC03–RC05 |
| RC07 | Implementação normal W04 | W04.1–W04.5 ainda ausentes | Gate A |
| RC08 | Aceitação até W04 | Regressões e campanhas | RC07 |

Ordem recomendada: RC00 → RC01 → RC02 → RC03 → RC04 → RC05 → RC06 → Gate A → RC07 → RC08.
Não transformar a correção num novo framework de validação ou num segundo motor selecionável.

## 3. RC00 — Fixar o ponto de partida

| ID | Trabalho | Entrega e critério de fecho |
| :--- | :--- | :--- |
| RC00.1 | Preservar estado revisto e hashes dos ficheiros. | Evidência identifica alterações tracked e untracked, imagem e configuração. |
| RC00.2 | Reclassificar estados W00–W04 nos registos de trabalho. | W04 não iniciado; W01–W03 sem aceitação integral; lacunas não desaparecem do inventário. |
| RC00.3 | Preparar execução local e confirmar alvos de teste. | doctor/runner operacionais; nenhuma credencial ou destino cloud usado nos ensaios. |
| RC00.4 | Converter probes R01–R12 em testes das expectativas corretas. | Testes falham pelo defeito esperado antes da alteração; não conservar o assert diagnóstico invertido. |

Não reduzir asserções dos testes novos para manter a suite verde.
Quando o contrato ainda não suporta a regra, criar primeiro o teste de aceitação do novo contrato.
Evitar copiar detalhes internos do algoritmo para o oráculo esperado.

## 4. RC01 — Contratos completos e realmente imutáveis

| ID | Trabalho | Critério de aceitação |
| :--- | :--- | :--- |
| RC01.1 | Representar estratégia, períodos elegíveis, timezone e instante de referência. | É possível distinguir geração inicial de recuperação e verificar períodos reais. |
| RC01.2 | Representar indisponibilidades por intervalos e recursos relevantes. | Sobreposição parcial é verificável; salas e turmas não ficam sem restrições representáveis. |
| RC01.3 | Separar baseline física, execução e projeção curricular. | Comparação de proteção não depende de `slices` futuras; docente histórico não deriva de atribuição mutada. |
| RC01.4 | Representar janela editável para novas aulas e alterações. | Inserção protegida é rejeitada mesmo com novo ID; N=0 preserva passado/início. |
| RC01.5 | Copiar e imobilizar estruturas internas. | Mutar o input original não altera snapshot, digest, procura ou resultado. |
| RC01.6 | Validar IDs, unicidade e coerência dos valores. | Duplicados, tipos inválidos e período UTC/local incoerente falham na fronteira. |
| RC01.7 | Representar pertença de dívida e reservas à atribuição/versão. | Validador consegue distinguir reserva válida de referência apenas coincidente na escola. |

Usar dataclasses/tuplos e funcionalidades nativas.
Não acrescentar abstrações para formatos de snapshot ainda inexistentes.

Loop: snapshot válido → mutação por alias → período inválido → ID duplicado → snapshot válido reconstruído.
Analisar se o erro pertence ao input ou ao candidato; não os misturar nos relatórios.

## 5. RC02 — Validador independente

| ID | Trabalho | Teste vermelho e resultado exigido |
| :--- | :--- | :--- |
| RC02.1 | Verificar módulos pela cronologia das aulas. | R01: M2 antes de M1 é rejeitado; cruzamento 75+75/50 continua válido. |
| RC02.2 | Verificar preenchimento curricular dos períodos editáveis. | R12: primeira aula parcialmente creditada sem justificação é rejeitada. |
| RC02.3 | Verificar grelha e limites por estratégia. | R03/R04: período externo e inicial além da preferência rejeitados. |
| RC02.4 | Verificar sobreposição com indisponibilidades. | R02 rejeitado; contacto apenas na fronteira semiaberta permitido. |
| RC02.5 | Comparar proteção por campos físicos. | R05 passa; mudança de sala, período, professor ou crédito protegido falha. |
| RC02.6 | Verificar inserções e fronteira em toda a proposta. | Nova aula dentro da janela falha; projeção modular atualizada passa. |
| RC02.7 | Recalcular reservas e correspondências. | Rejeitar outra atribuição, duplicação, excesso e versão errada. |
| RC02.8 | Recalcular métricas básicas necessárias a W04. | Totais e conclusões independentes; não confiar em métricas declaradas pelo candidato. |

RC02.8 não antecipa a otimização de W05/W06.
Preparar métricas de furos a partir da grelha; calibrar objetivos e perturbação continua nas fases previstas.
Se uma métrica ainda não existe, declarar indisponível; nunca preencher com zero fictício.

Loop curricular: correto → módulos trocados → parcela sobreposta → crédito não final parcial → correto com aula protegida parcial legítima.
Loop temporal: grelha válida → madrugada fora da grelha → indisponibilidade parcial → fronteira adjacente válida → data além do limite.
Loop estabilidade: físico fixo → apenas módulo muda → sala muda → inserção nova proibida → avanço de data.

Após cada passo, verificar o código específico e os totais, além de `valid`.
Manter o validador independente do modelo matemático e da função que constrói a projeção.

## 6. RC03 — Oráculo fiável e limitado desde o início

| ID | Trabalho | Critério de aceitação |
| :--- | :--- | :--- |
| RC03.1 | Descontar créditos protegidos da procura a enumerar. | R06 retorna o testemunho completo; aulas protegidas não são duplicadas. |
| RC03.2 | Considerar ocupações fixas e regras do snapshot corrigido. | Professor/sala fixos impedem colisões; limites iniciais corretos. |
| RC03.3 | Limitar enumeração durante construção e combinação. | Instância demasiado grande termina com limite explícito, nunca `INFEASIBLE`. |
| RC03.4 | Especificar o alcance do ótimo. | Só certificar componentes exaustivamente enumeradas; documentação e resultado indicam o âmbito. |
| RC03.5 | Comparar com soluções mínimas conhecidas manualmente. | Oráculo não depende apenas de validar o próprio output para justificar a verdade do caso. |

Loop: zero crédito protegido → metade protegida → toda a procura protegida → procura excedida → caso fora do orçamento.
Adicionar salas equivalentes progressivamente para verificar que a proteção de recursos atua antes de materializar todos os subconjuntos.
Usar limite de laboratório pequeno no teste; não provocar consumo descontrolado para provar a falha.

## 7. RC04 — Resultados experimentais confiáveis

| ID | Trabalho | Teste e critério de aceitação |
| :--- | :--- | :--- |
| RC04.1 | Chave de retoma com proveniência validada. | R08: mudar cenário, versão, código, política ou configuração impede reutilização silenciosa. |
| RC04.2 | Validar manifesto e seleção. | R09: ID inexistente, IDs duplicados, seleção vazia acidental e caminhos inválidos produzem erro explícito. |
| RC04.3 | Separar input inválido, candidato corrompido e pesquisa inconclusiva. | R10: input válido declarado inválido falha; inconclusivo não satisfaz expectativa obrigatória. |
| RC04.4 | Exigir códigos esperados de corrupção. | Mutação detectada pelo motivo errado não é evidência de cobertura dessa regra. |
| RC04.5 | Persistir falhas por caso e escrever resultados atomicamente. | Exceção gera `ERROR`; ficheiro truncado não é reutilizado; casos restantes seguem política declarada. |
| RC04.6 | Comparar relatórios equivalentes por expectativa. | R11: deixar de rejeitar corrupção é regressão; digest/política incompatíveis são assinalados. |
| RC04.7 | Verificar cobertura contra a seleção aprovada. | Casos omitidos/duplicados/erros e métricas ausentes ficam visíveis; cobertura não é sinónimo de sucesso. |

Chave de retoma: caso e versão, digest de inputs, versão do schema, identidade do código, imagem, seeds e configuração relevante.
Não usar apenas o nome do ficheiro ou HEAD num working tree modificado.
Separar digest matemático de identidade da execução e do testemunho/resultado.

Loop retoma: executar → repetir igual → mudar 60 para 120 minutos → mudar commit/árvore → truncar resultado → recuperar corretamente.
Loop seleção: todos os casos → subconjunto explícito → ID errado → caso omitido → expectativa impossível contradita por testemunho.
Loop comparação: igual → erro novo → corrupção deixa de ser detetada → inputs diferentes → métrica desaparece.

Preservar outputs anteriores; não sobrescrever uma campanha com nova configuração sem identidade nova.

## 8. RC05 — Completar a base curricular persistida

| ID | Trabalho | Critério de aceitação em PostgreSQL |
| :--- | :--- | :--- |
| RC05.1 | Compensações retroativas e projeção efetiva auditável. | Sequência A50/B50/reversãoA25/novo25 sem sobreposição curricular efetiva. |
| RC05.2 | Reservas ativas, liquidação e reversão na mesma transação. | Reservado nunca excede dívida aberta após sumário ou acerto. |
| RC05.3 | Cancelamento de recuperação e revisão de dívida. | Libertar reserva sem criar dívida duplicada; replay não altera saldo. |
| RC05.4 | Configuração anual com início/preferência/limite. | Ordem das datas validada; preferência persiste e integra o snapshot. |
| RC05.5 | Comandos de configuração com lock e revisões. | Alteração semântica incrementa revisões; no-op não; rollback preserva estado. |
| RC05.6 | Relações entre atribuição, módulo, dívida, aula e versão. | Referências erradas dentro da mesma escola são rejeitadas; isolamento entre escolas permanece. |
| RC05.7 | Consistência física e destino das constraints de colisão. | Duração corresponde ao intervalo; teste demonstra mecanismo que impede publicação incoerente. |

Para RC05.7, definir e testar a fronteira transacional/constraint necessária sem implementar todo o fluxo HTTP de aprovação W08.
Não declarar a publicação completa entregue nesta fase.

Loop PostgreSQL: executar → reservar → acerto positivo → reversão retroativa → cancelar recuperação → repetir comandos → tentar concorrência.
Verificar saldos, intervalos, origem, revisões e rollback depois de cada operação.
Dividir a atual sequência longa de integração em exemplos focados com helpers pequenos, preservando um percurso integrado.

## 9. RC06 — Fechar infraestrutura de prova antes de W04

| ID | Trabalho | Critério de aceitação |
| :--- | :--- | :--- |
| RC06.1 | Ensaiar reset e instalação vazia local. | Alvos nomeados, rejeição de alvo errado e repetição sem dependência de dados anteriores. |
| RC06.2 | Resolver o caminho administrativo das tabelas append-only. | Apagamento autorizado testado; runtime normal continua sem DELETE de evidência. |
| RC06.3 | Fixar plano executável de consolidação Alembic. | Não marcar baseline final pronta enquanto depender do histórico; checkpoint obrigatório antes de P11. |
| RC06.4 | Fixtures grandes com testemunhos independentes da enumeração mínima. | Construção de 10/30/45/60 turmas não chama o oráculo exponencial. |
| RC06.5 | Identificar modo de campanha: validador, oráculo ou gerador. | Validar uma fixture nunca aparece como resultado de CompleteGeneration. |
| RC06.6 | Medição e diversidade real. | Registar fases/CPU/RAM; seeds de fixture/eventos usadas ou explicitamente não aplicáveis. |
| RC06.7 | Rever documentação e evidência de W00–W03. | Afirmações de conclusão/óptimo/imutabilidade correspondem ao contrato efetivamente testado. |

RC06.3 admite a migração transitória durante a construção da branch, conforme o registo W02.
Essa tolerância não fecha a baseline final nem autoriza levar compatibilidade antiga a produção.
Se consolidar já for seguro no schema disponível, executar; caso contrário manter responsável, checkpoint e teste explícitos.

Não fabricar geração aleatória só para consumir seeds.
Fixtures estáticas podem ter seed não aplicável; diversidade deve resultar de topologias e transformações reais.

## 10. Gate A — Autorização técnica para construir W04 sobre estes fundamentos

Este gate é verificação de evidência, não uma nova aprovação para cada tarefa.
O implementador pode avançar quando os critérios estiverem demonstrados.

- F01–F08 corrigidos, com regressões das expectativas corretas.
- R01–R12 deixam de reproduzir as discrepâncias; casos positivos equivalentes continuam válidos.
- Oráculo limitado durante toda a enumeração e correto com crédito protegido.
- Laboratório rejeita evidência antiga, seleção vazia e expectativas não satisfeitas.
- RC05 concluído nas regras que alimentam snapshots, procura e validação.
- Instalação/reset local demonstrados; pendência final Alembic explicitamente rastreada, se ainda aplicável.
- Suites relevantes, integração e contratos verdes; outputs vinculados à mesma revisão.
- Fixtures de W04 classificadas por testemunho, prova ou desconhecimento antes do solve.

Não exigir frontend final, fila final ou AdaptiveRecovery para este gate.
Não declarar W00–W03 integralmente encerrados se restarem itens do respetivo WBS.

## 11. RC07 — Implementar W04, sem o apresentar como correção já feita

| ID | Correspondência | Trabalho e prova |
| :--- | :--- | :--- |
| RC07.1 | W04.1 | Compilar atribuições e elegibilidade; docente fixo, disponibilidade conjunta, preferências soft e carga densa. |
| RC07.2 | W04.2 | Planeamento anual por duração e crédito final; distinguir capacidade agregada de viabilidade detalhada. |
| RC07.3 | W04.3 | Colocação detalhada revisível; conflitos demonstrados realimentam quotas; timeout nunca cria corte de impossibilidade. |
| RC07.4 | W04.4 | Matching de salas reais; lotação, equipamento, reservas e sobreposição física. |
| RC07.5 | W04.5 | Materializar o ano completo, projetar módulos e executar validador corrigido. |
| RC07.6 | Integração W03/W04 | Runner executa o novo gerador sobre fixtures; testemunho permanece apenas como oráculo. |

Manter a implementação no domínio/aplicação/infraestrutura previstos.
Nenhum fallback para o solver antigo pode produzir um resultado atribuído a W04.
O ótimo de qualidade completa e a calibração avançada continuam em W05 e seguintes.
W04 deve demonstrar cobertura completa, validade e procura exata, com resultados de pesquisa honestos.

## 12. RC08 — Loops de aceitação até W04

Executar, analisar e guardar evidência após cada seta.
As campanhas C referidas pertencem ao WBS principal; aqui usa-se a fatia de geração inicial e validação aplicável a W04.
Não considerar recuperações anuais ou UI concluídas por executar estes loops.

| Loop | Sequência de ambientes | Verificação |
| :--- | :--- | :--- |
| A — Currículo | Limpo → 75+75/50 → períodos mistos → residual parcial → toda procura cumprida. | Minutos, ordem modular e ausência de aulas inventadas. |
| B — Espaço | Pouca procura/muito espaço → muita/muito → pouca/pouco → muita/pouco. | Cobertura e interseção real; não contar apenas buracos da turma. |
| C — Docentes | Independentes → professor partilhado → disponibilidade reduzida → docente extra não atribuído → reatribuição explícita. | Capacidade real e ausência de distribuição automática de serviço. |
| D — Salas | Suficientes → retirar salas → laboratório único → retirar elegibilidade → repor sala → salas redundantes. | Matching concreto, conflito explicado e custo de simetria. |
| E — Datas | Horizonte amplo → perto da preferência → limite preferencial exato → só caberia depois da preferência. | Inicial rejeita extensão silenciosa; unknown distinto de impossível. |
| F — Agregação | Totais suficientes → disponibilidades desencontradas → quota alternativa → semana anterior reaberta. | Corte correto, sem congelamento que elimina testemunho válido. |
| G — Escala | Microcaso enumerado → 10 → 30 → 45 → 60 turmas. | Validade, memória, tempo por fase e resultado completo nas fixtures obrigatórias. |
| H — Evidência | Execução normal → interrupção → retoma igual → input alterado → repetição corrigida. | Nenhum resultado antigo ou incompleto contado como sucesso novo. |

Em B–D, aproximar a fronteira retirando uma unidade relevante de capacidade.
Quando possível, criar um caso impossível com prova independente e depois restaurar a capacidade.
Não inferir a fronteira apenas de uma execução sem solução.

Não multiplicar todos os microcasos por todas as configurações de workers.
Usar um worker como controlo e um ensaio multithread para detetar pressupostos de determinismo.
A comparação extensa 1/2/4/8 e seleção de produção permanece em W11.

Para cada falha:

```text
preservar caso/output → reduzir → teste vermelho → corrigir causa
→ repetir caso → repetir vizinhos da matriz → reexecutar campanha afetada
```

Fecho de RC08:

- Casos viáveis obrigatórios produzem candidatos completos e válidos.
- Casos impossíveis demonstrados não são classificados por mero timeout.
- Outputs do gerador e do validador têm identidade e métricas reproduzíveis.
- Nenhum corte inválido, consumo duplicado ou violação de regra foi observado nos casos obrigatórios.
- Cobertura inclui C01–C08 e C10 na fatia W04, conforme o WBS principal.
- Limitações de hardware ou casos não concluídos permanecem explícitos e bloqueiam a respetiva aceitação.

## 13. Verificação final e entrega ao próximo implementador

Executar o conjunto mais estreito durante a correção.
No fecho, executar unitários backend, testes do runner, integração completa relevante, contratos, lint/format e auditorias de base de dados.
Repetir instalação vazia e roundtrip conforme a baseline adotada.
Não alterar ficheiros de produção só para eliminar warnings fora do âmbito.

Comandos existentes de referência:

```text
node --test scripts/test.test.mjs
node scripts/test.mjs fast --scope backend
node scripts/test.mjs integration -- -k scheduler_v1
node scripts/test.mjs integration
node scripts/test.mjs campaign --manifest <manifesto-versionado> --out <diretório-novo>
```

Acrescentar os novos testes ao runner existente; não criar um runner paralelo.
Depois de modificar código relevante, associar evidência à nova revisão, não ao relatório de 24 de setembro.
Qualquer push continua sujeito ao acompanhamento de CI e à fronteira de deployments definida no plano.

Entregar um relatório de fecho com:

1. F01–F08 e L01–L05 ligados às correções e testes.
2. Itens RC concluídos, pendentes e respetiva razão.
3. Revisão, imagem, schema, configuração e manifests usados.
4. Matriz W04 executada, resultados inconclusivos e limites conhecidos.
5. Estado atualizado dos pacotes originais, sem antecipar W05–W14.

O plano principal continua em W05 apenas quando W04 tiver evidência própria de aceitação.
