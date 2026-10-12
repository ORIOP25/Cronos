import assert from 'node:assert/strict'
import { mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import test from 'node:test'
import { finalizeRun, verifyRunArtifacts, verifySignedResult } from './finalize-real-browser-run.mjs'
import { sanitizeCampaignDiagnostics } from './sanitize-test-artifacts.mjs'
import { retainPersistentSchoolFile, signRegistry, verifyRegistry } from './e2e-run-registry.mjs'
import { protectEvidence, recoverEvidence } from './protect-test-evidence.mjs'
import { evaluatePreparation } from './prepare-history.mjs'
import { preparationFixture } from './preparation-test-fixture.mjs'
import { REQUIRED_CASES } from '../frontend/e2e/utils/acceptance-policy.js'

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

test('preparation promotion signs both updated registries before the delivered manifest', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'cronos-preparation-'))
  try {
    const { run, registry } = preparationFixture()
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

const finalizerCli = fileURLToPath(new URL('./finalize-real-browser-run.mjs', import.meta.url))
const cliEnv = () => ({ ...process.env, E2E_ARTIFACT_KEY: key.toString('base64'), E2E_REGISTRY_HMAC_KEY: signingKey.toString('base64') })

async function finalizedFixture() {
  const directory = await mkdtemp(join(tmpdir(), 'cronos-verify-cli-'))
  const artifactRoot = join(directory, 'acceptance-artifacts')
  await mkdir(artifactRoot)
  await writeFile(join(artifactRoot, 'output.log'), 'OTP 123456')
  await writeFile(join(artifactRoot, 'trace.zip'), 'private OTP 123456')
  const result = await finalizeRun(campaign(), artifactRoot, { key, signingKey, secrets: ['123456'] })
  const resultPath = join(directory, 'acceptance-result.json')
  await writeFile(resultPath, `${JSON.stringify(result, null, 2)}\n`)
  return { directory, artifactRoot, resultPath }
}

test('verifySignedResult rejects an altered wrapper and accepts an intact signed result', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'cronos-verify-lib-'))
  try {
    await writeFile(join(directory, 'trace.zip'), 'private OTP 123456')
    const result = await finalizeRun(campaign(), directory, { key, signingKey, secrets: ['123456'] })
    const manifest = await verifySignedResult(result, directory, { key, signingKey })
    assert.equal(manifest.assessment.status, 'validated')
    await assert.rejects(
      verifySignedResult({ ...result, assessment: { status: 'failed', failures: ['tampered'] } }, directory, { key, signingKey }),
      /mirror/i,
    )
    await assert.rejects(verifySignedResult({ ...result, envelope: null }, directory, { key, signingKey }), /envelope/i)
  } finally { await rm(directory, { recursive: true, force: true }) }
})

test('the finalizer redacts production JSON evidence as a tree and verifies the signed root', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'cronos-json-evidence-'))
  try {
    const weird = 'pw"q\\r\ns'
    await writeFile(join(directory, 'assertion.json'), `${JSON.stringify({ password: weird, code: 123456 })}\n`)
    const run = campaign()
    run.cases = run.cases.map(item => ({ ...item, evidence: ['assertion.json'] }))
    const result = await finalizeRun(run, directory, { key, signingKey, secrets: [weird, '123456'] })
    assert.equal(result.assessment.status, 'validated')
    const value = JSON.parse(await readFile(join(directory, 'assertion.json'), 'utf8'))
    assert.deepEqual(value, { password: '[REDACTED]', code: '[REDACTED]' })
    assert.equal(JSON.stringify(value).includes('123456'), false)
    await verifySignedResult(result, directory, { key, signingKey })
  } finally { await rm(directory, { recursive: true, force: true }) }
})

test('diagnostics never re-redact a sealed signed result even when a secret matches a digest', async () => {
  const { directory, artifactRoot, resultPath } = await finalizedFixture()
  try {
    const before = await readFile(resultPath, 'utf8')
    const parsed = JSON.parse(before)
    const digest = parsed.artifacts[0].sha256
    assert.match(digest, /^[a-f0-9]{64}$/)
    const colliding = digest.slice(0, 6)
    await sanitizeCampaignDiagnostics(directory, [colliding])
    assert.equal(await readFile(resultPath, 'utf8'), before)
    await verifySignedResult(JSON.parse(before), artifactRoot, { key, signingKey })
  } finally { await rm(directory, { recursive: true, force: true }) }
})

test('diagnostics never mutate the sealed result and a tampered wrapper stays rejected', async () => {
  const { directory, artifactRoot, resultPath } = await finalizedFixture()
  try {
    const before = await readFile(resultPath, 'utf8')
    await sanitizeCampaignDiagnostics(directory, ['123456'])
    assert.equal(await readFile(resultPath, 'utf8'), before)
    await verifySignedResult(JSON.parse(before), artifactRoot, { key, signingKey })
    const tampered = JSON.parse(before)
    tampered.run.failures = ['leaked OTP 123456']
    await writeFile(resultPath, `${JSON.stringify(tampered, null, 2)}\n`)
    const tamperedBytes = await readFile(resultPath, 'utf8')
    await sanitizeCampaignDiagnostics(directory, ['123456'])
    assert.equal(await readFile(resultPath, 'utf8'), tamperedBytes)
    await assert.rejects(verifySignedResult(JSON.parse(tamperedBytes), artifactRoot, { key, signingKey }), /mirror/i)
  } finally { await rm(directory, { recursive: true, force: true }) }
})

test('the verify CLI reports receipt availability and never presents a stale receipt as current', async () => {
  const { directory, artifactRoot, resultPath } = await finalizedFixture()
  try {
    const output = join(directory, 'github-output.txt')
    const receiptPath = join(directory, 'artifact-verification.json')
    const verified = spawnSync(process.execPath, [finalizerCli, 'verify', resultPath, artifactRoot, receiptPath], { encoding: 'utf8', env: { ...cliEnv(), GITHUB_OUTPUT: output } })
    assert.equal(verified.status, 0)
    assert.deepEqual(JSON.parse(await readFile(receiptPath, 'utf8')), { integrity: 'verified', reason: null, certifies_production: false })
    assert.equal(await readFile(output, 'utf8'), 'receipt_available=true\n')

    // A tampered rerun on the SAME path preserves the old bytes, reports a fixed conflict and emits no availability.
    const signed = await readFile(resultPath, 'utf8')
    await writeFile(resultPath, JSON.stringify({ ...JSON.parse(signed), assessment: { status: 'failed', failures: ['tampered'] } }))
    const conflictOutput = join(directory, 'conflict-output.txt')
    const conflict = spawnSync(process.execPath, [finalizerCli, 'verify', resultPath, artifactRoot, receiptPath], { encoding: 'utf8', env: { ...cliEnv(), GITHUB_OUTPUT: conflictOutput } })
    assert.equal(conflict.status, 1)
    assert.equal(conflict.stderr.trim(), 'Artifact integrity: receipt unavailable (conflict)')
    assert.deepEqual(JSON.parse(await readFile(receiptPath, 'utf8')), { integrity: 'verified', reason: null, certifies_production: false })
    await assert.rejects(readFile(conflictOutput), { code: 'ENOENT' })

    // A fresh path on the rejected verification writes a rejected receipt and reports availability, still exiting one.
    const freshReceipt = join(directory, 'fresh-receipt.json')
    const freshOutput = join(directory, 'fresh-output.txt')
    const freshRejected = spawnSync(process.execPath, [finalizerCli, 'verify', resultPath, artifactRoot, freshReceipt], { encoding: 'utf8', env: { ...cliEnv(), GITHUB_OUTPUT: freshOutput } })
    assert.equal(freshRejected.status, 1)
    const receipt = await readFile(freshReceipt, 'utf8')
    assert.deepEqual(JSON.parse(receipt), { integrity: 'rejected', reason: 'integrity', certifies_production: false })
    assert.equal(receipt.includes('tampered'), false)
    assert.equal(receipt.includes(artifactRoot), false)
    assert.equal(await readFile(freshOutput, 'utf8'), 'receipt_available=true\n')

    // The legacy two-argument form never emits an availability flag.
    await writeFile(resultPath, signed)
    const legacyOutput = join(directory, 'legacy-output.txt')
    const legacy = spawnSync(process.execPath, [finalizerCli, 'verify', resultPath, artifactRoot], { encoding: 'utf8', env: { ...cliEnv(), GITHUB_OUTPUT: legacyOutput } })
    assert.equal(legacy.status, 0)
    await assert.rejects(readFile(legacyOutput), { code: 'ENOENT' })
  } finally { await rm(directory, { recursive: true, force: true }) }
})

test('the verify CLI accepts a real signed result and rejects every post-sign mutation with a safe enum', async () => {
  const { directory, artifactRoot, resultPath } = await finalizedFixture()
  const run = () => spawnSync(process.execPath, [finalizerCli, 'verify', resultPath, artifactRoot], { encoding: 'utf8', env: cliEnv() })
  try {
    const signed = await readFile(resultPath, 'utf8')
    const verified = run()
    assert.equal(verified.status, 0)
    assert.equal(verified.stdout.trim(), 'Artifact integrity: verified')
    assert.equal(verified.stdout.includes(key.toString('base64')), false)
    assert.equal(verified.stderr, '')

    await writeFile(resultPath, JSON.stringify({ ...JSON.parse(signed), assessment: { status: 'failed', failures: ['tampered'] } }))
    const altered = run()
    assert.equal(altered.status, 1)
    assert.equal(altered.stdout, '')
    assert.equal(altered.stderr.trim(), 'Artifact integrity: rejected (integrity)')
    assert.equal(altered.stderr.includes(signingKey.toString('base64')), false)
    await writeFile(resultPath, signed)

    const outputLog = join(artifactRoot, 'output.log')
    const originalLog = await readFile(outputLog)
    const originalEnc = await readFile(join(artifactRoot, 'trace.zip.enc'))
    await writeFile(join(artifactRoot, 'extra.log'), 'extra')
    assert.equal(run().status, 1)
    await rm(join(artifactRoot, 'extra.log'))

    await rm(outputLog)
    assert.equal(run().status, 1)
    await writeFile(outputLog, originalLog)

    await writeFile(outputLog, 'changed after signing')
    assert.equal(run().status, 1)
    await writeFile(outputLog, originalLog)

    const encPath = join(artifactRoot, 'trace.zip.enc')
    await writeFile(encPath, Buffer.concat([Buffer.from('x'), originalEnc.subarray(1)]))
    assert.equal(run().status, 1)
    await writeFile(encPath, originalEnc)

    await rm(encPath)
    assert.equal(run().status, 1)
    await writeFile(encPath, originalEnc)

    await writeFile(resultPath, JSON.stringify({ ...JSON.parse(signed), envelope: null }))
    const unsigned = run()
    assert.equal(unsigned.status, 1)
    assert.equal(unsigned.stderr.trim(), 'Artifact integrity: rejected (unsigned)')
    await writeFile(resultPath, signed)

    assert.equal(run().status, 0)
  } finally { await rm(directory, { recursive: true, force: true }) }
})
