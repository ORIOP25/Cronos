# Ficheiros Candidatos a Apagar

## ✅ Já Apagados (Auditoria Alpha 1.0)
- `documentation/GERADOR_HORARIOS_PLANO.md` — removido (legacy, conteúdo desatualizado)
- `documentation/ANALISE_ENDPOINT_RESUMO.md` — removido (duplicação com BEST_PRACTICES_ENDPOINTS.md)
- `documentation/sonar_low_issues.json` — removido
- `documentation/sonar_medium_issues.json` — removido
- `documentation/sonar_high_issues.json` — removido
- `frontend/src/components/ImportForms/LessonForm.jsx` — removido (deprecado)
- `frontend/src/pages/ServiceDistribution.jsx` — removido (deprecado)
- `frontend/src/assets/marketing/` — removido (diretório vazio)
- `frontend/src/components/luxury/` — removido (diretório vazio)
- `backend/scripts/` — repovoado com scripts de manutenção

## ✅ Já Movidos
- `plan.md` → `documentation/10_migration_map/plan.md`

## ✅ Já Arquivados
- Reports Fase A-G do Solver V2 → `03_scheduler_engine/archive/`
- WBS Solver V2 (3 ficheiros) → `03_scheduler_engine/archive/`
- IMPLEMENTACAO_OCORRENCIAS_DIVIDA_E_REGISTOS → `04_operational_features/archive/`

## Pendentes de limpeza pelo baseline Equipa/members/Clerk

Estes itens sao legado quando a implementacao da Tech Spec `TECH_SPEC_CLERK_BACKED_EQUIPA_MEMBER_MANAGEMENT.md` for aplicada. Devem ser apagados ou reescritos no mesmo corte de implementacao para nao manter dois modelos de staff management.

- `frontend/src/pages/Teachers.jsx` como superficie admin visivel de CRUD de professores.
- `frontend/src/components/Forms/TeacherForm.jsx` enquanto contiver `create_user_account`, password ou copy de conta local.
- Testes frontend que afirmam password/admin-created account em `TeacherForm`.
- `POST/PATCH/DELETE /api/v1/teachers/` como CRUD admin canonico.
- Schemas `TeacherCreate`/`TeacherUpdate` com `create_user_account` no contrato canonico de staff management.
- Chamadas de criacao de professor que criam `User` local com `clerk_user_id = null` para representar acesso.
- Documentacao ou testes que apresentem `Conta Ativa`/`Inativo` local como estado de acesso de lancamento.

Devem permanecer, adaptados ao novo modelo:

- endpoints self-service de professor como `/teachers/me/availability` e `/teachers/me/progress`;
- recursos de teacher profile usados pelo scheduler, disponibilidade, horarios, fecho semanal e historico operacional;
- `teacher_subject_link` e restantes relacoes pedagogicas.
