# Hard constraints e objetivos soft

## Objetivo
Definir o contrato operacional do motor de geracao.
Este contrato separa claramente inviabilidade (hard) de qualidade (soft).

## 5 Ws do motor

### What
Motor de geracao e regeneracao de horarios para toda a organizacao.

### Who
Execucao operacional e aprovada por admin.
Professores contribuem por disponibilidade, sem governar regras do motor.

### Where
Escopo multi-tenant por organization_id.
Geracao sempre organizacional, nao local por turma isolada.

### When
Aplicado em planeamento inicial e em regeneracao de futuro.
Nunca autoriza aulas apos school_hard_end_date.

### Why
Garantir viabilidade real de operacao escolar no ensino profissional modular.

## Hard constraints (inviolaveis)

1. Sem conflito de professor.
2. Sem conflito de turma.
3. Sem conflito de sala.
4. Tipo de sala obrigatorio deve ser respeitado.
5. Slots IMPOSSIBLE sao proibidos.
6. Regra de almoco e hard quando configurada.
7. school_hard_end_date e limite absoluto.

Se qualquer item acima falhar, a geracao nao e valida.

## Soft objectives (otimizacao)

1. Minimizar desvio de school_target_end_date.
2. Melhorar fairness entre turmas.
3. Reduzir furos de turmas e professores.
4. Preservar estabilidade em repair mode quando possivel.

Soft objectives nunca podem forcar violacao hard.

## Repair mode conservador (abordagem A definida)

1. Repair mode usa janela fixa de estabilidade.
2. A janela e parametro global nas configuracoes da escola (por organizacao).
3. Dentro da janela, horarios publicados nao sao regenerados.
4. Regeneracao atua apenas fora da janela.
5. Eventos dentro da janela sao tratados por ocorrencias (GAP, GIVEN, SUBSTITUTED), sem reescrever o publicado.
6. Valor de referencia para testes atuais: 2 semanas.

## Contrato implementado (Alpha V1 - Passo 3)

Aplicacao efetiva no backend:
1. `mode=repair` so pode regenerar fora da janela congelada.
2. Limite da janela: `today + repair_stability_window_days`.
3. Inicio da expansao em repair: `max(school_start_date, frozen_until + 1 dia)`.
4. Se nao existir horizonte fora da janela antes do `school_hard_end_date`, o pedido falha no preflight (sem enfileirar task).
5. Aprovacao de draft preserva publicado dentro da janela congelada:
	- nao apaga ativo dentro da janela;
	- nao ativa blocos de draft dentro da janela;
	- promove apenas blocos de draft fora da janela.

Fallback de seguranca:
- quando `repair_stability_window_days` nao esta configurado, aplica-se default conservador de 14 dias.

Compatibilidade com hard end date:
- hard end date continua absoluto;
- repair mode nunca cria blocos apos hard end date, mesmo fora da janela.

## Regra de decisao

Ordem obrigatoria:
1. Viabilidade hard.
2. Consistencia de dominio.
3. Qualidade soft.

## Criterios praticos de validacao (resposta ao ponto 4)

### Bloco A - Criterios de bloqueio
- taxa de violacao hard = 0;
- aulas apos hard end date = 0;
- vazamento entre tenants = 0.
- alteracoes em horario publicado dentro da janela fixa de repair mode = 0.

### Bloco B - Criterios de transparencia
- resultado de geracao deve indicar claramente se houve impossibilidade de concluir tudo ate hard end date;
- quando houver impossibilidade, deve haver contexto de carga remanescente.

### Bloco C - Criterios de qualidade
- metricas soft devem ser reportadas de forma comparavel entre execucoes;
- melhoria soft e desejavel, mas nao bloqueia publicacao se hard estiver 100% valido.

## Explicacao teorica

Hard constraints representam regras de realidade fisica e organizacional.
Soft objectives representam preferencia de qualidade.
Misturar os dois leva a horarios "bonitos" mas inviaveis.

## Explicacao pratica

Se existir um unico conflito de professor:
- o horario e rejeitado, mesmo que reduza furos.

Se dois planos forem hard-validos:
- escolhe-se o que melhor reduz furos e desvio da target end date.

## Exemplo operacional

Cenario:
- plano A: zero conflitos, fim em data target + 2 semanas, poucos furos.
- plano B: zero conflitos, fim em data target + 1 semana, mais furos.

Decisao:
- ambos sao validos hard;
- escolha depende do compromisso de qualidade definido pela escola, sem quebrar hard.

## Impacto por layer

### Interface
- deve expor resultado de validacao hard e resumo de metricas soft.

### Regras de negocio
- aplica prioridade hard > soft em toda decisao de geracao.

### Base de dados
- persiste resultados, justificacoes e estado de execucao sem reescrever historico passado.

## Contrato de execucao atomica e cancelamento (Alpha V1 - Ponto 14)

### What
- o motor passou a suportar cancelamento cooperativo durante FETCH, SOLVING, EXPANDING e SAVING;
- o fluxo reforca persistencia atomica: sem "meio horario" gravado.

### Who
- cancelamento e iniciado por admin na interface;
- worker aplica regra de cancelamento sem quebrar isolamento por tenant;
- decisao final de aceitar/nao aceitar resultado continua no backend com regras de dominio.

### Where
- aplicavel ao pipeline completo da geracao (task assincrona) por organizacao;
- sem alterar o principio de que ocorrencias executadas sao historico imutavel.

### When
- valido para geracao `full` e `repair`;
- checkpoints de cancelamento existem antes e durante etapas potencialmente longas;
- em deteccao de cancelamento, a task encerra com rollback do estado transacional em curso.

### Why
- garantir confiabilidade operacional: ou horario completo e consistente, ou nenhuma escrita final;
- reduzir risco de inconsistencias quando existe cancelamento tardio durante gravacao.

### Regras de negocio obrigatorias
1. Cancelamento nunca pode produzir persistencia parcial do horario.
2. Excecao de cancelamento deve levar a rollback total da transacao aberta.
3. Em `full`, limpeza de janela e escrita nova pertencem ao mesmo commit final.
4. Em `repair`, rascunho so fica visivel apos commit final com sucesso.
5. Registos historicos de execucao (ocorrencias) nao sao mutados por cancelamento de geracao.

### Transparencia de resultado
- task cancelada devolve estado de negocio `Canceled` com detalhe operacional explicito;
- quando hard end date impede concluir toda a carga, resultado deve indicar carga remanescente de forma transparente.

### 4 pilares (verificacao)
- Otimizacao: checkpoints evitam processamento inutil apos pedido de cancelamento.
- Estabilidade: rollback total impede estados intermédios inconsistentes.
- Escalabilidade: comportamento deterministico permite operar com multiplas tasks sem degradar consistencia.
- Seguranca: cancelamento respeita ownership por organizacao no fluxo API->worker.