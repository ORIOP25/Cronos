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

## Fluxo pratico minimo

1. Aula existe no planeamento publicado.
2. Ocorre evento de falta.
3. admin decide encaminhamento operacional.
4. Sistema regista ocorrencia com estado explicito.
5. Sistema preserva historico sem apagar o planeado original.

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

## Pontos ainda a definir (nao fechados)
- formula matematica exata de impacto em progresso/divida por estado;
- regras de prioridade quando houver multiplas faltas concorrentes no mesmo periodo.

## Impacto por layer

### Interface
- admin precisa de fluxo claro para decidir estado da ocorrencia.

### Regras de negocio
- deve manter separacao entre planeado e executado;
- deve aplicar estados de ocorrencia de forma consistente.

### Base de dados
- deve registar ocorrencia de modo imutavel e tenant-scoped.