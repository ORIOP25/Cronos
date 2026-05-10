# Plano WBS V4: Registo de Aulas — Simplificação + Centralização

## Estado da Implementação

| Fase | Estado | Data | Notas |
|------|--------|------|-------|
| 1. Modelo de Dados (REVOKED) | ✅ Concluído | 2026-05-05 | Enum, migração Alembic, transições |
| 2. Backend REVOKED pipeline | ✅ Concluído | 2026-05-05 | cancel_occurrence_sync → REVOKED |
| 3. Contabilidade SUBSTITUTED | ✅ Concluído | 2026-05-05 | Removido crédito executado, sub interativo |
| 4. Frontend LessonLogModal | ✅ Concluído | 2026-05-05 | 3 botões, SubstitutionStep removido |
| 5. Frontend WeekGrid grayed out | ✅ Concluído | 2026-05-05 | Todos estados finais grayed out |
| 6. Frontend /absences tabela | ✅ Concluído | 2026-05-05 | 8 colunas, tabs Pendentes/Histórico |
| 7. Frontend AlertBar | ✅ Concluído | 2026-05-05 | Navegação dashboard→/absences |
| 8. Testes | ✅ Concluído | 2026-05-05 | 97 testes passam (86 existentes + 11 novos) |

**Migração Alembic:** `f844853d7c29_add_revoked_to_lessonoccurrencestatus`

---

## 0. Contexto Técnico

### 0.1. Tech Stack (idêntico V1/V2)

| Camada | Tecnologia | Versão |
|--------|-----------|--------|
| **Backend** | Python, FastAPI | 3.12, 0.115+ |
| **ORM** | SQLAlchemy (async com asyncpg) | 2.0+ |
| **Base de Dados** | PostgreSQL | 15 |
| **Migrações** | Alembic | — |
| **Frontend** | React | 18+ |
| **UI Framework** | CoreUI (Bootstrap 5) | — |
| **State/Cache** | React Query (TanStack Query) | 5+ |
| **Estado Global** | Zustand (auth store) | — |
| **Routing** | React Router | 6+ |

### 0.2. Glossário de Domínio (recordatório)

| Termo | Definição |
|-------|-----------|
| **ScheduleOutput** | Bloco de aula gerado pelo Solver (data, timeslot, lesson, room) |
| **LessonLog** | Registo do que aconteceu com um bloco. `status`: PENDING / COMPLETED / OCCURRENCE. Campos: `summary`, `notes` |
| **LessonOccurrence** | Ocorrência operacional criada a partir de um LessonLog OCCURRENCE. `status`: GIVEN / GAP / SUBSTITUTED / REVOKED (novo). `decided_at` nulo = pendente de decisão |
| **TeacherWeeklyTimesheet** | Estado do fecho semanal. `status`: OPEN / SUBMITTED / APPROVED |
| **ClassProgress** | Progresso de horas por turma/módulo: `hours_completed`, `hours_debt`, `is_completed` |

### 0.3. Estado Pré-V4 (V3 concluído)

| Funcionalidade | Estado |
|----------------|--------|
| Auto-create LessonOccurrence OPEN no teacher OCCURRENCE | ✅ |
| Cleanup OPEN ao reverter OCCURRENCE→PENDING | ✅ |
| Rejeitar criação de ocorrência sobre LessonLog COMPLETED | ✅ |
| Re-decisão GAP↔SUBSTITUTED permitida | ✅ |
| `cancel_occurrence_sync` (apaga ocorrência) | ✅ (será alterado) |
| Blocos substituídos grayed out | ✅ (parcial, será revisto) |
| Blocos de substituição read-only | ✅ (será removido) |
| Dashboard pending_occurrences filtrado por `decided_at IS NULL` | ✅ |
| Filtro `status` em `GET /occurrences/` | ✅ |
| Endpoint `GET /timesheets/{id}/pending-occurrences` | ✅ |
| Botões de decisão inline no LessonLogModal | ✅ (será removido) |
| SubstitutionStep wizard | ✅ (será removido) |

---

## 1. O Conceito (Os 5 Ws)

- **Who (Quem):** Professores (registo de aulas) e Administradores (gestão de ocorrências em `/absences`).
- **What (O quê):** Simplificação radical do LessonLogModal para 3 botões universais. Centralização de TODA a gestão de ocorrências em `/absences` com tabela enriquecida. Novo estado REVOKED para auditoria. Contabilidade SUBSTITUTED corrigida para evitar dupla contagem.
- **Where (Onde):** Registo no modal (qualquer página com WeekGrid). Gestão em `/absences`. Dashboard para visibilidade.
- **When (Quando):** Substitui a implementação V3. Rollback das decisões inline do modal.
- **Why (Porquê):** A V3 introduziu decisões inline no modal que se revelaram confusas e redundantes com `/absences`. A separação clara entre "registar" (modal) e "gerir" (/absences) simplifica ambos os fluxos.

---

## 2. WBS (Work Breakdown Structure)

### Fase 1: Modelo de Dados — Estado REVOKED

#### 1.1. Adicionar `REVOKED` ao enum `LessonOccurrenceStatus`

- **Descrição:** Adicionar `REVOKED = "REVOKED"` ao enum Python em `models.py`.
- **Ficheiro:** `backend/app/models.py`
- **Resultado Esperado:** Enum Python tem 4 valores: GIVEN, GAP, SUBSTITUTED, REVOKED.

#### 1.2. Gerar e aplicar migração Alembic

- **Descrição:** `alembic revision --autogenerate -m "add REVOKED to lessonoccurrencestatus"` seguido de `alembic upgrade head`.
- **Comandos:**
  ```bash
  docker-compose exec -T backend alembic revision --autogenerate -m "add REVOKED to lessonoccurrencestatus"
  docker-compose exec -T backend alembic upgrade head
  ```
- **Resultado Esperado:** PostgreSQL aceita `REVOKED` como valor válido na coluna `status` da tabela `lesson_occurrences`.

#### 1.3. Atualizar `ALLOWED_STATE_TRANSITIONS`

- **Descrição:** Adicionar REVOKED como estado terminal. GAP e SUBSTITUTED podem transitar para REVOKED.
- **Ficheiro:** `backend/app/services/occurrence_service.py`
- **Novo dicionário:**
  ```python
  ALLOWED_STATE_TRANSITIONS = {
      GIVEN: {GIVEN, GAP, SUBSTITUTED},
      GAP: {GAP, SUBSTITUTED, REVOKED},
      SUBSTITUTED: {SUBSTITUTED, GAP, REVOKED},
      REVOKED: set(),  # terminal — imutável
  }
  ```

#### 1.4. Atualizar `_validate_state_transition`

- **Descrição:** Bloquear qualquer transição a partir de REVOKED. Permitir transição para REVOKED a partir de GAP/SUBSTITUTED.
- **Ficheiro:** `backend/app/services/occurrence_service.py`
- **Lógica:** Se `occurrence.status == REVOKED`, lançar `OccurrenceServiceError(409, "Ocorrência revertida não pode ser alterada.")`.

---

### Fase 2: Backend — REVOKED pipeline

#### 2.1. `cancel_occurrence_sync` → marcar REVOKED em vez de apagar

- **Descrição:** Alterar a função para definir `status = REVOKED` e `decided_at = now()` em vez de `db.delete(occurrence)`. A ocorrência permanece na BD para auditoria.
- **Ficheiro:** `backend/app/services/occurrence_service.py`
- **Linhas afetadas:** ~1094-1096 (substituir `db.delete(occurrence)` por `occurrence.status = REVOKED; occurrence.decided_at = now()`)
- **Resultado Esperado:** Ocorrência marcada como REVOKED persiste na BD. `GET /occurrences/` devolve-a com badge "Revertida".

#### 2.2. `cancel_open_occurrence_for_block_sync` → marcar REVOKED em vez de apagar

- **Descrição:** Mesma alteração para a variante que lida com ocorrências não decididas (teacher self-revert).
- **Ficheiro:** `backend/app/services/occurrence_service.py`
- **Linhas afetadas:** ~1019-1021
- **Resultado Esperado:** Teacher self-revert deixa rasto de auditoria.

---

### Fase 3: Backend — Contabilidade SUBSTITUTED corrigida

#### 3.1. Remover crédito de `hours_completed` no módulo executado

- **Descrição:** Em `_apply_state_accounting` para SUBSTITUTED, remover a segunda chamada a `_apply_module_delta` que credita `hours_completed` no módulo do substituto.
- **Ficheiro:** `backend/app/services/occurrence_service.py`
- **Linhas afetadas:** ~838-844 (remover o bloco `_apply_module_delta(db, executed_module_id, completed_delta=delta, debt_delta=0.0)`)
- **Resultado Esperado:** Ao decidir SUBSTITUTED, apenas o módulo original recebe `hours_debt`. O módulo do substituto é creditado quando o professor substituto regista "Aula Dada" no seu bloco.

#### 3.2. Remover bloqueio de LessonLog em blocos de substituição (Phase 4.4)

- **Descrição:** Remover o bloco de código que impede `upsert_lesson_log` em blocos de substituição. O bloco do substituto passa a ser totalmente interativo.
- **Ficheiro:** `backend/app/services/lesson_log_service.py`
- **Linhas afetadas:** ~65-79 (remover `is_substitution_block` check e raise HTTPException)
- **Resultado Esperado:** Professor substituto pode abrir o bloco "Substituição" e registar Aula Dada / Criar Ocorrência normalmente.

#### 3.3. Permitir `OCCURRENCE` em slots futuros (backend)

- **Descrição:** Alterar a validação de tempo em `upsert_lesson_log_sync` para apenas bloquear `COMPLETED` no futuro. `OCCURRENCE` é sempre permitido.
- **Ficheiro:** `backend/app/services/lesson_log_service.py`
- **Linhas afetadas:** ~47-49
- **Antes:** `if payload.status in (COMPLETED, OCCURRENCE): if end_datetime > now: raise`
- **Depois:** `if payload.status == COMPLETED: if end_datetime > now: raise`
- **Resultado Esperado:** Professor pode reportar ocorrência com antecedência (ex: "não posso dar a aula de amanhã").

---

### Fase 4: Frontend — Rollback do LessonLogModal

#### 4.1. Remover lógica de decisão inline

- **Descrição:** Remover do `LessonLogModal.jsx`:
  - Hooks: `useUpdateOccurrence`, `useCancelOccurrence`, `createOccurrenceMutation` (se não usado no modal)
  - Handlers: `handleMarkGap`, `handleCancelOccurrenceAction`, `handleStartSubstitution`, `handleConfirmSubstitution`, `handleBackToStep1`
  - Estado: `occurrenceId`, `substitutionError`, `step`, `showRevertConfirm`
  - Variáveis derivadas: `hasOpenOccurrence`, `occurrenceDecided`, `occurrenceStatusLabel`, `canShowSubstitution`
  - Banner de decisão inline
  - Banner de confirmação de reverter
  - Constantes: `OCCURRENCE_STATUS_LABELS`, `STATUS_INFO`
- **Ficheiro:** `frontend/src/components/LessonLogModal.jsx`
- **Resultado Esperado:** Componente sem lógica de decisão. Apenas lógica de registo.

#### 4.2. Simplificar footer para 3 botões

- **Descrição:** Footer do modal contém apenas:
  - Esquerda: `[Cancelar]`
  - Direita: `[Criar Ocorrência]` + `[Aula Dada]`
- **Ficheiro:** `frontend/src/components/LessonLogModal.jsx`
- **Resultado Esperado:** Modal idêntico para professor e admin. Sem botões condicionais complexos.

#### 4.3. Regras de disabled

- `[Aula Dada]`: disabled se `isFuture` OU `isLocked`
- `[Criar Ocorrência]`: disabled se `isLocked` (semana SUBMITTED/APPROVED). **Sempre enabled para slots futuros.**
- `[Cancelar]`: sempre enabled
- Sumário/Notas: disabled se `isLocked`. **Enabled para slots futuros.**
- **Ficheiro:** `frontend/src/components/LessonLogModal.jsx`

#### 4.4. Banner informativo (não interativo)

- **Descrição:** Se o bloco tem uma `LessonOccurrence` (qualquer estado), mostrar banner informativo:
  - OPEN: "Ocorrência registada. Geria em Faltas & Ocorrências."
  - Decidida: "Ocorrência decidida: [estado]. Consulte Faltas & Ocorrências."
- **Ficheiro:** `frontend/src/components/LessonLogModal.jsx`

#### 4.5. Apagar `SubstitutionStep.jsx`

- **Descrição:** Remover o ficheiro e todos os seus imports.
- **Ficheiro a apagar:** `frontend/src/components/SubstitutionStep.jsx`
- **Resultado Esperado:** Build sem erros de import.

#### 4.6. Limpar imports não utilizados

- **Descrição:** Remover `SubstitutionStep` import do `LessonLogModal.jsx`. Remover hooks não usados do import de `useSchoolData`.
- **Ficheiro:** `frontend/src/components/LessonLogModal.jsx`

---

### Fase 5: Frontend — Grayed out universal

#### 5.1. Estados finais não clicáveis

- **Descrição:** `SlotCell.canOpenOperationalAction = false` quando:
  - `lesson_log_status === 'COMPLETED'`
  - `lesson_log_status === 'OCCURRENCE'` (indeciso)
  - `occurrence_status` + `occurrence_decided_at` (qualquer estado decidido: GAP, SUBSTITUTED, GIVEN)
- **Exceção:** `is_substituted_block = true` → **clicável** (substituto pode interagir).
- **Ficheiro:** `frontend/src/components/WeekGrid.jsx`

#### 5.2. Visual grayed out

- **Descrição:** Aplicar `opacity: 0.55; filter: grayscale(0.5)` via `getCellVisuals()` para todos os estados não clicáveis.
- **Ficheiro:** `frontend/src/components/WeekGrid.jsx`

#### 5.3. Labels atualizados

| Estado | Label |
|--------|-------|
| `lesson_log_status=COMPLETED` | "Concluída ✓" |
| `lesson_log_status=OCCURRENCE` (sem decisão) | "Ocorrência" |
| `occurrence_status=GAP` + decidido | "Falta ✗" |
| `occurrence_status=SUBSTITUTED` + decidido | "Substituída ↔" |
| `occurrence_status=GIVEN` + decidido | "Dada ✓" |
| `is_substituted_block=true` | "Substituição" |
| Nenhum registo | "Pendente" |

- **Ficheiro:** `frontend/src/components/WeekGrid.jsx`

#### 5.4. Action label simplificado

- **Descrição:** Remover label "Gerir". Voltar a "Registar" para blocos pendentes, "Consultar" para locked, e não mostrar label para grayed out (não clicáveis).
- **Ficheiro:** `frontend/src/components/WeekGrid.jsx`

---

### Fase 6: Frontend — /absences tabela enriquecida

#### 6.1. Colunas da tabela

| Coluna | Fonte de dados | Notas |
|--------|---------------|-------|
| Data/Hora | `occurrence.date` + `timeslot.start_time`–`end_time` | Formato "05 Mai, 09:00–11:00" |
| Turma | `class_name` via `schedule_output.lesson.class_model` | |
| Disciplina | `subject_name` via `schedule_output.lesson.subject` | |
| Estado | `status` + `decided_at` | Badge com cor |
| Sumário | `lesson_log.summary` | Truncado 80 chars, expandível |
| Docente Previsto | `planned_teacher.name` | Quem devia dar a aula |
| Docente Efetivo | `executed_teacher.name` ou `substitute_teacher.name` | "—" se não decidido |
| Ações | Contextual | Botões por estado |

- **Ficheiro:** `frontend/src/pages/Occurrences.jsx`

#### 6.2. Badges de estado

| Estado | Cor | Texto |
|--------|-----|-------|
| `decided_at IS NULL` | âmbar (`warning`) | Pendente |
| GAP + decidido | vermelho (`danger`) | Furo |
| SUBSTITUTED + decidido | amarelo (`warning`) | Substituída |
| GIVEN + decidido | verde (`success`) | Dada |
| REVOKED | cinzento (`secondary`) | Revertida |

- **Ficheiro:** `frontend/src/pages/Occurrences.jsx`

#### 6.3. Botões de ação contextuais

| Estado | Ações |
|--------|-------|
| Pendente (OPEN) | `[Furo]` `[Substituir]` `[Reverter]` |
| GAP | `[Reverter]` |
| SUBSTITUTED | `[Reverter]` |
| GIVEN | — |
| REVOKED | — |

- **Ficheiro:** `frontend/src/pages/Occurrences.jsx`

#### 6.4. Tabs: Pendentes / Histórico

- **Descrição:** Secção superior com dois tabs:
  - "Decisões Pendentes" — filtra `decided_at IS NULL`
  - "Histórico" — todas as decididas + REVOKED
- **Ficheiro:** `frontend/src/pages/Occurrences.jsx`

#### 6.5. Expansão de linha (detalhe)

- **Descrição:** Ao clicar numa linha, expandir secção com:
  - Sumário completo
  - Notas do professor
  - Data de criação da ocorrência
  - Data de decisão
  - Quem decidiu (admin)
- **Ficheiro:** `frontend/src/pages/Occurrences.jsx`

#### 6.6. Filtro de estado funcional

- **Descrição:** Dropdown ou query param `?status=OPEN|GAP|SUBSTITUTED|GIVEN|REVOKED` filtra a lista.
- **Ficheiro:** `frontend/src/pages/Occurrences.jsx`

---

### Fase 7: Frontend — Ajustes no WeekGrid e Schedules

#### 7.1. Admin clica em bloco → modal (sem bifurcação)

- **Descrição:** `openCreateOccurrenceModal` em `Schedules.jsx` abre sempre o `LessonLogModal`. Confirmar que o código legacy `CreateOccurrenceModal` não é renderizado.
- **Ficheiro:** `frontend/src/pages/Schedules.jsx`
- **Resultado Esperado:** Qualquer clique em bloco abre o mesmo modal de 3 botões.

#### 7.2. Navegação dashboard → /absences

- **Descrição:** Card "Ocorrências por decidir" no dashboard navega para `/absences?status=OPEN`.
- **Ficheiro:** `frontend/src/components/dashboard/AlertBar.jsx`
- **Resultado Esperado:** Admin vê diretamente as pendentes.

---

### Fase 8: Testes

#### 8.1. Atualizar testes existentes

| Teste | Alteração |
|-------|-----------|
| `test_lesson_registration.py` 30 testes | Verificar que continuam a passar após alterações de contabilidade e REVOKED |
| `test_occurrence_state_machine.py` 9 testes | Atualizar para incluir transições REVOKED. Testar que REVOKED é imutável |
| `test_dashboard.py` 8 testes | `pending_occurrences_total` no schema — verificar |
| `test_business_logic.py` 30 testes | Verificar impacto da contabilidade SUBSTITUTED |

#### 8.2. Criar novos testes

| # | Teste | Fase | Valida |
|---|-------|------|--------|
| T1 | `test_completed_slot_is_not_interactive` | 5 | Bloco COMPLETED → `can_open = false` |
| T2 | `test_occurrence_slot_is_not_interactive` | 5 | Bloco OCCURRENCE → `can_open = false` |
| T3 | `test_substitute_block_accepts_lesson_log` | 3 | `upsert_lesson_log` funciona em bloco `is_substituted_block=true` |
| T4 | `test_substituted_accounting_only_debts_original` | 3 | SUBSTITUTED credita debt original, NÃO credita executado |
| T5 | `test_substitute_completed_credits_executed_module` | 3 | Substituto regista COMPLETED → `hours_completed` sobe no módulo dele |
| T6 | `test_cancel_marks_revoked_not_deleted` | 2 | `cancel_occurrence_sync` → status REVOKED, linha persiste |
| T7 | `test_revoked_is_immutable` | 1 | `update_occurrence_sync` em REVOKED → 409 |
| T8 | `test_future_slot_allows_occurrence` | 3 | `upsert_lesson_log` com OCCURRENCE em slot futuro → sucesso |
| T9 | `test_future_slot_blocks_completed` | 3 | `upsert_lesson_log` com COMPLETED em slot futuro → 400 |
| T10 | `test_absences_endpoint_filters_revoked` | 1 | `GET /occurrences/?status=REVOKED` → devolve revertidas |
| T11 | `test_open_occurrence_self_revert_marks_revoked` | 2 | Teacher reverte OCCURRENCE → ocorrência fica REVOKED |
| T12 | `test_substitute_block_lists_in_week_schedule` | 4 | `GET /schedule/week?teacher_id=<sub>` inclui bloco de substituição |

#### 8.3. Testes manuais de validação

| # | Cenário | Passos |
|---|---------|--------|
| M1 | Professor: Aula Dada → grayed out | Abrir bloco → clicar Aula Dada → bloco fica grayed out, não clicável |
| M2 | Professor: Criar Ocorrência → grayed out | Abrir bloco → Criar Ocorrência → bloco grayed out "Ocorrência" |
| M3 | Admin: modal idêntico ao professor | Admin abre bloco → vê mesmos 3 botões, sem decisões inline |
| M4 | Admin: gerir em /absences | Admin abre /absences → vê Pendentes → clica Furo/Substituir/Reverter |
| M5 | Substituto: regista Aula Dada | Login como sub → vê bloco "Substituição" → clica → Aula Dada → horas creditadas |
| M6 | Admin: reverte GAP → bloco volta normal | /absences → Reverter → bloco volta pendente, clicável |
| M7 | Admin: reverte SUB → bloco do sub desaparece | /absences → Reverter → bloco original pendente, bloco sub removido |
| M8 | Futuro: Criar Ocorrência disponível | Abrir bloco de amanhã → Criar Ocorrência enabled, Aula Dada disabled |
| M9 | Dashboard: contagem correta | Criar 2 ocorrências → dashboard mostra "2 / 2" |
| M10 | Histórico: REVOKED visível | Reverter ocorrência → aparece no Histórico com badge "Revertida" |

---

## 3. Tabela de Conformidade

| Fase | Passo | Ficheiro(s) Principal(is) |
|------|-------|---------------------------|
| 1.1 | REVOKED enum | `models.py` |
| 1.2 | Migração Alembic | `alembic/versions/` |
| 1.3 | ALLOWED_STATE_TRANSITIONS | `occurrence_service.py` |
| 1.4 | _validate_state_transition | `occurrence_service.py` |
| 2.1 | cancel_occurrence_sync → REVOKED | `occurrence_service.py` |
| 2.2 | cancel_open_occurrence_for_block_sync → REVOKED | `occurrence_service.py` |
| 3.1 | Remover crédito executado SUBSTITUTED | `occurrence_service.py` |
| 3.2 | Remover bloqueio LessonLog em sub blocks | `lesson_log_service.py` |
| 3.3 | Permitir OCCURRENCE futuro | `lesson_log_service.py` |
| 4.1 | Remover decisão inline | `LessonLogModal.jsx` |
| 4.2 | Footer 3 botões | `LessonLogModal.jsx` |
| 4.3 | Regras disabled | `LessonLogModal.jsx` |
| 4.4 | Banner informativo | `LessonLogModal.jsx` |
| 4.5 | Apagar SubstitutionStep.jsx | `SubstitutionStep.jsx` |
| 4.6 | Limpar imports | `LessonLogModal.jsx` |
| 5.1 | Estados finais não clicáveis | `WeekGrid.jsx` |
| 5.2 | Visual grayed out | `WeekGrid.jsx` |
| 5.3 | Labels atualizados | `WeekGrid.jsx` |
| 5.4 | Action label simplificado | `WeekGrid.jsx` |
| 6.1 | Colunas da tabela | `Occurrences.jsx` |
| 6.2 | Badges de estado | `Occurrences.jsx` |
| 6.3 | Botões contextuais | `Occurrences.jsx` |
| 6.4 | Tabs Pendentes/Histórico | `Occurrences.jsx` |
| 6.5 | Expansão de linha | `Occurrences.jsx` |
| 6.6 | Filtro de estado | `Occurrences.jsx` |
| 7.1 | Modal unificado em Schedules | `Schedules.jsx` |
| 7.2 | Navegação dashboard→/absences | `AlertBar.jsx` |
| 8.1 | Atualizar testes existentes | `tests/` |
| 8.2 | Criar 12 novos testes | `tests/test_lesson_registration.py` |

---

## 4. Dependências e Ordem de Implementação

```
Fase 1 (modelo + migração)
  │
  ├──► Fase 2 (REVOKED pipeline)
  │
  ├──► Fase 3 (contabilidade + futuro + sub interativo)
  │
  ├──► Fase 4 (rollback modal) ──► Fase 5 (grayed out) ──► Fase 7 (ajustes finais)
  │
  └──► Fase 6 (/absences tabela)
  
  Todas ──► Fase 8 (testes)
```

**Ordem recomendada:** 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8

---

## 5. Critérios de Aceitação Globais

1. **Modal idêntico:** Professor e admin veem exatamente os mesmos 3 botões no `LessonLogModal`.
2. **Registo sem gestão:** O modal serve apenas para registar (Aula Dada / Criar Ocorrência), nunca para decidir.
3. **Centralização:** 100% das decisões (Furo, Substituição, Reverter) são tomadas em `/absences`.
4. **Grayed out:** Blocos COMPLETED, OCCURRENCE, GAP, SUBSTITUTED são grayed out e não clicáveis.
5. **Bloco substituto interativo:** Professor substituto pode registar Aula Dada / Criar Ocorrência no bloco de substituição.
6. **Contabilidade correta:** SUBSTITUTED → debt no original. Substituto ganha horas via LessonLog.
7. **Auditoria:** Ocorrências revertidas ficam como REVOKED na BD, visíveis no Histórico.
8. **Antecedência:** Professor pode criar ocorrência e preencher sumário/notas em slots futuros.
9. **Testes:** 30 testes existentes passam + 12 novos testes passam.
10. **Build:** Frontend `npm run build` sem erros.
