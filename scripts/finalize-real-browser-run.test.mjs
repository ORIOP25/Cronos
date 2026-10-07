import assert from 'node:assert/strict'
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import test from 'node:test'
import { finalizeRun, verifyRunArtifacts } from './finalize-real-browser-run.mjs'
import { verifyRegistry } from './e2e-run-registry.mjs'
import { recoverEvidence } from './protect-test-evidence.mjs'
import { REQUIRED_CASES } from '../frontend/e2e/utils/acceptance-policy.js'

function campaign() {
  const revision = 'a'.repeat(40)
  return { schema_version: 1, run_id: 'run-1', mode: 'acceptance', tests_revision: revision, expected_revision: revision,
    started_at: '2026-10-07T08:00:00.000Z', finished_at: '2026-10-07T09:00:00.000Z',
    deployments: ['before', 'after'].map(phase => ({ phase, checked_at: phase === 'before' ? '2026-10-07T08:00:00.000Z' : '2026-10-07T09:00:00.000Z', components: Object.fromEntries(['frontend', 'api', 'worker', 'supervisor', 'beat'].map(name => [name, revision])) })),
    data_verified: true, cleanup: { status: 'completed' }, failures: [],
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
    const result = await finalizeRun(campaign(), directory, { key, signingKey, secrets: ['123456'] })
    assert.equal(result.assessment.status, 'validated')
    assert.deepEqual(result.run.cases[0].evidence, ['trace.zip.enc'])
    const signed = verifyRegistry(result.envelope, signingKey)
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
