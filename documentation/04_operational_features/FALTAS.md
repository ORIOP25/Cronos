# Faltas

## Objetivo
Definir o tratamento de faltas sem quebrar consistencia de horario, progresso e auditoria.

## 5 Ws

### What
Gestao de ocorrencias quando uma aula planeada nao ocorre como previsto por ausencia.

### Who
No sistema atual:
- admin aprova e governa as decisoes operacionais.
- professor nao possui permissao para gerir operacao global (apenas disponibilidade e consulta do proprio horario).

### Where
Sempre dentro da organizacao do tenant.
Nenhuma ocorrencia pode atravessar fronteira de organization_id.

### When
No dia a dia de execucao letiva, apos publicacao de horario.

### Why
Evitar perda de rastreabilidade e evitar distorcao artificial do progresso modular.

## Principios confirmados

1. Historico de ocorrencias e imutavel.
2. Planeado e executado sao entidades diferentes.
3. Decisao de falta deve explicitar estado operacional.
4. Impacto em progresso/divida deve ser transparente.

## Estados operacionais confirmados
- GAP
- GIVEN
- SUBSTITUTED

Nota:
o significado operacional detalhado de cada transicao deve permanecer consistente entre faltas e substituicoes.

## Maquina de estados implementada (Alpha V1 - Passo 1)

Regra oficial (2026-04-12):
- ocorrencia com `decided_at = null` esta aberta e aceita UMA decisao final;
- ocorrencia com `decided_at != null` e fechada e torna-se imutavel.

Transicoes permitidas:
- primeira decisao de ocorrencia aberta: `GIVEN` ou `GAP` ou `SUBSTITUTED`;
- retry idempotente da mesma decisao final (mesmo payload) sem alterar accounting.

Transicoes bloqueadas:
- qualquer tentativa de mudar estado de ocorrencia fechada deve falhar com conflito operacional;
- tentativa de sobrescrever decisao final (alteracao destrutiva) deve falhar;
- repeticao do mesmo pedido nao pode duplicar contabilizacao.

## Excecao operacional (a definir)

Pergunta de negocio: "existe situacao valida para alterar uma aula fechada no passado?"

Resposta tecnica recomendada:
- evitar alteracao in-place do historico fechado;
- se for legalmente necessario corrigir, criar fluxo especifico de retificacao por evento append-only,
  mantendo o registo original intocado e auditavel.

Estado atual da decisao:
- modelo de retificacao administrativa: a definir.

## Fluxo pratico minimo

1. Aula existe no planeamento publicado.
2. Ocorre evento de falta.
3. admin decide encaminhamento operacional.
4. Sistema regista ocorrencia com estado explicito.
5. Sistema preserva historico sem apagar o planeado original.

## Criacao de ocorrencia - estado atual implementado (2026-04-12)

Comportamento factual atual:
- existe acao "Criar Ocorrencia" no bloco da grelha semanal para role admin;
- existe endpoint publico de criacao operacional em `/api/v1/occurrences/` com comportamento idempotente (cria ou reutiliza);
- apos criar, o fluxo segue para a pagina de faltas para decisao final (GAP/SUBSTITUTED/GIVEN).

Como a ocorrencia pode nascer agora:
1. via acao manual no bloco semanal (fluxo preferencial de operacao diaria);
2. via confirmacao automatica diaria (Celery Beat, 23:59) para aulas decorridas sem registo manual;
3. via dados de seed/testes (cenarios tecnicos).

## Workflow operacional aprovado para Alpha (implementado)

1. Professor avisa admin que nao vai conseguir dar a aula programada.
2. Admin clica no bloco de hora da aula no horario semanal.
3. Admin seleciona "Criar Ocorrencia".
4. Ocorrencia passa a aparecer na pagina de faltas.
5. Admin gere a ocorrencia na pagina de faltas (GAP ou SUBSTITUTED).
6. Horario atualiza bloco para novo professor/disciplina ou marca vazio (GAP).
7. Mudanca reflete para admin, professores e turmas envolvidas.

## Exemplo pratico

Cenario:
- aula de quarta-feira 10:00 planeada para turma T2.
- docente previsto indisponivel no dia.

Acao:
- admin regista a ocorrencia e decide estado aplicavel.

Resultado esperado:
- calendario executado reflete o que aconteceu;
- historico da decisao fica auditavel;
- impacto curricular fica visivel para operacao futura.

## Regra oficial de progresso e divida (abordagem A definida)

Unidade de contabilizacao:
- horas do bloco da ocorrencia.

### Estado GIVEN
- progresso do modulo planeado soma 100% das horas do bloco;
- divida do modulo planeado soma 0 horas.

### Estado GAP
- progresso do modulo planeado soma 0 horas;
- divida do modulo planeado soma 100% das horas do bloco.

### Estado SUBSTITUTED
- progresso soma 100% das horas no modulo realmente executado na substituicao;
- divida soma 100% das horas no modulo originalmente planeado.

### Formula agregada por modulo
- hours_completed_modulo = soma das horas efetivamente executadas no modulo (GIVEN ou SUBSTITUTED nesse modulo).
- hours_debt_modulo = soma das horas planeadas para o modulo que nao foram executadas no proprio modulo (GAP ou SUBSTITUTED para outro modulo).
- progress_pct_modulo = min(100, (hours_completed_modulo / hours_total_modulo) * 100).

Resultado:
- regra deterministica, auditavel e sem interpretacao subjetiva por operador.

Aplicacao pratica no backend:
- debt operacional considera ocorrencias GAP e SUBSTITUTED no modulo originalmente planeado;
- calculo de percentagem final aplica cap em 100% para evitar progresso visual acima do total do modulo.

## Trilho de auditoria minimo persistido (Alpha V1 - Passo 1)

Para cada ocorrencia decidida, o sistema preserva:
- quem decidiu (`decided_by_user_id`);
- quando decidiu (`decided_at`);
- docente previsto (`planned_teacher_id`);
- docente executante (`executed_teacher_id`);
- modulo planeado (`planned_module_id`) e modulo executado (`executed_module_id`);
- horas planeadas do bloco (`planned_hours`) e horas efetivamente dadas (`hours_given`).

Protecao de integridade historica:
- remocao de ocorrencias historicas e bloqueada por regra de imutabilidade;
- decisao + contabilizacao (progresso/divida) executa em transacao atomica com rollback completo em erro intermedio.

## Concorrencia e retries implementados (Alpha V1 - Passo 4)

Concorrencia na mesma ocorrencia:
- confirmacoes simultaneas sao serializadas por lock de base de dados;
- apenas uma decisao conflitante pode vencer;
- tentativa concorrente incompatível falha com erro operacional de conflito.

Retry operacional:
- repeticao do mesmo pedido com payload identico e tratada como idempotente;
- retry nao duplica contabilizacao de progresso/divida nem cria historico duplicado.

Validacao de contrato de entrada:
- payload sem `status` ou com campos inesperados e rejeitado com erro de validacao;
- objetivo: evitar aceites silenciosos de input incompleto ou ambiguo.

## Decisao fechada para Alpha V1 (sem pendencias)

Regra de prioridade para faltas concorrentes:
- nao existe escalonador automatico global de faltas na Alpha V1;
- cada ocorrencia e tratada de forma independente pelo admin;
- a lista operacional e ordenada de forma deterministica por: data da ocorrencia (asc), inicio do slot (asc), id da ocorrencia (asc).

Objetivo da decisao:
- manter estabilidade e previsibilidade operacional sem introduzir heuristica opaca nesta fase.

## Impacto por layer

### Interface
- admin precisa de fluxo claro para criar e decidir estado da ocorrencia.

### Regras de negocio
- deve manter separacao entre planeado e executado;
- deve aplicar estados de ocorrencia de forma consistente;
- deve suportar criacao operacional inicial sem violar imutabilidade nem idempotencia.

### Base de dados
- deve registar ocorrencia de modo imutavel e tenant-scoped;
- deve garantir unicidade por bloco/data e transacao atomica na primeira decisao.