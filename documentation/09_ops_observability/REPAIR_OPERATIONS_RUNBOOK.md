# Repair Operations Runbook

## Objetivo
Garantir operacao segura do modo `repair` sem inflacionar remanescente, preservando historico e janela congelada.

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
- Regra ativa: reconciliacao virtual de compromissos publicados ate `frozen_until`.
- Credito contabilizado: blocos ativos com estado `NONE` e `GIVEN`.
- Sem credito: blocos `GAP` e `SUBSTITUTED` (mantem divida no planeado).
- Backfill historico de auto-confirm e opcional por tenant (nao obrigatorio para operar repair).

## Checklist pre-repair (obrigatorio)
1. Confirmar tenant alvo e role admin.
2. Verificar `school_hard_end_date` e `repair_stability_window_days`.
3. Verificar divida operacional atual em `/api/v1/occurrences/debts`.
4. Confirmar que existe horizonte apos `frozen_until` para gerar blocos.
5. Confirmar capacidade minima (timeslots/salas/calendario) para evitar `preflight_failed` por capacidade teorica.

## Fluxo operacional (admin, botao a botao)
1. Abrir pagina Horarios.
2. Clicar `Gerar Horario` e escolher modo `repair`.
3. Aguardar estado da task ate terminal em `GET /api/v1/schedule/status/{task_id}`.
4. Se `preflight_failed`, agir pela mensagem objetiva (janela/capacidade/hard end) e nao insistir sem correcao.
5. Quando houver draft, rever diff em `GET /api/v1/schedule/drafts/{gen_id}/diff`.
6. Decidir:
- `Aprovar e Ativar` quando diff e coerente com o plano operacional;
- `Rejeitar` quando impacto nao e aceitavel.
7. Pos-decisao, validar grelha semanal e ocorrencias pendentes.

## Contrato de rollback operacional
- Nao requer migracao destrutiva.
- Em caso de risco, rejeitar draft imediatamente (`DELETE /api/v1/schedule/drafts/{gen_id}`).
- Manter horario ativo atual e repetir repair apenas apos ajuste de capacidade/regras.

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
