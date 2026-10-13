# Privacy Operations

## Scope

This is the minimum operating manual for the Cronos launch. It is not legal advice. A Portuguese legal review remains a release gate.

## Roles and records

- For contact requests, Cronos is the controller. The service uses Resend for delivery and Turnstile for abuse prevention.
- For school records, the school is the controller and Cronos is the processor under the DPA.
- The organization acceptance records the legal entity, representative, current Terms version, current DPA version, and server timestamp.
- The acceptance table is append-only. Never edit or delete it through the application.

## Retention matrix

| Record | Rule |
| --- | --- |
| Completed or ignored Clerk webhook payload | Replace with `{}` immediately. |
| Completed or ignored Clerk webhook event | Delete after 30 days. |
| `received`, `processing`, or `retryable_failed` webhook | Keep while unresolved. |
| `sync_error` or `dead_letter` webhook | Delete 30 days after `support_resolved_at`. |
| Failed webhook payload | Keep until support resolution; never redact an unresolved failure. |
| Successful/compensated member access operation | Redact technical draft data immediately; delete after 30 days. |
| Failed member access operation | Keep for 30 days; do not delete while support is pending; delete 30 days after resolution. |
| Scheduler generation job | Keep operational history; no retention redaction or deletion worker. |
| Tutorial checkpoint | Browser-only, 30-day TTL; no server telemetry. |
| School data | Keep during service or until the school instructs deletion. |
| Legal acceptance | Keep for the necessary legal evidence period. |

The daily Celery task `privacy.run_maintenance` calls `PrivacyMaintenanceService` in
`backend/app/services/privacy_maintenance_service.py`. It processes batches of at
most 500 rows and logs counts only.

## Rights request procedure

1. Record the request date, identity checks, organization, scope, and deadline.
2. For school data, route the request to the school first and record the instruction.
3. Use the export command for a verified organization request.
4. Use the erase command only after the operator confirms the request and Clerk organization ID.
5. Respond without exposing another tenant. The normal legal response period is one month.

## Export

From `backend/`, run:

```text
python -m scripts.privacy export --organization-id <id> --output <explicit-file.zip>
```

The command writes one UTF-8 JSON member per relevant table, a manifest, and SHA-256 hashes. It excludes secrets, tokens, passwords, and other tenants.
The exporter creates each destination exclusively with mode `0600`; an existing file remains unchanged.
New parent directories use mode `0700`. Parent traversal and symbolic parent directories are rejected.
The plain and encrypted exporters share this file creation policy.
The standalone export reads through `DATABASE_URL` with the tenant context.
The campaign wrapper reuses the same classified export within its administrative transaction.

## Erasure

Always run a dry-run first:

```text
python -m scripts.privacy erase --organization-id <id> --confirm-clerk-org-id <clerk-id>
```

Execute only after approval:

```text
python -m scripts.privacy erase --organization-id <id> --confirm-clerk-org-id <clerk-id> --execute --provider-deleted
```

Execution suspends the organization, deletes operational tenant records in one transaction, deletes orphaned user profiles, preserves legal acceptance, and leaves a minimum tombstone. Disable the organization in Clerk through the runbook. The command prints counts, never deleted content.
The explicit `PRIVACY_TABLES` registry classifies every tenant table. The preserved
tables are `organization`, `organization_legal_acceptance`, and `alembic_version`.

The required sequence is export first, confirmed provider deletion second, and
the local transaction last. Execution requires both `--execute` and
`--provider-deleted`; the command is otherwise a dry-run.
Execution also refuses active jobs in both scheduler generations while holding
the organization row lock until commit.

## Incident and breach checklist

- Record discovery time, systems, organizations, categories, and containment actions.
- Preserve relevant evidence without copying unnecessary personal data.
- Assess risk and whether notification to the school or CNPD is required.
- Use the 72-hour assessment clock from awareness of a reportable breach.
- Record the decision, rationale, approver, communications, and follow-up controls.

## Supplier and document changes

Before changing Clerk, Railway, Resend, or Cloudflare configuration, update the public supplier list, assess transfer safeguards, and review the DPA.

When Terms or DPA versions change, update the backend constants and documents in the same change. The legal gate then requires fresh organization acceptance.
The current backend versions are Terms `2026-01`, DPA `2026-01`, and Privacy `2026-01` in `backend/app/legal.py`.

## Launch checklist

- Publish the complete professional address and public email.
- Complete legal review of Privacy, Terms, and DPA.
- Confirm Railway platform logs and alerts cover incident detection (there is no external error tracker).
- Notify API consumers that occurrence payloads containing `reason` now fail with `422`.
- Confirm Clerk Legal Compliance links and required cookies.
- Confirm Turnstile has no preclearance and loads only in the final contact step.
- Set the shortest Railway log retention available.
- Confirm supplier DPAs and regions.
- Run RLS, retention, export, erasure, build, and E2E gates.
