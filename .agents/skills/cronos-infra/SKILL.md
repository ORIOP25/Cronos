---
name: cronos-infra
description: Cronos infrastructure and release skill. Use for Docker and Compose, the test runner, GitHub Actions CI, pull request delivery, Railway, Cloudflare Pages and DNS, Clerk dashboard configuration, Hostinger mail, Resend, deploy verification, and production diagnosis.
---

# Cronos Infra

Load `cronos-base` and `ponytail` first.

## Start here

- Commands: [Command Reference](../../../documentation/00_getting_started/COMMAND_REFERENCE.md).
- Providers and production: [Cloud Operations](../../../documentation/09_ops_observability/CLOUD_OPERATIONS.md).
- Deployment contract and secrets: [Deployment Runbook](../../../documentation/09_ops_observability/DEPLOYMENT_RUNBOOK.md).
- CI: `.github/workflows/ci.yml`, `.github/workflows/deploy-check.yml`, and [Testing and CI](../../../documentation/08_security_quality/TESTING_AND_CI.md).
- Runner: `scripts/test.mjs` with tests in `scripts/test.test.mjs`.

## Delivery loop

1. Push the branch and open a pull request.
2. Run `gh pr checks <number> --watch` until `backend`, `frontend`, `e2e-runtime`, and `e2e-browser` finish.
3. On failure, run `gh run view <run-id> --log-failed`, fix the cause, push, and repeat.
4. Squash-merge with `gh pr merge <number> --squash` only when all four checks are green.
5. Run `gh run list --workflow "Deploy check" --limit 1` until the run for the merge commit passes.

## Boundaries

- Read-only provider inspection needs no approval. Every provider write needs explicit owner approval.
- Never print secret values. `railway variable list --json` prints raw values; list names only.
- Never use live Clerk keys in tests. E2E needs `pk_test_` and `sk_test_` keys and `+clerk_test@example.com` emails.
- Never run `docker compose down -v` or prune volumes.
- Never weaken a CI gate, skip a test, or add retries to make CI pass.
- Preserve the Hostinger MX, SPF, and DKIM records and the Resend `forms` records in any DNS change.

## Pitfalls

- A branch without a pull request gets no automatic CI.
- `e2e-browser` is skipped for Dependabot and fork pull requests; that skip is not proof.
- A frontend-only merge keeps the previous API revision; the Deploy check accepts that.
- Railway `railway.json` config-as-code ends on 1 December 2026. See [Cloud Operations](../../../documentation/09_ops_observability/CLOUD_OPERATIONS.md#known-open-items).
- On Windows, the runner runs Python inside `cronos-backend-test:local`. Rebuild it with `node scripts/test.mjs setup --scope backend` after dependency changes.
- Changes to `scripts/test.mjs` need `npm run test:scripts` in `frontend/`.

## Done when

- CI is green on the pull request, the merge is done, and the Deploy check passed for the merge commit.
- Any provider state you relied on is reported with the date you observed it.
