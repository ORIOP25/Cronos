import { mkdir, writeFile } from 'node:fs/promises'
import { dirname, isAbsolute, relative, resolve, sep } from 'node:path'

// A checkpoint proves one tightly related observable block. The enclosing test
// may pass, but a case without its own completed checkpoint must stay incomplete.
export const PROOF_SCHEMA_VERSION = 2

// The readonly public diagnosis selects exactly these cases. The whitelist is
// explicit so no user-supplied filter can hide a failure or add a case.
export const PUBLIC_READONLY_TAG = '@public-readonly'
export const PUBLIC_READONLY_CASES = Object.freeze([
  Object.freeze({ id: 'E2E-16/public-routing', requirement: 'E2E-16', name: 'public-routing' }),
  Object.freeze({ id: 'E2E-16/legal-pages', requirement: 'E2E-16', name: 'legal-pages' }),
  Object.freeze({ id: 'E2E-16/public-404', requirement: 'E2E-16', name: 'public-404' }),
  Object.freeze({ id: 'E2E-16/keyboard-focus-announcements', requirement: 'E2E-16', name: 'keyboard-focus-announcements' }),
])

const PUBLIC_READONLY_IDS = new Set(PUBLIC_READONLY_CASES.map(item => item.id))

// Pure pre-body guard. Under the readonly public diagnosis a group must declare
// exactly one acceptance-case annotation from the whitelist. The runtime fixture
// calls it before the group body, so an accidentally tagged contact or identity
// group is refused before it can send mail or write business state. Other modes
// are unaffected.
export function publicReadonlySelection({ mode, annotations } = {}) {
  if (mode !== 'diagnose-public') return { ok: true }
  const ids = (Array.isArray(annotations) ? annotations : [])
    .filter(item => item?.type === 'acceptance-case')
    .map(item => item.description)
  if (ids.length !== 1) return { ok: false, reason: `Public diagnosis requires exactly one acceptance case annotation, found ${ids.length}` }
  if (!PUBLIC_READONLY_IDS.has(ids[0])) return { ok: false, reason: `Public diagnosis refuses non-readonly case: ${ids[0]}` }
  return { ok: true, id: ids[0] }
}

const PROVENANCE_SOURCES = new Set(['page', 'actor', 'school'])
const UTC_INSTANT = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/

function exactInstant(value) {
  const time = typeof value === 'string' ? Date.parse(value) : Number.NaN
  if (!UTC_INSTANT.test(value || '') || !Number.isFinite(time) || new Date(time).toISOString() !== value) {
    throw new Error('Checkpoint timestamps must be exact UTC instants')
  }
  return value
}

const NUL = String.fromCharCode(0)

export function validEvidencePath(path) {
  if (typeof path !== 'string' || !path || path.includes(NUL)) return false
  if (path.startsWith('/') || isAbsolute(path) || /[\\:]/.test(path)) return false
  return path.split('/').every(part => part && part !== '.' && part !== '..')
}

export function evidencePath(artifactRoot, candidate) {
  const path = relative(resolve(artifactRoot), resolve(candidate))
  if (!path || path === '..' || path.startsWith(`..${sep}`) || isAbsolute(path)) return null
  const normalized = path.split(sep).join('/')
  return validEvidencePath(normalized) ? normalized : null
}

// Evidence paths must be relative to the configured project output directory,
// the same root the reporter receives. Use the native project value instead of
// inferring it from the (nested) per-test output directory.
export function proofArtifactRoot(testInfo) {
  const root = testInfo?.project?.outputDir
  if (typeof root !== 'string' || !root) throw new Error('Acceptance proof requires the configured project output directory')
  return resolve(root)
}

export function checkpointRecord({
  caseIds, evidence, startedAt, finishedAt, requires = 'page',
  pageObserved, actorObserved = false, schoolObserved = false,
}) {
  const ids = (Array.isArray(caseIds) ? caseIds : [caseIds]).filter(id => typeof id === 'string' && id)
  if (!ids.length) throw new Error('A checkpoint requires concrete acceptance case IDs')
  if (ids.length !== new Set(ids).size) throw new Error('A checkpoint cannot repeat acceptance case IDs')
  if (!Array.isArray(evidence) || !evidence.length || evidence.some(path => !validEvidencePath(path))) {
    throw new Error('A checkpoint requires materialized evidence paths')
  }
  if (!PROVENANCE_SOURCES.has(requires)) throw new Error('A checkpoint requires a known provenance source')
  const start = exactInstant(startedAt)
  const end = exactInstant(finishedAt)
  if (Date.parse(end) < Date.parse(start)) throw new Error('A checkpoint cannot finish before it starts')
  const uiProvenance = pageObserved === true
    && (requires === 'page' || (requires === 'actor' ? actorObserved === true : schoolObserved === true))
  return Object.freeze({
    schema_version: PROOF_SCHEMA_VERSION,
    case_ids: ids,
    started_at: start,
    finished_at: end,
    eligible: uiProvenance,
    ui_provenance: uiProvenance,
    evidence: [...new Set(evidence)],
  })
}

export function matchCaseProof(caseId, records) {
  const matches = (records || []).filter(record => Array.isArray(record?.case_ids) && record.case_ids.includes(caseId))
  if (matches.length > 1) return { failure: `Ambiguous acceptance proof: ${caseId}` }
  return { proof: matches[0] ?? null }
}

export function validateProofEvidence(proof, actualPaths, caseId) {
  if (!proof) return { evidence: [], failures: [] }
  if (!Array.isArray(proof.evidence) || !proof.evidence.length) {
    return { evidence: [], failures: [`Missing acceptance evidence: ${caseId}`] }
  }
  const evidence = []
  const failures = []
  for (const path of proof.evidence) {
    if (!validEvidencePath(path)) failures.push(`Invalid acceptance evidence: ${caseId}`)
    else if (!actualPaths.includes(path)) failures.push(`Unmatched acceptance evidence: ${caseId}`)
    else evidence.push(path)
  }
  return { evidence: [...new Set(evidence)], failures }
}

// Adapter state: pure policies above, observed browser/file effects below.
const sessions = new WeakMap()
let evidenceCounter = 0

export function beginProofSession(testInfo, artifactRoot) {
  const now = new Date().toISOString()
  const session = {
    artifactRoot, records: [], cursor: testInfo.attachments.length, mark: now,
    activities: 0, claimedActivities: 0, actor: false, school: false,
  }
  sessions.set(testInfo, session)
  return session
}

export function finishProofSession(testInfo) {
  const session = sessions.get(testInfo)
  sessions.delete(testInfo)
  return session?.records ?? []
}

export function notePageActivity(testInfo, count = 1) {
  const session = sessions.get(testInfo)
  if (session) session.activities += count
}

export function noteActorObservation(testInfo) {
  const session = sessions.get(testInfo)
  if (session) session.actor = true
}

export function noteSchoolObservation(testInfo) {
  const session = sessions.get(testInfo)
  if (session) session.school = true
}

// An existing signed persistent school only grants provenance when the live
// browser session shows the same Clerk actor that owns it and the same active
// organization. It never writes the old actor as a freshly created record.
export function persistentSchoolProvenance(school, observed) {
  if (!school || typeof school.clerk_id !== 'string' || !school.clerk_id) return false
  if (observed?.organization_id !== school.clerk_id) return false
  const actors = Array.isArray(school.actors) ? school.actors : []
  return actors.some(actor => actor?.id === observed?.actor_id && actor.provenance === 'ui'
    && (actor.creation_run_id === school.creation_run_id || actor.id === school.creator_id))
}

export function notePersistentSchoolObservation(testInfo, school, observed) {
  if (!persistentSchoolProvenance(school, observed)) return false
  noteActorObservation(testInfo)
  noteSchoolObservation(testInfo)
  return true
}

const JSON_CONTENT = /^application\/(?:[a-z0-9.+-]+\+)?json(?:;|$)/i

function evidenceExtension(attachment) {
  if (!JSON_CONTENT.test(String(attachment.contentType || ''))) return '.bin'
  try {
    const body = Buffer.isBuffer(attachment.body) ? attachment.body : Buffer.from(String(attachment.body))
    JSON.parse(body.toString('utf8'))
    return '.json'
  } catch { return '.bin' }
}

function evidenceName(attachment, extension) {
  const safe = String(attachment.name || 'evidence').replace(/[^a-zA-Z0-9._-]+/g, '-').slice(0, 60)
  evidenceCounter += 1
  return `${String(evidenceCounter).padStart(3, '0')}-${safe}${extension}`
}

async function materialize(testInfo, artifactRoot, attachment) {
  const bytes = Buffer.isBuffer(attachment.body) ? attachment.body : Buffer.from(String(attachment.body))
  const file = testInfo.outputPath('acceptance-evidence', evidenceName(attachment, evidenceExtension(attachment)))
  await mkdir(dirname(file), { recursive: true })
  await writeFile(file, bytes, { flag: 'wx', mode: 0o600 })
  await testInfo.attach(attachment.name, { path: file, contentType: attachment.contentType || 'application/octet-stream' })
  return evidencePath(artifactRoot, testInfo.attachments.at(-1).path)
}

const RESERVED_EVIDENCE_NAME = 'acceptance-proof'

// A required name must belong to the claimed evidence window and materialize
// into it. The claim loop never consumes the reserved proof attachment, a path
// outside the artifact root never claims the name, and a non-claiming
// checkpoint has no claimed window at all.
function missingRequiredEvidence(pending, requiredEvidence, { artifactRoot, claim }) {
  if (!requiredEvidence || !requiredEvidence.length) return []
  const claimable = name => name !== RESERVED_EVIDENCE_NAME && claim && pending.some(attachment => attachment.name === name
    && (attachment.path ? evidencePath(artifactRoot, attachment.path) !== null : Boolean(attachment.body)))
  return requiredEvidence.filter(name => !claimable(name))
}

// Claim the pending evidence for one checkpoint. The reserved proof attachment
// is never claimed. A path inside the artifact root is claimed as-is; a body is
// materialized into the artifact root. This is the only materialization site.
async function collectClaimedEvidence(testInfo, session, pending) {
  const evidence = []
  for (const attachment of pending) {
    if (attachment.name === RESERVED_EVIDENCE_NAME) continue
    if (attachment.path) {
      const path = evidencePath(session.artifactRoot, attachment.path)
      if (path) evidence.push(path)
      continue
    }
    if (attachment.body) {
      const path = await materialize(testInfo, session.artifactRoot, attachment)
      if (path) evidence.push(path)
    }
  }
  return evidence
}

export async function recordCheckpoint(testInfo, caseIds, { requires = 'page', startedAt, observation, requiredEvidence, claim = true } = {}) {
  const session = sessions.get(testInfo)
  if (!session) throw new Error('Acceptance checkpoints require an active proof session')
  const pending = testInfo.attachments.slice(session.cursor)
  const missing = missingRequiredEvidence(pending, requiredEvidence, { artifactRoot: session.artifactRoot, claim })
  if (missing.length) throw new Error(`A checkpoint requires completed evidence: ${missing.join(', ')}`)
  const evidence = claim ? await collectClaimedEvidence(testInfo, session, pending) : []
  if (!evidence.length) {
    if (observation === undefined) throw new Error('A checkpoint requires at least one materialized evidence attachment')
    const path = await materialize(testInfo, session.artifactRoot, {
      name: 'checkpoint-observation', body: Buffer.from(JSON.stringify(observation)), contentType: 'application/json',
    })
    evidence.push(path)
  }
  const finishedAt = new Date().toISOString()
  const record = checkpointRecord({
    caseIds, evidence, requires,
    startedAt: startedAt || session.mark, finishedAt,
    pageObserved: session.activities > session.claimedActivities,
    actorObserved: session.actor, schoolObserved: session.school,
  })
  session.records.push(record)
  // A non-claiming checkpoint shares its observed activity window and start
  // timestamp with the next checkpoint of the same block. Only a claiming
  // checkpoint consumes the window and advances the evidence cursor.
  if (claim) {
    session.claimedActivities = session.activities
    session.mark = finishedAt
    session.cursor = testInfo.attachments.length
  }
  await testInfo.attach('acceptance-proof', { body: Buffer.from(JSON.stringify(record)), contentType: 'application/json' })
  return record
}
