import { COMPONENTS } from '../frontend/e2e/utils/acceptance-policy.js'

export function preparationFixture(revision = 'a'.repeat(40)) {
  const runId = 'run-1'
  const organization = {
    local_id: 7, clerk_id: 'org_School', creation_run_id: runId, provenance: 'ui', type: 'persistent',
    actors: [
      { id: 'user_admin', email: `admincronos100+${runId}@gmail.com` },
      { id: 'user_teacher', email: `professorcronos100+${runId}@gmail.com` },
    ],
  }
  const data = { files: { rooms: { sha256: 'a'.repeat(64) } }, counts: { rooms: 48 }, required_minutes: 1_209_600 }
  const prepared = {
    schema_version: 1, status: 'prepared', run_id: runId, revision, organization,
    prepared_at: '2026-10-08T10:30:00.000Z', proposal_id: 6,
    publication: { publication_state: 'PUBLISHED', active_version_id: 8, active_job: null, pending_proposal: null },
    original_files: data.files, counts: data.counts, required_minutes: data.required_minutes, teacher_id: 9,
    credentials_path: 'preparation/persistent-credentials.json.enc', history_verified: false,
  }
  const run = {
    schema_version: 1, run_id: runId, mode: 'preparation', tests_revision: revision, expected_revision: revision,
    started_at: '2026-10-08T10:00:00.000Z', finished_at: '2026-10-08T11:00:00.000Z',
    cases: [], failures: [], data, preparation: prepared, data_verified: true, evidence_protected: false,
    cleanup: { run_id: runId, status: 'completed', pending: [], pending_actors: [] },
    deployments: ['before', 'after'].map((phase, index) => ({
      phase, checked_at: index ? '2026-10-08T10:59:00.000Z' : '2026-10-08T10:01:00.000Z',
      components: Object.fromEntries(COMPONENTS.map(name => [name, revision])),
    })),
  }
  return { run, registry: { run_id: runId, organizations: [organization] } }
}
