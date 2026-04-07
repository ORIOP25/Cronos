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