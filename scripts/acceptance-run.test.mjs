import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { mkdtemp, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import test from 'node:test'
import {
  ACCEPTANCE_PROJECT,
  PLAYWRIGHT_PROCESS_FAILURE,
  PUBLIC_READONLY_CASES,
  PUBLIC_READONLY_TAG,
  acceptanceExitCode,
  acceptancePlan,
  acceptanceSecrets,
  assembleCampaign,
  evaluatePublicDiagnosis,
  publicDiagnosisPlan,
  publicDiagnosisRecord,
  publicReadonlyCleanup,
} from './acceptance-run.mjs'
import { productionDependencies, publicDiagnosticDependencies } from './real-browser-preflight.mjs'
import { signRegistry } from './e2e-run-registry.mjs'
import { redactSecrets } from './sanitize-test-artifacts.mjs'
import { COMPONENTS, evaluateAcceptance, REQUIRED_CASES } from '../frontend/e2e/utils/acceptance-policy.js'

const ROOT = fileURLToPath(new URL('..', import.meta.url))

const revision = 'c'.repeat(40)
const artifactDir = join('artifacts', 'run-1')

test('public Railway token type cannot corrupt account identity evidence', () => {
  const secrets = acceptanceSecrets({ E2E_RAILWAY_TOKEN_TYPE: 'account', E2E_RAILWAY_TOKEN: 'actual-token-value' }, [])
  const evidence = JSON.parse(redactSecrets(JSON.stringify({ member: { account_id: 7 }, token_type: 'account', credential: 'actual-token-value' }), secrets))
  assert.equal(evidence.member.account_id, 7)
  assert.equal(evidence.token_type, 'account')
  assert.equal(JSON.stringify(evidence).includes('actual-token-value'), false)
})
const startedAt = '2026-10-07T08:00:00.000Z'
const finishedAt = '2026-10-07T09:00:00.000Z'

test('acceptance redacts dedicated environment credentials and dynamic values without exporting an aggregate', () => {
  const result = acceptanceSecrets({
    E2E_ADMIN_SSH_KEY: 'private-key', E2E_ARTIFACT_KEY: 'encryption-key', E2E_REGISTRY_HMAC_KEY: 'signing-key',
    E2E_RAILWAY_TOKEN: 'provider-token', E2E_GMAIL_CLIENT_ID: 'oauth-client', E2E_GMAIL_CLIENT_SECRET: 'oauth-secret',
    E2E_RAILWAY_PROJECT_ID: 'public-project', E2E_ADMIN_EMAIL: 'public-email', EMPTY_TOKEN: '',
    MIGRATION_DATABASE_URL: 'postgresql://owner:private@database/db',
  }, ['123456', 'provider-token'])
  assert.deepEqual(new Set(result), new Set(['private-key', 'encryption-key', 'signing-key', 'provider-token', 'oauth-client', 'oauth-secret', '123456', 'postgresql://owner:private@database/db']))
  assert.throws(() => acceptanceSecrets({}, { secret: '123456' }), /array/)
  assert.throws(() => acceptanceSecrets({}, [null]), /strings/)
})

function readyEnvironment() {
  const environment = {
    BASE_URL: 'https://cronos.pt',
    E2E_EXPECTED_REVISION: revision,
    E2E_ADMIN_EMAIL: 'admincronos100@gmail.com',
    E2E_TEACHER_EMAIL: 'professorcronos100@gmail.com',
    E2E_ARTIFACT_KEY: Buffer.alloc(32, 7).toString('base64'),
    E2E_SECRET_REGISTRY: 'private-secrets.json',
  }
  for (const name of productionDependencies({})) environment[name] = 'configured'
  environment.E2E_ARTIFACT_KEY = Buffer.alloc(32, 7).toString('base64')
  environment.E2E_RAILWAY_TOKEN_TYPE = 'account'
  return environment
}

function preflightSnapshot(phase, checkedAt) {
  return {
    status: 'ready',
    phase,
    checked_at: checkedAt,
    components: Object.fromEntries(COMPONENTS.map(name => [name, revision])),
    deployments: { frontend: 'pages-deployment', api: 'api-deployment', worker: 'worker-deployment', supervisor: 'supervisor-deployment', beat: 'beat-deployment' },
    data: { counts: { rooms: 48 } },
  }
}

function playwrightReport() {
  return {
    schema_version: 1,
    started_at: startedAt,
    finished_at: finishedAt,
    playwright_status: 'passed',
    failures: [],
    cases: REQUIRED_CASES.map(item => ({
      ...item,
      started_at: '2026-10-07T08:10:00.000Z',
      finished_at: '2026-10-07T08:20:00.000Z',
      status: 'passed',
      attempts: 1,
      evidence: ['proof.json'],
      eligible: true,
      ui_provenance: true,
    })),
  }
}

function assemble(overrides = {}) {
  return assembleCampaign({
    runId: 'run-1',
    testsRevision: revision,
    expectedRevision: revision,
    startedAt,
    finishedAt,
    before: preflightSnapshot('before', startedAt),
    after: preflightSnapshot('after', finishedAt),
    playwrightReport: playwrightReport(),
    cleanup: { status: 'completed', run_id: 'run-1', pending: [], pending_actors: [] },
    ...overrides,
  })
}

test('acceptance requires every configured dependency before any browser effect', () => {
  const plan = acceptancePlan(readyEnvironment(), artifactDir)
  assert.equal(plan.status, 'ready')
  assert.equal(plan.project, 'acceptance')
  assert.equal(plan.workers, 1)
  assert.equal(plan.reportPath, join(artifactDir, 'acceptance-report.json'))
  assert.equal(plan.artifactRoot, join(artifactDir, 'acceptance-artifacts'))
  assert.equal(plan.resultPath, join(artifactDir, 'acceptance-result.json'))

  const incomplete = readyEnvironment()
  delete incomplete.E2E_GMAIL_ADMIN_REFRESH_TOKEN
  delete incomplete.E2E_RAILWAY_TOKEN
  const unavailable = acceptancePlan(incomplete, artifactDir)
  assert.equal(unavailable.status, 'dependency_unavailable')
  assert.deepEqual(unavailable.missing, ['E2E_GMAIL_ADMIN_REFRESH_TOKEN', 'E2E_RAILWAY_TOKEN'])
  assert.equal(unavailable.reportPath, undefined)

  const withoutSecrets = readyEnvironment()
  delete withoutSecrets.E2E_SECRET_REGISTRY
  const secretUnavailable = acceptancePlan(withoutSecrets, artifactDir)
  assert.equal(secretUnavailable.status, 'dependency_unavailable')
  assert.deepEqual(secretUnavailable.missing, ['E2E_SECRET_REGISTRY'])
  // Standalone preflight and the runner share the same dependency list.
  assert.ok(productionDependencies(withoutSecrets).includes('E2E_SECRET_REGISTRY'))

  assert.throws(() => acceptancePlan({ ...readyEnvironment(), BASE_URL: 'http://localhost:5173' }, artifactDir), /BASE_URL/)
  assert.throws(() => acceptancePlan({ ...readyEnvironment(), E2E_ARTIFACT_KEY: 'short' }, artifactDir), /32 random bytes/)
})

test('persistent preparation has a separate project and does not require an existing historical login', () => {
  const environment = readyEnvironment()
  delete environment.E2E_HISTORY_TEACHER_PASSWORD
  delete environment.E2E_HISTORY_ADMIN_PASSWORD
  const plan = acceptancePlan(environment, artifactDir, { preparation: true })
  assert.equal(plan.status, 'ready')
  assert.equal(plan.project, 'preparation')
  assert.equal(plan.reportPath, join(artifactDir, 'preparation-report.json'))
  assert.equal(acceptancePlan(environment, artifactDir).status, 'dependency_unavailable')
  delete environment.E2E_GMAIL_ADMIN_REFRESH_TOKEN
  assert.equal(acceptancePlan(environment, artifactDir, { preparation: true }).status, 'dependency_unavailable')
})

test('a different test revision is rejected before production preparation or acceptance', () => {
  for (const preparation of [false, true]) {
    assert.throws(() => acceptancePlan(readyEnvironment(), artifactDir, { preparation, testsRevision: 'd'.repeat(40) }), /revision/)
    assert.equal(acceptancePlan(readyEnvironment(), artifactDir, { preparation, testsRevision: revision }).status, 'ready')
  }
})

test('acceptance exit codes preserve validated, incomplete and dependency states', () => {
  assert.equal(acceptanceExitCode('validated'), 0)
  assert.equal(acceptanceExitCode('incomplete'), 1)
  assert.equal(acceptanceExitCode('failed'), 1)
  assert.equal(acceptanceExitCode('dependency_unavailable'), 3)
})

test('assembled campaigns carry identity, snapshots, cases and cleanup into the policy', () => {
  const run = assemble()
  assert.equal(run.schema_version, 1)
  assert.equal(run.run_id, 'run-1')
  assert.equal(run.mode, 'acceptance')
  assert.equal(run.tests_revision, revision)
  assert.equal(run.expected_revision, revision)
  assert.deepEqual(run.deployments.map(item => item.phase), ['before', 'after'])
  assert.equal(run.data_verified, true)
  assert.equal(run.evidence_protected, false)
  assert.equal(evaluateAcceptance({ ...run, evidence_protected: true }).status, 'validated')
})

test('missing snapshots, revisions, data or cleanup never produce green', () => {
  assert.equal(evaluateAcceptance({ ...assemble({ after: null }), evidence_protected: true }).status, 'incomplete')
  const mismatch = preflightSnapshot('before', startedAt)
  mismatch.components.worker = 'd'.repeat(40)
  assert.equal(evaluateAcceptance({ ...assemble({ before: mismatch }), evidence_protected: true }).status, 'failed')
  assert.equal(evaluateAcceptance({ ...assemble({ before: { status: 'failed', reason: 'x', checked_at: startedAt } }), evidence_protected: true }).status, 'incomplete')
  assert.equal(evaluateAcceptance({ ...assemble({ cleanup: { status: 'pending' } }), evidence_protected: true }).status, 'failed')
  assert.equal(assemble().data_verified, true)
  const notReady = assemble({ before: { status: 'dependency_unavailable', missing: ['x'], checked_at: startedAt } })
  assert.equal(notReady.data_verified, false)
})

test('reporter infrastructure failures are preserved in the assembled campaign', () => {
  const report = playwrightReport()
  report.failures = ['Test without a concrete acceptance case']
  report.cases = report.cases.slice(1)
  assert.equal(evaluateAcceptance({ ...assemble({ playwrightReport: report }), evidence_protected: true }).status, 'failed')
})

test('a captured Playwright process failure is signed and forbids a full green', () => {
  const run = assemble({ processFailed: true })
  assert.deepEqual(run.failures, [PLAYWRIGHT_PROCESS_FAILURE])
  assert.equal(evaluateAcceptance({ ...run, evidence_protected: true }).status, 'failed')
})

test('a reflected process failure preserves the primary reporter failure and the cleanup outcome', () => {
  const report = playwrightReport()
  report.failures = ['Primary product regression']
  const run = assemble({
    playwrightReport: report,
    processFailed: true,
    cleanup: { status: 'failed', run_id: 'run-1', pending: [], pending_actors: [] },
  })
  assert.deepEqual(run.failures, ['Primary product regression', PLAYWRIGHT_PROCESS_FAILURE])
  const assessment = evaluateAcceptance({ ...run, evidence_protected: true })
  assert.equal(assessment.status, 'failed')
  assert.ok(assessment.failures.includes('Primary product regression'))
  assert.ok(assessment.failures.includes('Cleanup not completed'))
})

test('a captured Playwright process failure forbids a readonly diagnostic pass', () => {
  const run = diagnosticRun({ failures: [PLAYWRIGHT_PROCESS_FAILURE] })
  assert.equal(evaluatePublicDiagnosis(run).status, 'failed')
})

function publicEnvironment() {
  const environment = {
    BASE_URL: 'https://cronos.pt',
    E2E_EXPECTED_REVISION: revision,
    E2E_ADMIN_EMAIL: 'admincronos100@gmail.com',
    E2E_TEACHER_EMAIL: 'professorcronos100@gmail.com',
    E2E_ARTIFACT_KEY: Buffer.alloc(32, 7).toString('base64'),
    E2E_REGISTRY_HMAC_KEY: Buffer.alloc(32, 8).toString('base64'),
    E2E_SECRET_REGISTRY: 'private-secrets.json',
  }
  for (const name of publicDiagnosticDependencies({})) environment[name] = 'configured'
  environment.E2E_ARTIFACT_KEY = Buffer.alloc(32, 7).toString('base64')
  environment.E2E_REGISTRY_HMAC_KEY = Buffer.alloc(32, 8).toString('base64')
  return environment
}

function diagnosticRun(overrides = {}) {
  const cases = PUBLIC_READONLY_CASES.map(item => ({
    ...item,
    started_at: '2026-10-07T08:10:00.000Z',
    finished_at: '2026-10-07T08:20:00.000Z',
    status: 'passed',
    attempts: 1,
    evidence: ['proof.json'],
    eligible: true,
    ui_provenance: true,
  }))
  return {
    schema_version: 1,
    run_id: 'run-1',
    mode: 'diagnostic',
    tests_revision: revision,
    expected_revision: revision,
    selection: { tag: PUBLIC_READONLY_TAG, cases: PUBLIC_READONLY_CASES.map(item => item.id) },
    started_at: startedAt,
    finished_at: finishedAt,
    deployments: ['before', 'after'].map(phase => ({
      phase,
      checked_at: phase === 'before' ? startedAt : finishedAt,
      components: Object.fromEntries(COMPONENTS.map(name => [name, revision])),
    })),
    data_verified: false,
    evidence_protected: true,
    cleanup: { status: 'completed', run_id: 'run-1', scope: 'public_readonly', not_needed: true, completed: [], removed_actors: [], pending: [], pending_actors: [] },
    failures: [],
    cases,
    ...overrides,
  }
}

test('public readonly diagnosis requires only its own dependencies and the explicit whitelist', () => {
  const environment = publicEnvironment()
  const plan = publicDiagnosisPlan(environment, artifactDir)
  assert.equal(plan.status, 'ready')
  assert.equal(plan.project, ACCEPTANCE_PROJECT)
  assert.equal(plan.workers, 1)
  assert.equal(plan.tag, PUBLIC_READONLY_TAG)
  assert.deepEqual(plan.cases, [
    'E2E-16/public-routing',
    'E2E-16/legal-pages',
    'E2E-16/public-404',
    'E2E-16/keyboard-focus-announcements',
  ])
  // The same environment keeps the full campaign blocked on its missing Gmail,
  // history, persistent school and administrative dependencies.
  assert.equal(acceptancePlan(environment, artifactDir).status, 'dependency_unavailable')
  assert.ok(productionDependencies(environment).includes('E2E_GMAIL_CODE_SENDER'))
  assert.ok(productionDependencies(environment).includes('E2E_HISTORY_TEACHER_PASSWORD'))
  assert.ok(productionDependencies(environment).includes('E2E_ADMIN_SSH_KEY'))

  const blocked = publicDiagnosisPlan({ ...environment, E2E_RAILWAY_TOKEN: '' }, artifactDir)
  assert.equal(blocked.status, 'dependency_unavailable')
  assert.deepEqual(blocked.missing, ['E2E_RAILWAY_TOKEN'])
  assert.throws(() => publicDiagnosisPlan({ ...environment, E2E_ARTIFACT_KEY: 'short' }, artifactDir), /32 random bytes/)
  assert.throws(() => publicDiagnosisPlan({ ...environment, E2E_REGISTRY_HMAC_KEY: 'short' }, artifactDir), /UI registry key/)
  assert.throws(() => publicDiagnosisPlan({ ...environment, BASE_URL: 'http://localhost:5173' }, artifactDir), /BASE_URL/)
  assert.throws(() => publicDiagnosisPlan(environment, artifactDir, { testsRevision: 'd'.repeat(40) }), /revision/)
  assert.equal(publicDiagnosisPlan(environment, artifactDir, { testsRevision: revision }).status, 'ready')
})

test('a fully passing readonly diagnosis passes but never certifies production', () => {
  const run = diagnosticRun()
  assert.equal(evaluatePublicDiagnosis(run).status, 'passed')
  // The shared full-campaign policy contributes no failure, and still never validates.
  assert.deepEqual(evaluateAcceptance(run).failures, [])
  assert.notEqual(evaluateAcceptance(run).status, 'validated')
  assert.equal(evaluateAcceptance(run).status, 'incomplete')
})

test('a failed shared full-campaign assessment can never become a passing diagnosis', () => {
  for (const mutate of [
    run => { run.tests_revision = 'd'.repeat(40) },
    run => { run.evidence_protected = false },
    run => { run.failures = ['product regression'] },
    run => { run.deployments[1].components.worker = 'd'.repeat(40) },
    run => { run.cases[0].requirement = 'E2E-01' },
    run => { run.cases[0].name = 'wrong-name' },
    run => { run.run_id = '../escape' },
    run => { run.cases[0].started_at = '2026-10-06T08:00:00.000Z' },
    run => { run.cleanup = { status: 'failed', run_id: 'run-1', scope: 'public_readonly', completed: [], removed_actors: [], pending: [], pending_actors: [] } },
    run => { run.cleanup.pending = [7] },
  ]) {
    const run = diagnosticRun()
    mutate(run)
    assert.ok(evaluateAcceptance(run).failures.length, 'shared policy must report a failure')
    assert.equal(evaluatePublicDiagnosis(run).status, 'failed')
  }
})

test('missing, failed, retried, unknown or mismatched readonly cases and unproven output fail the diagnosis', () => {
  for (const mutate of [
    run => { run.cases.pop() },
    run => { run.cases[0].status = 'failed' },
    run => { run.cases[0].attempts = 2 },
    run => { run.cases[0].eligible = false },
    run => { run.cases[0].evidence = [] },
    run => { run.cases.push({ id: 'E2E-16/contact-delivered', requirement: 'E2E-16', name: 'contact-delivered', status: 'passed', attempts: 1, evidence: ['proof.json'], eligible: true, ui_provenance: true }) },
    run => { run.mode = 'acceptance' },
    run => { delete run.selection },
    run => { run.selection = { tag: 'not-public', cases: [] } },
    run => { run.deployments.pop() },
    run => { run.cleanup.scope = 'full_campaign' },
    run => { run.cleanup.completed = [7] },
    run => { run.cleanup.removed_actors = ['user_owned'] },
  ]) {
    const run = diagnosticRun()
    mutate(run)
    assert.equal(evaluatePublicDiagnosis(run).status, 'failed')
  }
})

test('the derived diagnostic record is safe, describes both SHAs and never certifies', () => {
  const run = diagnosticRun()
  const diagnosis = evaluatePublicDiagnosis(run)
  const before = JSON.parse(JSON.stringify(run))
  const record = publicDiagnosisRecord(run, diagnosis)
  assert.deepEqual(run, before, 'the signed run must not be mutated')
  assert.equal(record.mode, 'diagnostic')
  assert.equal(record.run_id, 'run-1')
  assert.equal(record.tests_revision, revision)
  assert.equal(record.expected_revision, revision)
  assert.deepEqual(record.selection, { tag: PUBLIC_READONLY_TAG, cases: PUBLIC_READONLY_CASES.map(item => item.id) })
  assert.equal(record.certifies_production, false)
  assert.equal(record.status, 'passed')
  assert.deepEqual(record.failures, [])
})

test('readonly cleanup completes only an empty journal and never claims deletions', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'cronos-public-cleanup-'))
  try {
    const signingKey = Buffer.alloc(32, 8)
    const registry = (organizations, actors) => signRegistry({
      schema_version: 1, run_id: 'run-1',
      started_at: '2026-10-07T08:00:00.000Z', finished_at: '2026-10-07T08:00:00.000Z',
      organizations, actors,
    }, signingKey)
    const emptyPath = join(directory, 'empty.json')
    await writeFile(emptyPath, JSON.stringify(registry([], [])))
    const completed = await publicReadonlyCleanup({ registryPath: emptyPath, runId: 'run-1', signingKey })
    assert.equal(completed.status, 'completed')
    assert.equal(completed.scope, 'public_readonly')
    assert.equal(completed.not_needed, true)
    assert.deepEqual(completed.completed, [])
    assert.deepEqual(completed.pending, [])
    assert.deepEqual(completed.pending_actors, [])

    const busyPath = join(directory, 'busy.json')
    await writeFile(busyPath, JSON.stringify(registry([{ local_id: 7 }], [{ id: 'user_owned' }])))
    const blocked = await publicReadonlyCleanup({ registryPath: busyPath, runId: 'run-1', signingKey })
    assert.equal(blocked.status, 'failed')
    assert.deepEqual(blocked.pending, [7])
    assert.deepEqual(blocked.pending_actors, ['user_owned'])
    assert.deepEqual(blocked.completed, [])

    const missing = await publicReadonlyCleanup({ registryPath: join(directory, 'missing.json'), runId: 'run-1', signingKey })
    assert.equal(missing.status, 'failed')
  } finally {
    await rm(directory, { recursive: true, force: true })
  }
})

test('only the four readonly public specs carry the diagnosis tag and the contact case never does', async () => {
  const source = await readFileSync(join(ROOT, 'frontend/e2e/acceptance/public.spec.js'), 'utf8')
  const blocks = source.split(/\btest\(/).slice(1)
  assert.equal(blocks.length, 5)
  const tagged = blocks.filter(block => block.includes(`tag: '${PUBLIC_READONLY_TAG}'`))
  assert.equal(tagged.length, PUBLIC_READONLY_CASES.length)
  for (const item of PUBLIC_READONLY_CASES) {
    assert.ok(tagged.some(block => block.includes(`'${item.id}'`)), item.id)
  }
  const contact = blocks.find(block => block.includes("E2E-16/contact-delivered"))
  assert.ok(contact)
  assert.equal(contact.includes(PUBLIC_READONLY_TAG), false)
})
