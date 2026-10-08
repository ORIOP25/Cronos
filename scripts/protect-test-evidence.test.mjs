import assert from 'node:assert/strict'
import test from 'node:test'
import { randomBytes } from 'node:crypto'
import { access, mkdir, mkdtemp, readFile, rm, symlink, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { protectEvidence, protectEvidenceFile, recoverEvidence, recoverEvidenceFile } from './protect-test-evidence.mjs'

test('authenticated evidence round trips with a separate 256-bit key', () => {
  const key = randomBytes(32)
  const content = Buffer.from('trace with private session')
  const metadata = { run_id: 'run-1', path: 'failure/trace.zip' }
  const first = protectEvidence(content, key, metadata)
  assert.notDeepEqual(first, protectEvidence(content, key, metadata))
  assert.deepEqual(recoverEvidence(first, key, metadata), content)
  assert.throws(() => recoverEvidence(first, randomBytes(32), metadata))
  const tampered = Buffer.from(first); tampered[tampered.length - 1] ^= 1
  assert.throws(() => recoverEvidence(tampered, key, metadata))
  assert.throws(() => recoverEvidence(first, key, { ...metadata, run_id: 'other' }))
  assert.throws(() => protectEvidence(content, Buffer.alloc(16), metadata), /32/)
})

test('evidence metadata rejects traversal and absolute destinations', () => {
  for (const path of ['../trace.zip', '/trace.zip', 'C:/trace.zip', 'failure/../../trace.zip', 'failure\\trace.zip', 'a//trace.zip']) {
    assert.throws(() => protectEvidence(Buffer.from('x'), randomBytes(32), { run_id: 'run', path }), /path/)
  }
})

test('file protection writes an exclusive authenticated envelope and refuses overwrite', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'cronos-protect-'))
  try {
    const key = randomBytes(32)
    const metadata = { run_id: 'run-1', path: 'preparation/registry.json' }
    const content = Buffer.from('{"organizations":[]}')
    const source = join(directory, 'registry.json')
    await writeFile(source, content)
    const destination = join(directory, 'artifacts', 'nested', 'registry.json.enc')
    await protectEvidenceFile(source, destination, key, metadata)
    const recovered = await recoverEvidenceFile(destination, join(directory, 'recovered'), key, metadata)
    assert.deepEqual(await readFile(recovered), content)
    await assert.rejects(protectEvidenceFile(source, destination, key, metadata), /EEXIST|exist/i)
    assert.deepEqual(await readFile(recovered), content)
    await assert.rejects(protectEvidenceFile(source, destination, randomBytes(16), metadata), /32/)
    assert.throws(() => protectEvidence(Buffer.from('x'), key, { ...metadata, path: '../registry.json' }), /path/)
  } finally { await rm(directory, { recursive: true, force: true }) }
})

test('file recovery authenticates before writing and never overwrites existing evidence', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'cronos-recover-'))
  try {
    const key = randomBytes(32)
    const metadata = { run_id: 'run-1', path: 'failed/trace.zip' }
    const content = Buffer.from('complete authenticated trace')
    const source = join(directory, 'source.enc')
    const output = join(directory, 'recovered')
    await writeFile(source, protectEvidence(content, key, metadata))
    await assert.rejects(recoverEvidenceFile(source, output, randomBytes(32), metadata))
    await assert.rejects(access(output))
    await assert.rejects(recoverEvidenceFile(source, output, key, { ...metadata, path: '../outside.zip' }), /path/)
    await assert.rejects(access(output))
    const destination = await recoverEvidenceFile(source, output, key, metadata)
    assert.deepEqual(await readFile(destination), content)
    await assert.rejects(recoverEvidenceFile(source, output, key, metadata), /exist/i)
    assert.deepEqual(await readFile(destination), content)
    const outside = join(directory, 'outside')
    await mkdir(outside)
    await symlink(outside, join(output, 'linked'), process.platform === 'win32' ? 'junction' : 'dir')
    const linked = { ...metadata, path: 'linked/trace.zip' }
    await writeFile(source, protectEvidence(content, key, linked))
    await assert.rejects(recoverEvidenceFile(source, output, key, linked), /symbolic link/)
    await assert.rejects(access(join(outside, 'trace.zip')))
  } finally { await rm(directory, { recursive: true, force: true }) }
})
