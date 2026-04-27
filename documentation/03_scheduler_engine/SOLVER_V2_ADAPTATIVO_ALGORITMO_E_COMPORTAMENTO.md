# Solver V2 Adaptativo - Algoritmo e Comportamento Operacional

## Estado do documento
- Tipo: especificacao funcional-tecnica detalhada.
- Escopo: comportamento do algoritmo, criterios de decisao e impacto operacional.
- Foco: terminar aulas o mais cedo possivel com hard constraints inviolaveis.

## 1. Problema que o V2 resolve

## 1.1 Dor real das escolas
1. Aulas terminam demasiado tarde (historico de fecho no fim de julho).
2. Horas por alocar podem alongar calendario quando o sistema nao reaproveita espacos libertados de forma eficaz.
3. Repair conservador reduz churn, mas pode atrasar conclusao global quando prioridade real e antecipar fim do ano letivo.

## 1.2 Limite do modelo atual
No modelo semanal+expansao, o solve fecha um padrao semanal primeiro e so depois expande para datas. Isso reduz capacidade de capturar oportunidades que surgem mais tarde no mesmo ciclo.

## 2. Objetivo formal do V2
Maximizar conclusao antecipada das aulas no horizonte restante, respeitando:
1. hard constraints;
2. isolamento por tenant;
3. historico imutavel;
4. janela congelada de repair.

## 3. Principios de desenho
1. Hard constraints sempre acima de qualquer objetivo soft.
2. Conclusao antecipada e prioridade numero 1.
3. Estabilidade e secundaria no perfil agressivo definido para esta fase.
4. Geracao continua manual e auditavel por admin.
5. Transparencia obrigatoria de remanescente/residual em cada run.

## 4. Modelo conceptual do algoritmo

## 4.1 Entrada do solver
1. Snapshot tenant-scoped de estado curricular e operacional.
2. Minutos remanescentes por tarefa (class+subject+module).
3. Minutos de backlog unico de horas por alocar (sem distincao entre divida normal e divida vencida).
4. Slots absolutos por data real no horizonte adaptativo.
5. Matriz de elegibilidade (professor, turma, sala, disponibilidade, calendario).

## 4.2 Saida do solver
1. Plano em datas absolutas fora da janela congelada.
2. Delta de mudancas para diff e aprovacao manual.
3. Metricas de runtime e qualidade operacional.
4. Resumo de remanescente bruto, reconciliado e residual pos-expansao.

## 5. Comportamento detalhado do V2

## 5.1 Fase A - Build de demanda
1. Determinar modulo ativo por disciplina/turma.
2. Calcular minutos curriculares remanescentes.
3. Consolidar backlog unico de horas por alocar.
4. Atribuir prioridade operacional por impacto em conclusao global e equilibrio entre turmas.

## 5.2 Fase B - Build de capacidade
1. Gerar slots por data real numa janela rolling principal de 8 semanas, com validacao de viabilidade ate `hard_end_date` (modelo hibrido).
2. Excluir datas bloqueadas por calendario.
3. Excluir candidatos inviaveis por hard rules antes do solve.

## 5.3 Fase C - Solve principal
1. Alocar primeiro tarefas com maior risco de empurrar data de fim.
2. Tratar backlog como horas normais por alocar, sem reserva fixa para divida.
3. Preservar cadeia de modulos sem quebra de ordem.

## 5.4 Fase D - Fill-opportunistic
1. Reaproveitar espacos restantes do horizonte para antecipar fecho global.
2. Usar slots libertados por conclusoes de outras tarefas no mesmo ciclo.
3. Priorizar ganhos de conclusao e equilibrio entre turmas no perfil agressivo.

## 5.5 Fase E - Refinamento local
1. Reduzir furos internos quando nao prejudica objetivo principal.
2. Melhorar fairness sem perder data de conclusao.

## 5.6 Fase F - Persistencia segura
1. Gravar em draft fora da zona congelada.
2. Nao alterar historico executado.
3. Exigir aprovacao manual para ativacao.

## 6. Funcao objetivo (perfil agressivo)

## 6.1 Ordem de prioridade
1. minimizar projected end date global;
2. reduzir dispersao de data final entre turmas (evitar uma turma acabar muito antes de outra);
3. reduzir desvio da data alvo;
4. reduzir churn fora da janela congelada (criterio secundario no perfil agressivo);
5. reduzir gaps.

## 6.2 Modelo lexicografico (decisao fechada)
O solver resolve por prioridades em cascata. So passa para a prioridade seguinte quando encontrou o melhor valor da prioridade anterior:
1. minimizar `makespan_global`;
2. minimizar `end_date_spread_classes`;
3. minimizar `target_drift_total`;
4. minimizar `churn_outside_frozen`;
5. minimizar `class_gaps_total`.

## 6.3 Definicao operacional de churn
- Churn e a percentagem de blocos alterados fora da janela congelada, comparando plano publicado atual vs draft novo.
- Alteracao conta quando ha mudanca de data, bloco, professor, sala, criacao ou remocao de bloco.
- No perfil agressivo desta fase, pode chegar a 100% se isso reduzir a data final global.

## 6.4 Desempate (decisao fechada)
Se duas solucoes tiverem o mesmo `projected_end_date`, usar desempate por ordem:
1. menor dispersao de data final entre turmas;
2. menor churn fora da janela congelada;
3. menor numero de gaps.

## 7. Regras de dominio preservadas
1. Sem conflito professor/turma/sala.
2. Tipo de sala obrigatorio.
3. Slots IMPOSSIBLE proibidos.
4. Almoco hard quando configurado.
5. Hard end date absoluto.
6. Ordem de modulos obrigatoria.
7. Tenant isolation em todas as leituras/escritas.

## 8. Exemplos praticos

## 8.1 Exemplo A - Backlog de 10h com slots libertados no medio prazo
1. Semana 1-4: disciplina X so tem 1 slot viavel/semana.
2. Semana 5: disciplina Y conclui e liberta mais slots da turma.
3. V2 usa esses novos slots para X no mesmo ciclo adaptativo.
4. Resultado: backlog fecha antes do que no modelo semanal fixo.

## 8.2 Exemplo B - GAP na terca compensado na quinta
1. Ocorre GAP na terca sem substituicao.
2. Quinta de semanas seguintes ganha disponibilidade real.
3. V2 move recuperacao para quinta sem depender de matching rigido dia/hora original.

## 8.3 Exemplo C - Pressao alta perto do hard end
1. Remanescente elevado e horizonte curto.
2. Perfil agressivo permite mudanca ampla fora da janela congelada.
3. Sistema procura conclusao mais cedo e reporta residual se fisicamente impossivel.

## 9. Porque este comportamento e correto para o negocio
1. Alinha com necessidade real das escolas: terminar aulas mais cedo.
2. Reduz risco de fecho no fim de julho por inercia de padrao.
3. Mantem governanca administrativa via aprovacao manual.
4. Mantem seguranca e integridade do dominio modular.

## 10. Interface e experiencia operacional esperada
1. Admin inicia geracao manual.
2. Sistema mostra ETA e estado de fila.
3. Resultado apresenta diff, projected end date e resumo de remanescente.
4. Admin aprova ou rejeita draft.

Fluxo pratico de diff na operacao:
1. O plano publicado atual nao muda no momento da geracao.
2. O solver cria um draft com a proposta nova.
3. O admin compara resumo estatistico do draft vs plano publicado (sem comparacao aula-a-aula obrigatoria).
4. Se aprovar, o draft passa a publicado.
5. Se rejeitar, o draft e apagado permanentemente sem sequelas no plano publicado.

Indicadores minimos para aprovacao do draft:
1. `projected_end_date` atual vs draft e delta em dias;
2. `end_date_spread_days` entre turmas atual vs draft;
3. `churn_outside_frozen_ratio`;
4. total de blocos alterados fora da janela congelada;
5. `backlog_remaining_hours` apos solve;
6. variacao de gaps agregada.

Nota operacional:
- Vista detalhada aula-a-aula pode existir como opcional de auditoria, mas nao e requisito para decisao no MVP local.

## 11. Observabilidade minima obrigatoria
1. projected_end_delta_days por run;
2. backlog_remaining_hours por run;
3. ram_peak_mb e runtime_seconds;
4. queue_wait_seconds;
5. end_date_spread_days entre turmas por run;
6. churn_outside_frozen_ratio por run;
7. taxa de sucesso/falha por tenant.

## 12. Integracao com arquitetura produtiva multi-escola
O V2 depende de arquitetura de capacidade dedicada para evitar saturacao de RAM com multiplos clientes concorrentes. A especificacao operacional desta camada esta em:
- `documentation/09_ops_observability/SOLVER_V2_CAPACITY_MULTI_ESCOLA.md`

## 13. Itens a definir
Sem itens pendentes no escopo local de implementacao do Solver V2.