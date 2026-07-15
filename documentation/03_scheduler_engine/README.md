# Scheduler Engine

Esta secao define o contrato tecnico-funcional do motor.

## Conteudo principal
- PRD_SCHEDULE_GENERATOR_NEW_BASELINE.md: fonte de verdade atual do gerador. Supersede conceitos antigos de target/preferred end date, horizonte rolling fixo de 8 semanas, modos manuais Complete/Repair e otimizacao quality-only.
- TECH_SPEC_SCHEDULE_GENERATOR_NEW_BASELINE.md: arquitetura tecnica atual para implementar o novo baseline do gerador.
- WBS_SCHEDULE_GENERATOR_NEW_BASELINE_IMPLEMENTATION.md: plano de execucao para implementar o novo baseline. Deve remover, adaptar ou isolar comportamento legado que contradiga o PRD.
- HARD_CONSTRAINTS_SOFT_OBJECTIVES.md: contrato atual de hard validity, regras custom e politica interna de qualidade `baseline-v1`.
- BETA_REMEDIATION_IMPLEMENTATION_2026-07-15.md: mapa de implementação, testes e gates para SCHED-001..007 e APP-001.
- SOLVER_V2_ADAPTATIVO_ALGORITMO_E_COMPORTAMENTO.md: especificacao historica do algoritmo adaptativo. Nao e fonte de verdade se contradisser o novo PRD.
- ROADMAP_ENGINE_V2.md: roadmap historico. Nao governa a nova implementacao do gerador.
- RELEASE_SOLVER_V2_GO_NOGO_2026-04-22.md: relatorio historico de uma versao anterior. Nao representa estado atual de aceitacao.

## Garantia central
- hard constraints sempre vencem objetivos soft.
- Para o novo schedule generator, PRD_SCHEDULE_GENERATOR_NEW_BASELINE.md vence documentos legados.
