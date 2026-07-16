# Adaptive Repair Operations Runbook

## Objetivo
Garantir operacao segura da estrategia interna `ADAPTIVE_REPAIR`, preservando divida explicita, historico e janela de estabilidade.

## Escopo
- 1 tenant por vez (sempre validar `organization_id` antes de qualquer acao);
- periodo de operacao: semanas proximas ao `school_hard_end_date`;
- fluxo cobre trigger, validacao, aprovacao/rejeicao e rollback operacional.

## Regras inviolaveis
1. Nunca gerar ou aprovar alteracoes dentro de `today + repair_stability_window_days`.
2. Nunca mutar historico de ocorrencias para "corrigir" metricas.
3. Hard end date e absoluto.
4. Tenant isolation e obrigatorio em toda leitura/escrita.

## Estrategia oficial de accounting
- A divida nasce apenas de estados operacionais explicitamente declarados.
- Recuperacoes aprovadas reservam apenas os minutos ligados por `PlannedRecoveryLink`.
- `DELIVERED` liquida a parcela ligada; `CANCELED` volta a disponibiliza-la.
- Historico executado e blocos anteriores ao limite editavel permanecem imutaveis.

## Checklist pre-repair (obrigatorio)
1. Confirmar tenant alvo e role admin.
2. Verificar `school_hard_end_date` e `repair_stability_window_days`.
3. Verificar divida operacional atual em `/api/v1/occurrences/debts`.
4. Confirmar que existe horizonte apos `editable_start_date` para gerar blocos.
5. Confirmar capacidade minima (timeslots/salas/calendario) para evitar `preflight_failed` por capacidade teorica.

## Fluxo operacional (admin, botao a botao)
1. Abrir pagina Horarios.
2. Clicar `Gerar Horario`; o sistema escolhe automaticamente a estrategia.
3. Acompanhar `GET /api/v1/scheduler/jobs/{job_id}` ou `GET /api/v1/scheduler/status` ate estado terminal.
4. Em falha ou `NO_VALID_OUTPUT`, agir pelo bloqueador e acoes recomendadas antes de repetir.
5. Quando houver draft, rever resumo e diff em `GET /api/v1/scheduler/drafts/{draft_id}` e `/diff`.
6. Decidir:
- `Aprovar e Ativar` via `POST /api/v1/scheduler/drafts/{draft_id}/approve`;
- `Rejeitar` via `POST /api/v1/scheduler/drafts/{draft_id}/reject`.
7. Pos-decisao, validar grelha semanal e ocorrencias pendentes.

## Contrato de rollback operacional
- Nao requer migracao destrutiva.
- Em caso de risco, rejeitar o draft pelo endpoint canonico de rejeicao.
- O horario ativo atual permanece publicado; repetir geracao apenas apos ajustar capacidade ou regras.

## Alterar a grelha horária

- Uma alteração estrutural depois de existirem horários, drafts ou registos
  operacionais devolve `409 Conflict`. É proteção de dados esperada, não uma
  indisponibilidade do backend.
- Se a destruição for intencional, o admin deve abrir **Período Letivo**, usar
  **Recomeçar Ano Letivo** e confirmar explicitamente a operação antes de voltar
  a guardar a grelha.
- O reset é destrutivo e nunca é chamado automaticamente pelo formulário da
  grelha. Alterações apenas ao almoço e submissões idênticas não exigem reset.

## Monitores minimos de rollout (WP-8.2)
1. `repair_remaining_raw_hours` vs `repair_remaining_reconciled_hours`.
2. `repair_hard_end_residual_hours`.
3. `%occurrences_none_past`.
4. `repair_diff_added_removed_ratio`.

## Gate rapido Go/No-Go (WP-8.3)
Go quando:
1. Hard constraints preservadas em 100% dos testes alvo.
2. Tenant isolation sem regressao.
3. Fluxo admin (gerar, rever diff, aprovar/rejeitar) validado end-to-end.
4. Sem erro operacional bloqueante aberto (P0/P1).

No-Go quando:
1. Repair tenta violar janela congelada ou hard end.
2. Regressao de isolamento multi-tenant.
3. Draft diff sem coerencia operacional para decisao humana.
4. Falhas repetidas de preflight sem causa controlada.
