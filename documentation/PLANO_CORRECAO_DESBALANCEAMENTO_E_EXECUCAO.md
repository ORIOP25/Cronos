# Plano de Correcao do Desbalanceamento e Execucao Guiada

## 1. Contexto e Problema

O sistema de geracao de horarios em Ensino Profissional e dinamico por natureza. A cada semana, o agendamento deve refletir:
- modulos ativos por turma;
- disponibilidade de professores;
- conflito de salas/turmas/professores;
- continuidade realista da carga letiva.

Nos testes de escala alargada, foram observados sintomas de incoerencia:
- percentagens de progresso demasiado uniformes entre turmas/disciplina;
- classes com grelha semanal vazia enquanto outras ficam sobrecarregadas;
- slots duplicados na mesma semana para o mesmo professor/timeslot;
- no frontend, possivel ocultacao de colisoes quando existem multiplos registos para a mesma celula.

## 2. Causas-Raiz Confirmadas

### 2.1 Progresso inicial artificialmente uniforme
O seed de escala inicializa `ClassProgress` por regra fixa de ano/modulo, produzindo padrao repetitivo. Isso causa percepcao de progresso "igual" antes de ocorrencias reais.

### 2.2 Persistencia nao totalmente idempotente na janela ativa
A limpeza antiga removia apenas futuro (`date > today`) e nao garantia substituicao completa da janela efetivamente regenerada.

Impacto:
- regeneracoes sucessivas na semana podem acumular registos ativos em datas dentro da janela atual;
- visualizacao semanal passa a mostrar comportamento inconsistente.

### 2.3 Protecao insuficiente contra conflitos herdados
Mesmo com solver valido por execucao, conflitos historicos podem permanecer em base se nao forem removidos por chave funcional (professor/turma/timeslot/data).

### 2.4 Frontend com mapa 1:1 por celula
A grelha semanal colapsa para um unico slot por chave `day:start`, ocultando colisoes em vez de as explicitar.

### 2.5 Distribuicao de seed favorece concentracao de carga
Cada turma recebe disciplinas todas associadas ao mesmo professor principal, elevando desequilibrio estrutural.

## 3. Objetivo Final

Ao concluir este plano, espera-se:
1. geracao full idempotente para a janela regenerada;
2. eliminacao de duplicados herdados sem apagar historico confirmado;
3. deteccao explicita de colisoes na grelha;
4. seed com progresso e atribuicao docente mais realistas;
5. melhoria observavel de equilibrio em testes de escala.

## 4. Estrategia de Implementacao (Passo a Passo)

## Passo 1 - Persistencia idempotente por janela

### Alteracoes
- Introduzir limpeza por janela de datas regenerada (inicio/fim), por organizacao.
- Preservar `LessonOccurrence` existente: nao apagar outputs com ocorrencias associadas.
- No `mode=full`, limpar a janela antes de gravar novos `ScheduleOutput` ativos.

### Testes
- Unit/integration backend para validar que:
  - registos na janela sao removidos quando nao confirmados;
  - registos com ocorrencia nao sao removidos;
  - outras organizacoes nao sao afetadas.

### Resultado esperado
- duas geracoes consecutivas para a mesma janela nao acumulam outputs ativos duplicados.

## Passo 2 - Protecao anti-duplicacao por conflito funcional

### Alteracoes
- Antes de inserir um bloco ativo, remover conflitos antigos (mesma data/timeslot) para:
  - mesma turma;
  - mesmo professor;
  - mesma licao.
- Se existir conflito com `LessonOccurrence` confirmado, nao sobrescrever esse slot.

### Testes
- Teste de servico para garantir:
  - conflitos sem ocorrencia sao limpos;
  - conflitos com ocorrencia bloqueiam insercao substitutiva;
  - insercao normal continua funcional.

### Resultado esperado
- nao existem triplicacoes para mesma combinacao professor+data+timeslot no horario ativo.

## Passo 3 - Frontend: visibilidade de colisoes

### Alteracoes
- Substituir mapa `slot unico` por agrupamento de slots por celula.
- Renderizar indicador de colisao quando houver mais de 1 slot na mesma celula.
- Manter acessibilidade e legibilidade da grelha.

### Testes
- Lint frontend.
- Validacao funcional visual: celulas em colisao deixam de parecer "vazias/aleatorias".

### Resultado esperado
- o utilizador identifica imediatamente conflito de dados na celula.

## Passo 4 - Seed: realismo de progresso e distribuicao docente

### Alteracoes
- Introduzir variacao deterministica no progresso inicial por turma/disciplina/modulo.
- Distribuir disciplinas por mais do que um professor por turma (sem quebrar preflight).
- Preservar constraints pedidas: 3 escolas, 30 cursos, 90 turmas, 31 salas/escola.

### Testes
- Execucao do seed de escala.
- Queries de verificacao para:
  - diversidade de progresso medio por turma;
  - ausencia de padrao uniforme por ano;
  - maior distribuicao de carga por docente.

### Resultado esperado
- progresso inicial deixa de apresentar padrao uniforme artificial.

## Passo 5 - Validacao ponta-a-ponta

### Procedimento
1. correr seed de escala;
2. gerar horario full por cada organizacao;
3. recolher metricas SQL:
   - classes vazias por org;
   - min/max/media slots por turma;
   - duplicados por professor/timeslot/data;
   - distribuicao de progresso.

### Criterios de aceite
- duplicados por professor/timeslot/data = 0 (sem contar casos historicos com ocorrencia preservada);
- sem acumulacao apos nova geracao para mesma janela;
- grelha com colisoes explicitadas (quando existirem);
- melhoria de equilibrio e menor assimetria extrema.

## 5. Plano de Testes por Etapa

## Backend (por passo)
- `pytest backend/tests/test_sprint3.py -q`
- `pytest backend/tests/test_solver_logic.py -q`
- novos testes de servico focados em idempotencia e anti-duplicacao.

## Frontend
- `npm --prefix frontend run lint`

## Integracao SQL
- query de duplicados por professor/data/timeslot;
- query de slots por turma por semana;
- query de distribuicao de progresso por org/ano.

## 6. Riscos e Mitigacoes

- Risco: apagar historico relevante.
  - Mitigacao: nao apagar outputs com ocorrencias ligadas.

- Risco: impacto de performance em limpeza de conflitos.
  - Mitigacao: limitar consultas por organizacao+data+timeslot e usar lotes pequenos.

- Risco: mascara de colisao no frontend confundir utilizador.
  - Mitigacao: badge explicita de conflito com tooltip detalhada.

## 7. Estado de Execucao

Este documento serve como guia de execucao e validacao. A implementacao sera realizada sequencialmente, com testes ao final de cada passo e evidencias de resultado esperado.

## 8. Relatorio de Execucao Real (2026-03-24)

### 8.1 Passo 1 executado - Limpeza idempotente por janela

Implementado:
- nova funcao de servico para limpeza por intervalo de datas em horario ativo;
- preservacao de outputs com `LessonOccurrence` associada;
- uso no fluxo `mode=full` antes de gravar a nova solucao.

Testes corridos:
- `docker compose exec -T backend pytest tests/test_sprint3.py -q`
  - resultado final apos ajustes: `27 passed`.
- `docker compose exec -T backend pytest tests/test_solver_logic.py -q`
  - resultado: `5 passed`.

Conclusao:
- comportamento de limpeza por janela validado e sem regressao no solver.

### 8.2 Passo 2 executado - Anti-duplicacao por conflito funcional

Implementado:
- deteccao de conflitos ativos no mesmo `date + timeslot` por:
  - mesma licao, ou
  - mesma turma, ou
  - mesmo professor;
- remocao de conflitos nao confirmados;
- bloqueio de sobrescrita quando o conflito possui ocorrencia confirmada;
- prevencao de insercao duplicada exata (mesma licao/timeslot/data/is_draft).

Testes corridos:
- incluidos novos testes de servico no ficheiro Sprint 3 para:
  - substituir conflito nao confirmado;
  - nao substituir conflito confirmado;
  - manter escopo por organizacao.
- resultado agregado mantido: `27 passed`.

Conclusao:
- protecao anti-duplicacao ativa e validada por testes.

### 8.3 Passo 3 executado - Frontend com visibilidade de colisoes

Implementado:
- grelha semanal passou de mapa 1:1 para agrupamento por celula;
- badge de conflito `Conflito xN` quando existem multiplos slots na mesma celula;
- tooltip consolidada com detalhe por entrada.

Validacao:
- lint global do frontend apresenta erros pre-existentes no repositorio (nao introduzidos nesta tarefa);
- lint dedicado ao ficheiro alterado executado sem erros bloqueantes:
  - `Set-Location frontend; npx eslint src/components/WeekGrid.jsx`.

Conclusao:
- colisoes deixam de ser silenciosamente mascaradas na grelha.

### 8.4 Passo 4 executado - Seed com progresso e carga docente mais realistas

Implementado:
- variacao deterministica de progresso inicial por ano/modulo/entidade;
- distribuicao de disciplinas por varios professores por turma (rotacao), em vez de concentracao total num unico docente;
- manutencao de escala e constraints pedidas (3 escolas, 30 cursos, 90 turmas, 31 salas/escola).

Validacao:
- `docker compose exec -T backend python -m py_compile seed_data_large_scale.py` (ok);
- `docker compose exec -T backend python seed_data_large_scale.py` (ok, seed completo).

Conclusao:
- dataset de teste ficou menos uniforme e mais representativo.

### 8.5 Passo 5 executado - Validacao ponta-a-ponta

Geracao full executada para as 3 organizacoes via Celery task:
- Org 1: Success, 9248 blocos;
- Org 2: Success, 9528 blocos;
- Org 3: Success, 9851 blocos.

Metricas SQL apos geracao:
- duplicados por professor+data+timeslot (ativo): `0` linhas;
- classes vazias na semana atual:
  - Org 1: `0/30`
  - Org 2: `0/30`
  - Org 3: `0/30`
- distribuicao semanal de slots por turma:
  - Org 1: min 2, max 23, media 10.7
  - Org 2: min 5, max 21, media 10.7
  - Org 3: min 3, max 17, media 10.7
- progresso inicial com variancia (std_hours > 0 em todos os anos), eliminando padrao uniforme estrito anterior.

Conclusao final:
- os objetivos desta execucao foram atingidos: eliminacao de duplicacao ativa, equilibrio semanal muito superior entre organizacoes e maior realismo no estado inicial de progresso.

## 9. Complemento - Fairness Explicito e Seed 100% do Zero

### 9.1 Fairness explicito no objetivo do solver

Foi adicionado um bloco de objetivo dedicado a equidade entre turmas:
- penalizacao de desvio da meta semanal agregada por turma (falta e excesso);
- penalizacao de spread normalizado entre pares de turmas para reduzir assimetria de carga.

Interpretacao:
- o solver continua a respeitar hard constraints;
- entre solucoes viaveis, passa a preferir distribuicoes com menor desigualdade relativa entre turmas;
- reduz casos de turmas sobrecarregadas e outras subagendadas sem justificacao estrutural.

### 9.2 Geração desde setembro

A expansao para datas passou a iniciar sempre em `school_start_date`.
Resultado:
- o planeamento deixa de arrancar na semana corrente;
- a solucao cobre o ano letivo desde o inicio ate concluir carga modular remanescente.

### 9.3 Seed com horas totalmente a zero

Politica aplicada:
- todos os `ClassProgress.hours_completed = 0`;
- todos os `ClassProgress.is_completed = False`;
- sem qualquer hora hard-coded de progresso inicial.

Resultado esperado:
- algoritmo planeia de forma independente, sem influencia de progresso predefinido;
- toda a evolucao de conclusao deve decorrer da execucao operacional e ocorrencias registadas.

### 9.4 Testes e validacao desta fase

Checklist:
1. testes unitarios/integracao backend sem regressao;
2. seed recomposto e executado com sucesso;
3. query de sanity para confirmar progresso inicial a zeros;
4. geracao full por organizacao com estado `Success`;
5. queries finais de auditoria (duplicados, classes vazias, distribuicao de carga).

## 10. Dashboard Tecnico de Auditoria Automatica por Geracao

## 10.1 O que e

Um painel tecnico interno que regista e compara, por `generation_id`, a qualidade da solucao gerada.
Nao substitui UI operacional; funciona como observabilidade e controlo de qualidade continuo.

## 10.2 Como funciona

Fluxo sugerido:
1. Geracao termina (Celery task em estado terminal `Success`/`Impossible`/`Error`).
2. Job de auditoria executa queries agregadas e calcula KPIs.
3. Resultado e persistido numa tabela de auditoria por `generation_id`.
4. Dashboard consome API de auditoria e mostra:
  - estado atual;
  - tendencia vs ultima geracao;
  - alertas de regressao.

## 10.3 Informacao que deve ter

Identificacao:
- generation_id
- org_id
- modo (`full`/`repair`)
- timestamp inicio/fim
- duracao total

Integridade:
- duplicados ativos por professor+data+timeslot
- duplicados por turma+data+timeslot
- conflitos bloqueados por ocorrencias confirmadas
- blocos inseridos, removidos, preservados

Cobertura:
- turmas com 0 slots na semana atual
- min/max/media slots por turma
- ocupacao por dia da semana

Fairness:
- desvio medio da carga semanal por turma
- spread de carga normalizada entre turmas
- ranking de turmas mais sub/sobrecarregadas

Curriculo modular:
- minutos restantes agregados por turma/curso
- estimativa de data de conclusao por turma
- modulos ativos por disciplina

Recursos:
- utilizacao por professor
- utilizacao por tipo de sala
- taxa de ocupacao de laboratorios e espacos EF

Confiabilidade:
- motivo de `Impossible` (quando aplicavel)
- fase onde ocorreu `Error` (`FETCHING`/`SOLVING`/`EXPANDING`/`SAVING`)
- erros tecnicos agregados

## 10.4 Alertas automaticos recomendados

- `critical`: duplicados ativos > 0
- `high`: turmas vazias > 0
- `medium`: spread fairness acima do limiar
- `medium`: carga de docente acima de limiar semanal
- `low`: regressao de qualidade vs geracao anterior

## 10.5 Resultado esperado

Com este dashboard, cada geracao deixa um rasto auditavel e comparavel, permitindo:
- detecao precoce de regressao;
- explicabilidade tecnica da qualidade do horario;
- decisao rapida para aprovar, rejeitar ou regenerar.

## 11. Escalada de Complexidade do Seed (Fase Atual)

Perfil aplicado:
- 10 cursos por escola (inalterado);
- 3 turmas por curso (inalterado);
- 8 disciplinas por turma;
- 5 a 6 modulos por disciplina (variacao deterministica);
- 25h a 35h por modulo (variacao deterministica);
- progresso inicial totalmente a zero em todos os modulos;
- ratio docente recalculado para 1 professor por 6 disciplinas.

Objetivo:
- aumentar o espaco de solucao do solver e o grau de competicao por recursos;
- validar robustez com carga curricular mais proxima de cenario exigente.

## 12. Dashboard Tecnico Entregue (Implementacao)

Backend:
- endpoint para listar geracoes auditaveis (`/schedule/audit/generations`);
- endpoint para resumo tecnico por geracao (`/schedule/audit/summary`), com fallback para geracao mais recente.

Frontend:
- nova pagina de auditoria tecnica com:
  - seletor de geracao,
  - KPIs de integridade,
  - indicadores de fairness semanal,
  - distribuicao de carga docente,
  - utilizacao por tipo de sala.

Navegacao:
- nova entrada de menu: "Auditoria Tecnica".
