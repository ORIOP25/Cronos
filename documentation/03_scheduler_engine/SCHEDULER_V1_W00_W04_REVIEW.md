# Revisão independente — Scheduler v1, âmbito W00–W04

Data: 24 de setembro de 2026.
Decisão: **não aceitar W00–W04 como concluídos; corrigir os fundamentos antes de certificar W04**.

Referências: [plano](SCHEDULER_V1_REVAMP_PLAN.md), [tech spec](SCHEDULER_V1_TECH_SPEC.md), [WBS](SCHEDULER_V1_WBS.md).
Execução das correções: [WBS de correção](SCHEDULER_V1_W00_W04_CORRECTION_WBS.md).

## 1. Conclusão e âmbito real

Existe trabalho útil e verificável: domínio puro, minutos inteiros, projeção curricular, regras de comparação, transações serializadas e isolamento relacional.
O runner local funciona e os testes existentes voltaram a passar nesta revisão.

Contudo, os critérios de aceitação dos pacotes ainda não foram atingidos.
O validador aceita alguns candidatos incorretos e rejeita uma atualização modular permitida.
O oráculo pode declarar inviável um caso com testemunho válido.
O laboratório pode aceitar resultados desatualizados e campanhas sem casos executados.
Essas lacunas impedem usar resultados verdes como prova suficiente para o novo gerador.

**W04 não foi iniciado no estado analisado.**
Isto consta do resumo fornecido e do registo W03, e coincide com o código inspecionado.
Não existe a implementação v1 do planeador anual e detalhe coordenado exigida em W04.
O código CP-SAT anterior continua presente; não constitui a entrega da nova geração.

A expressão “até W04” é tratada como âmbito da revisão e da recuperação do plano.
Não atribuo resultados de geração v1 a código que ainda não existe.
O WBS de correção separa defeitos, entregas incompletas e continuação normal de W04.

## 2. Evidência recolhida nesta revisão

Branch: `codex/scheduler-v1-revamp`.
Commit de base: `facd1d93bead7fc6ed481de6761644afd2e0be81`.
As alterações revistas estão por commitar; o SHA de HEAD isolado não identifica a implementação testada.

Guardei um [manifesto com hashes de 71 ficheiros relevantes](review_evidence/2026-09-24/source_manifest.json).
Imagem local utilizada: `sha256:8ecfee9d6f78e29624c9226f208aaff7f0888a149dde648b0860f67ff1f5ad44`.

| Verificação executada | Resultado observado |
| :--- | :--- |
| `node scripts/test.mjs fast --scope backend` | 509 testes passaram; Python 3.14.7 no Docker. |
| `node --test scripts/test.test.mjs` | 17 testes passaram. |
| `node scripts/test.mjs integration -- -k scheduler_v1` | 8 testes passaram em PostgreSQL temporário. |
| Contratos executados pelo runner de integração | 47 testes passaram. |
| Contraexemplos adicionais, container sem rede | 12 discrepâncias reproduzidas. |

Os oito testes de integração incluem instalação, metadata Alembic, roundtrip, auditoria, RLS, constraints e a sequência de progresso existente.
Não repeti a suite integral de 300 testes de integração; esse número pertence à evidência histórica apresentada.
Não executei E2E frontend, campanhas anuais ou benchmarks de W04, que ainda não existe.
Não executei Railway/Cloudflare nem alterei a base de desenvolvimento.
O runner removeu apenas a stack temporária de teste que criou.

Artefactos locais desta execução:

- Unitários: `.test-artifacts/1790272945198-36332/backend-unit.xml`.
- Integração e contratos: `.test-artifacts/1790273057605-20176/`.
- Contraexemplos: `.test-artifacts/scheduler-v1-review-20260924/`.

Os [contraexemplos](review_evidence/2026-09-24/probes.py) e os [resultados JSON](review_evidence/2026-09-24/probes.json) também acompanham este relatório.
O script é diagnóstico: passa quando reproduz os defeitos atuais.
Não o usar como teste de aceitação; converter as expectativas em regressões convencionais durante a correção.

Reprodução do diagnóstico a partir da raiz do repositório, em PowerShell e com a imagem local já construída:

```powershell
docker run --rm --network none --mount "type=bind,source=$($PWD.Path),target=/workspace" -w /workspace/backend -e PYTHONPATH=/workspace/backend cronos-backend-test:local python /workspace/documentation/03_scheduler_engine/review_evidence/2026-09-24/probes.py
```

Depois de corrigir os defeitos, o assert final deste diagnóstico deve deixar de passar.
Os testes de regressão convencionais devem passar com o comportamento esperado correto.

## 3. Avaliação por pacote

| Pacote | Estado observado | Decisão |
| :--- | :--- | :--- |
| W00 | Inventário e runner funcionais; boundary externo documentado como não comprovado. | Base local utilizável; sem aceitação integral do pacote. |
| W01 | Regras e exemplos implementados; contratos de snapshot/proteção ainda insuficientes. | Parcialmente demonstrado; corrigir antes de considerar domínio fechado. |
| W02 | 13 tabelas, RLS, grants e transações parciais; vários itens explicitamente abertos. | Em execução; não confundir schema instalado com domínio persistido completo. |
| W03 | Validador, oráculo e laboratório presentes, mas com falsos positivos/negativos reproduzidos. | Não aceite como fundação de certificação. |
| W04 | Sem implementação nova e sem horários produzidos por ela. | Não iniciado; não há resultado de geração v1 a aprovar. |

O tamanho reduzido do oráculo não é um defeito: foi previsto para microinstâncias.
Também não é defeito ainda não existir AdaptiveRecovery, otimização final ou fila v1 operacional; pertencem a fases posteriores.
O problema é a correção dos casos que os componentes já afirmam verificar.

## 4. Defeitos reproduzidos

P1 significa bloqueio da confiança nos fundamentos ou risco de aceitar um horário inválido.
P2 significa lacuna de integridade/reprodução que deve fechar antes da aceitação dos pacotes.
Estas prioridades referem-se à branch em construção, não a incidentes de produção.

### F01 — P1: a validação curricular não verifica cronologia

Local: [candidate_validation.py](../../backend/app/scheduler/domain/candidate_validation.py), `_check_module_tiling`, linha 147.
Evidência: R01 e R12.

R01 coloca M2 na segunda e M1 na terça, mantendo todas as somas e offsets corretos.
O validador devolve `valid=True`.
Ordena parcelas por offset dentro de cada módulo, mas não verifica a sequência real das aulas.
Assim, não garante a regra central dos módulos dinâmicos.

R12 distribui 60 minutos por duas aulas físicas de 60, creditando 30 em cada uma.
O validador aceita, embora a primeira aula editável não possa ser parcial neste caso.
O total correto não basta para validar a distribuição curricular.

Correção: percorrer aulas cronologicamente e verificar a alocação esperada de minutos, sem reutilizar a construção do solver como prova.
Validar a regra de crédito parcial e a exceção explícita das aulas protegidas.

### F02 — P1: o calendário validado é menos restritivo do que o contrato

Locais: [candidate.py](../../backend/app/scheduler/domain/candidate.py), `PlanningSnapshot`, linha 69;
[candidate_validation.py](../../backend/app/scheduler/domain/candidate_validation.py), linhas 178 e 200.
Evidência: R02–R04.

- R02: indisponibilidade 09:30–10:30 não impede aula 09:00–10:00; a comparação exige igualdade exata do `Period`.
- R03: uma aula às 02:00 passa; o snapshot contém weekdays, mas não os períodos concretos da grelha.
- R04: um candidato inicial depois da preferência passa até ao limite absoluto; o contrato não distingue estratégia.

R03/R04 demonstram informação ausente no contrato, além de checks ausentes.
O validador não consegue inferir a grelha ou a estratégia que não recebeu.
Também não recebe disponibilidade temporal das salas, restrições de turma nem fronteira editável completa.

Correção: tornar explícitos esses factos e verificar interseções físicas, não apenas igualdade de objetos.
Só depois compilar candidatos W04 contra o mesmo significado das regras.

### F03 — P1: proteção confunde identidade física com projeção modular

Local: [candidate_validation.py](../../backend/app/scheduler/domain/candidate_validation.py), comparação integral na linha 377.
Evidência: R05.

Uma aula protegida permanece no mesmo lugar, sala e atribuição, mas recebe a projeção modular atualizada correta.
O validador rejeita porque compara toda a dataclass, incluindo `slices`.
Isto contradiz D18 e T03.

No sentido oposto, a lista de aulas protegidas não basta para impedir inserções novas dentro da janela.
Falta uma fronteira temporal verificável para todos os candidatos, incluindo novos IDs.
Esta segunda lacuna foi identificada por inspeção do contrato, não por um teste de inserção com fronteira representada.

Correção: comparar explicitamente campos físicos e validar toda inserção contra a janela recebida.
Conservar a identidade antiga dos recursos quando comparar uma atribuição entretanto alterada.

### F04 — P1: o oráculo pode produzir falsa impossibilidade

Local: [oracle.py](../../backend/app/scheduler/domain/oracle.py), `_assignment_options` e `enumerate_candidates`, linhas 61 e 128.
Evidência: R06.

Uma atribuição requer 60 minutos e já tem uma aula futura protegida de 60 minutos.
O candidato com essa aula passa no validador.
O oráculo tenta ainda gerar os 60 minutos e depois acrescenta a aula protegida.
Todos os candidatos ficam duplicados/excedentários e `feasible=False`.

Além disso, o limite de 50 000 combinações é verificado depois de construir todas as opções de cada atribuição.
A enumeração de subconjuntos período×sala pode consumir recursos antes de atingir esse limite.
Este risco foi identificado por inspeção; não provoquei uma expansão exponencial no computador.

Correção: descontar crédito protegido e fixar ocupações antes de enumerar.
Limitar esforço também durante a construção; interrupção não pode retornar impossibilidade.
Documentar que `oracle_objective` certifica apenas o vetor de conclusões atualmente implementado.
Não chamar a isso ótimo de todas as prioridades de qualidade futuras.

### F05 — P2: o snapshot dito imutável pode mudar por alias

Local: [candidate.py](../../backend/app/scheduler/domain/candidate.py), `PlanningSnapshot`.
Evidência: R07.

Alterar o dicionário original `executed_minutes[1][1]` depois da construção altera o snapshot.
`frozen=True` protege a atribuição do campo, mas não as estruturas internas.
Assim, o mesmo objeto pode representar procura diferente entre digest, validação e pesquisa.

Correção: copiar e imobilizar recursivamente os valores aceites, ou usar tuplos tipados.
Validar IDs, tipos, unicidade de módulos/atribuições e coerência de períodos na fronteira.
Não introduzir um framework de serialização para resolver este caso.

### F06 — P1: retoma pode reutilizar evidência de outro cenário

Local: [campaign.py](../../backend/app/scheduler/lab/campaign.py), linha 83.
Evidência: R08.

Executar um caso viável de 60 minutos; depois alterar a versão e procura para 120 minutos na mesma hora disponível.
Com `resume=True`, o resultado antigo `VALID` é reutilizado e a campanha não reporta falha.
Não verifica input digest, versão, commit, configuração ou manifesto.

Correção: validar uma chave completa de proveniência antes de reutilizar o resultado.
Incluir identidade da árvore modificada enquanto o código não estiver commitado.
Resultados truncados ou de execuções diferentes não podem certificar a execução atual.

### F07 — P1: campanhas podem passar sem executar ou verificar o esperado

Local: [campaign.py](../../backend/app/scheduler/lab/campaign.py), linhas 27, 54, 77 e 100.
Evidência: R09–R10; inspeção das regras de mutação.

R09 pede um ID inexistente: seleciona zero casos e não reporta falhas.
R10 declara `INVALID_INPUT`, mas fornece dados válidos: devolve `INCONCLUSIVE`, que é aceite.
As mutações passam se produzirem qualquer `INVALID`; o código pretendido não é exigido pelo runner.
Uma exceção em `run_case` aborta sem materializar um resultado `ERROR` por caso.

Correção: validar seleção e unicidade; comparar expectativas estritamente; exigir violações esperadas nas mutações.
Representar erro, omissão e inconclusivo no relatório, com política explícita de exit code.
Não tratar candidato adulterado e configuração de entrada inválida como o mesmo teste.

### F08 — P2: comparação de relatórios não garante equivalência nem regressão semântica

Local: [reports.py](../../backend/app/scheduler/lab/reports.py), `compare_reports`, linha 112.
Evidência: R11 e inspeção.

A comparação ignora alterações de digest e versão.
Também pode considerar limpa a passagem de `INVALID` para `VALID` num teste de corrupção.
Não conhece a expectativa que define se o resultado constitui aprovação ou falha.
Assim, um validador que deixa de detetar a corrupção pode parecer uma melhoria.

Correção: separar comparabilidade de regressão e comparar sucesso contra a expectativa do caso.
Métricas desaparecidas, resultados omitidos e mudanças de política devem ficar explícitos.

## 5. Entregas incompletas confirmadas por inspeção

Estes pontos não são doze testes adicionais falhados; são diferenças entre artefactos existentes e entregas exigidas.

### L01 — W02: histórico, reservas e configuração ainda abertos

[progress.py](../../backend/app/scheduler/infrastructure/progress.py) implementa `record_execution` e `record_debt`.
O lock escolar, replay e conservação agregada têm evidência positiva nos testes repetidos.
Faltam compensações completas após correções retroativas, transações de configuração e ciclo persistido de reservas.
`_validate_debt_state` não carrega reservas ativas para reconciliar execução/acertos com essas reservas.

`_credit_offset` usa o total líquido para novos créditos.
Após reversão retroativa, esse total não representa necessariamente a próxima posição curricular livre.
Exemplo a transformar em teste PostgreSQL: A=[0,50), B=[50,100), reverter 25 de A e adicionar 25.
O novo offset calculado é 75; sobrepõe B sem compensação histórica.
O teste existente verifica o offset da reversão, mas não essa conservação intervalar posterior.

O schema atual de `SchedulerSchoolYear` continua sem a data preferencial da configuração v1.
É preciso materializar início, preferência e limite e garantir revisões nos comandos que os alteram.
Não basta ter essas datas apenas no snapshot sintético.

### L02 — W02: schema instalado não demonstra publicação íntegra

As FKs isolam organizações, mas não substituem regras dentro da mesma escola.
Uma reserva deve pertencer à mesma atribuição da dívida e da aula, além da mesma versão/ano aplicáveis.
As parcelas devem pertencer ao currículo da atribuição.
É preciso demonstrar essas regras nos comandos transacionais e nas constraints expressáveis.

As aulas têm checks de duração positiva, mas falta evidência de concordância entre intervalo e `physical_minutes`.
Também não há ainda o mecanismo completo de exclusão de sobreposições na versão publicada.
Não exijo publicar horários em W02; exijo que estes invariantes tenham destino e testes antes dessa publicação.

### L03 — Baseline e reset permanecem provisórios

A migração `0011` depende da cadeia anterior; a nova baseline final ainda não foi consolidada.
Isto está explicitamente registado como transitório, não constitui por si só um workaround de produção.
Não aceitar W02 como integralmente fechado nem transportar essa cadeia por esquecimento até P11.
Faltam o reset local ensaiado e o caminho administrativo de apagamento das novas tabelas append-only.
Não resolver apagamento concedendo DELETE ao papel normal da aplicação.

### L04 — W03 ainda não é o laboratório de aceitação do gerador

Os casos atuais são construídos pelo oráculo e validam o testemunho ou a sua adulteração.
Ainda não executam uma implementação W04, conforme esperado neste momento.
As seeds estão registadas, mas não produzem diversidade de fixtures/eventos no gerador atual.
Faltam métricas recalculadas de qualidade, recursos/tempo e geração de fixtures grandes sem enumeração exaustiva.

Não é necessário antecipar a calibração completa W05–W11.
É necessário preparar a medição e os casos independentes que permitirão avaliar W04.

### L05 — W00: limites de evidência

O repositório não demonstra as definições externas de auto-deploy.
Não houve push nesta revisão; essa incerteza não impediu os testes locais.
As identidades E2E externas e os gates de frontend permanecem fora da evidência repetida.
Manter a restrição local; não desbloquear cloud apenas porque o backend unitário passou.

## 6. Recomendação

Preservar o trabalho correto; não reiniciar o revamp.
Corrigir primeiro contratos, validador, oráculo e credibilidade dos resultados.
Completar as fatias W02 que condicionam os contratos do gerador.
Depois implementar W04 e submetê-lo às campanhas do WBS com evidência nova.

Os testes verdes confirmam comportamento coberto, não todos os resultados pretendidos.
Nesta revisão, os contraexemplos são suficientes para rejeitar a aceitação integral, mesmo sem implementar W04.
O [WBS de correção](SCHEDULER_V1_W00_W04_CORRECTION_WBS.md) define a sequência e os gates para retomar o plano.
