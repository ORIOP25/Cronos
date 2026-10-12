# Testing and CI

The [production-browser acceptance PRD](REAL_BROWSER_TESTING_PLAN.md) and its [four-part WBS](REAL_BROWSER_TESTING_WBS.md) describe the agreed redesign.
The [implementation record](REAL_BROWSER_TESTING_IMPLEMENTATION.md) lists which parts are already proven and which dependencies remain.
This guide describes the implemented behaviour.

Cronos runs backend, frontend, and end-to-end suites through one root runner.
GitHub Actions enforces the same gates on every pull request and on every push to `main`.
A feature branch with an open pull request runs the full pipeline once through the pull request, instead of a second identical push run.
A branch pushed without a pull request has no automatic CI and requires an explicit manual `workflow_dispatch` checkpoint.

## Quick start

The supported entry point is the root runner:

```powershell
node scripts/test.mjs setup --scope all
node scripts/test.mjs doctor --profile all
node scripts/test.mjs fast --scope all
node scripts/test.mjs integration
node scripts/test.mjs e2e --project public
node scripts/test.mjs capacity-smoke
node scripts/test.mjs acceptance
node scripts/test.mjs all --scope all
node scripts/test.mjs benchmark --profile fast
node scripts/test.mjs campaign --manifest backend/tests/scheduler_lab/manifest.json
```

The runner exposes `setup`, `doctor`, `fast`, `integration`, `e2e`, `capacity`, `capacity-smoke`, `acceptance`, `prepare-history`, `diagnose-public`, `all`, `benchmark`, and `campaign`. The `e2e` command accepts `--project public|auth|app|isolated|readonly|provider|capacity`. E2E starts its own stack on port `5174`.

`fast` never starts Docker or installs packages. Forwarded arguments are accepted only after `--` by `fast` and `integration`, and are passed as separate process arguments. Run artefacts are written to `.test-artifacts/`.

## Backend suites

| Suite | Location | Execution |
| :--- | :--- | :--- |
| Unit | `backend/tests/unit/` | no database or external network; loopback-only socket policy |
| Transactional integration | `backend/tests/integration/transactional/` | real PostgreSQL/Redis stack |
| Committed integration | `backend/tests/integration/committed/` | real PostgreSQL/Redis stack, xdist=4 |
| Contracts | `backend/tests/contracts/` | real PostgreSQL/Redis stack, serial |

Suite membership is structural. PostgreSQL migrations always run through Alembic; SQLite and `metadata.create_all` are not valid substitutes. The runner creates `cronos_test_gw0` through `cronos_test_gw3` for xdist and uses separate migrator/runtime credentials. Destructive operations are accepted only for exact test database names.

Integration runs with `-n 4 --dist=loadscope`. Contracts run serially with rate limiting enabled. The coverage gate requires 70 percent overall, 100 percent for `app/scheduler/domain/constraint_policy.py`, and 90 percent for `app/scheduler/domain/candidate_validation.py`. Any skipped test fails the run.

## Frontend suites

The 48-class correctness test uses the production 900-second safety budget and stops at the first complete candidate.
It validates curricular coverage and completion dates. Short optimization deadlines must not make correctness depend on host load.

Vitest is configured in `frontend/vitest.config.js` with isolated `node`, `dom` and `dom-network` projects and thread pooling. Only the `dom-network` project keeps the MSW server with strict unhandled-request failures. Every other DOM test replaces `fetch` and `XMLHttpRequest` with a fail-closed guard that throws a classified `TestNetworkDeniedError`, so no accidental external request leaves the process. Coverage uses V8 and enforces thresholds of 45 percent statements, 40 percent branches, 35 percent functions, and 45 percent lines. React interactions that cross async boundaries use Testing Library `user-event`.

Playwright is configured in `frontend/playwright.config.js`. The `setup` project feeds `auth` and `auth-state`; the `public` project needs no authentication and no `setup` dependency. The shared chain is `auth-state` → `app` → `provider` → `readonly`. The `isolated` project depends on `setup` and covers fresh-or-existing journeys that create and clean their own user or organization. The `readonly` project depends on `provider` and runs after it, so the tutorial and localStorage-only journeys never race the shared soft-reset. The `app`, `provider`, `isolated` and `readonly` projects use one worker; independent projects receive a global fan-out of four workers, `auth` is bounded to two and `capacity` uses two. The retired `faults` project now maps to the two `isolated` and `readonly` case paths. The `capacity` project runs only when `CAPACITY_ENABLED=1`. The `acceptance` project matches `frontend/e2e/acceptance/*.spec.js`, uses the installed Chrome channel, one worker, no setup dependency and no test credentials. Retries are disabled; traces are retained on failure and screenshots are captured on failure.

All projects use the shared `E2E_BASE_URL`, which defaults to `http://127.0.0.1:5174`.
This address matches the owned Docker stack's IPv4 binding and avoids other processes listening on `localhost` over IPv6.
The runner supplies `http://localhost:5173` for an external stack.

After sign-in, the E2E helper waits for the loaded Clerk session and expected identity before activating the organization.
This prevents organization activation during a sign-in navigation while the browser reloads Clerk.

## CI gates

The owned local E2E stack builds the frontend `ci` target, which permits the dedicated Clerk test domain.
Its Nginx application routes include `/imports`. Production keeps its runtime browser policy.

GitHub Actions keeps backend, frontend and E2E in separate jobs. The backend job has a 45-minute timeout, the frontend job has a 20-minute timeout, and the E2E job has a 30-minute timeout.

Backend gates use Python 3.14 with `postgres:16` and `redis:7` services. The job provisions `cronos_migrator`, `cronos_app`, and `cronos_auth_definer`, installs locked dependencies with `--require-hashes`, runs `pip check` and `pip-audit`, checks Ruff formatting and linting, runs Alembic upgrade/check/downgrade/upgrade, runs the database integrity audits, runs unit tests with `-n 4 --dist=loadscope`, then integration tests, then contract tests, applies the coverage gates, and builds the hardened runtime image.

Frontend gates use Node 24 with `npm ci --ignore-scripts` and `npm run audit:production`. The job then runs the full `npm run verify` sequentially. An earlier in-job overlap of the static checks and the coverage run added wall time, so `verify` keeps `verify:checks`, coverage and build in order. The job also runs `node scripts/loc-report.mjs` against `documentation/08_security_quality/loc-baseline.json`.

E2E uses `docker-compose.ci.yml`. The stack builds the backend and frontend images in parallel before it starts. The job prepares dedicated Clerk test identities, runs `node scripts/test.mjs e2e` and `node scripts/test.mjs capacity-smoke`, sanitizes `.test-artifacts/` and Playwright output, and always cleans Compose resources and revokes Clerk invitations. A guarded upload keeps the runner `run.json` metadata always and the Playwright `e2e-all.xml` only when the E2E step passed; it never adds auth state, binaries, logs or private files. The E2E job is skipped for Dependabot.

Skipped tests, retries, missing artifacts and migration drift are release failures. E2E credentials must be dedicated Clerk test identities; they are not generated or persisted by local test setup.

## Production acceptance

`node scripts/test.mjs acceptance` is the entry point for the real-browser campaign against `https://cronos.pt`.
It runs the reporter-backed Playwright `acceptance` project in Chrome, verifies the Gmail mailboxes and the deployment revisions before and after the run, protects every binary artifact with the campaign key, and evaluates the case matrix with `frontend/e2e/utils/acceptance-policy.js`.
The runner exits `3` while any campaign dependency is missing, and writes the missing names to `.test-artifacts/<run>/acceptance-plan.json`.
The result document is `.test-artifacts/<run>/acceptance-result.json`; only `validated` for the complete matrix can certify production.

The campaign is fail-closed: a failed or missing reporter, an unprotected artifact, a revision mismatch, an unfinished cleanup or a retried case cannot produce green.
A nonzero Playwright process is signed as a failure even when a reporter still writes a passing matrix.
The finalizer redacts the report before signing.
Redaction walks the report structure and replaces string leaves.
An exact numeric match becomes `[REDACTED]`; other numeric and boolean metadata stays unchanged.
Short and six-digit secrets remain redacted; the redactor does not apply a minimum length.
The text sanitizer keeps its strict substring replacement for artifacts.
A finalization failure keeps the primary failure and records a fixed stage class.
The stage classes are `keys`, `root`, `registries`, `sanitize`, `inventory`, `evidence` and `sign`.
The finalizer never copies a raw exception message or an exception secret into the result.
The runner invokes the administrative wrapper (`backend/scripts/cleanup_e2e_run.py`) through native Railway SSH after the browser phase.
The wrapper consumes the dedicated `ui-run-registry.json` envelope, not the signed result manifest.
The transport authenticates encrypted exports before accepting deletion results; unfinished cleanup fails the campaign.
Actual production exports and deletion remain unverified.
The native Clerk deletion case exports its selected disposable school before confirming deletion through visible controls.
Final cleanup authenticates that prior backup locally and remotely before reconciling Clerk 404 with the current local ownership.
The returned archive must preserve its original bytes; changed or missing evidence prevents green.
Acceptance rejects cleanup from another `run_id` and requires empty `pending` and `pending_actors` arrays.
The legacy local `e2e` command remains a diagnostic until each substituted group has real proof.

`.github/workflows/acceptance.yml` runs the same command on the `main` SHA, serialized without automatic cancellation.
The finalizer already redacts the run before it signs, so `acceptance-result.json` is sealed and immutable after the signature.
The workflow never re-redacts its envelope, digests or wrapper; a registered secret that matches a digest substring cannot invalidate a legitimate sealed result.
The artifact-root sanitizer runs first and applies the shared tree policy to production `.json` evidence, so an escaped secret is redacted and the document stays well formed.
Other text artifacts (`.xml`, `.log`, `.html`) keep raw text redaction.
The legacy mode without a protection key keeps its raw text behaviour until cutover.
A malformed production JSON fails closed before the inventory and signature.
Then a dedicated verify step reuses the finalizer in the same CLI as `verify <result.json> <artifactRoot> [<verification-receipt.json>]`.
The verify step validates the signed envelope, the current artifact inventory and the wrapper `run`, `assessment` and `artifacts` mirror of the signed manifest.
Verification exits zero for artifact integrity only; it never certifies production.
The signed assessment stays incomplete or partial for preparation and diagnosis.
It rejects an altered result, an extra file, a tampered envelope, a missing file and a null envelope.
It prints a fixed status enum and never echoes a key or raw exception text.
The receipt is a fixed JSON document outside the artifact root with only `integrity`, `reason` and `certifies_production: false`.
It never contains a URL, file path, key or secret.
An existing receipt is never overwritten.
A conflicting path reports `receipt unavailable (conflict)` and exits nonzero without an availability flag.
The step writes one fixed boolean to the standard `GITHUB_OUTPUT`: `receipt_available=true` only when it created a new receipt in this execution.
An absent output means false.
A verify failure exits one after it writes the rejected receipt.
The diagnostics upload includes `artifact-verification.json` only when `receipt_available` is true, so a stale receipt is never published as the current verification.
The legacy two-argument verify form emits no availability flag and keeps its integrity exit code.
A later diagnostics step redacts only four allowlisted JSON files with the registered secrets: `acceptance-plan.json`, `acceptance-cleanup.json`, `diagnostic-assessment.json` and `artifact-verification.json`.
The step and the finalizer share one pure report-redaction policy.
It walks the parsed JSON tree: a decoded string leaf is redacted with the raw secret, an exact numeric secret becomes the redacted string, and field names stay unchanged.
It never rewrites escaped JSON text, so the document stays well formed.
A malformed document fails closed before any write.
A document whose parsed value is unchanged keeps its exact bytes.
The step rejects a non-regular path and never touches the private UI journal or secret registries that share the parent directory.
It also requires the directory and every ancestor to be a real directory, never a symbolic link or junction.
An empty diagnostics directory list is a usage error with a nonzero exit.
It uses the existing sanitizer secret and dynamic-registry logic and never prints a value.
The protected artifact root and the sealed result upload only when the verify step succeeds.
The diagnostic allowlist uploads only when the diagnostics step succeeds, so a failed job keeps a safe failure receipt.
When the verify step rejects, the sealed result and the protected root stay offline; only the redacted diagnostics and the rejected receipt upload.
When the campaign fails before a signed result exists, the dependency plan still uploads as a safe diagnostic and the verify step is skipped.
The derived diagnosis status describes the selected cases only; the receipt records the integrity outcome, so a failed integrity check is never labelled as a production certificate.
The mandatory CI exit status and the integrity receipt together govern the run outcome.
The runner also calls the verified-result guard after it writes the result and before any zero exit in the acceptance, preparation and diagnosis modes.
A guard failure is a separate classified runner stage; it never mutates the signed run or envelope.
It keeps the original verification error as a safe cause and never prints it.
The guard keeps the first Playwright failure class when that primary failure already exists.
Raw Playwright reports, JUnit output, private registries, storage state and other files outside this upload list remain excluded.
The sanitizer reads separated environment credentials and the private dynamic registry; an invalid registry prevents artifact changes and upload.
Both workflow modes require the `main` ref; PRs never receive these credentials.
The complete matrix runs only when `E2E_ACCEPTANCE_ENABLED` is `true`.
Manual dispatch with `mode=prepare-history` permits initial preparation while that variable remains disabled.
Both modes retain the same revision, Gmail, evidence and cleanup gates.
The three production modes share one runner flow and one signed-result finalizer; only the plan, preflight, Playwright selection, cleanup and final assessment differ.
An unknown mode is rejected before any effect.
Manual dispatch with `mode=diagnose-public` runs an explicit readonly public diagnosis while the full campaign variable remains disabled.
It selects only the four `@public-readonly` acceptance cases.
These cover public routing and canonicals, legal documents, the public 404 and the keyboard validation with zero business writes.
The runtime fixture refuses any extra, unannotated, identity or contact group before its body starts.
The runtime observer classifies a CSP-blocked Cloudflare beacon as optional telemetry only after it observes the matching script GET request.
Chrome can report console errors before the network request.
The observer resolves the console and CSP `requestfailed` pair causally.
Unverified console or network errors remain failures.
It attaches a safe snapshot of each ignored event to the signed artifact root.
Every other console, network, authentication or HTTP failure stays fail-closed.
It reuses the same Chrome `acceptance` project, reporter, run composition and finalizer.
It verifies the five deployment components before, per group and after the run.
It requires the Cloudflare and Railway provider tokens, the evidence and HMAC keys and the private redaction registry.
It does not require Gmail, the production code sender, a persistent school, historical passwords or the administrative SSH key.
It does not read mail and it does not open the administrative SSH channel, because the selected cases create no business state.
An empty journal reports zero business targets as `not needed`.
The run records `mode: diagnostic` with an explicit selection and both the test and production SHAs.
The command exits zero only when the selected four cases pass on one attempt.
It also requires valid revisions, protected evidence and an empty readonly journal.
Missing dependencies exit three and any failure exits non-zero.
The diagnosis reuses the full policy for the common schema, revision, timestamp, evidence path, cleanup and case-identity integrity.
A failed full assessment can never become a passing diagnosis.
The signed assessment always stays `incomplete`, because an incomplete diagnosis is not a production certificate.
The workflow uploads a derived `diagnostic-assessment.json` with the mode, run id, both SHAs, selection, `certifies_production: false` and the computed status.
The raw run report stays outside the upload allowlist.
The real campaign still requires the two Gmail OAuth consents, the Cloudflare and Railway read tokens, the browser/admin credentials, the signed persistent registry and the protected secret registry.
Isolated worker recovery is verified with real PostgreSQL, Redis, a real broker message and an owned Celery worker process in `backend/tests/integration/committed/test_worker_process_recovery.py`.

### Credential and provenance registries

Keep credentials in separate GitHub secrets.
Store the Pages token as `E2E_CLOUDFLARE_API_TOKEN`; the workflow maps it to `CLOUDFLARE_API_TOKEN`.
The runner collects sensitive environment values in memory for artifact redaction.
`E2E_SECRET_REGISTRY_JSON` initializes the private file named by `E2E_SECRET_REGISTRY`.
The workflow creates registry directories with mode `0700` and files with mode `0600`.
The running campaign appends observed verification codes and generated passwords to that file, without changing the GitHub secret.
It can start as `[]`; it must grow when the campaign observes new secrets.
The identity journey persists generated passwords and delivered codes before using them in the browser.
`E2E_GMAIL_CODE_SENDER` identifies the observed production verification/recovery sender; configure it as a repository variable.
Preflight requires this value before account creation. Do not derive it from the development Clerk instance.
The contact journey requires an authorized forward from `contacto@cronos.pt` to `admincronos100@gmail.com`.
Keep the production contact recipient unchanged. Configure forwarding separately; these tests do not provision it.
The provider check on 2026-10-08 found Hostinger MX records and disabled Cloudflare Email Routing.
Configure the forward with the current mailbox provider. Do not replace working MX records to enable these tests.
The reader checks the original To, Delivered-To, Reply-To, sender, bounded delivery time and all seven submitted answers.
Discovery includes the unique contact run marker. Other contact messages cannot satisfy the case.
`E2E_CONTACT_SENDER` optionally identifies a configured production sender; its default is `website@forms.cronos.pt`.
The browser uses the real Turnstile widget. Missing verification or missing delivered email fails the case.
Cloudflare does not support automated browsers for solving production challenges.
A manual challenge in another browser does not prove autonomous CI execution.
Test keys certify isolated integration behavior; they do not replace the required production acceptance proof.
OAuth profile verification does not prove that the forward exists; actual message observation provides that proof.
The current identity spec covers registration, verification, fresh-context login and delivered recovery through visible controls.
Its real execution remains pending production deployment alignment and the observed code sender; no new identity is certified by these code changes.
Logout, old-password rejection, teacher invitation and school setup have concrete UI journeys.
Their real production execution remains pending the complete campaign prerequisites.
The old-password journey accepts only the documented Clerk HTTP 422 password error for the observed request.
Other authentication failures, network failures and server errors fail the campaign.
Do not duplicate the administrative SSH private key in that JSON registry.

`E2E_PERSISTENT_REGISTRY_JSON` contains the signed campaign school inventory.
An empty signed inventory permits initial preparation; it does not prove eligible historical schools.
Historical cases require observed UI provenance, ended lessons and the required consecutive campaigns.

Run `node scripts/test.mjs prepare-history` to create a persistent full school through the production UI.
This command requires Gmail, matching published revisions, protected evidence and administrative access, but no existing historical password.
It reuses registration, Foundation, five original imports, invitation, generation, independent validation and native approval.
It stores registration, recovered administrator and teacher passwords in an encrypted recovery attachment before creating accounts.
The separate `preparation` project declares no acceptance case IDs and is excluded from default local E2E.
The runner protects evidence, checks the final deployments, preserves persistent identities and authenticates the prepared result.
Successful preparation atomically appends the school and preparation metadata to the signed persistent registry without replacing prior schools.
The metadata retains the observed approved proposal ID for later independent comparison of the materialized baseline.
Retain the protected artifact directory for credential recovery. Update the private GitHub persistent registry secret from the resulting signed file.
Configure the recovered persistent teacher credential as `E2E_HISTORY_TEACHER_PASSWORD` after successful preparation.
Configure the recovered founder credential as `E2E_HISTORY_ADMIN_PASSWORD` for native historical decisions and weekly approval.
The school starts after its actual creation day. Preparation neither backdates lessons nor certifies ended history.

### Preparation finalization and recovery

The preparation command protects every binary artifact before it signs the result.
It promotes the persistent school before the final signature.
It then encrypts the updated persistent registry and private secret registry into the artifact root.
The final manifest includes `preparation/persistent-registry.json.enc` and `preparation/private-secret-registry.json.enc`.
Verification accepts the delivered manifest only when both registries are present and authenticated.
The workflow never adds files to the signed artifact root after the signature.
The sanitizer runs after the signature and only validates the existing envelopes.

The finalization runs in two stages.
The first stage protects evidence and evaluates the preparation.
The second stage runs after the promotion and includes both protected registries.
The second stage starts from the first-stage assessment.
All first-stage ineligibility and promotion failures enter the signed run before signing.
No signed field changes after the final signature.
A failure in either stage prevents `prepared` and preserves the primary failure.
A promotion rejection becomes a classified failure.
The runner still writes protected recovery output when a stage fails.
The runner never uploads a raw registry file.

Recover one protected file with the separate artifact key:

```powershell
node scripts/protect-test-evidence.mjs recover <source.enc> <output-directory> <run-id> <original-relative-path>
```

Use the original relative path without the `.enc` suffix.
The command authenticates before writing and refuses overwrite, traversal and symbolic parents.
For preparation, the run id is the value in `E2E_RUN_ID`.
Recover `preparation/persistent-registry.json.enc`, `preparation/private-secret-registry.json.enc` and `preparation/persistent-credentials.json.enc`.
Update `E2E_PERSISTENT_REGISTRY_JSON` and `E2E_SECRET_REGISTRY_JSON` from the recovered registries.

Protect a raw registry only when the artifact root lacks its envelope:

```powershell
node scripts/protect-test-evidence.mjs protect <source> <destination.enc> <run-id> <relative-path>
```

The destination rejects lexical traversal and symbolic parents.
Write the envelope into the artifact root under the same relative path.
Do not upload a raw registry file.

`E2E_HISTORY_TEACHER_PASSWORD` holds the UI login credential of the first registered persistent school's invited teacher.
The history spec derives its dedicated alias from the signed school creation run and verifies the actual Clerk actor and organization.
It selects an ended, unregistered lesson at the actual curricular frontier and reads exact minute balances from weekly slices.
Editing the completed summary must preserve its log identity, minute balances and teacher progress.
Historical preflight requires both passwords; preparation requires neither. The runner and CI sanitizer redact both.

After preflight, the runner creates `.test-artifacts/<run>/ui-run-registry.json` with an authenticated empty actor inventory.
Acceptance fixtures record the current Clerk identity through `provenance.recordCurrentActor()` after a passing body.
The runtime fixture teardown reuses that same strict observation once when the body fails before its own recording.
The teardown observation runs only on the main page and is bounded by an explicit 5 second native poll.
It skips an actor already recorded for the session and never creates users or alters authentication.
The journal accepts only fresh dedicated aliases created within the run and preserves previous data when validation fails.
A passing body with a failing observation fails the test; a failed body keeps its primary error even when the auxiliary observation or diagnostic fails.
The plaintext journal stays outside the artifact upload list. The runner encrypts a recovery copy before automatic administrative cleanup.

The `acceptance` project currently implements five public cases, of which four are `@public-readonly`.
They use Chrome, semantic locators and the runtime observer without programmatic authentication or business seeds.
The fifth public case reads a delivered contact message and is excluded from the readonly diagnosis.
All 69 case IDs are defined and discovered. The matrix still requires real execution.
A green legacy CI run does not certify this production matrix.

## Code sender observation

`E2E_GMAIL_CODE_SENDER` must be the real production verification sender.
Observe it before setting the variable; never guess the address.

Run the readonly metadata observation against one dedicated mailbox:

```powershell
node scripts/inspect-e2e-code-sender.mjs
```

The environment selects the mailbox, the purpose and the bounded UTC window.
`E2E_INSPECT_MAILBOX` is `admin` or `teacher`; the default is `admin`.
`E2E_INSPECT_PURPOSE` is `verification` or `reset`; the default is `verification`.
`E2E_INSPECT_AFTER` and `E2E_INSPECT_BEFORE` are ISO-8601 UTC timestamps.
The default window ends now and starts seven days earlier.
A window above seven days requires `E2E_INSPECT_WINDOW_REASON`.
The maximum window is 30 days, with bounded messages, pages and time.
The workflow injects the selected mailbox token as `E2E_GMAIL_REFRESH_TOKEN`.
A local run may keep the role-specific `E2E_GMAIL_<ROLE>_REFRESH_TOKEN` fallback.

The reader requests only the `From`, `To` and `Subject` metadata headers.
It never reads the body, the snippet or the full message.
It reports only a fixed status, the distinct senders, the sender count, the message count and the bounded window.
It never prints the subject, the code, the body, raw headers, tokens, message IDs or alias addresses.
`certifies_production` is always `false`; the command never configures the variable.

The status is `observed`, `incomplete`, `dependency_unavailable` or `failed`.
`observed` exits zero, `dependency_unavailable` exits three, and anything else exits one.
A missing sender blocks preflight as `dependency_unavailable`.
A present but malformed sender fails preflight before any external request.
Set `E2E_GMAIL_CODE_SENDER` only after observing a unique sender.

Dispatch `.github/workflows/acceptance.yml` manually on `main`:

```powershell
gh workflow run acceptance.yml --ref main -f mode=inspect-code-sender -f mailbox=admin -f purpose=verification
```

Add `-f recipient=<base-or-alias>` to observe a specific authorized recipient.
`purpose` is `verification` or `reset`.
The dedicated readonly job installs no browser or Railway client.
It exposes one selected mailbox token, never both mailboxes at once.
It needs no administrative, deployment or evidence secret.
The metadata observation does not authenticate the mail origin and does not certify the case matrix.

## References

- [Contributing Guidelines](../00_getting_started/CONTRIBUTING.md)
- [Security and Tenant Isolation](SECURITY_AND_TENANT_ISOLATION.md)
- [Local Runtime](../09_ops_observability/LOCAL_RUNTIME.md)
- [Real browser testing WBS](REAL_BROWSER_TESTING_WBS.md)
- Workflows: `.github/workflows/ci.yml`, `.github/workflows/acceptance.yml`
