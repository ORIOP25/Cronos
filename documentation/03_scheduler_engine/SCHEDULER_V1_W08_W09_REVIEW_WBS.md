# WBS de correção — revisão de W08 e W09

Data: 26 de setembro de 2026. Branch revisto: `codex/scheduler-v1-revamp`.

Referências: [plano v2](SCHEDULER_V1_REVAMP_PLAN_V2.md), [WBS v2](SCHEDULER_V1_WBS_V2.md) e [especificação v2](SCHEDULER_V1_TECH_SPEC_V2.md).

## Decisão da revisão

Não aceitar W08, W09 ou G4 como fechados para utilização escolar. Existem falhas de continuidade curricular e de recuperação operacional.
Os testes atuais demonstram percursos simples. Não demonstram qualidade consistente perante os cenários combinados do plano.

Esta revisão é de código e cobertura. Os riscos abaixo resultam de percursos concretos no código.
Os testes propostos devem reproduzir cada falha antes da correção.

## Trabalhos por prioridade

| ID | Prioridade | Problema e evidência | Correção mínima | Regressão e critério de aceitação |
| :--- | :--- | :--- | :--- | :--- |
| R89.01 | P0 | `persist_proposal` cria novos IDs para todas as aulas da versão. `scheduler_lesson_log_v1` aponta para o ID antigo. `week_schedule` procura sumários apenas pelos IDs novos. Uma aula protegida e já cumprida reaparece sem registo após uma atualização. Ver `proposals.py:162–181` e `operations.py:196–204,259–263`. | Preservar uma identidade operacional estável para aulas protegidas. Reconciliar sumários na transação de aprovação através da identidade e da origem da aula. Impedir novo crédito da mesma execução. | Publicar, registar aula, reparar, aprovar e consultar a semana anterior. O sumário e os minutos cumpridos persistem. Repetir o registo não duplica crédito. Incluir aula com várias parcelas. |
| R89.02 | P0 | O lock PostgreSQL é adquirido uma vez e não tem prova de vida durante o solve. O supervisor partilha o worker Celery com concorrência um. Se a ligação do lock cair, outro processo pode iniciar enquanto o CPU antigo ainda calcula. Um bloqueio do worker também impede o próprio supervisor de executar. Ver `scheduler_v1_worker.py:71–95,111–123`, `jobs.py:460–515` e `docker-compose.yml:104`. | Executar o supervisor fora do processo de cálculo. Verificar continuamente a ligação do lock. Interromper ou terminar o processo de cálculo ao perder o lock. Confirmar a morte do processo anterior antes de reclamar outro job. | Induzir perda de ligação, bloqueio na construção, solve e persistência, morte do worker e reentrega. Medir processos ativos: nunca há dois cálculos simultâneos. A fila progride após recuperação. |
| R89.03 | P1 | A finalização compara revisões e digest do snapshot antigo, mas não reconstrói a fronteira temporal. Também não revalida o candidato com o relógio atual. O relógio de 28 dias reinicia antes de uma aprovação poder detetar a proposta inválida. Ver `proposals.py:84–253`; a validação atual só ocorre em `proposals.py:338–374`. | Revalidar o candidato com o relógio atual antes da transação. Sob o lock do estado, confirmar revisões e fronteira imediatamente antes da escrita. Se a data mudou, terminar como `STALE` sem atualizar o relógio. | Iniciar antes da meia-noite local e terminar depois. Incluir mudança exata da fronteira e execução concorrente. Nunca persistir proposta inválida nem consumir o motivo de geração. |
| R89.04 | P1 | A proposta de recuperação copia apenas `bundle.snapshot.reservations`, ligadas à versão anterior. O candidato contém aulas, mas não reservas novas. Uma aula nova que recupera dívida fica sem vínculo planeado. Uma reserva antiga cujo ID desapareceu provoca erro. Ver `proposals.py:198–211` e `candidate.py:455`. | Produzir as alocações de dívida para a versão candidata. Validar limites por dívida e aula. Persistir essas alocações e reconciliá-las atomicamente na aprovação. | Criar ocorrência, reparar e aprovar. Confirmar dívida aberta, recuperação planeada e crédito executado separados. Cobrir divisão de uma dívida por aulas, várias dívidas numa aula e movimento de aula reservada. |
| R89.05 | P1 | O acerto negativo soma reversões de todos os módulos por origem e desconta esse total de cada módulo. Uma aula com duas parcelas pode impedir uma redução válida no segundo módulo. A reversão do sumário regressa cedo se encontrar qualquer reversão parcial; a ocorrência pode manter crédito indevido. Ver `operations.py:509–551,647–672`. | Calcular reversões por `(origem, módulo)`. Ao corrigir um sumário, reverter apenas o saldo ainda não revertido em cada módulo. | Registar aula cruzando módulos A/B. Reduzir A e depois B. Alterar o sumário para ocorrência. O ledger permanece dentro dos requisitos e conserva os minutos. |
| R89.06 | P1 | `finish_job` aceita um resultado terminal mesmo com cancelamento pedido ou dados alterados durante o solve. Assim, `INFEASIBLE` pode descrever dados antigos, e um cancelamento tardio pode surgir como `INCONCLUSIVE`. Ver `jobs.py:399–430,432–458` e `scheduler_v1_worker.py:125–149`. | Decidir cancelamento, revisões, versão base e resultado sob o mesmo bloqueio do estado e do job. Aplicar `CANCELLED` ou `STALE` antes do resultado calculado. | Sincronizar cancelamento e alteração de dados no ponto anterior a `_finish`. Confirmar `CANCELLED` ou `STALE`, sem proposta nem conclusão enganadora. |
| R89.07 | P1 | A especificação exige repetição idempotente da aprovação. `approve_proposal` devolve conflito para qualquer estado diferente de `PENDING`; o endpoint não reconhece repetição do mesmo comando. Ver `proposals.py:291–298` e `api/v1/endpoints/scheduler.py:214–255`. | Reconhecer uma repetição da aprovação já confirmada e devolver a versão ativa original. Preservar conflito para uma decisão diferente ou versão substituída. | Enviar duas aprovações idênticas, incluindo timeout da primeira resposta. Ambas devolvem o mesmo resultado; há uma única ativação e uma auditoria coerente. |
| R89.08 | P1 | O registo v1 cria dívida e sumário no ledger novo. A página de análise de ocorrências continua no modelo antigo, conforme o próprio registo W08/W09. O percurso escolar C20 fica incompleto. | Adaptar o consumidor existente de ocorrências ao ledger v1. Manter uma só fonte de verdade para consulta, decisão e reversão. | Registar ocorrência pela UI, consultar na página administrativa, decidir, reparar e verificar mapa, dívida e relatório concordantes. |
| R89.09 | P1 | Os testes W08/W09 usam sobretudo uma escola mínima. O FIFO é ensaiado sequencialmente; não existe ensaio de processos concorrentes, falhas induzidas ou sequência escolar anual. C16, C17 e C20 continuam marcadas por executar no WBS v2. | Criar regressões dos percursos R89.01–R89.08 e executar C16, C17 e C20 com PostgreSQL e containers reais. Reusar o laboratório e os manifestos existentes. | Injetar falha a meio da aprovação e confirmar rollback integral. Publicar inputs, digests, resultados, tempos e cobertura efetiva. Triar todo o caso crítico omitido, inconclusivo ou inválido. |
| R89.10 | P2 | O motor entrega evidência por etapa, mas a proposta persiste apenas `stop_reason` e número de etapas certificadas. Limites, valores, âmbito e rondas não ficam auditáveis. Ver `publishing.py:220–244` e `proposals.py:234–237`. | Persistir a evidência tipada completa e a versão da política com a proposta. Expor um resumo escolar sem declarar ótimo fora do âmbito certificado. | Recarregar proposta e reconstruir cada afirmação de qualidade a partir da evidência persistida. Comparar digest e versão da política. |

## Protocolo para demonstrar qualidade do gerador

1. Corrigir R89.01–R89.08 com teste falhado primeiro. Executar o menor conjunto relevante após cada alteração.
2. Executar oráculos enumerativos nos microcasos. Comparar o vetor completo, não apenas a validade ou a data final.
3. Executar C01–C20 em combinações de procura, recursos, datas, dívida e alterações sucessivas.
4. Repetir casos anuais com 10, 30, 45 e 60 turmas e várias sementes. Separar treino e famílias reservadas.
5. Comparar a versão candidata com a baseline por família. Medir conclusão por turma, margem, furos, perturbação e tempo.
6. Tratar `INCONCLUSIVE`, timeout e OOM como resultados explícitos. Nunca converter ausência de prova em ótima decisão.
7. Executar o percurso escolar C20 com teclado, refresh, duplo clique, sessão sem permissão e respostas atrasadas.
8. Fechar G4 apenas com publicação atómica, isolamento real, operações consistentes e falhas induzidas verdes.
9. Fechar G5 apenas depois de W10–W12, calibração W11 e avaliação reservada sem regressões materiais.

Os manifestos atuais têm 26 casos de geração, 18 de reparação e 15 anuais.
Os 25 testes de integração W08/W09 revistos não substituem C16, C17 ou C20.
Nenhuma contagem de testes, por si só, demonstra decisões excelentes em todas as escolas.

## Verificação desta revisão

- 25 testes unitários de publicação, qualidade e recuperação: passaram.
- 25 testes de integração W08/W09 com PostgreSQL real: passaram.
- 47 testes de contratos de infraestrutura: passaram.
- 20 testes frontend dos painéis e fluxo de geração: passaram.
- Não executei falhas de processo, E2E com Clerk nem campanhas anuais nesta revisão.

As aprovações acima confirmam apenas os casos existentes. Não eliminam os percursos descobertos por inspeção.
