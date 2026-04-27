# WBS Super Detalhada - Implementacao Solver V2 Local (2026-04-20)

## Estado do documento
- Tipo: WBS executavel em microtarefas (MVP local).
- Escopo: implementacao ponta a ponta do Solver V2 em Docker local, single-user.
- Objetivo: reduzir risco tecnico por entregas pequenas, testaveis e cumulativas.

## 1. Objetivo final desta WBS
Implementar o Solver V2 com comportamento adaptativo por data real, mantendo:
1. hard constraints inviolaveis;
2. tenant isolation em todas as leituras/escritas;
3. historico executado imutavel;
4. geracao manual com fluxo de draft seguro;
5. decisao operacional por comparacao estatistica (nao aula-a-aula obrigatoria).

## 2. Decisoes fechadas que esta WBS respeita
1. Prioridade maxima: terminar aulas o mais cedo possivel.
2. Horizonte hibrido: janela rolling principal de 8 semanas + viabilidade ate hard_end_date.
3. Backlog unico de horas por alocar (sem separar divida normal/vencida).
4. Objetivo lexicografico.
5. Desempate: menor dispersao de fecho entre turmas, depois menor churn, depois menos gaps.
6. Perfil agressivo: churn fora da janela congelada pode chegar a 100% se melhorar conclusao.
7. Draft pendente bloqueia nova geracao.
8. Rejeicao de draft apaga draft sem sequelas no plano publicado.
9. Aprovacao usa painel estatistico (projected end, spread, churn, blocos alterados, backlog, gaps).

## 3. Escopo e nao escopo

### Em escopo
1. Backend solver (core + tasks + service + endpoints relacionados).
2. Persistencia e ciclo de vida de draft (gerar, aprovar, rejeitar).
3. Testes unitarios, integracao e regressao orientados a Solver V2.
4. Validacao manual click-by-click em ambiente local.

### Fora de escopo desta iteracao
1. Quotas/SLA/autoscaling para multi-cliente.
2. Otimizacao de infraestrutura cloud para producao 1.0.
3. Revisao de UX premium completa fora da pagina de decisao do draft.

## 4. Regras de execucao deste plano
1. Cada microtarefa deve terminar com teste automatizado ou validacao manual objetiva.
2. Sem avancar para a microtarefa seguinte se o criterio de aceite da atual falhar.
3. Todas as mudancas devem preservar hard constraints e tenant isolation.
4. Se houver conflito entre objetivo soft e hard constraint, hard vence sempre.

## 5. Definicao de pronto (DoD global)
1. `POST /api/v1/schedule/generate` com Solver V2 gera draft valido sem violar hard.
2. Fluxo draft funciona ponta a ponta: gerar -> comparar resumo estatistico -> aprovar/rejeitar.
3. Rejeicao remove draft sem efeitos no publicado.
4. Nova geracao e bloqueada enquanto houver draft pendente.
5. Suite de testes alvo desta WBS passa sem regressao critica.
6. Validacao manual local concluida com checklist completa.

## 6. Sequencia macro e dependencias
1. Fase A: Preparacao e baseline local.
2. Fase B: Modelo de demanda/backlog e regras de modulo.
3. Fase C: Horizonte hibrido e preflight.
4. Fase D: Universo de candidatos e pruning hard-first.
5. Fase E: Solver V2 lexicografico.
6. Fase F: Expansao/adaptacao e residual transparente.
7. Fase G: Persistencia de draft e ciclo de vida.
8. Fase H: Painel estatistico de comparacao draft vs publicado.
9. Fase I: Testes finais, regressao e validacao manual.

Cada fase depende da anterior para garantir progresso cumulativo e compativel.

---

## 7. Microtarefas detalhadas (ponta a ponta)

## Fase A - Preparacao e baseline local

### A.01 - Congelar contrato de configuracao V2
- Objetivo: definir chaves e defaults do Solver V2 local.
- Implementacao:
1. Introduzir constantes explicitas para janela rolling (8 semanas) e modo lexicografico.
2. Definir toggle interno de ativacao V2 (por organizacao ou config local).
3. Garantir fallback seguro para comportamento atual quando V2 desativado.
- Ficheiros alvo:
1. `backend/app/config.py`
2. `backend/app/services/settings_service.py` (se necessario)
- Testes:
1. unitario de leitura de defaults e toggle.
- Criterio de aceite:
1. V2 pode ser ligado/desligado sem quebrar endpoint de geracao.

### A.02 - Baseline funcional antes da migracao
- Objetivo: fixar ponto de comparacao para evitar regressao silenciosa.
- Implementacao:
1. Executar seed `small-realistic` com reset.
2. Gerar horario em modo atual e guardar metricas base.
3. Registar output baseline (runtime, projected end, blocos gerados).
- Comandos:
1. `docker compose exec backend python seed_data.py --profile small-realistic --reset`
2. `docker compose exec backend pytest tests/test_solver_logic.py -q`
- Criterio de aceite:
1. baseline documentada e reproduzivel localmente.

### A.03 - Guardrail de versao do solver por run
- Objetivo: saber em cada execucao se foi V1 ou V2.
- Implementacao:
1. Adicionar campo de versao em metadados da geracao.
2. Persistir no estado final da task e no resumo retornado.
- Ficheiros alvo:
1. `backend/app/solver_tasks.py`
2. `backend/app/api/v1/endpoints/schedule.py`
- Testes:
1. teste de endpoint validando presenca do campo `solver_version`.
- Criterio de aceite:
1. toda geracao devolve versao explicita do motor.

## Fase B - Modelo de demanda e backlog unico

### B.01 - Estrutura de demanda V2
- Objetivo: ter estrutura unica de demanda por class+subject+module ativo.
- Implementacao:
1. Criar estrutura interna (dataclass ou equivalente) para demanda V2.
2. Incluir campos minimos: class_id, subject_id, module_id, backlog_minutes, target_end_date.
3. Garantir valores sempre inteiros para minutos.
- Ficheiros alvo:
1. `backend/app/solver_tasks.py`
2. `backend/app/core/solver_engine.py` ou novo modulo V2.
- Testes:
1. unitario de construcao de demanda com dados minimos.
- Criterio de aceite:
1. demanda e criada sem depender de conceito de divida vencida.

### B.02 - Consolidacao de backlog unico
- Objetivo: remover bifurcacao entre tipos de divida.
- Implementacao:
1. substituir calculos que separam divida por backlog unico.
2. normalizar backlog como `max(0, remaining_minutes)`.
3. ajustar resumo operacional para refletir backlog unico.
- Ficheiros alvo:
1. `backend/app/solver_tasks.py`
2. `backend/app/services/occurrence_service.py` (apenas se impactar reconciliacao)
- Testes:
1. unitario com cenarios mistos garantindo saida unica de backlog.
- Criterio de aceite:
1. nao existe ramo logico por overdue vs non-overdue no caminho V2.

### B.03 - Regra de fecho de modulo e transicao imediata
- Objetivo: validar modulo fecha a 100% e proximo pode iniciar imediatamente.
- Implementacao:
1. aplicar fecho quando `hours_completed >= hours_total`.
2. habilitar modulo seguinte no mesmo ciclo de geracao quando elegivel.
3. preservar ordem estrita de modulos.
- Ficheiros alvo:
1. `backend/app/services/module_service.py`
2. `backend/app/solver_tasks.py`
- Testes:
1. unitario: modulo fecha a 100%.
2. integracao: modulo seguinte inicia sem intervalo artificial.
- Criterio de aceite:
1. transicao imediata ocorre sem quebrar ordem de modulos.

### B.04 - Testes unitarios dedicados da fase B
- Objetivo: fechar base de dominio antes de mexer no solve.
- Implementacao:
1. criar `backend/tests/test_solver_v2_demand_builder.py`.
2. cobrir backlog unico, arredondamento de minutos e transicao de modulo.
- Criterio de aceite:
1. testes da fase B verdes e estaveis em 3 execucoes consecutivas.

## Fase C - Horizonte hibrido e preflight

### C.01 - Builder da janela rolling de 8 semanas
- Objetivo: gerar janela principal de otimizacao com data real.
- Implementacao:
1. iniciar em `max(school_start_date, frozen_until + 1 dia)` quando repair.
2. limitar janela principal a 8 semanas corridas.
3. excluir datas bloqueadas por calendario.
- Ficheiros alvo:
1. `backend/app/solver_tasks.py`
- Testes:
1. unitario com calendario e feriados.
- Criterio de aceite:
1. janela principal sempre correta para full e repair.

### C.02 - Validador de viabilidade ate hard_end_date
- Objetivo: garantir transparencia quando horizonte principal nao chega.
- Implementacao:
1. calcular capacidade teorica ate hard end.
2. comparar com backlog total apos filtros hard.
3. marcar residual esperado quando capacidade insuficiente.
- Ficheiros alvo:
1. `backend/app/solver_tasks.py`
2. `backend/app/api/v1/endpoints/schedule.py`
- Testes:
1. integracao: caso viavel e caso inviavel com mensagem explicita.
- Criterio de aceite:
1. preflight reporta claramente impossibilidade sem erro ambiguo.

### C.03 - Ajuste de contrato do endpoint de geracao
- Objetivo: refletir no contrato API a logica do horizonte hibrido.
- Implementacao:
1. incluir metadados da janela principal e verificacao ate hard end.
2. padronizar resposta preflight_failed com problemas claros.
- Ficheiros alvo:
1. `backend/app/api/v1/endpoints/schedule.py`
2. `backend/app/schemas.py`
- Testes:
1. atualizar `backend/tests/test_schedule_generate_preflight.py`.
- Criterio de aceite:
1. contrato API previsivel e alinhado com endpoint standards.

### C.04 - Regressao da fase C
- Objetivo: evitar quebra dos cenarios atuais de preflight.
- Testes:
1. `docker compose exec backend pytest tests/test_schedule_generate_preflight.py -q`
- Criterio de aceite:
1. sem regressao de status code e mensagens de erro.

## Fase D - Universo de candidatos e pruning hard-first

### D.01 - Gerador de candidatos por data real
- Objetivo: construir universo inicial tarefa+slot+sala.
- Implementacao:
1. expandir candidatos por dia real na janela rolling.
2. anexar professor, turma e sala em estrutura unica.
3. manter chaves deterministicas para rastreio.
- Ficheiros alvo:
1. `backend/app/solver_tasks.py`
2. novo modulo sugerido: `backend/app/core/solver_v2_candidates.py`
- Testes:
1. unitario de cardinalidade esperada em dataset pequeno.
- Criterio de aceite:
1. universo inicial reproduzivel com mesma seed.

### D.02 - Filtro hard de conflitos
- Objetivo: remover candidatos inviaveis antes do CP-SAT.
- Implementacao:
1. excluir conflito professor.
2. excluir conflito turma.
3. excluir conflito sala.
- Testes:
1. unitarios por tipo de conflito.
- Criterio de aceite:
1. nenhum candidato hard-invalido chega ao modelo.

### D.03 - Filtro hard de tipo de sala, impossible e almoco
- Objetivo: aplicar todos hard constraints restantes no pruning.
- Implementacao:
1. validar `required_room_type`.
2. remover slots `IMPOSSIBLE`.
3. aplicar regra de almoco hard quando configurada.
- Testes:
1. unitarios dedicados por regra.
- Criterio de aceite:
1. pruning hard-first completo e consistente com contrato canonico.

### D.04 - Telemetria de pruning
- Objetivo: medir o ganho da reducao do espaco de procura.
- Implementacao:
1. guardar contagem antes/depois do pruning.
2. expor ratio no resumo da task.
- Testes:
1. unitario validando calculo do ratio.
- Criterio de aceite:
1. metrica de pruning disponivel em todas as runs V2.

### D.05 - Suite da fase D
- Implementacao:
1. criar `backend/tests/test_solver_v2_candidate_pruning.py`.
2. cobrir conflitos, sala, impossible, almoco e telemetria.
- Criterio de aceite:
1. suite da fase D verde.

## Fase E - Solver V2 lexicografico

### E.01 - Base do modelo CP-SAT por data real
- Objetivo: criar variaveis binarias por tarefa+slot+sala em data absoluta.
- Implementacao:
1. definir variaveis de decisao.
2. criar auxiliares por turma/professor/dia para restricoes.
3. manter naming deterministico para debug.
- Ficheiros alvo:
1. novo modulo sugerido: `backend/app/core/solver_engine_v2.py`
- Testes:
1. unitario de criacao de variaveis sem crash.
- Criterio de aceite:
1. modelo compila em CP-SAT para dataset minimo.

### E.02 - Hard constraints no modelo V2
- Objetivo: reimplementar HC1-HC8 no contexto de data real.
- Implementacao:
1. conflito professor, turma e sala.
2. tipo de sala.
3. impossible.
4. almoco hard.
5. hard end absoluto.
- Testes:
1. adaptacao de `tests/test_solver_logic.py` para caminho V2.
- Criterio de aceite:
1. taxa de violacao hard = 0 nos testes.

### E.03 - Objetivo lexicografico etapa 1 (makespan_global)
- Objetivo: minimizar data final global.
- Implementacao:
1. resolver etapa 1 e fixar otimo.
2. preparar passagem para etapa 2.
- Testes:
1. unitario com cenario de duas solucoes e data final distinta.
- Criterio de aceite:
1. solver escolhe menor projected_end_date.

### E.04 - Etapa 2 (end_date_spread_classes)
- Objetivo: reduzir dispersao de fecho entre turmas.
- Implementacao:
1. calcular fim por turma.
2. minimizar max_end - min_end com makespan fixado.
- Testes:
1. unitario com empate de makespan e spreads diferentes.
- Criterio de aceite:
1. desempate por spread funciona.

### E.05 - Etapa 3 (target_drift_total)
- Objetivo: reduzir desvio total da data alvo da escola.
- Implementacao:
1. modelar desvio absoluto agregado por turma.
2. otimizar sem perder etapas anteriores.
- Testes:
1. unitario com empate em etapas 1 e 2.
- Criterio de aceite:
1. solver reduz drift mantendo prioridades anteriores.

### E.06 - Etapa 4 (churn_outside_frozen)
- Objetivo: minimizar churn apenas como criterio secundario.
- Implementacao:
1. comparar proposta com plano publicado fora da janela congelada.
2. contar blocos alterados (data/bloco/professor/sala/criado/removido).
- Testes:
1. unitario de calculo de churn.
- Criterio de aceite:
1. churn nao domina etapas 1-3.

### E.07 - Etapa 5 (class_gaps_total)
- Objetivo: reduzir gaps como ultimo criterio.
- Implementacao:
1. modelar gaps agregados por turma/dia.
2. otimizar sem afetar ordem lexicografica.
- Testes:
1. unitario com empate em etapas 1-4.
- Criterio de aceite:
1. gaps reduzidos apenas quando nao quebra prioridades superiores.

### E.08 - Regra de desempate final fechada
- Objetivo: garantir implementacao fiel ao contrato aprovado.
- Implementacao:
1. validar ordem efetiva: spread -> churn -> gaps quando projected_end empata.
2. adicionar assert de ordem no resumo da run.
- Testes:
1. `backend/tests/test_solver_v2_lexicographic.py`.
- Criterio de aceite:
1. desempate deterministico em 3 execucoes consecutivas.

### E.09 - Regressao da fase E
- Comandos:
1. `docker compose exec backend pytest tests/test_solver_logic.py -q`
2. `docker compose exec backend pytest tests/test_solver_tasks_expansion.py -q`
- Criterio de aceite:
1. sem regressao critica no comportamento base.

## Fase F - Expansao adaptativa, fill e residual

### F.01 - Expansao para datas absolutas no caminho V2
- Objetivo: converter saida CP-SAT em blocos reais de calendario.
- Implementacao:
1. mapear decisoes para datas uteis validas.
2. respeitar bloqueios de calendario.
- Ficheiros alvo:
1. `backend/app/solver_tasks.py`
- Testes:
1. integracao em cenario com feriados.
- Criterio de aceite:
1. blocos expandidos sem sair do calendario valido.

### F.02 - Fill-opportunistic
- Objetivo: aproveitar slots restantes para antecipar conclusao global.
- Implementacao:
1. preencher slots livres com tarefas elegiveis apos solve principal.
2. manter regras hard intactas.
- Testes:
1. integracao com cenario de slots libertados no medio prazo.
- Criterio de aceite:
1. projected_end melhora ou mantem, nunca piora por bug.

### F.03 - Residual transparente
- Objetivo: reportar claramente carga remanescente quando hard end impede fecho total.
- Implementacao:
1. calcular `backlog_remaining_hours` apos expansao.
2. devolver mensagem explicita de limite hard atingido.
- Testes:
1. integracao de capacidade insuficiente ate hard end.
- Criterio de aceite:
1. residual sempre visivel, sem mascarar impossibilidade.

### F.04 - Suite da fase F
- Implementacao:
1. criar `backend/tests/test_solver_v2_expansion_fill.py`.
- Criterio de aceite:
1. suite verde com dados `small-realistic`.

## Fase G - Persistencia de draft e ciclo de vida

### G.01 - Persistencia atomica do draft
- Objetivo: gravar draft sem risco de estado parcial.
- Implementacao:
1. transacao unica de escrita.
2. rollback total em erro.
3. sem escrita dentro da janela congelada em repair.
- Ficheiros alvo:
1. `backend/app/solver_tasks.py`
2. `backend/app/services/schedule_service.py`
- Testes:
1. integracao com falha forcada e verificacao de rollback.
- Criterio de aceite:
1. zero persistencia parcial em cancelamento/erro.

### G.02 - Bloqueio de nova geracao com draft pendente
- Objetivo: impedir corridas de draft.
- Implementacao:
1. check no preflight/endpoint antes de enfileirar.
2. erro claro orientando aprovar ou rejeitar draft atual.
- Testes:
1. endpoint: tentativa de nova geracao com draft pendente retorna bloqueio.
- Criterio de aceite:
1. nao e possivel iniciar segunda geracao com draft aberto.

### G.03 - Aprovacao de draft
- Objetivo: promover draft a publicado sem tocar historico imutavel.
- Implementacao:
1. promover apenas escopo permitido.
2. preservar invariantes de repair e hard constraints.
- Testes:
1. integracao aprovacao com validacao de publicado final.
- Criterio de aceite:
1. publicado final consistente e auditavel.

### G.04 - Rejeicao de draft sem sequelas
- Objetivo: apagar draft integralmente na rejeicao.
- Implementacao:
1. remocao completa de blocos/metadados de draft.
2. manter publicado atual intocado.
- Testes:
1. integracao rejeicao + comparacao antes/depois do publicado.
- Criterio de aceite:
1. publicado nao muda apos rejeicao.

### G.05 - Suite da fase G
- Implementacao:
1. criar `backend/tests/test_solver_v2_draft_lifecycle.py`.
- Criterio de aceite:
1. fluxo gerar/aprovar/rejeitar/bloquear nova geracao verde.

## Fase H - Comparacao estatistica draft vs publicado

### H.01 - Servico de resumo estatistico de diff
- Objetivo: gerar resumo para decisao admin sem vista obrigatoria aula-a-aula.
- Implementacao:
1. calcular delta de projected_end_date.
2. calcular end_date_spread_days.
3. calcular churn_outside_frozen_ratio.
4. calcular total de blocos alterados fora da janela.
5. calcular backlog_remaining_hours.
6. calcular variacao agregada de gaps.
- Ficheiros alvo:
1. novo modulo sugerido: `backend/app/services/solver_v2_diff_service.py`
- Testes:
1. unitario por indicador.
- Criterio de aceite:
1. resumo consistente e estavel para mesma entrada.

### H.02 - Contrato API do painel estatistico
- Objetivo: expor resumo no endpoint de decisao do draft.
- Implementacao:
1. definir schema Pydantic para `draft_comparison_summary`.
2. incluir no payload de leitura do draft.
- Ficheiros alvo:
1. `backend/app/schemas.py`
2. `backend/app/api/v1/endpoints/schedule.py`
- Testes:
1. teste de contrato de resposta.
- Criterio de aceite:
1. frontend recebe os 6 indicadores minimos em formato estavel.

### H.03 - Integracao frontend minima (MVP)
- Objetivo: apresentar comparacao estatistica para aprovacao.
- Implementacao:
1. renderizar card de resumo com indicadores minimos.
2. acoes explicitas: aprovar e rejeitar.
3. mensagem clara de que vista aula-a-aula e opcional.
- Ficheiros alvo:
1. `frontend/src` (modulo de horarios/draft atual)
- Testes:
1. atualizar/adicionar teste de UI do fluxo de decisao de draft.
- Criterio de aceite:
1. admin decide draft apenas com painel estatistico sem friccao.

### H.04 - Suite da fase H
- Implementacao:
1. criar `backend/tests/test_solver_v2_diff_summary.py`.
2. cobrir 6 indicadores e formato do payload.
- Criterio de aceite:
1. suite da fase H verde.

## Fase I - Testes finais, validacoes e hardening

### I.01 - Matriz de testes automatizados obrigatorios
- Objetivo: executar gate completo antes de declarar pronto.
- Suite minima:
1. `tests/test_solver_logic.py`
2. `tests/test_solver_tasks_expansion.py`
3. `tests/test_schedule_generate_preflight.py`
4. `tests/test_solver_v2_demand_builder.py`
5. `tests/test_solver_v2_candidate_pruning.py`
6. `tests/test_solver_v2_lexicographic.py`
7. `tests/test_solver_v2_expansion_fill.py`
8. `tests/test_solver_v2_draft_lifecycle.py`
9. `tests/test_solver_v2_diff_summary.py`
- Comando sugerido:
1. `docker compose exec backend pytest tests/test_solver_logic.py tests/test_solver_tasks_expansion.py tests/test_schedule_generate_preflight.py tests/test_solver_v2_demand_builder.py tests/test_solver_v2_candidate_pruning.py tests/test_solver_v2_lexicographic.py tests/test_solver_v2_expansion_fill.py tests/test_solver_v2_draft_lifecycle.py tests/test_solver_v2_diff_summary.py -q`
- Criterio de aceite:
1. 100% da suite obrigatoria verde.

### I.02 - Validacao manual click-by-click (admin)
- Objetivo: validar experiencia real no MVP local.
- Checklist:
1. seed `small-realistic` carregada.
2. iniciar geracao V2 manual.
3. confirmar criacao de draft.
4. abrir resumo estatistico e validar indicadores.
5. rejeitar draft e confirmar zero mudancas no publicado.
6. gerar novo draft e aprovar.
7. confirmar horario publicado atualizado.
8. tentar nova geracao com draft pendente e validar bloqueio.
- Criterio de aceite:
1. checklist completa sem comportamento inesperado.

### I.03 - Teste de resiliencia de cancelamento
- Objetivo: garantir integridade em cancelamento tardio.
- Implementacao:
1. cancelar task durante solve/expansao/saving.
2. verificar rollback e ausencia de persistencia parcial.
- Referencia:
1. contrato de cancelamento em hard constraints docs.
- Criterio de aceite:
1. cancelamento nao gera estado intermediario corrompido.

### I.04 - Teste de regressao de tenant isolation
- Objetivo: confirmar zero vazamento entre organizacoes.
- Implementacao:
1. executar cenarios com dois tenants (perfil operacional quando necessario).
2. validar que geracao de um tenant nao usa dados do outro.
- Criterio de aceite:
1. zero cross-tenant access.

### I.05 - Pacote final de evidencias
- Objetivo: deixar release local auditavel e repetivel.
- Entregaveis:
1. resultado da suite automatizada.
2. checklist manual assinada.
3. metricas baseline vs V2.
4. lista de riscos residuais e mitigacoes.
- Criterio de aceite:
1. artefactos completos para Go/No-Go local.

---

## 8. Criterios de Go/No-Go local
1. hard constraints: zero violacoes.
2. fluxo draft: aprovado e rejeitado com comportamento correto.
3. nova geracao bloqueada com draft pendente.
4. resumo estatistico do diff disponivel e coerente.
5. projected_end_date em V2 nao piora por regressao tecnica nos cenarios alvo.

## 9. Riscos tecnicos e mitigacoes diretas
1. Risco: explosao de candidatos por data real.
- Mitigacao: pruning hard-first + telemetria antes/depois.
2. Risco: prioridade lexicografica implementada fora de ordem.
- Mitigacao: testes de empate por etapa com asserts deterministicas.
3. Risco: persistencia parcial no draft.
- Mitigacao: transacao unica + testes de rollback/cancelamento.
4. Risco: decisao admin sem clareza.
- Mitigacao: painel com 6 indicadores minimos obrigatorios.

## 10. Resultado esperado desta WBS
Ao final, o Solver V2 fica implementado de forma incremental, com baixo acoplamento entre etapas, alta rastreabilidade de regressao e validacao funcional suficiente para uso local continuo com o minimo de complicacoes tecnicas.