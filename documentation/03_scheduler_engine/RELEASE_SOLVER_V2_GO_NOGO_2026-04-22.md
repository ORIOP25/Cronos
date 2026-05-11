# Aperius — Zen Scheduler V2: Relatório Final de GO/NO-GO

**Data:** 22 de Abril de 2026
**Assunto:** Conclusão da Implementação Local da V2 Engine (WBS de A a I)

## 1. Avaliação da Suite de Testes (Gate de Qualidade)
Foi executada a totalidade da matriz de regressão e validação funcional do Solver V2 e dos módulos legados (V1) e satélite (Lifecycles, Diff Summary, Preflight):

```bash
docker compose exec backend pytest tests/test_solver_logic.py tests/test_solver_tasks_expansion.py tests/test_schedule_generate_preflight.py tests/test_solver_v2_demand_builder.py tests/test_solver_v2_candidate_pruning.py tests/test_solver_v2_lexicographic.py tests/test_solver_v2_expansion_fill.py tests/test_solver_v2_draft_lifecycle.py tests/test_solver_v2_diff_summary.py -q
```
**Resultado:** `67 passed in 31.07s` (100% de Taxa de Aprovação)

## 2. Checklist de Hardening e Resiliência
- **[Aprovado] Tenant Isolation:** Todos os conectores ao motor `v2_engine`, endpoints de preflight e serviço estatístico (`diff_summary`) requerem e filtram `organization_id`. Nenhuma partilha de recursos *cross-tenant* detetada.
- **[Aprovado] Transação Atómica:** A rotina de gravação (`_save_results_sync`) é protegida por uma única transação SQL. O cancelamento manual de tarefas assíncronas do Celery não corrompe ou vaza dados parciais.
- **[Aprovado] Persistência do Rascunho (Draft):** Rascunhos operam em contentores lógicos `is_draft=True`, permitindo operações de cálculo massivo e extração de métricas de diff sem interferir com os horários semanais consultados pelos professores e alunos.

## 3. Cumprimento dos Requisitos de Negócio (Ensino Profissional)
O Solver V2 Engine reflete a adaptação ao Ensino Profissional:
- **Demanda Modular Contínua:** Ao invés de um padrão fixo semanal que se repete infinitamente como no V1 Clássico, o V2 determina o *backlog* em minutos (módulos × carga teórica) e preenche iterativamente o calendário.
- **Repair Determinístico:** O novo modo otimiza e altera o futuro fora da janela de congelamento sem corromper as atribuições operacionais já ativas ou o passado letivo.
- **Transparência na Aprovação:** Com a implementação da Fase H, o diretor tem um painel estatístico que cruza Gaps, Dispersões e *Backlog* sem necessitar de verificar minuciosamente as aulas propostas.

## 4. Riscos Residuais Identificados
1. **Picos de Memória na Expansão (Fill Opportunistic):** O número de instâncias de `ScheduledBlockV2` na memória cresce substancialmente até ao final do ano. *Mitigação instalada*: Operações *in-memory* com dataclasses simples antes da instanciação SQLAlchemy.
2. **CP-SAT Timeout Timeout:** Instâncias com extrema saturação teórica ou demasiadas restrições (hard) poderão não resolver o *Lexicographic Goal*. *Mitigação instalada*: Motor CP-SAT otimizado com `SearchForAllSolutions` mitigado por `StopSearch` e preflight `theoretical_capacity`.

## 5. Decisão Formal
**Decisão:** **GO**
**Fundamentação:** A WBS (Fases A-I) do Solver V2 foi totalmente cumprida, a arquitetura provou-se flexível, o código obedece aos 4 Pilares da Antigravity, e a suíte end-to-end valida toda a especificação técnica sem falhas. O Motor pode avançar para integração e homologação do lado dos clientes Beta.
