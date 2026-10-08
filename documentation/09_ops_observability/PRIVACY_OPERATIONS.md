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

## Disposable browser campaign cleanup

From `backend/`, pass the signed UI ownership registry on stdin:

```text
python -m scripts.cleanup_e2e_run --run-id <run-id> --output-dir <private-export-directory>
```

The default is dry-run. Add `--execute` for the authorized campaign cleanup.
The wrapper requires `MIGRATION_DATABASE_URL`, `E2E_CLEANUP_CLERK_SECRET_KEY`,
`E2E_REGISTRY_HMAC_KEY`, and `E2E_ARTIFACT_KEY` in the administrative environment.
Protection keys contain 32 bytes encoded as canonical base64.
Keep these credentials out of the browser job.

The wrapper authenticates the registry before reading its IDs, preserves
persistent schools, and verifies live local/provider identities, creation,
creator and exact run aliases. It validates the whole plan before effects and
rechecks each disposable school under its row lock. It encrypts the export
before requesting provider deletion, requires the returned ID and `deleted=true`,
then reuses local erasure within the same transaction.
Only accounts created during the campaign without any remaining local or
provider memberships can be removed. Shared accounts remain intact.
The JSON result identifies completed and pending targets without printing
provider error bodies or credentials. A failed result requires reconciliation
of pending targets before the campaign can be considered clean.

The production acceptance runner invokes this wrapper through Railway SSH after every browser outcome.
It authenticates the signed UI registry, checks the published revision, and sends protection keys through SSH stdin.
The private SSH identity stays in a temporary local file and is removed after transport.
The runner stores authenticated encrypted exports and a protected copy of the UI registry with the acceptance evidence.
Encrypted remote backups remain in a private `/tmp/cronos-e2e-<run-id>-*` directory until recovery and reconciliation are confirmed.
The cleanup result records `remote_export_directory` for this recovery; it never includes provider credentials or exception bodies.
Use the exact recorded directory for administrative recovery. Preserve pending-target evidence before removing a remote backup.
If local export persistence fails, the failed result preserves authenticated remote completions and remaining targets.
It identifies exports already stored locally without overwriting existing evidence.

Use `--export-only` on the campaign wrapper to create protected backups before a native UI deletion.
This mode applies the same signed ownership, live membership and active-job checks.
It exports disposable schools without deleting provider organizations, accounts or local records.
`--execute` and `--export-only` are mutually exclusive.
An `exported` result keeps every deletion target pending; it cannot certify cleanup.
The Node transport requires authenticated backups for every reported exported organization.
Campaign organization archives include an `e2e_ownership` receipt captured under the organization lock.
The receipt records the actual provider identity and memberships checked before export.
Archive recovery verifies AES-GCM authentication, the complete manifest, table hashes and the organization/run scope before returning ownership.
This receipt does not certify provider deletion.
The backend wrapper can accept authenticated prior archives for disposable targets in the same signed run.
It validates their complete ownership scope before connecting to the database.
Only Clerk HTTP 404 permits using prior provider observations; other provider failures remain fatal.
The wrapper rechecks local accounts, current actor emails, creation times and active jobs under the organization lock.
It preserves the original protected backup before local erasure and does not repeat provider deletion.
The native deletion case first exports the selected disposable school into the protected campaign artifact directory.
The final runner authenticates existing target backups before SSH and sends only encrypted archives for the current signed run.
The returned backup must preserve the original bytes. Existing evidence cannot be replaced.
Actual native deletion and reconciliation in production remain unverified.
Actual production execution of this mode remains unverified.

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
- Approve the Sentry removal and equivalent platform alert coverage.
- Notify API consumers that occurrence payloads containing `reason` now fail with `422`.
- Confirm Clerk Legal Compliance links and required cookies.
- Confirm Turnstile has no preclearance and loads only in the final contact step.
- Set the shortest Railway log retention available.
- Confirm supplier DPAs and regions.
- Run RLS, retention, export, erasure, build, and E2E gates.
