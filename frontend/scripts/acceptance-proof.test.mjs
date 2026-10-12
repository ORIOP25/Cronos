import assert from 'node:assert/strict'
import { randomBytes } from 'node:crypto'
import { mkdtemp, readFile, readdir, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import test from 'node:test'
import { finalizeRun } from '../../scripts/finalize-real-browser-run.mjs'
import {
  beginProofSession, checkpointRecord, evidencePath, finishProofSession, matchCaseProof,
  noteActorObservation, notePageActivity, notePersistentSchoolObservation, noteSchoolObservation,
  persistentSchoolProvenance, proofArtifactRoot, PUBLIC_READONLY_CASES, PUBLIC_READONLY_TAG,
  publicReadonlySelection, recordCheckpoint, validEvidencePath,
} from '../e2e/utils/acceptance-proof.js'

function fakeTestInfo(root) {
  const attachments = []
  return {
    attachments,
    outputPath: (...parts) => join(root, ...parts),
    attach: async (name, options) => {
      if (options.path !== undefined) attachments.push({ name, path: options.path, contentType: options.contentType })
      else attachments.push({ name, body: options.body, contentType: options.contentType })
    },
  }
}

test('a checkpoint record requires concrete cases, materialized evidence and a bounded interval', () => {
  const base = { startedAt: '2026-10-08T10:00:00.000Z', finishedAt: '2026-10-08T10:00:01.000Z', pageObserved: true }
  assert.throws(() => checkpointRecord({ ...base, caseIds: [], evidence: ['a.json'] }), /case IDs/)
  assert.throws(() => checkpointRecord({ ...base, caseIds: 'E2E-01/founder-registration', evidence: [] }), /evidence/)
  assert.throws(() => checkpointRecord({ ...base, caseIds: 'x', evidence: ['../escape.json'] }), /evidence/)
  assert.throws(() => checkpointRecord({ ...base, caseIds: 'x', evidence: ['ok.json'], finishedAt: '2026-10-08T09:59:59.000Z' }), /finish/)
  assert.throws(() => checkpointRecord({ ...base, caseIds: 'x', evidence: ['ok.json'], startedAt: '2026-10-08T10:00:00Z' }), /UTC/)
  assert.throws(() => checkpointRecord({ ...base, caseIds: ['x', 'x'], evidence: ['ok.json'] }), /repeat/)
  const record = checkpointRecord({ ...base, caseIds: ['x', 'y'], evidence: ['ok.json', 'ok.json'] })
  assert.deepEqual(record.case_ids, ['x', 'y'])
  assert.deepEqual(record.evidence, ['ok.json'])
  assert.equal(record.eligible, true)
  assert.equal(record.ui_provenance, true)
})

test('provenance needs an observed page and the required actor or school signature', () => {
  const base = { caseIds: 'x', evidence: ['ok.json'], startedAt: '2026-10-08T10:00:00.000Z', finishedAt: '2026-10-08T10:00:01.000Z' }
  assert.equal(checkpointRecord({ ...base, pageObserved: false }).ui_provenance, false)
  assert.equal(checkpointRecord({ ...base, pageObserved: true, requires: 'actor', actorObserved: false }).ui_provenance, false)
  assert.equal(checkpointRecord({ ...base, pageObserved: true, requires: 'actor', actorObserved: true }).ui_provenance, true)
  assert.equal(checkpointRecord({ ...base, pageObserved: true, requires: 'school', schoolObserved: false }).ui_provenance, false)
  assert.equal(checkpointRecord({ ...base, pageObserved: true, requires: 'school', schoolObserved: true }).ui_provenance, true)
})

test('path validation rejects traversal, absolute, drive and backslash references', () => {
  for (const value of ['../x.json', 'a/../../b', '/abs.json', 'C:/x.json', 'a\\b.json', '', 'a//b', 'a/./b']) {
    assert.equal(validEvidencePath(value), false, value)
  }
  assert.equal(validEvidencePath('acceptance/evidence.json'), true)
  assert.equal(evidencePath('C:/root', 'C:/root/nested/file.json'), 'nested/file.json')
  assert.equal(evidencePath('C:/root', 'C:/elsewhere/file.json'), null)
})

test('a skipped helper cannot emit a completion checkpoint', async () => {
  const root = await mkdtemp(join(tmpdir(), 'cronos-proof-'))
  try {
    const testInfo = fakeTestInfo(root)
    beginProofSession(testInfo, root)
    assert.deepEqual(finishProofSession(testInfo), [])
    assert.equal(testInfo.attachments.some(item => item.name === 'acceptance-proof'), false)
  } finally { await rm(root, { recursive: true, force: true }) }
})

test('each checkpoint materializes its own body evidence and keeps it bounded to its own window', async () => {
  const root = await mkdtemp(join(tmpdir(), 'cronos-proof-'))
  try {
    const testInfo = fakeTestInfo(root)
    beginProofSession(testInfo, root)
    await testInfo.attach('first-observation', { body: Buffer.from('{"variant":1}'), contentType: 'application/json' })
    notePageActivity(testInfo)
    const first = await recordCheckpoint(testInfo, 'E2E-16/public-404')
    await testInfo.attach('second-observation', { body: Buffer.from('{"variant":2}'), contentType: 'application/json' })
    notePageActivity(testInfo)
    const second = await recordCheckpoint(testInfo, 'E2E-16/legal-pages')
    assert.equal(first.eligible, true)
    assert.equal(second.eligible, true)
    assert.notDeepEqual(first.evidence, second.evidence)
    assert.ok(first.evidence.every(path => validEvidencePath(path)))
    assert.ok(Date.parse(second.started_at) >= Date.parse(first.finished_at))
    const materialized = JSON.parse(await readFile(join(root, ...first.evidence[0].split('/')), 'utf8'))
    assert.deepEqual(materialized, { variant: 1 })
    const proofs = testInfo.attachments.filter(item => item.name === 'acceptance-proof')
    assert.equal(proofs.length, 2)
    assert.equal(finishProofSession(testInfo).length, 2)
  } finally { await rm(root, { recursive: true, force: true }) }
})

test('absent page activity marks a checkpoint ineligible until an actor or school observation is signed', async () => {
  const root = await mkdtemp(join(tmpdir(), 'cronos-proof-'))
  try {
    const testInfo = fakeTestInfo(root)
    beginProofSession(testInfo, root)
    await testInfo.attach('no-ui-action', { body: Buffer.from('{}'), contentType: 'application/json' })
    const unobserved = await recordCheckpoint(testInfo, 'E2E-15/teacher-admin-routes-denied')
    assert.equal(unobserved.eligible, false)
    assert.equal(unobserved.ui_provenance, false)
    noteSchoolObservation(testInfo)
    await testInfo.attach('school-observation', { body: Buffer.from('{}'), contentType: 'application/json' })
    notePageActivity(testInfo)
    const schoolScoped = await recordCheckpoint(testInfo, 'E2E-18/school-year-change', { requires: 'school' })
    assert.equal(schoolScoped.ui_provenance, true)
    noteActorObservation(testInfo)
    await testInfo.attach('actor-observation', { body: Buffer.from('{}'), contentType: 'application/json' })
    notePageActivity(testInfo)
    const actorScoped = await recordCheckpoint(testInfo, 'E2E-03/recovered-login', { requires: 'actor' })
    assert.equal(actorScoped.ui_provenance, true)
  } finally { await rm(root, { recursive: true, force: true }) }
})

test('a block without its own attachment still materializes an explicit observation', async () => {
  const root = await mkdtemp(join(tmpdir(), 'cronos-proof-'))
  try {
    const testInfo = fakeTestInfo(root)
    beginProofSession(testInfo, root)
    notePageActivity(testInfo)
    const record = await recordCheckpoint(testInfo, 'E2E-07/readiness', {
      requires: 'page', observation: { can_generate: true },
    })
    assert.equal(record.eligible, true)
    assert.equal(record.evidence.length, 1)
    const materialized = JSON.parse(await readFile(join(root, ...record.evidence[0].split('/')), 'utf8'))
    assert.deepEqual(materialized, { can_generate: true })
    await assert.rejects(() => recordCheckpoint(testInfo, 'E2E-07/readiness'), /evidence/)
  } finally { await rm(root, { recursive: true, force: true }) }
})

test('matching keeps a case bound to exactly one proof and rejects unmatched evidence', () => {
  const records = [
    { case_ids: ['E2E-01/founder-registration', 'E2E-01/email-verification'], evidence: ['a.json'] },
    { case_ids: ['E2E-01/founder-registration'], evidence: ['b.json'] },
  ]
  assert.match(matchCaseProof('E2E-01/founder-registration', records).failure, /Ambiguous/)
  assert.equal(matchCaseProof('E2E-01/email-verification', records).proof.evidence[0], 'a.json')
  assert.equal(matchCaseProof('E2E-01/unknown', records).proof, null)
})

test('proof evidence is rooted at the configured project output directory, not an inferred parent', () => {
  const projectOutput = resolve('artifacts', 'acceptance')
  const testInfo = { project: { outputDir: projectOutput }, outputDir: join(projectOutput, 'nested', 'identity--founder'), attachments: [] }
  assert.equal(proofArtifactRoot(testInfo), projectOutput)
  assert.notEqual(proofArtifactRoot(testInfo), resolve(testInfo.outputDir))
  const file = join(projectOutput, 'nested', 'identity--founder', 'acceptance-evidence', '001.json')
  assert.equal(evidencePath(proofArtifactRoot(testInfo), file), 'nested/identity--founder/acceptance-evidence/001.json')
  assert.throws(() => proofArtifactRoot({ outputDir: projectOutput }), /project output/)
  assert.throws(() => proofArtifactRoot(null), /project output/)
})

test('a screenshot body is encrypted by the finalizer while JSON assertions stay readable text', async () => {
  const root = await mkdtemp(join(tmpdir(), 'cronos-finalize-'))
  try {
    const testInfo = fakeTestInfo(root)
    beginProofSession(testInfo, root)
    const png = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0x00, 0x01, 0x02, 0x03])
    await testInfo.attach('browser-evidence', { body: png, contentType: 'image/png' })
    await testInfo.attach('assertion', { body: Buffer.from(JSON.stringify({ ok: true })), contentType: 'application/json' })
    notePageActivity(testInfo)
    const record = await recordCheckpoint(testInfo, 'E2E-16/public-404')
    assert.ok(record.evidence.some(path => path.endsWith('.bin')), 'opaque screenshot must not be named .json')
    assert.ok(record.evidence.some(path => path.endsWith('.json')))
    const run = {
      schema_version: 1, run_id: 'run-1', mode: 'acceptance', tests_revision: 'a'.repeat(40), expected_revision: 'a'.repeat(40),
      started_at: '2026-10-08T10:00:00.000Z', finished_at: '2026-10-08T11:00:00.000Z',
      deployments: [], data_verified: false, evidence_protected: false,
      cleanup: { status: 'completed', run_id: 'run-1', pending: [], pending_actors: [] }, failures: [],
      cases: [{ id: 'E2E-16/public-404', requirement: 'E2E-16', name: 'public-404', status: 'passed', attempts: 1,
        started_at: '2026-10-08T10:00:00.000Z', finished_at: '2026-10-08T10:01:00.000Z', eligible: true, ui_provenance: true, evidence: record.evidence }],
    }
    const result = await finalizeRun(run, root, { key: randomBytes(32), signingKey: randomBytes(32), secrets: [] })
    assert.equal(result.run.evidence_protected, true)
    const protectedEvidence = result.run.cases[0].evidence
    assert.ok(protectedEvidence.some(path => path.endsWith('.bin.enc')))
    assert.ok(protectedEvidence.some(path => path.endsWith('.json')))
    const remaining = await readdir(root, { recursive: true })
    assert.equal(remaining.some(name => name.endsWith('.bin')), false, 'raw binary must not remain')
    assert.equal(remaining.some(name => name.endsWith('.json.enc')), false, 'JSON assertions must not be encrypted')
    const jsonFile = remaining.find(name => name.endsWith('.json'))
    assert.deepEqual(JSON.parse(await readFile(join(root, jsonFile), 'utf8')), { ok: true })
  } finally { await rm(root, { recursive: true, force: true }) }
})

test('a resource CRUD checkpoint requires every completed catalog observation', async () => {
  const root = await mkdtemp(join(tmpdir(), 'cronos-proof-'))
  try {
    const testInfo = fakeTestInfo(root)
    beginProofSession(testInfo, root)
    await testInfo.attach('course-and-initial-class-observation', { body: Buffer.from('{"course":true}'), contentType: 'application/json' })
    await testInfo.attach('subject-crud-observation', { body: Buffer.from('{"subject":true}'), contentType: 'application/json' })
    notePageActivity(testInfo)
    await assert.rejects(() => recordCheckpoint(testInfo, 'E2E-06/resource-crud', {
      requires: 'school', requiredEvidence: ['room-crud-observation', 'subject-crud-observation', 'course-and-initial-class-observation'],
    }), /room-crud-observation/)
    await testInfo.attach('room-crud-observation', { body: Buffer.from('{"room":true}'), contentType: 'application/json' })
    noteSchoolObservation(testInfo)
    const record = await recordCheckpoint(testInfo, 'E2E-06/resource-crud', {
      requires: 'school', requiredEvidence: ['room-crud-observation', 'subject-crud-observation', 'course-and-initial-class-observation'],
    })
    assert.equal(record.eligible, true)
    assert.equal(record.evidence.length, 3)
  } finally { await rm(root, { recursive: true, force: true }) }
})

test('a required evidence name outside the artifact root cannot fall back to an observation', async () => {
  const root = await mkdtemp(join(tmpdir(), 'cronos-proof-'))
  const outside = await mkdtemp(join(tmpdir(), 'cronos-outside-'))
  try {
    const testInfo = fakeTestInfo(root)
    beginProofSession(testInfo, root)
    const external = join(outside, 'room-crud-observation.json')
    await writeFile(external, '{}')
    await testInfo.attach('room-crud-observation', { path: external, contentType: 'application/json' })
    notePageActivity(testInfo)
    await assert.rejects(() => recordCheckpoint(testInfo, 'E2E-06/resource-crud', {
      requires: 'school', observation: { class_id: 7 }, requiredEvidence: ['room-crud-observation'],
    }), /room-crud-observation/)
    assert.equal(testInfo.attachments.some(item => item.name === 'acceptance-proof'), false)
  } finally {
    await rm(root, { recursive: true, force: true })
    await rm(outside, { recursive: true, force: true })
  }
})

test('a required evidence name cannot be proven by a non-claiming checkpoint without a claimed window', async () => {
  const root = await mkdtemp(join(tmpdir(), 'cronos-proof-'))
  try {
    const testInfo = fakeTestInfo(root)
    beginProofSession(testInfo, root)
    await testInfo.attach('room-crud-observation', { body: Buffer.from('{"room":true}'), contentType: 'application/json' })
    notePageActivity(testInfo)
    await assert.rejects(() => recordCheckpoint(testInfo, 'E2E-06/resource-crud', {
      requires: 'school', claim: false, observation: { class_id: 7 }, requiredEvidence: ['room-crud-observation'],
    }), /room-crud-observation/)
    assert.equal(testInfo.attachments.some(item => item.name === 'acceptance-proof'), false)
  } finally { await rm(root, { recursive: true, force: true }) }
})

test('the reserved acceptance-proof attachment cannot satisfy required evidence', async () => {
  const root = await mkdtemp(join(tmpdir(), 'cronos-proof-'))
  try {
    const testInfo = fakeTestInfo(root)
    beginProofSession(testInfo, root)
    await testInfo.attach('subject-crud-observation', { body: Buffer.from('{"subject":true}'), contentType: 'application/json' })
    notePageActivity(testInfo)
    // A non-claiming checkpoint leaves its own acceptance-proof attachment in the shared window.
    await recordCheckpoint(testInfo, 'E2E-06/initial-class', { requires: 'school', claim: false, observation: { class_id: 1 } })
    assert.equal(testInfo.attachments.some(item => item.name === 'acceptance-proof'), true)
    notePageActivity(testInfo)
    await assert.rejects(() => recordCheckpoint(testInfo, 'E2E-06/resource-crud', {
      requires: 'school', observation: { class_id: 7 }, requiredEvidence: ['acceptance-proof'],
    }), /acceptance-proof/)
  } finally { await rm(root, { recursive: true, force: true }) }
})

test('a non-claiming checkpoint shares its activity window with the following shared checkpoint', async () => {
  const root = await mkdtemp(join(tmpdir(), 'cronos-proof-'))
  try {
    const testInfo = fakeTestInfo(root)
    beginProofSession(testInfo, root)
    await testInfo.attach('course-and-initial-class-observation', { body: Buffer.from('{"course":true}'), contentType: 'application/json' })
    await testInfo.attach('subject-crud-observation', { body: Buffer.from('{"subject":true}'), contentType: 'application/json' })
    await testInfo.attach('room-crud-observation', { body: Buffer.from('{"room":true}'), contentType: 'application/json' })
    notePageActivity(testInfo)
    noteSchoolObservation(testInfo)
    const initialClass = await recordCheckpoint(testInfo, 'E2E-06/initial-class', {
      requires: 'school', claim: false, observation: { class_id: 7 },
    })
    const resourceCrud = await recordCheckpoint(testInfo, 'E2E-06/resource-crud', {
      requires: 'school', requiredEvidence: ['room-crud-observation', 'subject-crud-observation', 'course-and-initial-class-observation'],
    })
    assert.equal(initialClass.eligible, true)
    assert.equal(resourceCrud.eligible, true)
    assert.equal(resourceCrud.started_at, initialClass.started_at)
    for (const name of ['room-crud-observation', 'subject-crud-observation', 'course-and-initial-class-observation']) {
      assert.ok(resourceCrud.evidence.some(path => path.includes(name)), name)
    }
    // A later claimed checkpoint must observe fresh activity, not the shared block.
    await testInfo.attach('later-observation', { body: Buffer.from('{"later":true}'), contentType: 'application/json' })
    const stale = await recordCheckpoint(testInfo, 'E2E-06/initial-class', { requires: 'school' })
    assert.equal(stale.eligible, false)
    notePageActivity(testInfo)
    await testInfo.attach('later-observation-2', { body: Buffer.from('{"later":true}'), contentType: 'application/json' })
    const fresh = await recordCheckpoint(testInfo, 'E2E-06/initial-class', { requires: 'school' })
    assert.equal(fresh.eligible, true)
  } finally { await rm(root, { recursive: true, force: true }) }
})

test('a signed persistent school grants provenance only for its own live actor and organization', async () => {
  const root = await mkdtemp(join(tmpdir(), 'cronos-proof-'))
  try {
    const testInfo = fakeTestInfo(root)
    beginProofSession(testInfo, root)
    const school = { clerk_id: 'org_School', creation_run_id: 'run-1', creator_id: 'user_admin',
      actors: [{ id: 'user_teacher', provenance: 'ui', creation_run_id: 'run-1' }, { id: 'user_admin', provenance: 'ui', creation_run_id: 'run-1' }] }
    assert.equal(persistentSchoolProvenance(school, { actor_id: 'user_teacher', organization_id: 'org_School' }), true)
    assert.equal(persistentSchoolProvenance(school, { actor_id: 'user_teacher', organization_id: 'org_Foreign' }), false)
    assert.equal(persistentSchoolProvenance(school, { actor_id: 'user_foreign', organization_id: 'org_School' }), false)
    await testInfo.attach('history-observation', { body: Buffer.from('{}'), contentType: 'application/json' })
    notePageActivity(testInfo)
    assert.equal(notePersistentSchoolObservation(testInfo, school, { actor_id: 'user_foreign', organization_id: 'org_School' }), false)
    const foreign = await recordCheckpoint(testInfo, 'E2E-10/ended-lesson-log', { requires: 'school' })
    assert.equal(foreign.eligible, false)
    await testInfo.attach('history-observation-2', { body: Buffer.from('{}'), contentType: 'application/json' })
    notePageActivity(testInfo)
    assert.equal(notePersistentSchoolObservation(testInfo, school, { actor_id: 'user_teacher', organization_id: 'org_School' }), true)
    const valid = await recordCheckpoint(testInfo, 'E2E-10/ended-lesson-log', { requires: 'school' })
    assert.equal(valid.eligible, true)
  } finally { await rm(root, { recursive: true, force: true }) }
})

// Mirrors the runtime fixture order: a refused group never reaches its body.
function runGuardedGroup({ mode, annotations }, body) {
  const selection = publicReadonlySelection({ mode, annotations })
  if (!selection.ok) throw new Error(selection.reason)
  return body()
}

test('the readonly diagnosis refuses an unauthorized annotated group before its body can run', () => {
  const annotations = description => [{ type: 'acceptance-case', description }]
  let ran = false
  const body = () => { ran = true; return 'ran' }
  assert.throws(() => runGuardedGroup({ mode: 'diagnose-public', annotations: annotations('E2E-16/contact-delivered') }, body), /non-readonly/)
  assert.throws(() => runGuardedGroup({ mode: 'diagnose-public', annotations: annotations('E2E-01/founder-registration') }, body), /non-readonly/)
  assert.throws(() => runGuardedGroup({ mode: 'diagnose-public', annotations: [] }, body), /exactly one/)
  assert.throws(() => runGuardedGroup({ mode: 'diagnose-public', annotations: [...annotations('E2E-16/public-404'), ...annotations('E2E-16/legal-pages')] }, body), /exactly one/)
  assert.equal(ran, false, 'the group body must not run after a refusal')
  for (const item of PUBLIC_READONLY_CASES) {
    ran = false
    assert.equal(runGuardedGroup({ mode: 'diagnose-public', annotations: annotations(item.id) }, body), 'ran')
    assert.equal(ran, true)
  }
})

test('full and preparation modes keep every group eligible regardless of the whitelist', () => {
  for (const mode of ['acceptance', 'prepare-history', undefined]) {
    assert.deepEqual(publicReadonlySelection({ mode, annotations: [] }), { ok: true })
    assert.deepEqual(publicReadonlySelection({ mode, annotations: [{ type: 'acceptance-case', description: 'E2E-16/contact-delivered' }] }), { ok: true })
  }
  assert.equal(PUBLIC_READONLY_TAG, '@public-readonly')
  assert.equal(PUBLIC_READONLY_CASES.length, 4)
})

test('the runtime fixture guards the readonly selection before any group body', async () => {
  const source = await readFile(new URL('../e2e/acceptance/fixtures.js', import.meta.url), 'utf8')
  const guard = source.indexOf('publicReadonlySelection(')
  const body = source.indexOf('runFixture(runtime)')
  assert.ok(guard !== -1, 'the runtime fixture must call the readonly selection guard')
  assert.ok(body !== -1 && guard < body, 'the guard must run before the group body')
})
