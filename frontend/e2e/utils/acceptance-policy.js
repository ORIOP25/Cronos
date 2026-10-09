const FULL_REVISION = /^[a-f0-9]{40}$/
const MAILBOXES = { admin: 'admincronos100@gmail.com', teacher: 'professorcronos100@gmail.com' }
export const CODE_SENDER_PATTERN = /^[a-z0-9._-]+@cronos\.pt$/
export const COMPONENTS = ['frontend', 'api', 'worker', 'supervisor', 'beat']

// The single observed production sender must be known before any account effect.
// Presence stays a dependency; a present but malformed value is a hard failure.
export function validateCodeSender(value) {
  if (!CODE_SENDER_PATTERN.test(value || '')) throw new Error('Configure the observed production code sender')
  return value
}

// Each variant is required separately. A requirement label alone is not coverage.
export const REQUIRED_CASES = Object.entries({
  'E2E-01': ['founder-registration', 'email-verification', 'foundation-completion'],
  'E2E-02': ['admin-login-logout', 'teacher-login-logout', 'new-context-login'],
  'E2E-03': ['delivered-recovery', 'credential-change', 'recovered-login'],
  'E2E-04': ['delivered-invitation', 'invitation-acceptance', 'pending-conversion-relations'],
  'E2E-05': ['five-original-imports', 'entity-relations', 'import-report', 'reload-persistence'],
  'E2E-06': ['resource-crud', 'archive-restore', 'initial-class', 'availability-persistence'],
  'E2E-07': ['ten-foundation-steps', 'preferred-date-draft', 'calendar-persistence', 'readiness'],
  'E2E-08': ['generation-confirmation', 'terminal-job', 'complete-coverage', 'hard-constraints'],
  'E2E-09': ['approve-proposal', 'reject-proposal', 'teacher-published-schedule', 'new-session-progress'],
  'E2E-10': ['ended-lesson-log', 'exact-minute-delta', 'repeat-without-duplicate', 'premature-execution-blocked'],
  'E2E-11': ['pending-zero-credit', 'given-decision', 'gap-debt', 'planned-substitution-reservation', 'ended-substitution-credit', 'reversal-compensations', 'stale-version'],
  'E2E-12': ['incomplete-week-blocked', 'submit-week', 'approve-week', 'closed-week-blocked', 'reopen-week'],
  'E2E-13': ['future-change-repair', 'physical-lineage', 'residual-coverage', 'historical-credit-preserved'],
  'E2E-14': ['distinct-schools', 'switch-without-cache-leak', 'stale-feedback-blocked'],
  'E2E-15': ['teacher-admin-routes-denied', 'denied-actions-no-effects'],
  'E2E-16': ['public-routing', 'legal-pages', 'contact-delivered', 'public-404', 'authenticated-404', 'keyboard-focus-announcements', 'five-model-downloads'],
  'E2E-17': ['guide-complete-resume', 'tutorial-isolation'],
  'E2E-18': ['school-year-change', 'disposable-school-deletion', 'protected-history'],
}).flatMap(([requirement, names]) => names.map(name => Object.freeze({ id: `${requirement}/${name}`, requirement, name })))
Object.freeze(REQUIRED_CASES)

function utcTimestamp(value) {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?(?:Z|\+00:00)$/.test(value)) return Number.NaN
  const timestamp = Date.parse(value)
  return Number.isFinite(timestamp) && new Date(timestamp).toISOString().slice(0, 19) === value.slice(0, 19) ? timestamp : Number.NaN
}

export function validateProductionConfig(environment) {
  if (environment.BASE_URL !== 'https://cronos.pt') throw new Error('BASE_URL must be exactly https://cronos.pt')
  if (!FULL_REVISION.test(environment.E2E_EXPECTED_REVISION || '')) throw new Error('Expected revision must be a full SHA')
  for (const [actor, mailbox] of Object.entries(MAILBOXES)) {
    if (environment[`E2E_${actor.toUpperCase()}_EMAIL`] !== mailbox) throw new Error(`Use the dedicated ${actor} mailbox`)
  }
  return { baseUrl: environment.BASE_URL, expectedRevision: environment.E2E_EXPECTED_REVISION, mailboxes: { ...MAILBOXES } }
}

function evaluateSnapshotTiming(snapshot, cases, started, finished, failures) {
  const checked = utcTimestamp(snapshot.checked_at)
  if (!Number.isFinite(checked) || checked < started || checked > finished) failures.push('Deployment snapshot is outside the campaign')
  if (snapshot.phase === 'before' && cases.some(item => utcTimestamp(item.started_at) < checked)) failures.push('Deployment preflight occurred after case execution')
  if (snapshot.phase === 'after' && cases.some(item => utcTimestamp(item.finished_at) > checked)) failures.push('Final deployment check occurred before case execution ended')
}

function evaluateSnapshotComponents(snapshot, expectedRevision, failures) {
  for (const name of COMPONENTS) {
    if (snapshot.components?.[name] !== expectedRevision) failures.push(`Deployment revision mismatch: ${name}`)
  }
}

function evaluateDeploymentSnapshots(run, cases, { started, finished }, { failures, incomplete }) {
  const deployments = run.deployments || []
  for (const phase of ['before', 'after']) {
    if (deployments.filter(item => item.phase === phase).length !== 1) incomplete.push(`Missing unique ${phase} deployment snapshot`)
  }
  for (const snapshot of deployments) {
    evaluateSnapshotTiming(snapshot, cases, started, finished, failures)
    evaluateSnapshotComponents(snapshot, run.expected_revision, failures)
  }
}

function evaluateProtectionAndCleanup(run, { failures, incomplete }) {
  if (run.data_verified !== true) incomplete.push('Original data not verified')
  if (run.evidence_protected !== true) failures.push('Evidence protection not confirmed')
  if (run.cleanup?.status !== 'completed') failures.push('Cleanup not completed')
  if (run.cleanup?.run_id !== run.run_id) failures.push('Cleanup run identity does not match the campaign')
  for (const name of ['pending', 'pending_actors']) {
    if (!Array.isArray(run.cleanup?.[name]) || run.cleanup[name].length) failures.push(`Cleanup targets remain pending or unknown: ${name}`)
  }
}

function evaluateCaseStatus(item, { failures, incomplete, dependencies }) {
  if (item.status === 'failed' || item.attempts !== 1) failures.push(`Case failed or retried: ${item.id}`)
  else if (item.status === 'dependency_unavailable') dependencies.push(item.id)
  else if (item.status !== 'passed') incomplete.push(`Case not passed: ${item.id}`)
}

function evaluateCaseEvidence(item, { failures, incomplete }) {
  if (!Array.isArray(item.evidence) || !item.evidence.length || item.evidence.some(path => typeof path !== 'string' || !path)) incomplete.push(`Missing evidence: ${item.id}`)
  else if (item.evidence.some(path => /[\\:]/.test(path) || path.includes('\0') || path.split('/').some(part => !part || part === '.' || part === '..'))) failures.push(`Invalid evidence reference: ${item.id}`)
}

function evaluateCaseIdentity(item, expected, { failures, incomplete }) {
  if (item.eligible !== true || item.ui_provenance !== true) incomplete.push(`Ineligible state or provenance: ${item.id}`)
  if (item.requirement !== expected?.requirement || item.name !== expected?.name) failures.push(`Case identity mismatch: ${item.id}`)
}

function evaluateCampaignCases(cases, { started, finished }, result) {
  const { failures, incomplete } = result
  const seen = new Set()
  const required = new Map(REQUIRED_CASES.map(item => [item.id, item]))
  for (const item of cases) {
    const caseStarted = utcTimestamp(item.started_at)
    const caseFinished = utcTimestamp(item.finished_at)
    if (!Number.isFinite(caseStarted) || !Number.isFinite(caseFinished) || caseStarted < started || caseFinished > finished || caseFinished < caseStarted) failures.push(`Invalid case timestamps: ${item.id}`)
    if (!required.has(item.id) || seen.has(item.id)) failures.push(`Unknown or duplicate case: ${item.id}`)
    seen.add(item.id)
    evaluateCaseStatus(item, result)
    evaluateCaseEvidence(item, result)
    evaluateCaseIdentity(item, required.get(item.id), result)

  }
  for (const id of required.keys()) if (!seen.has(id)) incomplete.push(`Missing case: ${id}`)
}

function acceptanceStatus({ failures, dependencies, incomplete }) {
  if (failures.length) return 'failed'
  if (dependencies.length) return 'dependency_unavailable'
  if (incomplete.length) return 'incomplete'
  return 'validated'
}

export function evaluateAcceptance(run) {
  const failures = [...(run.failures || [])]
  const incomplete = []
  const dependencies = []
  const result = { failures, dependencies, incomplete }
  const cases = run.cases || []
  const started = utcTimestamp(run.started_at)
  const finished = utcTimestamp(run.finished_at)
  if (run.schema_version !== 1 || typeof run.run_id !== 'string' || !/^[a-z0-9-]+$/.test(run.run_id)) failures.push('Invalid run identity')
  if (!FULL_REVISION.test(run.expected_revision || '') || run.tests_revision !== run.expected_revision) failures.push('Test revision does not match production')
  if (run.mode !== 'acceptance') incomplete.push('Diagnostic selection cannot certify production')
  if (!Number.isFinite(started) || !Number.isFinite(finished) || finished < started) failures.push('Invalid campaign timestamps')
  const timing = { started, finished }
  evaluateDeploymentSnapshots(run, cases, timing, result)
  evaluateProtectionAndCleanup(run, result)
  evaluateCampaignCases(cases, timing, result)
  return { status: acceptanceStatus(result), failures, dependencies, incomplete }
}
