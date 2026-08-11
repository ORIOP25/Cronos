# Production Deployment Runbook

## Service Map

Create all Railway services in the Amsterdam region.

| Service | Configuration | Purpose |
|---|---|---|
| `api` | `/backend/railway/api.json` | Serve FastAPI and run migrations. |
| `worker` | `/backend/railway/worker.json` | Execute scheduler jobs. |
| `beat` | `/backend/railway/beat.json` | Publish hourly reconciliation jobs. |
| `db-bootstrap` | `/backend/railway/bootstrap.json` | Create restricted database roles once. |

Create one PostgreSQL service and one Redis service.

Attach persistent volumes to both data services.

Keep Redis on the private Railway network.

## Shared Variables

Set these variables on `api`, `worker`, and `beat`:

```dotenv
ENVIRONMENT=production
FRONTEND_URL=https://cronos.pt
CORS_ORIGINS=https://cronos.pt
CLERK_AUTHORIZED_PARTIES=https://cronos.pt
CLERK_INVITATION_REDIRECT_URL=https://cronos.pt/login
CLERK_CLOCK_SKEW_MS=60000
SOLVER_ENGINE_VERSION=v2
SOLVER_V2_ROLLING_WEEKS=8
RATELIMIT_ENABLED=true
CLERK_SECRET_KEY=
CLERK_WEBHOOK_SECRET=
RESEND_API_KEY=
TURNSTILE_SECRET_KEY=
SECRET_KEY=
CONTACT_EMAIL_FROM=website@forms.cronos.pt
CONTACT_EMAIL_TO=contacto@cronos.pt
CONTACT_EMAIL_TIMEOUT_SECONDS=10
TURNSTILE_ALLOWED_HOSTNAMES=cronos.pt,www.cronos.pt
TURNSTILE_TIMEOUT_SECONDS=5
TRUSTED_PROXY_IPS=100.0.0.0/8
```

Set private database and Redis references on each runtime service.

Set `DATABASE_POOLING_ENABLED=true` only on `api`.

Set `DATABASE_POOLING_ENABLED=false` on `worker` and `beat`.

Set `PORT=8000` on `api`.

## Database Bootstrap

1. Generate distinct passwords for `cronos_migrator` and `cronos_app`.
2. Create the temporary `db-bootstrap` service.
3. Select `/backend/railway/bootstrap.json` as its configuration.
4. Set `BOOTSTRAP_DATABASE_URL` to the private administrator URL.
5. Set `CRONOS_MIGRATOR_PASSWORD` and `CRONOS_APP_PASSWORD`.
6. Deploy the service.
7. Confirm exit code `0`.
8. Deploy it again to confirm idempotency.
9. Delete the temporary service.
10. Delete `BOOTSTRAP_DATABASE_URL` from Railway.

Build `DATABASE_URL` with the `cronos_app` role.

Build `MIGRATION_DATABASE_URL` with the `cronos_migrator` role.

## Runtime Deployment

1. Deploy `api` with one replica.
2. Confirm `GET /health/live` returns `200`.
3. Confirm `GET /health/ready` returns `200`.
4. Deploy `worker` with one replica.
5. Confirm worker concurrency equals one.
6. Confirm `scheduler.run_generation_job` appears in worker logs.
7. Deploy `beat` with one replica.
8. Confirm `members.run_scheduled_reconciliation` appears in beat logs.

Never run more than one Beat replica.

## Cloudflare Pages

Use `frontend` as the project root.

Run `npm ci && npm run build`.

Publish the `dist` directory.

Set Node.js to version 22.

Set these public build variables:

```dotenv
VITE_API_BASE_URL=https://api.cronos.pt/api/v1
VITE_CLERK_PUBLISHABLE_KEY=
VITE_TURNSTILE_SITE_KEY=
```

Test the `pages.dev` address before DNS cutover.

## DNS

1. Test the generated Railway domain.
2. Add `api.cronos.pt` to the Railway API service.
3. Create the requested Cloudflare records as DNS-only.
4. Wait for the Railway certificate.
5. Add `cronos.pt` to Cloudflare Pages.
6. Add `www.cronos.pt` to Cloudflare Pages.
7. Redirect `www` to the apex domain.
8. Verify TLS on all three hostnames.

Do not change Hostinger MX records.

Do not change the Hostinger apex SPF record.

## Backups

Railway-managed backups and point-in-time recovery require the Pro plan. The
initial Hobby deployment intentionally defers managed backups; do not upgrade
the workspace automatically.

Before relying on Cronos for irreplaceable production data, either upgrade to
Pro and enable daily plus weekly retention, or implement and restore-test an
encrypted external PostgreSQL backup outside Railway.

Until one of those options is active, record the deployment as operating
without backups and treat recovery from database loss as unavailable.

When backups are enabled, create a manual backup after bootstrap and migrations
and record its identifier in the release notes.

## Post-Deployment Verification

1. Submit one valid contact request.
2. Confirm the Hostinger mailbox receives the message.
3. Confirm `Reply-To` uses the visitor address.
4. Confirm Railway logs contain no personal data.
5. Test registration, login, logout, and invitations.
6. Generate and approve one complete schedule.
7. Test one repair operation.
8. Test one absence and substitution.
9. Confirm timesheets and progress views.
10. Confirm Redis has no public endpoint.

## Rollback

Restore the previous Cloudflare Pages deployment first.

Roll back `api`, `worker`, and `beat` independently.

Do not run automatic Alembic downgrades.

Confirm reverted code supports the current schema.

Restore prior DNS records only when deployment rollback fails.

Never change mail records during application rollback.

## Secret Rotation

1. Create the replacement provider secret.
2. Update the Railway variable.
3. Redeploy affected services.
4. Verify the affected production flow.
5. Revoke the previous secret.
6. Record the rotation date.

Never place secret values in Git, logs, screenshots, or tickets.
