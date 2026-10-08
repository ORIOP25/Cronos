import assert from 'node:assert/strict'
import { mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import test from 'node:test'
import { finalizeRun, verifyRunArtifacts } from './finalize-real-browser-run.mjs'
import { retainPersistentSchoolFile, signRegistry, verifyRegistry } from './e2e-run-registry.mjs'
import { protectEvidence, recoverEvidence } from './protect-test-evidence.mjs'
import { evaluatePreparation } from './prepare-history.mjs'
import { COMPONENTS, REQUIRED_CASES } from '../frontend/e2e/utils/acceptance-policy.js'

function campaign() {
  const revision = 'a'.repeat(40)
  return { schema_version: 1, run_id: 'run-1', mode: 'acceptance', tests_revision: revision, expected_revision: revision,
    started_at: '2026-10-07T08:00:00.000Z', finished_at: '2026-10-07T09:00:00.000Z',
    deployments: ['before', 'after'].map(phase => ({ phase, checked_at: phase === 'before' ? '2026-10-07T08:00:00.000Z' : '2026-10-07T09:00:00.000Z', components: Object.fromEntries(['frontend', 'api', 'worker', 'supervisor', 'beat'].map(name => [name, revision])) })),
    data_verified: true, cleanup: { status: 'completed', run_id: 'run-1', pending: [], pending_actors: [] }, failures: [],
    cases: REQUIRED_CASES.map(item => ({ ...item, started_at: '2026-10-07T08:10:00.000Z', finished_at: '2026-10-07T08:20:00.000Z', status: 'passed', attempts: 1, evidence: ['trace.zip'], eligible: true, ui_provenance: true })),
  }
}

const key = Buffer.alloc(32, 17)
const signingKey = Buffer.alloc(32, 29)

test('finalization protects actual files, rewrites evidence paths and signs their digests', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'cronos-finalize-'))
  try {
    await writeFile(join(directory, 'trace.zip'), 'private OTP 123456')
    await writeFile(join(directory, 'output.log'), 'OTP 123456')
    for (const name of ['Z.log', 'a.log', 'ä.log']) await writeFile(join(directory, name), 'safe')
    const result = await finalizeRun(campaign(), directory, { key, signingKey, secrets: ['123456'] })
    assert.equal(result.assessment.status, 'validated')
    assert.deepEqual(result.run.cases[0].evidence, ['trace.zip.enc'])
    const signed = verifyRegistry(result.envelope, signingKey)
    assert.deepEqual(signed.artifacts.map(item => item.path), ['Z.log', 'a.log', 'output.log', 'trace.zip.enc', 'ä.log'])
    assert.equal(signed.run.run_id, 'run-1')
    assert.match(signed.artifacts.find(item => item.path === 'trace.zip.enc').sha256, /^[a-f0-9]{64}$/)
    assert.equal(await readFile(join(directory, 'output.log'), 'utf8'), 'OTP [REDACTED]')
    assert.equal(recoverEvidence(await readFile(join(directory, 'trace.zip.enc')), key, { run_id: 'run-1', path: 'trace.zip' }).toString(), 'private OTP 123456')
    assert.equal((await verifyRunArtifacts(result.envelope, directory, { key, signingKey })).assessment.status, 'validated')
    await writeFile(join(directory, 'output.log'), 'tampered after signing')
    await assert.rejects(verifyRunArtifacts(result.envelope, directory, { key, signingKey }), /inventory/i)
    await assert.rejects(readFile(join(directory, 'trace.zip')), { code: 'ENOENT' })
  } finally { await rm(directory, { recursive: true, force: true }) }
})

test('missing and unauthenticated artifacts preserve the primary failure and forbid green', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'cronos-finalize-'))
  try {
    const run = campaign()
    run.failures = ['Primary product regression']
    const result = await finalizeRun(run, directory, { key, signingKey, secrets: [] })
    assert.equal(result.assessment.status, 'failed')
    assert.ok(result.assessment.failures.includes('Primary product regression'))
    assert.equal(result.run.evidence_protected, false)
    await writeFile(join(directory, 'trace.zip.enc'), 'fake envelope')
    const tampered = await finalizeRun(campaign(), directory, { key, signingKey, secrets: [] })
    assert.equal(tampered.assessment.status, 'failed')
    assert.equal(tampered.run.evidence_protected, false)
  } finally { await rm(directory, { recursive: true, force: true }) }
})

test('partial diagnostics and removed raw authentication states cannot certify a campaign', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'cronos-finalize-'))
  try {
    await writeFile(join(directory, 'auth-state.json'), '{"cookie":"secret"}')
    const run = campaign()
    run.mode = 'diagnostic'
    run.cases[0].evidence = ['auth-state.json']
    const result = await finalizeRun(run, directory, { key, signingKey, secrets: [] })
    assert.equal(result.assessment.status, 'failed')
    await assert.rejects(readFile(join(directory, 'auth-state.json')), { code: 'ENOENT' })
  } finally { await rm(directory, { recursive: true, force: true }) }
})

test('a registry protection failure forbids green, keeps the primary failure and hides the raw error', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'cronos-registry-failure-'))
  try {
    const run = campaign()
    run.failures = ['Primary product regression']
    const result = await finalizeRun(run, directory, {
      key, signingKey, secrets: [],
      registries: [{ source: join(directory, 'missing-registry.json'), path: 'preparation/persistent-registry.json' }],
    })
    assert.equal(result.envelope, null)
    assert.equal(result.run.evidence_protected, false)
    assert.deepEqual(result.artifacts, [])
    assert.equal(result.assessment.status, 'failed')
    assert.ok(result.run.failures.includes('Primary product regression'))
    assert.ok(result.run.failures.includes('Artifact finalization failed: registries'))
    assert.equal(result.run.failures.some(message => /missing-registry|ENOENT/.test(message)), false)
  } finally { await rm(directory, { recursive: true, force: true }) }
})

test('a short secret that is a substring of numeric metadata keeps the report valid', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'cronos-finalize-'))
  try {
    await writeFile(join(directory, 'trace.zip'), 'private OTP 123456')
    const run = campaign()
    run.failures = ['Primary product regression']
    run.numeric_metadata = 1234567
    run.note = 'delivered code 123456'
    const result = await finalizeRun(run, directory, { key, signingKey, secrets: ['123456'] })
    assert.ok(result.envelope)
    assert.equal(result.run.numeric_metadata, 1234567)
    assert.equal(result.run.note, 'delivered code [REDACTED]')
    assert.equal(result.assessment.status, 'failed')
    assert.ok(result.assessment.failures.includes('Primary product regression'))
    assert.equal(result.run.note.includes('123456'), false)
    const manifest = await verifyRunArtifacts(result.envelope, directory, { key, signingKey })
    assert.deepEqual(manifest.run, result.run)
    assert.deepEqual(manifest.assessment, result.assessment)
  } finally { await rm(directory, { recursive: true, force: true }) }
})

test('registered secrets with quotes and backslashes cannot corrupt the finalizer report', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'cronos-finalize-'))
  try {
    await writeFile(join(directory, 'trace.zip'), 'opaque trace')
    const run = campaign()
    run.note = 'password a"b and path c\\d'
    const result = await finalizeRun(run, directory, { key, signingKey, secrets: ['"', '\\', '123456'] })
    assert.ok(result.envelope)
    assert.equal(result.run.note, 'password a[REDACTED]b and path c[REDACTED]d')
    assert.equal(result.assessment.status, 'validated')
    const manifest = await verifyRunArtifacts(result.envelope, directory, { key, signingKey })
    assert.deepEqual(manifest.run, result.run)
  } finally { await rm(directory, { recursive: true, force: true }) }
})

test('finalizer classifies sanitize, evidence and registry stages without echoing raw errors', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'cronos-finalize-'))
  try {
    await writeFile(join(directory, 'trace.zip.enc'), 'not a protected envelope')
    const sanitized = await finalizeRun(campaign(), directory, { key, signingKey, secrets: [] })
    assert.equal(sanitized.envelope, null)
    assert.equal(sanitized.run.evidence_protected, false)
    assert.ok(sanitized.run.failures.includes('Artifact finalization failed: sanitize'))
    assert.equal(sanitized.run.failures.some(message => /envelope|base64|JSON/i.test(message)), false)
  } finally { await rm(directory, { recursive: true, force: true }) }

  const missing = await mkdtemp(join(tmpdir(), 'cronos-finalize-'))
  try {
    const result = await finalizeRun(campaign(), missing, { key, signingKey, secrets: [] })
    assert.equal(result.envelope, null)
    assert.ok(result.run.failures.includes('Artifact finalization failed: evidence'))
    assert.equal(result.run.failures.some(message => /trace\.zip/.test(message)), false)
  } finally { await rm(missing, { recursive: true, force: true }) }

  const registry = await mkdtemp(join(tmpdir(), 'cronos-finalize-'))
  try {
    const result = await finalizeRun(campaign(), registry, {
      key, signingKey, secrets: [],
      registries: [{ source: join(registry, 'missing-registry.json'), path: 'preparation/persistent-registry.json' }],
    })
    assert.equal(result.envelope, null)
    assert.ok(result.run.failures.includes('Artifact finalization failed: registries'))
    assert.equal(result.run.failures.some(message => /missing-registry/.test(message)), false)
  } finally { await rm(registry, { recursive: true, force: true }) }
})

function preparationCampaign(revision = 'a'.repeat(40)) {
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

test('preparation promotion signs both updated registries before the delivered manifest', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'cronos-preparation-'))
  try {
    const { run, registry } = preparationCampaign()
    const artifactRoot = join(directory, 'acceptance-artifacts')
    await mkdir(join(artifactRoot, 'preparation'), { recursive: true })
    await writeFile(join(artifactRoot, 'preparation', 'persistent-credentials.json.enc'),
      protectEvidence(Buffer.from('private login credentials'), key, { run_id: 'run-1', path: 'preparation/persistent-credentials.json' }))
    const persistentPath = join(directory, 'persistent-registry.json')
    await writeFile(persistentPath, JSON.stringify(signRegistry({ schema_version: 1, run_id: 'run-1', organizations: [], history_verified: false }, signingKey)))
    const secretPath = join(directory, 'private-secret-registry.json')
    await writeFile(secretPath, JSON.stringify(['123456']))

    const first = await finalizeRun(run, artifactRoot, { key, signingKey, secrets: ['123456'] })
    assert.equal(evaluatePreparation(first.run, registry, first.artifacts).status, 'prepared')

    await retainPersistentSchoolFile(persistentPath, signingKey, run.preparation, registry)
    const result = await finalizeRun(run, artifactRoot, {
      key, signingKey, secrets: ['123456'],
      registries: [
        { source: persistentPath, path: 'preparation/persistent-registry.json' },
        { source: secretPath, path: 'preparation/private-secret-registry.json' },
      ],
    })
    const paths = result.artifacts.map(item => item.path)
    assert.ok(paths.includes('preparation/persistent-registry.json.enc'))
    assert.ok(paths.includes('preparation/private-secret-registry.json.enc'))
    assert.equal(evaluatePreparation(result.run, registry, result.artifacts).status, 'prepared')
    const manifest = await verifyRunArtifacts(result.envelope, artifactRoot, { key, signingKey })
    assert.deepEqual(manifest.artifacts, result.artifacts)
    assert.equal(recoverEvidence(await readFile(join(artifactRoot, 'preparation', 'private-secret-registry.json.enc')),
      key, { run_id: 'run-1', path: 'preparation/private-secret-registry.json' }).toString(), '["123456"]')

    const secretEnvelope = join(artifactRoot, 'preparation', 'private-secret-registry.json.enc')
    const original = await readFile(secretEnvelope)
    await writeFile(secretEnvelope, Buffer.concat([Buffer.from('x'), original.subarray(1)]))
    await assert.rejects(verifyRunArtifacts(result.envelope, artifactRoot, { key, signingKey }))
    await writeFile(secretEnvelope, original)
    await writeFile(join(artifactRoot, 'preparation', 'extra.json.enc'), original)
    await assert.rejects(verifyRunArtifacts(result.envelope, artifactRoot, { key, signingKey }))
    await rm(join(artifactRoot, 'preparation', 'extra.json.enc'))
    await rm(join(artifactRoot, 'preparation', 'persistent-registry.json.enc'))
    await assert.rejects(verifyRunArtifacts(result.envelope, artifactRoot, { key, signingKey }))
  } finally { await rm(directory, { recursive: true, force: true }) }
})
