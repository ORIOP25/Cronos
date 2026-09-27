# Plano de consolidação da revisão W00–W05

Data: 25 de setembro de 2026.
Branch: `codex/scheduler-v1-revamp`.
Base: `facd1d93bead7fc6ed481de6761644afd2e0be81`, com alterações locais ainda não commitadas.

## 1. Decisão e âmbito

**Não considerar W00–W05 integralmente fechados nem reconfirmar G2 sem executar o WBS desta revisão.**

A arquitetura continua adequada. A revisão encontrou defeitos reais que os testes anteriores não detetavam.
Várias correções já estão no working tree. Isso não equivale à aprovação integral do gerador.
W06 continua por iniciar. Este plano consolida os fundamentos existentes; não implementa AdaptiveRecovery.

Documentos de autoridade:

- [Plano original](SCHEDULER_V1_REVAMP_PLAN.md).
- [Especificação técnica](SCHEDULER_V1_TECH_SPEC.md).
- [WBS original](SCHEDULER_V1_WBS.md).
- [WBS desta revisão](SCHEDULER_V1_W00_W05_AUDIT_WBS.md).

Os registos anteriores permanecem como história. A aceitação anterior de G2 não cobre os novos contraexemplos.
Também não comprova o encerramento de W00–W03, que já tinham pendências documentadas.

## 2. Melhorias que devem permanecer

| Melhoria | Decisão | Condição de correção |
| :--- | :--- | :--- |
| Master anual e detalhe reabrível | Manter | Cortes descrevem integralmente o subproblema excluído. |
| Hint greedy earliest-week | Manter | É um arranque de pesquisa; não prova viabilidade detalhada. |
| Conclusões por contagens de limiar | Manter | Abranger todas as turmas e verificar equivalência com o vetor ordenado. |
| Congelar prioridades superiores | Manter | Distinguir valores provados de valores conservados heuristicamente. |
| Orçamento por janela e pré-solve | Manter | Contar construção e finalização; evitar starvation e certificados de etapas omitidas. |
| Poda pela semana do incumbente | Manter | Permitir a mesma semana, para melhorar os restantes componentes. |
| Matching global de salas após posições | Manter com correções | Considerar sobreposições físicas e reconhecer que as posições continuam fixas. |
| Elegibilidade conjunta e proteção | Manter | Testar turma, docente, salas, passado, datas protegidas e timezone. |
| Cache de janelas provadas | Manter | Nunca reutilizar uma janela interrompida como ótima. |

Os ganhos históricos de aproximadamente 90 para 22 segundos pertencem às medições anteriores.
Esta revisão não os apresenta como nova comparação controlada nem como garantia universal.

A antecipação das conclusões resulta da política aprovada. Distribuir procura ao longo do ano exige uma decisão explícita de produto.
Não introduzir limites semanais ou penalizações de antecipação para obter uma aparência mais uniforme.
Agrupamento de salas equivalentes e calibração 1/2/4/8 workers continuam dependentes de medições em W11.

## 3. Defeitos reproduzidos e já corrigidos localmente

Cada caso abaixo teve teste vermelho antes da alteração.
As regressões estão em [test_scheduler_w05_audit.py](../../backend/tests/unit/test_scheduler_w05_audit.py).

| ID | Prioridade | Defeito observado | Correção local |
| :--- | :--- | :--- | :--- |
| A01 | P1 | Cortes ignoravam quotas zero e excluíam outras distribuições viáveis. | Incluir contagens zero no no-good. |
| A02 | P1 | O limite inferior anual usava o máximo entre bound e incumbente. | Conservar o bound matemático, sem o substituir pelo incumbente. |
| A03 | P1 | O pós-passo criava conflitos entre períodos parcialmente sobrepostos. | Restringir sobreposições físicas por sala. |
| A04 | P2 | Preferência docente e preferência de sala contavam a mesma aula de forma diferente. | Contar uma aula desfavorável uma única vez. |
| A05 | P1 | Procura satisfeita por execução ou aulas protegidas devolvia INCONCLUSIVE. | Aceitar o candidato completo sem aulas novas. |
| A06 | P1 | O validador aceitava docente ou turma alterados numa aula nova. | Verificar os recursos contra a atribuição. |
| A07 | P1 | Uma janela interrompida podia entrar na cache e produzir um prefixo falso. | Excluir interrupções da cache; retirar certificação quando faltam etapas. |
| A08 | P2 | O objetivo de furos ignorava ocupações protegidas fora dos candidatos elegíveis. | Incluir as ocupações fixas do dia e da janela. |
| A09 | P1 | O snapshot convertia floats, booleanos e strings em minutos. | Exigir inteiros sem coerção silenciosa. |
| A10 | P1 | Coleções mutáveis permitiam alterar o snapshot após construção. | Copiar coleções para tuplos e frozensets. |
| A11 | P1 | Períodos noutra timezone eram aceites como períodos da escola. | Verificar timezone na elegibilidade, no oráculo e no validador. |
| A12 | P2 | Continuidade de salas era certificada após fixar posições potencialmente piores. | Otimizar posições e salas numa janela; limitar a prova do pós-passo. |

A12 tem um contraexemplo mínimo com três períodos e duas salas.
O resultado anterior tinha uma mudança de sala; a enumeração encontrava zero, sem piorar qualquer prioridade superior.
A correção numa janela passou. A otimização conjunta entre várias semanas continua aberta.

O validador passou de `v2` para `v3`.
Artefactos antigos exigem revalidação explícita; não alterar silenciosamente a versão guardada.

## 4. Problemas residuais confirmados

### B01 — Colisão de identidades geradas, P1

`_build_candidate` calcula identidades através de `assignment_id * 1_000_000 + rank`.
Uma aula protegida pode já ter essa identidade.

Reprodução: atribuição 1, procura 120 minutos, aula protegida 1000001 com 60 minutos e outro período livre.
O gerador devolve `FAILED`, com `DUPLICATE_IDENTITY`, embora exista solução completa.

Escolher identidades novas sem colisões. Preservar as identidades protegidas e os vínculos das parcelas.
Não criar um serviço de IDs para resolver este problema local.

### B02 — Inputs inválidos atravessam o snapshot, P1

Reprodução: uma atribuição existente e `executed_minutes={99: {1: 60}}`.
O gerador devolve `COMPLETE` e ignora a atribuição desconhecida.

Reprodução: `executed_minutes={1: {1: -1}}`.
O gerador lança `ValueError` durante a projeção, em vez de rejeitar o input na fronteira.

Validar pertença, limites por módulo, referências protegidas e dívida antes de construir modelos.
Separar rejeição de input, falha interna e impossibilidade demonstrada.
Não transformar todas as exceções em INFEASIBLE.

### B03 — Continuidade entre semanas permanece heurística, P2

O matching global escolhe salas com posições fixas.
Não explora uma mudança temporal que preserve conclusões, furos e preferências, mas reduza mudanças de sala.

Conservar a heurística como incumbente. Permitir refinamento temporal limitado quando existe custo de salas evitável.
Um custo positivo no matching não prova o ótimo global.
A correção local já retirou essa certificação indevida do pós-passo.

### B04 — Orçamento e contabilidade temporal incompletos, P2

O master atribui o limite ao solver depois de construir o modelo.
O seu `wall_time_seconds` usa o último `solver.WallTime()`, apesar de poder executar dois solves.
A avaliação opcional de recuperabilidade recebe outro orçamento completo.

Definir um deadline monotónico partilhado e separar claramente os custos adicionais autorizados.
Contabilizar preparação, construção, solves, matching e validação.
O supervisor operacional completo permanece em W07–W08.

### B05 — Corpus anual insuficiente para generalização, P1 de aceitação

As fixtures anuais agrupam poucos colegas por docente e usam uma sala elegível por atribuição.
As três disciplinas da turma partilham o mesmo professor nesses casos.
Os componentes de recursos permanecem pequenos, mesmo quando o total chega a 60 turmas.

Isso demonstra volume e viabilidade dessas famílias. Não demonstra uma rede escolar extensa e fortemente ligada.
Acrescentar topologias conectadas, alternativas de salas, durações heterogéneas e disponibilidades assimétricas.
Conservar as fixtures anteriores como regressões, sem as substituir por casos mais fáceis.

## 5. Riscos que ainda exigem confirmação dirigida

Estes itens resultam de inspeção. Não estão apresentados como falhas já reproduzidas.

- Confirmar prioridade de SAFETY_LIMIT quando outra janela já terminou como FEASIBLE.
- Confirmar que certificados não atravessam uma etapa omitida noutra janela.
- Confirmar a semântica de cada bound depois de excluir distribuições já exploradas.
- Confirmar que uma solução FEASIBLE do pós-passo nunca piora o incumbente conhecido.
- Confirmar contexto completo da cache após acrescentar otimização de salas numa única janela.
- Verificar projeção quando aulas protegidas e novas se intercalam cronologicamente.
- Auditar valores `Period` construídos diretamente, sem `normalize_period`.

Reduzir cada discrepância a um teste determinístico antes de alterar código.
Fechar hipóteses não reproduzidas com justificação e evidência, sem criar abstrações preventivas.

## 6. Evidência desta revisão

| Verificação | Resultado | Alcance |
| :--- | :--- | :--- |
| Regressões adversariais | 16 testes vermelhos antes das respetivas correções. | Defeitos A01–A12. |
| Suite unitária antes da última correção de salas | 628 passaram. | Inclui as primeiras 15 regressões. |
| Testes dirigidos após A12 | 36 passaram. | Auditoria, regressões anteriores e qualidade inicial. |
| Integração PostgreSQL | 321 passaram. | Transações, schema e integrações existentes. |
| Contratos | 47 passaram. | Contratos de infraestrutura existentes. |
| Runner | 17 passaram. | Infraestrutura de testes. |
| Campanha curta | 20 VALID e 6 INFEASIBLE; saída zero. | 26 casos existentes. |
| Comparação adicional com enumeração | 40/40 vetores completos coincidiram. | Microinstâncias; não inclui o contraexemplo dirigido A12. |

Artefactos locais:

- Unitários: `.test-artifacts/1790327893767-12336/backend-unit.xml`.
- Integração e contratos: `.test-artifacts/1790327077704-15056/`.
- Campanha curta: `.test-artifacts/1790327571126-22112/scheduler-lab/`.
- Comparação enumerativa: `.test-artifacts/w05-audit-oracle.json`.
- [Script da comparação](review_evidence/2026-09-25-w05-audit/probes.py).

A repetição anual foi iniciada em `.test-artifacts/1790327956106-3848/scheduler-lab/`.
Foi iniciada antes da última correção A12; não representa a validação integral da revisão final.
O WBS exige resultados completos e uma baseline identificada por hashes, incluindo ficheiros ainda não commitados.

Não houve push, deployment, testes remotos ou alterações às bases de desenvolvimento.
O frontend não foi alterado.

## 7. Plano de execução

1. Fixar a revisão e concluir a verificação das correções locais.
2. Corrigir B01 e B02 com TDD e validação independente.
3. Fechar certificados, preservação do incumbente e hipóteses de cache.
4. Refinar salas entre semanas sem degradar prioridades superiores.
5. Corrigir deadline e medição do esforço.
6. Expandir oráculos e corpus por topologia, não apenas por dimensão.
7. Executar campanhas controladas, analisar falhas e repetir as famílias afetadas.
8. Publicar o dossier e decidir novamente G2 antes de iniciar W06.

Aplicar Clean Architecture nas fronteiras existentes. Não criar frameworks ou novos serviços.
Manter Ponytail full: reutilizar primeiro, corrigir a causa e escolher o menor desenho correto.
Não refatorar todo o motor para eliminar um defeito localizado.

## 8. Critérios de saída

- Zero candidatos inválidos reconhecidos como completos.
- Zero falsas impossibilidades nos casos com testemunho.
- Zero certificados que excedam o âmbito demonstrado.
- Inputs inválidos rejeitados antes do solver, sem perda silenciosa de minutos.
- Candidatos protegidos preservados e identidades novas sem colisões.
- Oráculos verificam todo o vetor nos casos exatos obrigatórios.
- Casos grandes obrigatórios terminam completos e passam no validador independente.
- Limites heurísticos, falhas, censura e casos inconclusivos ficam visíveis no dossier.
- Checks obrigatórios passam na revisão final identificada.

Não exigir prova de ótimo global em todas as escolas grandes.
Exigir qualidade comparada, cobertura representativa e informação honesta sobre o que ficou por provar.

Pendências legítimas de fases posteriores mantêm os seus responsáveis.
Baseline Alembic final pertence ao checkpoint W12; fila e publicação completas pertencem a W08–W09.
Calibração de workers pertence a W11. Essas pendências não autorizam declarar W00–W05 integralmente concluídos.
