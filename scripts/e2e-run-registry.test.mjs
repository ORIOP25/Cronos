import assert from 'node:assert/strict'
import test from 'node:test'
import { randomBytes } from 'node:crypto'
import { mkdir, mkdtemp, readFile, rm, symlink, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { createUiRegistry, createUiRegistryFile, recordUiActor, recordUiActorFile, recordSecretFile, signRegistry, verifyRegistry } from './e2e-run-registry.mjs'

test('dynamic credentials are durably registered before browser use and invalid registries remain untouched', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'cronos-dynamic-secrets-'))
  try {
    const path = join(directory, 'private.json')
    await writeFile(path, '[]', { mode: 0o600 })
    await recordSecretFile(path, 'generated-password')
    await recordSecretFile(path, '123456')
    await recordSecretFile(path, '123456')
    assert.deepEqual(JSON.parse(await readFile(path, 'utf8')), ['generated-password', '123456'])
    for (const secret of ['', null, 123456]) await assert.rejects(recordSecretFile(path, secret), /secret/i)
    await writeFile(path, '[17]')
    await assert.rejects(recordSecretFile(path, 'another'), /registry/i)
    assert.equal(await readFile(path, 'utf8'), '[17]')
    await assert.rejects(recordSecretFile(join(directory, 'missing.json'), 'another'), { code: 'ENOENT' })
    const outside = join(directory, 'outside')
    await mkdir(outside)
    await writeFile(join(outside, 'private.json'), '[]')
    const linked = join(directory, 'linked')
    await symlink(outside, linked, process.platform === 'win32' ? 'junction' : 'dir')
    await assert.rejects(recordSecretFile(join(linked, 'private.json'), 'another'), /confined/)
    assert.equal(await readFile(join(outside, 'private.json'), 'utf8'), '[]')
  } finally { await rm(directory, { recursive: true, force: true }) }
})

test('UI journal refuses a redirected directory before writing ownership records', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'cronos-ui-journal-link-'))
  try {
    const outside = join(directory, 'outside')
    await mkdir(outside)
    const linked = join(directory, 'linked')
    await symlink(outside, linked, process.platform === 'win32' ? 'junction' : 'dir')
    const path = join(linked, 'registry.json')
    await assert.rejects(createUiRegistryFile(path, randomBytes(32), 'run-1', '2026-10-07T08:00:00.000Z'), /confined/)
    await assert.rejects(readFile(join(outside, 'registry.json')), { code: 'ENOENT' })
  } finally { await rm(directory, { recursive: true, force: true }) }
})

test('signed UI journal never overwrites an existing run or accepts tampered observations', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'cronos-ui-journal-'))
  try {
    const path = join(directory, 'registry.json')
    const key = randomBytes(32)
    await createUiRegistryFile(path, key, 'run-1', '2026-10-07T08:00:00.000Z')
    await assert.rejects(createUiRegistryFile(path, key, 'run-1', '2026-10-07T08:00:00.000Z'), /exist/i)
    const actor = { id: 'user_owned', email: 'admincronos100+run-1@gmail.com', created_at: '2026-10-07T08:05:00.000Z' }
    await recordUiActorFile(path, key, 'run-1', actor, '2026-10-07T08:06:00.000Z')
    const before = await readFile(path)
    assert.equal(verifyRegistry(JSON.parse(before), key).actors[0].id, actor.id)
    await assert.rejects(recordUiActorFile(path, key, 'other', actor, '2026-10-07T08:07:00.000Z'), /identity/)
    await assert.rejects(recordUiActorFile(path, randomBytes(32), 'run-1', actor, '2026-10-07T08:07:00.000Z'), /signature/)
    assert.deepEqual(await readFile(path), before)
    const invalid = JSON.parse(before)
    invalid.signature = '0'.repeat(64)
    await writeFile(path, JSON.stringify(invalid))
    await assert.rejects(recordUiActorFile(path, key, 'run-1', actor, '2026-10-07T08:07:00.000Z'), /signature/)
  } finally { await rm(directory, { recursive: true, force: true }) }
})

test('UI provenance preserves an actor before any school exists and refuses existing identities', () => {
  const registry = createUiRegistry('run-1', '2026-10-07T08:00:00.000Z')
  const actor = { id: 'user_owned', email: 'admincronos100+run-1@gmail.com', created_at: '2026-10-07T08:05:00.000Z' }
  const observedAt = '2026-10-07T08:06:00.000Z'
  const observed = recordUiActor(registry, actor, observedAt)
  assert.deepEqual(registry.actors, [])
  assert.deepEqual(observed.organizations, [])
  assert.equal(observed.finished_at, observedAt)
  assert.deepEqual(observed.actors, [{ ...actor, creation_run_id: 'run-1', provenance: 'ui', type: 'disposable' }])
  assert.equal(recordUiActor(observed, actor, observedAt).actors.length, 1)
  const reordered = { ...observed, actors: [Object.fromEntries(Object.entries(observed.actors[0]).reverse())] }
  assert.equal(recordUiActor(reordered, actor, observedAt).actors.length, 1)
  for (const change of [
    { id: '../outside' }, { email: 'admincronos100@gmail.com' }, { email: 'admincronos100+other@gmail.com' },
    { created_at: '2026-10-06T08:05:00.000Z' }, { created_at: '2026-10-07T09:00:00.000Z' },
  ]) assert.throws(() => recordUiActor(registry, { ...actor, ...change }, observedAt))
  assert.throws(() => recordUiActor(observed, { ...actor, email: 'professorcronos100+run-1@gmail.com' }, observedAt), /identity/)
  assert.throws(() => recordUiActor(observed, actor, '2026-10-07T08:01:00.000Z'), /timestamp/)
  assert.throws(() => createUiRegistry('run/invalid', observedAt), /identity/)
  assert.throws(() => createUiRegistry('run-1', '2026-10-07T08:00:00'), /timestamp/)
  assert.throws(() => createUiRegistry('run-1', '2026-02-31T08:00:00.000Z'), /timestamp/)
  for (const runId of [17, true, ['run-1']]) assert.throws(() => createUiRegistry(runId, observedAt), /identity/)
})

test('authenticated registry rejects unknown keys and changed ownership', () => {
  const key = randomBytes(32)
  const registry = { schema_version: 1, run_id: 'run-1', organizations: [{ local_id: 17, clerk_id: 'org_owned', type: 'disposable' }] }
  const envelope = signRegistry(registry, key)
  assert.deepEqual(verifyRegistry(envelope, key), registry)
  assert.throws(() => verifyRegistry(envelope, randomBytes(32)), /signature/)
  const changed = { ...envelope, payload: Buffer.from(JSON.stringify({ ...registry, run_id: 'other' })).toString('base64') }
  assert.throws(() => verifyRegistry(changed, key), /signature/)
  assert.throws(() => verifyRegistry({ ...envelope, payload: '../outside' }, key))
  assert.throws(() => signRegistry(registry, Buffer.alloc(16)), /32/)
  for (const invalid of [null, [], 'not-a-registry', 17]) {
    assert.throws(() => signRegistry(invalid, key), /payload/)
  }
})
