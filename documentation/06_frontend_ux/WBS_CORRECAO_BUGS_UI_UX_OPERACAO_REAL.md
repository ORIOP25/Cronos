# WBS Correcao de Bugs UI/UX - Operacao Real (Alpha)

## Estado deste documento
Documento de planeamento tecnico-operacional.
✅ **Todas as correções planeadas neste WBS foram aplicadas a 03 Maio 2026.**
Ver `documentation/auditoria-frontend-ui-ux.md` para o registo completo de 46 correções implementadas.

## Objetivo
Definir um plano WBS para corrigir bugs de experiencia real (UI/UX) que criam ambiguidade operacional para admin e professores, com foco em:
- consistencia de estados de ocorrencia (pendente vs decidida);
- previsibilidade da lista operacional;
- linguagem clara para utilizadores nao tecnicos;
- alinhamento com regras canonicas de faltas/substituicoes e historico imutavel.

## 5 Ws da iniciativa

### What
Correcao orientada a UX operacional em ecras de horarios, ocorrencias e configuracao, com eliminacao de ambiguidades de estado e de texto tecnico para o utilizador final.

### Who
- Admin escolar: principal operador de faltas/substituicoes e geracao.
- Professor: consulta semanal e feedback de estado do horario.
- Equipa tecnica: implementa e valida sem quebrar regras hard.

### Where
- Layer Interface: `frontend/src/pages/*`, `frontend/src/components/WeekGrid.jsx`.
- Layer Regras de negocio: servicos de ocorrencias e contrato de estado.
- Layer Base de dados: sem mudanca estrutural prevista, mantendo imutabilidade e isolamento por tenant.

### When
Execucao recomendada em 3 fases curtas:
1. Fase A (Quick Wins de copy e estado visual): 2-3 dias uteis.
2. Fase B (consistencia de ordenacao e regra de acao em blocos passados): 2-4 dias uteis.
3. Fase C (testes, regressao e validacao com utilizadores): 2-3 dias uteis.

Total estimado: 6-10 dias uteis (dependente de decisoes "a definir").

### Why
Porque erros pequenos de linguagem e classificacao visual geram decisoes operacionais erradas, aumentam retrabalho administrativo e reduzem confianca no produto premium.

## Principios obrigatorios (4 pilares)
Qualquer implementacao deste WBS deve proteger simultaneamente:
1. Otimizacao: reduzir tempo de decisao operacional e retrabalho.
2. Estabilidade: evitar regressao no fluxo diario de faltas/substituicoes.
3. Escalabilidade: comportamento previsivel em escolas com volume elevado de ocorrencias.
4. Seguranca: manter tenant isolation, role boundaries e historico imutavel.

## Evidencia tecnica atual (base factual)

### E1 - Ocorrencia pode nascer "aberta" mas com status GIVEN
- `backend/app/services/occurrence_service.py` cria ocorrencia com:
  - `status=models.LessonOccurrenceStatus.GIVEN`
  - `decided_at=None`
- Referencia: bloco de criacao em `create_occurrence_from_block_sync`.

### E2 - API semanal envia estado e decisao separados
- `backend/app/services/schedule_service.py` devolve simultaneamente:
  - `occurrence_status`
  - `occurrence_decided_at`
  - `can_create_occurrence`
  - `can_decide_occurrence`

### E3 - Grelha semanal privilegia occurrence_status para label
- `frontend/src/components/WeekGrid.jsx`:
  - se `slot.occurrence_status` existe, mostra label do estado (ex.: "Dado");
  - so mostra "Pendente" quando nao ha `occurrence_status` e o bloco e passado.

### E4 - Lista de ocorrencias mostra badge por status e resumo por decided_at
- `frontend/src/pages/Occurrences.jsx`:
  - badge usa `STATUS_LABELS[occ.status]` (ex.: "Dada");
  - resumo usa `buildDecisionSummary` e mostra "Pendente de decisao do admin" quando `decided_at` e nulo.

### E5 - Lista operacional sem ordenacao explicita no frontend
- `frontend/src/pages/Occurrences.jsx` usa:
  - `const sortedOccurrences = useMemo(() => [...occurrences], [occurrences])`

### E6 - Linguagem tecnica exposta ao utilizador final
Exemplos confirmados:
- `frontend/src/pages/Schedules.jsx`: "CP-SAT a otimizar", "Visualize e gere horarios por CP-SAT".
- `frontend/src/pages/MySchedules.jsx`: "hard end date".
- `frontend/src/pages/SchoolConfig.jsx`: "Benchmark para o solver", "Hard stop".
- `frontend/src/pages/ScheduleAuditDashboard.jsx`: "Dashboard Tecnico de Auditoria por Geracao".
- `frontend/src/pages/Occurrences.jsx`: "Sem execucao (GAP)", "admin #id".

## Backlog priorizado de bugs UI/UX (impacto real)

### UX-01 (Critico) - Estado pendente pode aparecer como estado final
Sintoma:
- Ocorrencia ainda sem decisao final (`decided_at = null`) pode aparecer com badge "Dada".

Impacto no utilizador:
- Admin interpreta que a decisao ja foi fechada e pode deixar ocorrencia sem tratamento correto.

Causa provavel:
- A UI usa `status` como estado final visual, enquanto a abertura/fecho real depende de `decided_at`.

Resultado esperado:
- Enquanto `decided_at` for nulo, UI deve mostrar estado "Pendente de decisao" (ou equivalente definido), independentemente de `status` tecnico interno.

### UX-02 (Alto) - Lista de ocorrencias pode variar de ordem
Sintoma:
- A lista visivel pode mudar ordem conforme resposta da API/cache sem criterio explicito no frontend.

Impacto no utilizador:
- Dificulta triagem em momentos de pressao operacional.

Causa provavel:
- Falta de ordenacao deterministica explicita no frontend.

Resultado esperado:
- Ordenacao unica e previsivel: data asc, inicio do slot asc, id asc.

### UX-03 (Alto) - Acao operacional bloqueada em bloco passado
Sintoma:
- Nao e possivel abrir acao operacional para blocos passados na grelha.

Impacto no utilizador:
- Admin pode perder janela de registo manual imediato apos a aula, dependendo do momento do reporte.

Causa provavel:
- Condicao `!slot.is_past` na habilitacao da acao.

Resultado esperado:
- Regra explicita e uniforme para blocos passados.

Estado de decisao:
- a definir com produto/operacao:
  - opcao A: permitir criacao/decisao em blocos passados dentro de janela controlada;
  - opcao B: manter bloqueio e reforcar mensagem orientando para fluxo automatico diario.

### UX-04 (Medio) - Terminologia tecnica em ecras operacionais
Sintoma:
- Textos exibem termos de engenharia (CP-SAT, solver, hard stop, hard end date, GAP).

Impacto no utilizador:
- Aumenta carga cognitiva e reduz clareza para equipas administrativas.

Causa provavel:
- Copy tecnica foi mantida em ecras de operacao final.

Resultado esperado:
- Linguagem funcional, simples e orientada a tarefa administrativa.

### UX-05 (Medio) - Mistura de estado tecnico com estado de negocio no mesmo bloco textual
Sintoma:
- "Execucao / Decisao Final" pode combinar label tecnica e texto de pendencia no mesmo registo.

Impacto no utilizador:
- Mensagem contraditoria no mesmo item.

Causa provavel:
- Falta de modelo visual unico para "aberta" vs "fechada".

Resultado esperado:
- Separacao clara entre:
  - estado operacional da ocorrencia (aberta/fechada);
  - resultado final (GIVEN/GAP/SUBSTITUTED) apenas quando fechada.

## WBS detalhado

### 1.0 Modelo canonico de estado visual de ocorrencia

#### 1.1 Definir contrato de estado UI
Implementacao:
- formalizar estado visual primario por ocorrencia:
  - `OPEN_PENDING` quando `decided_at == null`;
  - `CLOSED_GIVEN` quando `decided_at != null && status == GIVEN`;
  - `CLOSED_GAP` quando `decided_at != null && status == GAP`;
  - `CLOSED_SUBSTITUTED` quando `decided_at != null && status == SUBSTITUTED`.
- preservar `status` tecnico interno para accounting sem expor como decisao final quando aberta.

Testes obrigatorios:
- ocorrencia aberta nunca exibe "Dada/Furo/Substituida" como estado final.
- ocorrencia fechada exibe estado final coerente com `status`.

Edge cases:
- resposta parcial sem `decided_at` (fallback seguro).
- valor de status desconhecido (fallback visual sem quebra).

#### 1.2 Aplicar contrato na grelha semanal
Implementacao:
- ajustar label da celula para privilegiar aberto/fechado e evitar ambiguidade.
- manter codificacao de cores consistente com legenda e contexto.

Testes obrigatorios:
- celula com ocorrencia aberta mostra "Pendente" (ou label definida).
- celula com ocorrencia fechada mostra resultado final correto.

Edge cases:
- colisoes de blocos no mesmo slot.
- carregamento parcial de week slots.

#### 1.3 Aplicar contrato no painel de ocorrencias
Implementacao:
- badge principal passa a representar estado operacional aberto/fechado.
- decisao final aparece como detalhe quando fechada.

Testes obrigatorios:
- filtro de pendentes considera `decided_at == null`.
- filtro de resolvidas considera `decided_at != null`.

Edge cases:
- transicao de pendente para resolvida em polling/refetch.
- retries de PATCH sem duplicar feedback.

### 2.0 Ordenacao deterministica e triagem previsivel

#### 2.1 Ordenacao canonica na lista operacional
Implementacao:
- aplicar sort explicito por `date`, `timeslot.start_time`, `id`.
- definir compare function explicita para estabilidade.

Testes obrigatorios:
- lista reproduzivel com mesmo input.
- empate em data/slot resolve por id.

Edge cases:
- ocorrencias sem `timeslot` (fallback deterministico).
- mistura de formatos de data invalidos (defensive fallback).

#### 2.2 Alinhamento com regra documental de faltas
Implementacao:
- validar que ordenacao implementada coincide com regra oficial em documentacao de faltas.

Testes obrigatorios:
- teste de contrato frontend/backend para ordenacao final apresentada.

Edge cases:
- ordenacao da API divergente da UI (UI deve manter previsibilidade final).

### 3.0 Regra de acao em blocos passados

#### 3.1 Fechar decisao de produto
Implementacao:
- fechar criterio unico para permitir ou bloquear acao operacional em bloco passado.

Decisao fechada (2026-04-17):
- opcao A aprovada: permitir acao operacional em blocos passados quando o bloco tiver contexto operacional valido (`schedule_output_id` + `date`) e houver acao legitima (`can_create_occurrence` ou `can_decide_occurrence`).
- a janela efetiva fica limitada pelo proprio horario publicado e pelas regras de imutabilidade ja existentes (ocorrencia fechada continua sem edicao destrutiva).
- o frontend nao deve bloquear por `is_past`; deve seguir flags operacionais devolvidas pelo backend.

Testes obrigatorios:
- cobertura da regra escolhida (A ou B) em cenario diario.

Edge cases:
- aula acabada ha poucos minutos.
- ocorrencia ja criada automaticamente no fecho diario.

#### 3.2 Mensagem de orientacao operacional
Implementacao:
- sempre que a acao for bloqueada, mostrar mensagem clara com proximo passo.

Testes obrigatorios:
- utilizador entende o motivo do bloqueio e a acao seguinte.

Edge cases:
- bloqueio por role vs bloqueio por regra temporal.

### 4.0 Linguagem nao tecnica orientada ao utilizador

#### 4.1 Criar glossario de copy operacional
Implementacao:
- substituir termos tecnicos por texto funcional em ecras admin/professor.

Mapa inicial recomendado:
- "CP-SAT a otimizar" -> "A calcular o melhor horario para a escola".
- "Visualize e gere horarios por CP-SAT" -> "Consulte e atualize os horarios da escola".
- "hard end date" -> "data limite do ano letivo".
- "Benchmark para o solver" -> "data de referencia para concluir o planeamento".
- "Hard stop" -> "limite obrigatorio: nao ha aulas apos esta data".
- "Dashboard Tecnico de Auditoria por Geracao" -> "Painel de verificacao de horarios".
- "Sem execucao (GAP)" -> "Aula nao realizada".
- "admin #id" -> "equipa administrativa".

Testes obrigatorios:
- varredura de UI para garantir remocao de termos tecnicos definidos.
- validacao semantica por 2 perfis (admin e professor).

Edge cases:
- ecras de auditoria com detalhe tecnico interno devem manter-se admin-only e nunca ser rota principal de professor.

#### 4.2 Alinhar mensagens de erro e loading
Implementacao:
- transformar mensagens de pipeline tecnico em mensagens de tarefa.
- manter detalhe tecnico apenas em logs/admin tecnico quando necessario.

Testes obrigatorios:
- erros comuns apresentam acao recomendada ao utilizador.

Edge cases:
- falhas transientes de rede sem detalhe backend.

### 5.0 Validacao, qualidade e rollout seguro

#### 5.1 Testes automatizados
Implementacao:
- atualizar testes unitarios/componentes para novo contrato visual.
- incluir regressao para classificacao pendente e ordenacao deterministica.

Testes obrigatorios:
- `WeekGrid`: estado aberto/fechado coerente.
- `Occurrences`: badge + resumo sem contradicao.
- `Schedules` e `MySchedules`: copy nao tecnica nas mensagens alvo.

Edge cases:
- regressao de traducoes e strings em snapshots.

#### 5.2 Script de validacao manual (operacao real)
Implementacao:
- roteiro curto para admin validar:
  1. criar ocorrencia;
  2. confirmar que aparece como pendente;
  3. decidir GAP/GIVEN/SUBSTITUTED;
  4. confirmar mudanca para resolvida e impacto visual coerente.

Testes obrigatorios:
- execucao completa sem ambiguidade de estado.

Edge cases:
- duas admins em paralelo na mesma ocorrencia (deve manter imutabilidade apos fecho).

## Criterios de saida
A iniciativa e considerada concluida quando:
1. nenhuma ocorrencia aberta aparece como "Dada", "Furo" ou "Substituida" em estado final.
2. lista de ocorrencias mantem ordenacao deterministica em 100% dos reloads com mesmo dataset.
3. textos tecnicos alvo deixam de aparecer nos ecras operacionais definidos.
4. fluxo operacional continua a cumprir role boundaries e tenant isolation.
5. regressao automatizada e validacao manual passam sem bloqueio critico.

## Impacto por layer (clean architecture)

### Interface
- melhora clareza de estado, reduz contradicoes visuais e simplifica linguagem.

### Regras de negocio
- reforca separacao entre estado tecnico interno e estado de decisao operacional.
- preserva invariantes de ocorrencia aberta/fechada por `decided_at`.

### Base de dados
- sem mudancas estruturais obrigatorias previstas.
- mantem historico imutavel, contabilizacao transacional e isolamento por `organization_id`.

## Riscos e mitigacao

R1. Mudanca visual sem alinhamento de produto para blocos passados.
- Mitigacao: fechar decisao UX-03 antes de desenvolver e registrar decisao no documento de faltas.

R2. Copy simplificada perder precisao operacional.
- Mitigacao: validar com admin real e manter glosario canonico versionado.

R3. Regressao em testes existentes de strings.
- Mitigacao: atualizar testes de forma controlada e executar suite focada de frontend.

## Pendencias "a definir"
Nao existem pendencias abertas para este plano base.

Decisoes fechadas nesta revisao:
1. UX-03: permitir acao operacional em bloco passado (opcao A), sem bloqueio por `is_past` no frontend, respeitando flags e invariantes backend.
2. Escopo do ecran de auditoria: admin-only, com linguagem funcional no cabecalho e texto tecnico apenas como contexto secundario.
3. Terminologia final de estado aberto: "Pendente de decisao".

## Protocolo de sincronizacao documental (obrigatorio)
Quando a implementacao comecar:
1. atualizar `documentation/06_frontend_ux/UX_CONSISTENCY_SCHEDULES.md` com o novo contrato visual.
2. atualizar `documentation/04_operational_features/FALTAS.md` se UX-03 for decidido.
3. atualizar `documentation/05_backend_api/ENDPOINT_STANDARDS.md` se houver ajuste contratual de payload/resposta.
4. manter itens nao fechados marcados como "a definir".
# Historical UI/UX WBS

This document is retained as pre-beta history. References to `ScheduleAuditDashboard` are not current beta behavior; the page was removed in the 2026-07-05 baseline cleanup.
