import assert from 'node:assert/strict'
import test from 'node:test'
import { evaluatePreparation } from './prepare-history.mjs'
import { COMPONENTS, evaluateAcceptance } from '../frontend/e2e/utils/acceptance-policy.js'

function fixture() {
  const organization = { local_id: 7, clerk_id: 'org_school', creation_run_id: 'run-1', provenance: 'ui', type: 'persistent',
    actors: [{ id: 'user_admin', email: 'admincronos100+run-1@gmail.com' }, { id: 'user_teacher', email: 'professorcronos100+run-1@gmail.com' }] }
  const data = { files: { rooms: { sha256: 'a'.repeat(64) } }, counts: { rooms: 48 }, required_minutes: 1_209_600 }
  const revision = 'a'.repeat(40)
  const prepared = { schema_version: 1, status: 'prepared', run_id: 'run-1', revision, organization,
    prepared_at: '2026-10-08T10:30:00.000Z', proposal_id: 6, publication: { publication_state: 'PUBLISHED', active_version_id: 8, active_job: null, pending_proposal: null },
    original_files: data.files, counts: data.counts, required_minutes: data.required_minutes, teacher_id: 9,
    credentials_path: 'preparation/persistent-credentials.json.enc', history_verified: false }
  const run = { schema_version: 1, run_id: 'run-1', mode: 'preparation', expected_revision: revision, tests_revision: revision,
    started_at: '2026-10-08T10:00:00.000Z', finished_at: '2026-10-08T11:00:00.000Z', cases: [], failures: [], data, preparation: prepared,
    data_verified: true, evidence_protected: true, cleanup: { run_id: 'run-1', status: 'completed', pending: [], pending_actors: [] },
    deployments: ['before', 'after'].map((phase, index) => ({ phase, checked_at: index ? '2026-10-08T10:59:00.000Z' : '2026-10-08T10:01:00.000Z', components: Object.fromEntries(COMPONENTS.map(name => [name, revision])) })) }
  return { run, registry: { run_id: 'run-1', organizations: [organization] }, artifacts: [{ path: prepared.credentials_path }] }
}

test('preparation can prove a published UI school without certifying the acceptance matrix', () => {
  const f = fixture()
  assert.equal(evaluatePreparation(f.run, f.registry, f.artifacts).status, 'prepared')
  assert.equal(evaluateAcceptance(f.run).status, 'incomplete')
})

test('preparation refuses incomplete UI evidence, mixed campaigns and unprotected credentials', () => {
  for (const corrupt of [
    f => { f.run.preparation.organization.type = 'disposable' },
    f => { f.run.preparation.organization.provenance = 'seed' },
    f => { f.run.preparation.run_id = 'foreign' },
    f => { f.run.preparation.revision = 'b'.repeat(40) },
    f => { f.run.preparation.prepared_at = '2026-10-09T10:30:00.000Z' },
    f => { f.run.preparation.prepared_at = '2026-10-08T10:00:30.000Z' },
    f => { f.run.preparation.prepared_at = '2026-10-08T10:59:30.000Z' },
    f => { f.run.preparation.publication.active_version_id = null },
    f => { delete f.run.preparation.proposal_id },
    f => { f.run.preparation.proposal_id = 0 },
    f => { f.run.preparation.publication.pending_proposal = { id: 1 } },
    f => { f.run.preparation.original_files = {} },
    f => { f.run.preparation.required_minutes = 1 },
    f => { f.run.preparation.history_verified = true },
    f => { f.run.cleanup.status = 'failed' },
    f => { f.run.deployments.pop() },
    f => { f.run.deployments[0].components.worker = 'b'.repeat(40) },
    f => { f.run.evidence_protected = false },
    f => { f.run.failures.push('Browser runtime failed') },
    f => { f.artifacts = [] },
    f => { f.run.preparation.credentials_path = '../persistent-credentials.json.enc' },
    f => { f.registry = { ...f.registry, organizations: [] } },
  ]) {
    const f = fixture(); corrupt(f)
    assert.equal(evaluatePreparation(f.run, f.registry, f.artifacts).status, 'failed')
  }
})
