import { readFile } from 'node:fs/promises'
import { join } from 'node:path'
import { evaluateAcceptance, validateProductionConfig } from '../frontend/e2e/utils/acceptance-policy.js'
import { PUBLIC_READONLY_CASES, PUBLIC_READONLY_TAG } from '../frontend/e2e/utils/acceptance-proof.js'
import { productionDependencies, publicDiagnosticDependencies } from './real-browser-preflight.mjs'
import { unresolvedUiCreationIntents, verifyRegistry } from './e2e-run-registry.mjs'

export const ACCEPTANCE_PROJECT = 'acceptance'
export const ACCEPTANCE_WORKERS = 1

export { PUBLIC_READONLY_CASES, PUBLIC_READONLY_TAG }

export function acceptanceSecrets(environment, dynamic) {
  if (!Array.isArray(dynamic)) throw new Error('Dynamic secret registry must be an array')
  if (dynamic.some(value => typeof value !== 'string')) throw new Error('Dynamic secrets must be strings')
  const configured = Object.entries(environment)
    .filter(([name, value]) => name !== 'E2E_RAILWAY_TOKEN_TYPE' && value && (/(?:SECRET|TOKEN|PASSWORD|KEY|AUTHORIZATION|COOKIE|DATABASE_URL)/i.test(name) || name === 'E2E_GMAIL_CLIENT_ID'))
    .map(([, value]) => value)
  return [...new Set([...configured, ...dynamic].filter(Boolean))]
}

export function acceptancePlan(environment, artifactDir, { preparation = false, testsRevision } = {}) {
  const config = validateProductionConfig(environment)
  const missing = productionDependencies(environment, { preparation })
  if (missing.length) return { status: 'dependency_unavailable', missing }
  if (testsRevision !== undefined && testsRevision !== config.expectedRevision) throw new Error('Test revision does not match production')
  if (Buffer.from(environment.E2E_ARTIFACT_KEY, 'base64').length !== 32) {
    throw new Error('Evidence key must contain exactly 32 random bytes')
  }
  return {
    status: 'ready',
    config,
    project: preparation ? 'preparation' : ACCEPTANCE_PROJECT,
    workers: ACCEPTANCE_WORKERS,
    reportPath: join(artifactDir, preparation ? 'preparation-report.json' : 'acceptance-report.json'),
    artifactRoot: join(artifactDir, 'acceptance-artifacts'),
    resultPath: join(artifactDir, 'acceptance-result.json'),
  }
}

export function acceptanceExitCode(status) {
  if (status === 'validated') return 0
  if (status === 'dependency_unavailable') return 3
  return 1
}

export function publicDiagnosisPlan(environment, artifactDir, { testsRevision } = {}) {
  const config = validateProductionConfig(environment)
  const missing = publicDiagnosticDependencies(environment)
  if (missing.length) return { status: 'dependency_unavailable', missing }
  if (testsRevision !== undefined && testsRevision !== config.expectedRevision) throw new Error('Test revision does not match production')
  if (Buffer.from(environment.E2E_ARTIFACT_KEY, 'base64').length !== 32) {
    throw new Error('Evidence key must contain exactly 32 random bytes')
  }
  if (Buffer.from(environment.E2E_REGISTRY_HMAC_KEY, 'base64').length !== 32) {
    throw new Error('UI registry key must contain exactly 32 random bytes')
  }
  return {
    status: 'ready',
    config,
    project: ACCEPTANCE_PROJECT,
    workers: ACCEPTANCE_WORKERS,
    tag: PUBLIC_READONLY_TAG,
    cases: PUBLIC_READONLY_CASES.map(item => item.id),
    reportPath: join(artifactDir, 'acceptance-report.json'),
    artifactRoot: join(artifactDir, 'acceptance-artifacts'),
    resultPath: join(artifactDir, 'acceptance-result.json'),
  }
}

// A readonly diagnosis writes no business state. An empty journal means cleanup
// is not needed; a non-empty journal is a real pending target, never a deletion.
export async function publicReadonlyCleanup({ registryPath, runId, signingKey }) {
  const failure = {
    run_id: runId, status: 'failed', scope: 'public_readonly', not_needed: false,
    completed: [], removed_actors: [], pending: [], pending_actors: [], failure_type: 'PublicReadonlyCleanupFailed',
  }
  try {
    const registry = verifyRegistry(JSON.parse(await readFile(registryPath, 'utf8')), signingKey)
    if (registry.schema_version !== 1 || registry.run_id !== runId
      || !Array.isArray(registry.organizations) || !Array.isArray(registry.actors)) {
      throw new Error('Public diagnosis registry identity mismatch')
    }
    // A write-ahead intent is possible orphaned identity even with no observed
    // actor or school. It fails closed and only reports a safe projection.
    let unresolved = [], invalid = false
    try { unresolved = unresolvedUiCreationIntents(registry) } catch { invalid = true }
    const pending = registry.organizations.map(item => item.local_id)
    const pendingActors = registry.actors.map(item => item.id)
    if (pending.length || pendingActors.length || unresolved.length || invalid) {
      return { ...failure, pending, pending_actors: pendingActors, ...(unresolved.length || invalid ? { unresolved_intents: unresolved } : {}) }
    }
    return {
      run_id: runId, status: 'completed', scope: 'public_readonly', not_needed: true,
      completed: [], removed_actors: [], pending: [], pending_actors: [], exports: [],
    }
  } catch {
    return failure
  }
}

// Diagnostic-specific pass/fail. The common schema, run identity, revision,
// timestamp, evidence path, cleanup and case identity integrity stays in the
// single full-campaign policy: a failed full assessment can never pass here.
// The diagnostic adds only the readonly whitelist, single-attempt provenance,
// unique before/after snapshots and an honest public_readonly journal. It never
// certifies production; the signed assessment stays incomplete.
export function evaluatePublicDiagnosis(run) {
  const policy = evaluateAcceptance(run)
  const failures = [...policy.failures]
  if (run.mode !== 'diagnostic') failures.push('Diagnostic selection mode is required')
  if (run.selection?.tag !== PUBLIC_READONLY_TAG) failures.push('Diagnostic selection tag is missing')
  const selected = new Set(PUBLIC_READONLY_CASES.map(item => item.id))
  const seen = new Set()
  for (const item of run.cases || []) {
    if (!selected.has(item.id) || seen.has(item.id)) { failures.push(`Unexpected diagnostic case: ${item.id}`); continue }
    seen.add(item.id)
    if (item.status !== 'passed' || item.attempts !== 1) failures.push(`Case failed or retried: ${item.id}`)
    if (!Array.isArray(item.evidence) || !item.evidence.length) failures.push(`Missing evidence: ${item.id}`)
    if (item.eligible !== true || item.ui_provenance !== true) failures.push(`Ineligible state or provenance: ${item.id}`)
  }
  for (const id of selected) if (!seen.has(id)) failures.push(`Missing diagnostic case: ${id}`)
  for (const phase of ['before', 'after']) {
    if ((run.deployments || []).filter(item => item.phase === phase).length !== 1) failures.push(`Missing unique ${phase} deployment snapshot`)
  }
  if (run.cleanup?.scope !== 'public_readonly') failures.push('Public readonly cleanup scope is missing')
  for (const name of ['completed', 'removed_actors']) {
    if (!Array.isArray(run.cleanup?.[name]) || run.cleanup[name].length) failures.push(`Readonly diagnosis performed deletions: ${name}`)
  }
  return { status: failures.length ? 'failed' : 'passed', failures }
}

// Safe derived summary for the artifact upload. It never mutates the signed run
// and never certifies production.
export function publicDiagnosisRecord(run, diagnosis) {
  return {
    mode: 'diagnostic',
    run_id: run.run_id,
    tests_revision: run.tests_revision,
    expected_revision: run.expected_revision,
    selection: { tag: run.selection?.tag, cases: [...(run.selection?.cases || [])] },
    certifies_production: false,
    status: diagnosis.status,
    failures: [...diagnosis.failures],
  }
}

function deploymentSnapshot(phase, result, checkedAt) {
  if (result?.status !== 'ready' || !result.components || !Object.keys(result.components).length) return null
  return { phase, checked_at: result.checked_at ?? checkedAt, components: { ...result.components }, deployments: { ...(result.deployments ?? {}) } }
}

export const PLAYWRIGHT_PROCESS_FAILURE = 'Playwright process did not pass'

export function assembleCampaign({ runId, testsRevision, expectedRevision, startedAt, finishedAt, before, after, playwrightReport, cleanup, processFailed = false }) {
  const report = playwrightReport ?? { failures: ['Acceptance reporter produced no report'], cases: [] }
  const failures = [...(report.failures ?? [])]
  // A nonzero Playwright process is a signed failure even when a reporter still
  // wrote a passing matrix. The reason is fixed and carries no raw process text.
  if (processFailed) failures.push(PLAYWRIGHT_PROCESS_FAILURE)
  return {
    schema_version: 1,
    run_id: runId,
    mode: 'acceptance',
    tests_revision: testsRevision,
    expected_revision: expectedRevision,
    started_at: startedAt,
    finished_at: finishedAt,
    deployments: [deploymentSnapshot('before', before, startedAt), deploymentSnapshot('after', after, finishedAt)].filter(Boolean),
    data_verified: before?.status === 'ready' && before.data !== undefined && before.data !== null,
    evidence_protected: false,
    cleanup: cleanup ?? { status: 'pending' },
    failures,
    cases: report.cases ?? [],
  }
}
