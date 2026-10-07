import assert from 'node:assert/strict'
import { join } from 'node:path'
import test from 'node:test'
import { acceptanceExitCode, acceptancePlan, acceptanceSecrets, assembleCampaign } from './acceptance-run.mjs'
import { productionDependencies } from './real-browser-preflight.mjs'
import { COMPONENTS, evaluateAcceptance, REQUIRED_CASES } from '../frontend/e2e/utils/acceptance-policy.js'

const revision = 'c'.repeat(40)
const artifactDir = join('artifacts', 'run-1')
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
  assert.equal(acceptancePlan(withoutSecrets, artifactDir).status, 'dependency_unavailable')

  assert.throws(() => acceptancePlan({ ...readyEnvironment(), BASE_URL: 'http://localhost:5173' }, artifactDir), /BASE_URL/)
  assert.throws(() => acceptancePlan({ ...readyEnvironment(), E2E_ARTIFACT_KEY: 'short' }, artifactDir), /32 random bytes/)
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
