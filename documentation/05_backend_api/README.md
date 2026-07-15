# Backend API

Esta secao cobre a Layer Interface do lado backend.

## Conteudo principal
- ENDPOINT_STANDARDS.md: padroes de contrato, autorizacao por role e fronteira clean architecture.
- Baseline Equipa/membros: a API admin canonica de staff management e `/members`; `/teachers` fica reservado para self-service do professor e operacoes de dominio/scheduler quando aplicavel.

## Compromisso
- API previsivel, segura e orientada a tenant isolation.

## Beta remediation contracts

- `POST /api/v1/session/bootstrap` has no body. It uses the verified Clerk user,
  active organization, and role claims, confirms provider membership, and
  idempotently returns the local organization/member bootstrap result.
- Constraint creation accepts only `specific_room`, `lock_time`,
  `teacher_unavailable`, and `teacher_preferred`, each with a strict typed
  payload. Unsupported or malformed writes return `422`.
- Constraint reads include `generation_compatible` and `validation_errors`.
- Generation returns `409 SCHEDULER_CONSTRAINT_CONFIGURATION_INVALID` before
  queueing work when a persisted legacy row cannot be interpreted safely.
