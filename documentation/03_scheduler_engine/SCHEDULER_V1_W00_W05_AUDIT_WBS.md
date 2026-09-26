# WBS de correções e aceitação após revisão W00–W05

Data: 25 de setembro de 2026.
Referência: [plano desta revisão](SCHEDULER_V1_W00_W05_AUDIT_PLAN.md).
Âmbito: consolidar o trabalho existente antes de iniciar W06.

## 1. Regras de execução

- Manter Ponytail full, Clean Code, Clean Architecture e TDD.
- Escrever o teste vermelho antes de cada correção não trivial.
- Inspecionar chamadores e invariantes antes de editar.
- Executar apenas Docker local e bases temporárias para testes transacionais.
- Preservar dados de desenvolvimento e todas as alterações anteriores do proprietário.
- Não fazer push sem resolver a pendência existente de configurações externas de auto-deploy.
- Depois de qualquer push autorizado, acompanhar CI até passar.
- Se ocorrer alteração frontend, reconstruir ou atualizar o respetivo container.
- Não iniciar W06 como forma de contornar defeitos de W00–W05.

**P1** bloqueia confiança, integridade ou aceitação. **P2** exige correção de qualidade, medição ou âmbito.
Os responsáveis abaixo identificam funções, não agentes adicionais ou trabalho delegado.

## 2. Correções já realizadas nesta revisão

A01–A12 estão implementadas localmente, com 16 regressões adicionadas.
Não repetir essas implementações; rever os diffs e concluir a verificação na baseline final.
A12 está corrigida para uma janela. O refinamento entre janelas pertence a R55.04.

| Estado | Entrega | Verificação restante |
| :--- | :--- | :--- |
| Implementado localmente | Cortes completos e limite inferior anual. | R55.00 e R55.03. |
| Implementado localmente | Sobreposições de salas e preferência contada uma vez. | R55.00 e R55.04. |
| Implementado localmente | Procura zero e recursos de aulas novas. | R55.00 e R55.01. |
| Implementado localmente | Cache interrompida, certificados e furos protegidos. | R55.00 e R55.03. |
| Implementado localmente | Minutos estritos, coleções imutáveis e timezone. | R55.00 e R55.01. |
| Implementado localmente | Continuidade conjunta numa janela. | R55.00, R55.03 e R55.04. |

## 3. Dependências

```text
R55.00 Fixar baseline
  -> R55.01 Inputs e R55.02 Identidades
  -> R55.03 Evidência e R55.04 Salas
  -> R55.05 Orçamento
  -> R55.06 Oráculos e R55.07 Corpus
  -> R55.08 Campanhas
  -> R55.09 Revisão de arquitetura e checks
  -> R55.10 Dossier e novo G2
```

A preparação das fixtures pode decorrer antes de terminar todas as correções.
As medições comparativas devem usar código fixo e identificar cada revisão.

## 4. Pacotes de trabalho

### R55.00 — Fixar e verificar a baseline da revisão

Prioridade: P1. Dependências: nenhuma. Responsável: implementação e revisão técnica.

| ID | Trabalho | Critério de aceitação |
| :--- | :--- | :--- |
| R55.00.1 | Inventariar alterações anteriores e alterações desta revisão. | Nenhuma alteração do proprietário é descartada ou atribuída incorretamente. |
| R55.00.2 | Guardar hashes de fontes, testes, manifests e imagem. | A identidade inclui ficheiros não commitados e reproduz o estado executado. |
| R55.00.3 | Formatar e rever os diffs das correções A01–A12. | Ruff limpo nos ficheiros alterados; nenhuma abstração sem necessidade. |
| R55.00.4 | Executar novamente unitários após a última correção A12. | Suite completa verde, incluindo as 16 novas regressões. |
| R55.00.5 | Encerrar e classificar campanhas já iniciadas. | Separar resultados anteriores e posteriores à correção final. |

### R55.01 — Fechar validação dos inputs

Prioridade: P1. Dependência: R55.00. Responsável: domínio/aplicação.

| ID | Trabalho | Critério de aceitação |
| :--- | :--- | :--- |
| R55.01.1 | Reproduzir execução para atribuição desconhecida. | `{99: {1: 60}}` nunca desaparece silenciosamente num COMPLETE. |
| R55.01.2 | Rejeitar créditos negativos, módulos desconhecidos e excesso por módulo. | Rejeição ocorre antes de construir o modelo. |
| R55.01.3 | Validar referências de dívida, reservas e aulas protegidas. | Todos os IDs pertencem ao snapshot e conservam as relações exigidas. |
| R55.01.4 | Auditar `Period` construído diretamente. | Instantes incoerentes ou durações inválidas são rejeitados explicitamente. |
| R55.01.5 | Unificar o resultado de input inválido na fronteira adequada. | Não há exceção tardia de projeção nem conversão para INFEASIBLE. |
| R55.01.6 | Verificar conservação modular com aulas protegidas intercaladas. | Projeção respeita cronologia e não reescreve execução. |

Reutilizar validações existentes. Não duplicar o validador completo dentro dos construtores.
Não alargar este pacote à implementação do motor adaptativo.

### R55.02 — Gerar identidades sem colisões

Prioridade: P1. Dependência: R55.00. Responsável: materialização.

| ID | Trabalho | Critério de aceitação |
| :--- | :--- | :--- |
| R55.02.1 | Adicionar regressão com aula protegida 1000001 e atribuição 1. | O caso viável deixa de falhar com DUPLICATE_IDENTITY. |
| R55.02.2 | Escolher IDs novos fora do conjunto protegido e já usado. | Nenhuma colisão entre atribuições, aulas novas ou protegidas. |
| R55.02.3 | Preservar referências das parcelas e identidades publicadas. | Validador confirma cobertura, referências e proteção. |
| R55.02.4 | Aplicar a mesma garantia ao oráculo quando necessário. | O oráculo não rejeita testemunhos por identidades artificiais. |

Usar um alocador local simples. Não adicionar persistência ou um serviço de IDs.

### R55.03 — Tornar evidência e reutilização honestas

Prioridade: P1. Dependências: R55.00, R55.01. Responsável: infraestrutura do solver.

| ID | Trabalho | Critério de aceitação |
| :--- | :--- | :--- |
| R55.03.1 | Testar interrupções antes e depois de cada tipo de objetivo. | Nenhum prefixo atravessa uma etapa omitida ou não provada. |
| R55.03.2 | Testar FEASIBLE numa janela seguido de SAFETY_LIMIT noutra. | O motivo agregado preserva a interrupção e o âmbito correto. |
| R55.03.3 | Verificar bounds após cortes de inviabilidade e exclusões de exploração. | Cada limite identifica o espaço sobre o qual foi calculado. |
| R55.03.4 | Rever cache com e sem otimização conjunta de salas. | Reutilização conserva o subproblema e a qualidade declarada. |
| R55.03.5 | Separar prova temporal, quotas e matching de posições fixas. | Um ótimo condicionado nunca aparece como ótimo global. |
| R55.03.6 | Testar o pós-passo sob retorno FEASIBLE ou UNKNOWN. | O melhor candidato conhecido nunca piora nem se perde. |

A política conservadora atual pode retirar todo o prefixo após interrupção.
Recuperar prefixos mais precisos só quando existir prova e necessidade concreta.

### R55.04 — Melhorar continuidade de salas entre janelas

Prioridade: P2. Dependências: R55.02, R55.03. Responsável: pesquisa temporal e matching.

| ID | Trabalho | Critério de aceitação |
| :--- | :--- | :--- |
| R55.04.1 | Estender A12 a duas ou mais semanas. | Enumerar uma alternativa com melhor sala e prioridades superiores iguais. |
| R55.04.2 | Conservar matching global com conflitos físicos corretos. | Intervalos sobrepostos, adjacentes e salas protegidas passam nos testes. |
| R55.04.3 | Reabrir apenas posições relevantes para mudanças de sala evitáveis. | O contraexemplo melhora sem degradar conclusões, furos ou preferências. |
| R55.04.4 | Preservar o incumbente sob orçamento curto. | A otimização opcional não transforma COMPLETE em falha ou pior qualidade. |
| R55.04.5 | Comparar custo e benefício nas famílias com alternativas de sala. | Relatório mostra validade, qualidade, CPU e duração. |

Não construir um modelo anual monolítico por defeito.
Começar pelo menor refinamento que resolve os contraexemplos e mantém a decomposição.
Se o ótimo global continuar desconhecido, publicar esse limite sem certificado artificial.

### R55.05 — Corrigir orçamento e contabilidade temporal

Prioridade: P2. Dependências: R55.03–R55.04. Responsável: aplicação/infraestrutura.

| ID | Trabalho | Critério de aceitação |
| :--- | :--- | :--- |
| R55.05.1 | Medir construção e ambos os solves do master. | O tempo do master não corresponde apenas ao último solve. |
| R55.05.2 | Propagar deadline absoluto entre fases. | Construção consome o orçamento disponível para as fases seguintes. |
| R55.05.3 | Clarificar o orçamento da avaliação de recuperabilidade. | O relatório não oculta um segundo cálculo completo. |
| R55.05.4 | Testar interrupção durante construção e finalização. | O resultado e a censura são honestos; o incumbente válido é preservado. |
| R55.05.5 | Separar limite experimental de tempo total observado. | Nunca declarar 108 ou 125 segundos como execução dentro de 100 segundos totais. |

Não introduzir metas de p95. O supervisor de processo e cancelamento operacional permanecem em W07–W08.

### R55.06 — Alargar o oráculo ao vetor completo

Prioridade: P1 de aceitação. Dependências: R55.01–R55.04. Responsável: testes de domínio e laboratório.

| ID | Trabalho | Critério de aceitação |
| :--- | :--- | :--- |
| R55.06.1 | Reutilizar candidatos enumerados para comparar os cinco componentes. | Conclusões, furos docentes, furos das turmas, preferências e salas são verificados. |
| R55.06.2 | Incorporar casos dirigidos e seeds fixas em regressões permanentes. | A12 não depende de uma ordem favorável do solver. |
| R55.06.3 | Variar procura por atribuição e durações por período. | Casos cruzam módulos e usam crédito parcial final. |
| R55.06.4 | Testar permutações de entidades e de períodos. | Viabilidade e ótimo exato permanecem iguais. |
| R55.06.5 | Separar propriedade matemática de rendimento sob timeout. | Um insucesso limitado nunca se torna prova de impossibilidade. |

Manter o limite finito da enumeração. Não usar o oráculo exponencial nas instâncias anuais.

### R55.07 — Construir corpus anual representativo

Prioridade: P1 de aceitação. Dependências: R55.00; critérios de R55.06. Responsável: laboratório.

| ID | Trabalho | Critério de aceitação |
| :--- | :--- | :--- |
| R55.07.1 | Acrescentar grafos conectados de docentes e turmas. | Aumentar turmas aumenta o componente de conflito, não apenas grupos independentes. |
| R55.07.2 | Variar docentes por disciplina e partilha transversal. | Uma turma não fica sempre ligada a um único professor. |
| R55.07.3 | Acrescentar conjuntos de salas parcialmente sobrepostos. | Existem alternativas e gargalos de equipamento, lotação ou reservas. |
| R55.07.4 | Variar calendário, durações, carga e indisponibilidade conjunta. | Incluir capacidade exata, quase saturação e excesso mínimo demonstrado. |
| R55.07.5 | Criar testemunhos independentes e versões impossíveis mínimas. | A expectativa existe antes de executar o gerador. |
| R55.07.6 | Separar desenvolvimento e avaliação reservada por topologia. | Casos usados para corrigir deixam de contar como avaliação reservada. |
| R55.07.7 | Medir conectividade, alternativas e pressão por recurso. | O relatório explica dificuldade além do número de turmas. |

Preservar as famílias de 10/30/45/60 turmas existentes.
Começar pequeno para reduzir falhas; ampliar depois aos quatro tamanhos previstos.
Não exigir um produto cartesiano integral de todas as variáveis.

### R55.08 — Executar campanhas e revalidar artefactos

Prioridade: P1 de aceitação. Dependências: R55.05–R55.07. Responsável: laboratório/revisão.

| ID | Trabalho | Critério de aceitação |
| :--- | :--- | :--- |
| R55.08.1 | Repetir campanhas curta e anual na baseline final. | Todos os casos obrigatórios têm resultado e classificação. |
| R55.08.2 | Executar baseline, mutação, pressão e recuperação por família. | Cada transição tem análise de causa e resultado. |
| R55.08.3 | Revalidar candidatos guardados sem executar o solver. | Digest, validador v3 e métricas recalculadas concordam. |
| R55.08.4 | Comparar revisões com inputs e limites iguais. | Publicar regressões de qualidade, conclusão e recursos. |
| R55.08.5 | Conservar falhas, OOM, timeout e resultados inconclusivos. | Nenhum caso difícil desaparece da amostra. |

Executar primeiro com um worker para manter comparabilidade com a baseline atual.
Não antecipar a calibração completa de W11 neste pacote.

### R55.09 — Rever arquitetura e executar checks finais

Prioridade: P2. Dependências: correções concluídas. Responsável: revisão técnica.

| ID | Trabalho | Critério de aceitação |
| :--- | :--- | :--- |
| R55.09.1 | Rever fronteiras domínio/aplicação/infraestrutura. | Domínio não importa ORM, CP-SAT, serviços ou relógio global. |
| R55.09.2 | Rever duplicações de regras entre métricas e modelo. | Equivalência observável testada; validador continua independente. |
| R55.09.3 | Rever complexidade introduzida pelas correções. | Sem novas dependências, configurações ou abstrações desnecessárias. |
| R55.09.4 | Executar unitários, integração, contratos, runner e Ruff. | Checks verdes na mesma revisão final. |
| R55.09.5 | Registar avisos ou desvios anteriores não alterados. | Não esconder falhas preexistentes nem atribuir-lhes sucesso. |

Comandos existentes a reutilizar:

```text
node scripts/test.mjs fast --scope backend
node scripts/test.mjs integration
node --test scripts/test.test.mjs
node scripts/test.mjs campaign --manifest backend/tests/scheduler_lab/generation_manifest.json --mode generator --time-limit 30
node scripts/test.mjs campaign --manifest backend/tests/scheduler_lab/annual_manifest.json --mode generator --time-limit 100
```

Os valores 30 e 100 são parâmetros históricos de laboratório, não requisitos de produto.
Alterá-los exige identificação explícita da configuração comparada.

### R55.10 — Publicar dossier e decidir G2

Prioridade: P1 de aceitação. Dependências: R55.00–R55.09. Responsável: revisão técnica e proprietário.

| ID | Trabalho | Critério de aceitação |
| :--- | :--- | :--- |
| R55.10.1 | Mapear A01–A12 e B01–B05 para código, testes e resultados. | Nenhum achado desaparece sem resolução ou decisão explícita. |
| R55.10.2 | Resolver as hipóteses da secção 5 do plano. | Cada hipótese tem teste, conclusão e âmbito. |
| R55.10.3 | Atualizar o estado dos documentos anteriores sem apagar história. | O leitor identifica a decisão de gate mais recente. |
| R55.10.4 | Publicar limites de qualidade e desempenho ainda desconhecidos. | Não confundir heurística, prova condicionada e garantia global. |
| R55.10.5 | Decidir prontidão para W06. | Critérios técnicos demonstrados; aceitação funcional pertence ao proprietário. |

## 5. Gate de entrada em W06

- B01 e B02 corrigidos, com regressões verdes.
- A01–A12 confirmados na revisão final, sem regressões.
- Certificados e resultados respeitam o seu âmbito.
- Continuidade entre janelas tem melhoria demonstrada e limites explícitos.
- Oráculo completo e corpus conectado passaram nos casos obrigatórios.
- Nenhum caso viável obrigatório termina FAILED, INFEASIBLE ou INCONCLUSIVE.
- Todas as campanhas guardam inputs, resultados e identidade exata da revisão.
- O dossier distingue pendências W00–W05 de entregas posteriores legítimas.

## 6. Entregas posteriores que permanecem fora deste WBS

| Entrega | Pacote original | Tratamento |
| :--- | :--- | :--- |
| AdaptiveRecovery e cadeias de reparação | W06 | Começar após o novo gate. |
| Controlador de paragem e diagnóstico operacional | W07 | Reutilizar certificados já honestos. |
| Fila, snapshots persistidos e aprovação atómica | W08 | Completar integração dos fundamentos testados. |
| API, UI e percurso escolar completo | W09 | Preservar autorização e linguagem escolar. |
| Simulações longitudinais | W10 | Usar o motor adaptativo e eventos reais. |
| Calibração 1/2/4/8 workers | W11 | Comparar famílias representativas. |
| Baseline Alembic consolidada e remoção de legado | W12 | Manter checkpoint obrigatório. |
| Validação remota e corte | W13–W14 | Só depois do gate local integral. |

Não estabelecer datas de entrega ou estimativas de esforço sem decompor os contraexemplos e medir as campanhas.
Concluir por evidência observável, não pelo número de tarefas marcadas.
