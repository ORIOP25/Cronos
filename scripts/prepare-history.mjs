import { isDeepStrictEqual } from 'node:util'
import { evaluateAcceptance } from '../frontend/e2e/utils/acceptance-policy.js'

export function evaluatePreparation(run, registry, artifacts) {
  const failures = [...evaluateAcceptance(run).failures]
  const prepared = run.preparation
  if (run.mode !== 'preparation' || run.cases?.length) failures.push('Preparation cannot certify acceptance cases')
  if (!run.data_verified || !run.data || !run.evidence_protected) failures.push('Preparation data or protection is unavailable')
  for (const phase of ['before', 'after']) {
    if (run.deployments?.filter(item => item.phase === phase).length !== 1) failures.push('Preparation deployment snapshot is missing')
  }
  if (!prepared || prepared.schema_version !== 1 || prepared.status !== 'prepared' || prepared.run_id !== run.run_id
    || prepared.revision !== run.expected_revision || prepared.history_verified !== false) failures.push('Preparation identity or state is invalid')
  const checked = Date.parse(prepared?.prepared_at)
  if (!Number.isFinite(checked) || checked < Date.parse(run.started_at) || checked > Date.parse(run.finished_at)) failures.push('Preparation timestamp is outside the campaign')
  const before = Date.parse(run.deployments?.find(item => item.phase === 'before')?.checked_at)
  const after = Date.parse(run.deployments?.find(item => item.phase === 'after')?.checked_at)
  if (!Number.isFinite(before) || !Number.isFinite(after) || checked < before || checked > after) failures.push('Preparation is outside deployment verification')
  const school = prepared?.organization
  if (registry?.run_id !== run.run_id || registry.organizations?.length !== 1 || !isDeepStrictEqual(registry.organizations[0], school)
    || school?.type !== 'persistent' || school?.provenance !== 'ui' || school?.creation_run_id !== run.run_id
    || !Number.isSafeInteger(school?.local_id) || school.local_id <= 0 || !/^org_[a-zA-Z0-9]+$/.test(school?.clerk_id || '')
    || school?.actors?.length !== 2 || !['admincronos100', 'professorcronos100'].every(base => school.actors.some(actor => actor.email === `${base}+${run.run_id}@gmail.com`))) {
    failures.push('Persistent UI ownership is unconfirmed')
  }
  const publication = prepared?.publication
  if (publication?.publication_state !== 'PUBLISHED' || !Number.isSafeInteger(publication?.active_version_id)
    || publication.active_version_id <= 0 || publication.active_job !== null || publication.pending_proposal !== null
    || !Number.isSafeInteger(prepared?.teacher_id) || prepared.teacher_id <= 0
    || !Number.isSafeInteger(prepared?.proposal_id) || prepared.proposal_id <= 0) failures.push('Persistent publication is incomplete')
  if (!run.data || !isDeepStrictEqual(prepared?.original_files, run.data.files) || !isDeepStrictEqual(prepared?.counts, run.data.counts)
    || prepared?.required_minutes !== run.data.required_minutes) failures.push('Preparation does not match the full original data')
  const path = prepared?.credentials_path
  if (typeof path !== 'string' || !path.endsWith('.enc') || /[\\:\0]/.test(path)
    || path.split('/').some(part => !part || part === '.' || part === '..') || !artifacts?.some(item => item.path === path)) {
    failures.push('Protected persistent credentials are missing')
  }
  return { status: failures.length ? 'failed' : 'prepared', failures }
}
