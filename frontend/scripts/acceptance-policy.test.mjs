import assert from 'node:assert/strict'
import test from 'node:test'
import { validateProductionConfig, evaluateAcceptance, REQUIRED_CASES } from '../e2e/utils/acceptance-policy.js'

const revision = 'a'.repeat(40)
const environment = {
  BASE_URL: 'https://cronos.pt', E2E_EXPECTED_REVISION: revision,
  E2E_ADMIN_EMAIL: 'admincronos100@gmail.com', E2E_TEACHER_EMAIL: 'professorcronos100@gmail.com',
}

test('production configuration refuses local and unauthorised destinations', () => {
  assert.throws(() => validateProductionConfig({ BASE_URL: 'http://localhost' }), /BASE_URL/)
  assert.equal(validateProductionConfig(environment).expectedRevision, revision)
  for (const BASE_URL of [undefined, 'http://cronos.pt', 'https://cronos.pt.attacker.test', 'https://cronos.pt/path', 'https://user@cronos.pt']) {
    assert.throws(() => validateProductionConfig({ ...environment, BASE_URL }), /BASE_URL/)
  }
  for (const E2E_EXPECTED_REVISION of ['', 'abc123', 'x'.repeat(40)]) {
    assert.throws(() => validateProductionConfig({ ...environment, E2E_EXPECTED_REVISION }), /revision/i)
  }
  assert.throws(() => validateProductionConfig({ ...environment, E2E_TEACHER_EMAIL: 'customer@gmail.com' }), /dedicated/i)
})

function campaign() {
  return {
    schema_version: 1, run_id: 'run-1', mode: 'acceptance', tests_revision: revision, expected_revision: revision,
    started_at: '2026-10-07T08:00:00.000Z', finished_at: '2026-10-07T09:00:00.000Z',
    deployments: ['before', 'after'].map(phase => ({ phase, checked_at: phase === 'before' ? '2026-10-07T08:00:00.000Z' : '2026-10-07T09:00:00.000Z', components: Object.fromEntries(['frontend', 'api', 'worker', 'supervisor', 'beat'].map(name => [name, revision])) })),
    data_verified: true, evidence_protected: true, cleanup: { status: 'completed', run_id: 'run-1', pending: [], pending_actors: [] }, failures: [],
    cases: REQUIRED_CASES.map(item => ({ ...item, started_at: '2026-10-07T08:10:00.000Z', finished_at: '2026-10-07T08:20:00.000Z', status: 'passed', attempts: 1, evidence: ['proof.json'], eligible: true, ui_provenance: true })),
  }
}

test('only a complete campaign can validate production', () => {
  assert.equal(evaluateAcceptance(campaign()).status, 'validated')
  for (const mutate of [
    run => { run.cases.pop() }, run => { run.cases[0].status = 'skipped' },
    run => { run.cases[0].evidence = [] }, run => { run.mode = 'diagnostic' },
    run => { run.cases[0].eligible = false }, run => { run.cases[0].ui_provenance = false },
  ]) {
    const run = campaign(); mutate(run)
    assert.equal(evaluateAcceptance(run).status, 'incomplete')
  }
})

test('cleanup from another campaign or with unknown remaining targets cannot certify production', () => {
  for (const cleanup of [
    { status: 'completed', run_id: 'other', pending: [], pending_actors: [] },
    { status: 'completed', pending: [], pending_actors: [] },
    { status: 'completed', run_id: 'run-1' },
    { status: 'completed', run_id: 'run-1', pending: [17], pending_actors: [] },
    { status: 'completed', run_id: 'run-1', pending: [], pending_actors: ['user_owned'] },
  ]) assert.equal(evaluateAcceptance({ ...campaign(), cleanup }).status, 'failed')
})

test('revision, retry, duplicates and auxiliary failures never produce green', () => {
  for (const mutate of [
    run => { run.deployments[1].components.worker = 'b'.repeat(40) },
    run => { run.tests_revision = 'b'.repeat(40) }, run => { run.cases[0].attempts = 2 },
    run => { run.cleanup.status = 'failed' }, run => { run.evidence_protected = false },
    run => { run.failures = ['reporter failed'] }, run => { run.cases.push(run.cases[0]) },
  ]) {
    const run = campaign(); mutate(run)
    assert.equal(evaluateAcceptance(run).status, 'failed')
  }
  const run = campaign(); run.cases[0].status = 'dependency_unavailable'
  assert.equal(evaluateAcceptance(run).status, 'dependency_unavailable')
  run.failures = ['product regression']
  assert.equal(evaluateAcceptance(run).status, 'failed')
})

test('deployment observations and case proofs must be bounded by the actual campaign interval', () => {
  for (const mutate of [
    run => { run.deployments[0].checked_at = '2026-10-06T08:00:00.000Z' },
    run => { run.deployments[0].checked_at = '2026-10-07T08:15:00.000Z' },
    run => { run.deployments[1].checked_at = '2026-10-07T08:15:00.000Z' },
    run => { delete run.deployments[1].checked_at },
    run => { run.cases[0].started_at = '2026-10-07T07:00:00.000Z' },
    run => { run.cases[0].finished_at = '2026-10-07T08:00:00.000Z' },
    run => { run.cases[0].started_at = '2026-10-07T08:10:00' },
    run => { run.cases[0].evidence = ['../outside.json'] },
  ]) {
    const run = campaign(); mutate(run)
    assert.equal(evaluateAcceptance(run).status, 'failed')
  }
})
