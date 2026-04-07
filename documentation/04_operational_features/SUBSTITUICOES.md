# Substituicoes

## Objetivo
Definir substituicoes seguras para manter continuidade letiva sem quebrar regras hard do sistema.

## 5 Ws

### What
Processo de trocar o docente previsto por docente elegivel em aula afetada por indisponibilidade.

### Who
admin aprova e executa decisao operacional.
professor permanece com escopo de disponibilidade e consulta do proprio horario.

### Where
Sempre no mesmo tenant (organizacao).

### When
Durante operacao diaria, apos identificacao de falta ou necessidade de ajuste imediato.

### Why
Manter execucao curricular e reduzir impacto operacional sem perder rastreabilidade.

## Validacoes de elegibilidade (confirmadas)

1. Mesmo tenant (same organization).
2. Docente substituto qualificado/permitido.
3. Sem conflito no slot de substituicao.
4. Atualizacao consistente de progresso/accounting apos decisao.

## Estados de ocorrencia associados
- GAP
- GIVEN
- SUBSTITUTED

## Fluxo pratico minimo

1. Aula planeada sofre indisponibilidade do docente previsto.
2. admin avalia possibilidade de substituicao.
3. Sistema valida elegibilidade e conflitos.
4. Se elegivel, regista substituicao com estado explicito.
5. Se nao elegivel, regista alternativa operacional sem mascarar historico.

## Exemplo pratico

Cenario:
- professor P1 nao pode lecionar aula na sexta 14:00.
- admin analisa professor P2 como substituto.

Verificacoes:
- P2 pertence a mesma organizacao;
- P2 esta apto para a disciplina;
- P2 nao esta ocupado no mesmo slot.

Resultado:
- ocorrencia registada como SUBSTITUTED quando validacoes passam;
- historico preserva quem estava previsto e quem executou.

## Pontos ainda a definir (nao fechados)
- politica detalhada de prioridade entre multiplos substitutos elegiveis;
- regra exata de ponderacao quando substituicao compete com objetivo soft de reduzir furos.

## Impacto por layer

### Interface
- admin precisa de validacoes visiveis antes de confirmar substituicao.

### Regras de negocio
- substituicao so ocorre apos checks de elegibilidade e conflito.

### Base de dados
- ocorrencia e decisoes devem ficar auditaveis e imutaveis.