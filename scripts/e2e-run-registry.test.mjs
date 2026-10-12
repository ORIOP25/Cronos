import assert from 'node:assert/strict'
import test from 'node:test'
import { randomBytes, randomUUID } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { mkdir, mkdtemp, readFile, rm, symlink, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createUiRegistry, createUiRegistryFile, recordUiActor, recordUiActorFile, recordUiCreationIntent, recordUiCreationIntentFile, recordUiSchool, recordUiSchoolFile, recordSecretFile, retainPersistentSchoolFile, signRegistry, unresolvedUiCreationIntents, verifyRegistry } from './e2e-run-registry.mjs'

const ROOT = fileURLToPath(new URL('..', import.meta.url))

test('prepared persistent school is retained atomically without replacing older UI history', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'cronos-persistent-registry-'))
  try {
    const key = randomBytes(32), path = join(directory, 'persistent.json')
    const old = { local_id: 6, clerk_id: 'org_Old', type: 'persistent', preparation: { run_id: 'old-run' } }
    await writeFile(path, JSON.stringify(signRegistry({ schema_version: 1, organizations: [old], history_verified: false }, key)))
    const school = { local_id: 7, clerk_id: 'org_New', type: 'persistent', provenance: 'ui', creation_run_id: 'run-1' }
    const prepared = { schema_version: 1, status: 'prepared', run_id: 'run-1', organization: school, history_verified: false }
    const source = { run_id: 'run-1', organizations: [school] }
    await retainPersistentSchoolFile(path, key, prepared, source)
    await retainPersistentSchoolFile(path, key, prepared, source)
    const result = verifyRegistry(JSON.parse(await readFile(path, 'utf8')), key)
    assert.equal(result.organizations.length, 2)
    assert.deepEqual(result.organizations[0], old)
    assert.deepEqual(result.organizations[1].preparation, { schema_version: 1, status: 'prepared', run_id: 'run-1', history_verified: false })
    const unchanged = await readFile(path, 'utf8')
    for (const change of [{ status: 'failed' }, { run_id: 'foreign' }, { organization: { ...school, clerk_id: 'org_Conflicting' } }]) {
      await assert.rejects(retainPersistentSchoolFile(path, key, { ...prepared, ...change }, source))
      assert.equal(await readFile(path, 'utf8'), unchanged)
    }
    await assert.rejects(retainPersistentSchoolFile(path, randomBytes(32), prepared, source), /signature/)
    assert.equal(await readFile(path, 'utf8'), unchanged)
  } finally { await rm(directory, { recursive: true, force: true }) }
})

test('UI school ownership binds both identities and members to actors born in the campaign', () => {
  const actor = { id: 'user_founder', email: 'admincronos100+run-1@gmail.com', created_at: '2026-10-07T08:01:00.000Z' }
  const registry = recordUiActor(createUiRegistry('run-1', '2026-10-07T08:00:00.000Z'), actor, '2026-10-07T08:02:00.000Z')
  const school = { local_id: 17, clerk_id: 'org_owned', creator_id: actor.id, created_at: '2026-10-07T08:03:00.000Z', actors: [{ id: actor.id, email: actor.email }] }
  const observedAt = '2026-10-07T08:04:00.000Z'
  const recorded = recordUiSchool(registry, school, 'disposable', observedAt)
  assert.deepEqual(registry.organizations, [])
  assert.equal(recorded.organizations[0].creation_run_id, 'run-1')
  assert.equal(recorded.organizations[0].provenance, 'ui')
  assert.equal(recorded.organizations[0].actors[0].created_at, actor.created_at)
  assert.equal(recordUiSchool(recorded, school, 'disposable', observedAt).organizations.length, 1)
  assert.equal(recordUiSchool(registry, school, 'persistent', observedAt).organizations[0].type, 'persistent')
  for (const change of [
    { local_id: 0 }, { local_id: '17' }, { clerk_id: 'org/other' }, { creator_id: 'user_unknown' },
    { created_at: '2026-10-06T08:03:00.000Z' }, { created_at: '2026-10-07T08:05:00.000Z' },
    { actors: [] }, { actors: [school.actors[0], school.actors[0]] },
    { actors: [{ id: actor.id, email: 'someone@gmail.com' }] },
  ]) assert.throws(() => recordUiSchool(registry, { ...school, ...change }, 'disposable', observedAt))
  assert.throws(() => recordUiSchool(recorded, school, 'persistent', observedAt), /identity/)
  assert.throws(() => recordUiSchool(recorded, { ...school, clerk_id: 'org_other' }, 'disposable', observedAt), /identity/)
  assert.throws(() => recordUiSchool(registry, school, 'unknown', observedAt), /type/)
})

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
    await recordUiSchoolFile(path, key, 'run-1', { local_id: 17, clerk_id: 'org_owned', creator_id: actor.id, created_at: '2026-10-07T08:06:00.000Z', actors: [{ id: actor.id, email: actor.email }] }, 'disposable', '2026-10-07T08:06:00.000Z')
    const before = await readFile(path)
    assert.equal(verifyRegistry(JSON.parse(before), key).actors[0].id, actor.id)
    assert.equal(verifyRegistry(JSON.parse(before), key).organizations[0].local_id, 17)
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

test('write-ahead creation intents are typed, unique and exposed without identity', () => {
  const registry = createUiRegistry('run-1', '2026-10-07T08:00:00.000Z')
  const id = randomUUID(), observedAt = '2026-10-07T08:01:00.000Z'
  const recorded = recordUiCreationIntent(registry, { id, kind: 'actor', alias: 'admincronos100+run-1@gmail.com' }, observedAt)
  assert.deepEqual(registry.intents, [])
  assert.equal(recorded.finished_at, observedAt)
  assert.deepEqual(unresolvedUiCreationIntents(recorded), [{ id, kind: 'actor', attempted_at: observedAt }])
  const both = recordUiCreationIntent(recorded, { id: randomUUID(), kind: 'org' }, '2026-10-07T08:02:00.000Z')
  assert.equal(unresolvedUiCreationIntents(both).length, 2)

  for (const change of [
    { id: 'not-a-uuid', kind: 'org' },
    { id: randomUUID(), kind: 'school' },
    { id: randomUUID(), kind: 'actor' },
    { id: randomUUID(), kind: 'actor', alias: 'admincronos100@gmail.com' },
    { id: randomUUID(), kind: 'actor', alias: 'admincronos100+other@gmail.com' },
    { id: randomUUID(), kind: 'actor', alias: 'professorcronos100+run-1@gmail.com', local_id: 7 },
    { id: randomUUID(), kind: 'org', alias: 'admincronos100+run-1@gmail.com' },
    { id: randomUUID(), kind: 'org', local_id: 7 },
    { id: randomUUID(), kind: 'org', clerk_id: 'org_x' },
    { id: randomUUID(), kind: 'org', type: 'disposable' },
  ]) assert.throws(() => recordUiCreationIntent(registry, { ...change }, observedAt))
  assert.throws(() => recordUiCreationIntent(recorded, { id, kind: 'org' }, '2026-10-07T08:02:00.000Z'), /intent/i)
  assert.throws(() => recordUiCreationIntent(recorded, { id: randomUUID(), kind: 'actor', alias: 'admincronos100+run-1@gmail.com' }, '2026-10-07T08:02:00.000Z'), /intent/i)
  assert.throws(() => recordUiCreationIntent(both, { id: randomUUID(), kind: 'org' }, '2026-10-07T08:01:30.000Z'), /timestamp/)
})

test('an actor observation clears only its own write-ahead alias and never an organization intent', () => {
  const registry = createUiRegistry('run-1', '2026-10-07T08:00:00.000Z')
  const adminId = randomUUID(), teacherId = randomUUID(), orgId = randomUUID()
  let current = recordUiCreationIntent(registry, { id: adminId, kind: 'actor', alias: 'admincronos100+run-1@gmail.com' }, '2026-10-07T08:01:00.000Z')
  current = recordUiCreationIntent(current, { id: teacherId, kind: 'actor', alias: 'professorcronos100+run-1@gmail.com' }, '2026-10-07T08:01:01.000Z')
  current = recordUiCreationIntent(current, { id: orgId, kind: 'org' }, '2026-10-07T08:01:02.000Z')
  const observed = recordUiActor(current, { id: 'user_admin', email: 'admincronos100+run-1@gmail.com', created_at: '2026-10-07T08:01:30.000Z' }, '2026-10-07T08:02:00.000Z')
  assert.deepEqual(unresolvedUiCreationIntents(observed).map(item => item.id), [teacherId, orgId])
})

test('a school observation clears only the requested organization intent and leaves the rest pending', () => {
  const registry = createUiRegistry('run-1', '2026-10-07T08:00:00.000Z')
  const first = randomUUID(), second = randomUUID()
  let current = recordUiCreationIntent(registry, { id: first, kind: 'org' }, '2026-10-07T08:01:00.000Z')
  current = recordUiCreationIntent(current, { id: second, kind: 'org' }, '2026-10-07T08:01:01.000Z')
  current = recordUiActor(current, { id: 'user_admin', email: 'admincronos100+run-1@gmail.com', created_at: '2026-10-07T08:01:30.000Z' }, '2026-10-07T08:02:00.000Z')
  const school = { local_id: 7, clerk_id: 'org_School', creator_id: 'user_admin', created_at: '2026-10-07T08:02:30.000Z', actors: [{ id: 'user_admin', email: 'admincronos100+run-1@gmail.com' }] }
  const observedAt = '2026-10-07T08:03:00.000Z'
  assert.deepEqual(unresolvedUiCreationIntents(recordUiSchool(current, school, 'disposable', observedAt, first)).map(item => item.id), [second])
  assert.deepEqual(unresolvedUiCreationIntents(recordUiSchool(current, school, 'disposable', observedAt)).map(item => item.id), [first, second])
  const actorIntentId = randomUUID()
  const mixed = recordUiActor(
    recordUiCreationIntent(current, { id: actorIntentId, kind: 'actor', alias: 'professorcronos100+run-1@gmail.com' }, '2026-10-07T08:02:10.000Z'),
    { id: 'user_admin', email: 'admincronos100+run-1@gmail.com', created_at: '2026-10-07T08:01:30.000Z' }, '2026-10-07T08:02:20.000Z')
  assert.throws(() => recordUiSchool(mixed, school, 'disposable', observedAt, randomUUID()), /intent/i)
  assert.throws(() => recordUiSchool(mixed, school, 'disposable', observedAt, actorIntentId), /intent/i)
})

test('malformed creation intents are never collapsed to an empty journal', () => {
  const registry = createUiRegistry('run-1', '2026-10-07T08:00:00.000Z')
  const actor = { id: 'user_owned', email: 'admincronos100+run-1@gmail.com', created_at: '2026-10-07T08:01:00.000Z' }
  const observedAt = '2026-10-07T08:05:00.000Z'
  for (const intents of [
    'not-an-array', [null], ['intent'],
    [{ id: 'x', kind: 'actor', alias: actor.email, attempted_at: observedAt }],
    [{ id: randomUUID(), kind: 'actor', alias: actor.email, attempted_at: '2026-10-07T07:00:00.000Z' }],
    [{ id: randomUUID(), kind: 'actor', alias: actor.email, attempted_at: observedAt, extra: 1 }],
    [{ id: randomUUID(), kind: 'actor', alias: actor.email, attempted_at: observedAt }, { id: randomUUID(), kind: 'actor', alias: actor.email, attempted_at: observedAt }],
    (() => { const shared = randomUUID(); return [{ id: shared, kind: 'org', attempted_at: observedAt }, { id: shared, kind: 'org', attempted_at: observedAt }] })(),
  ]) {
    const broken = { ...registry, intents }
    assert.throws(() => unresolvedUiCreationIntents(broken))
    assert.throws(() => recordUiActor(broken, actor, observedAt))
  }
})

test('creation intents demand a canonical run identity and a complete chronological window', () => {
  const attemptedAt = '2026-10-07T08:01:00.000Z'
  const intent = { id: randomUUID(), kind: 'org', attempted_at: attemptedAt }
  const window = { started_at: '2026-10-07T08:00:00.000Z', finished_at: '2026-10-07T08:02:00.000Z' }
  // Absent or empty intents stay compatible with a legacy registry without a run clock.
  assert.deepEqual(unresolvedUiCreationIntents({ schema_version: 1, organizations: [], intents: [] }), [])
  assert.deepEqual(unresolvedUiCreationIntents({ organizations: [] }), [])
  for (const registry of [
    { schema_version: 2, run_id: 'run-1', ...window, organizations: [], intents: [intent] },
    { schema_version: 1, run_id: '../../bad', ...window, organizations: [], intents: [intent] },
    { schema_version: 1, run_id: 'Run-1', ...window, organizations: [], intents: [intent] },
    { schema_version: 1, run_id: 'run-1', organizations: [], intents: [intent] },
    { schema_version: 1, run_id: 'run-1', started_at: window.started_at, organizations: [], intents: [intent] },
    { schema_version: 1, run_id: 'run-1', ...window, organizations: [], intents: [intent, { id: randomUUID(), kind: 'org', attempted_at: '2026-10-07T08:03:00.000Z' }] },
  ]) assert.throws(() => unresolvedUiCreationIntents(registry))
  const actorRegistry = { schema_version: 1, ...window, organizations: [], actors: [] }
  assert.throws(() => recordUiCreationIntent({ ...actorRegistry, run_id: '../../bad' }, { id: randomUUID(), kind: 'org' }, '2026-10-07T08:01:30.000Z'))
  assert.throws(() => recordUiCreationIntent({ ...actorRegistry, run_id: 'Run-1' }, { id: randomUUID(), kind: 'org' }, '2026-10-07T08:01:30.000Z'))
  assert.throws(() => unresolvedUiCreationIntents({ schema_version: 1, ...window, organizations: [],
    intents: [{ id: randomUUID(), kind: 'actor', alias: 'admincronos100+undefined@gmail.com', attempted_at: attemptedAt }] }))
})

test('an organization intent written after an existing school cannot resolve that school', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'cronos-ui-late-org-intent-'))
  try {
    const key = randomBytes(32), path = join(directory, 'registry.json')
    await createUiRegistryFile(path, key, 'run-1', '2026-10-07T08:00:00.000Z')
    const actor = { id: 'user_admin', email: 'admincronos100+run-1@gmail.com', created_at: '2026-10-07T08:01:00.000Z' }
    await recordUiActorFile(path, key, 'run-1', actor, '2026-10-07T08:02:00.000Z')
    const school = { local_id: 7, clerk_id: 'org_School', creator_id: actor.id, created_at: '2026-10-07T08:03:00.000Z', actors: [{ id: actor.id, email: actor.email }] }
    await recordUiSchoolFile(path, key, 'run-1', school, 'disposable', '2026-10-07T08:04:00.000Z')
    const lateId = randomUUID()
    await recordUiCreationIntentFile(path, key, 'run-1', { id: lateId, kind: 'org' }, '2026-10-07T08:05:00.000Z')
    const before = await readFile(path)
    assert.throws(() => recordUiSchool(verifyRegistry(JSON.parse(before), key), school, 'disposable', '2026-10-07T08:06:00.000Z', lateId), /intent/i)
    await assert.rejects(recordUiSchoolFile(path, key, 'run-1', school, 'disposable', '2026-10-07T08:06:00.000Z', lateId), /intent/i)
    assert.deepEqual(await readFile(path), before)
    assert.deepEqual(unresolvedUiCreationIntents(verifyRegistry(JSON.parse(before), key)).map(item => item.id), [lateId])
  } finally { await rm(directory, { recursive: true, force: true }) }
})

test('write-ahead intents update the signed journal atomically and refuse a redirected directory', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'cronos-ui-intents-'))
  try {
    const path = join(directory, 'registry.json')
    const key = randomBytes(32)
    await createUiRegistryFile(path, key, 'run-1', '2026-10-07T08:00:00.000Z')
    const id = randomUUID()
    await recordUiCreationIntentFile(path, key, 'run-1', { id, kind: 'actor', alias: 'admincronos100+run-1@gmail.com' }, '2026-10-07T08:01:00.000Z')
    const before = await readFile(path)
    assert.deepEqual(unresolvedUiCreationIntents(verifyRegistry(JSON.parse(before), key)), [{ id, kind: 'actor', attempted_at: '2026-10-07T08:01:00.000Z' }])
    await assert.rejects(recordUiCreationIntentFile(path, randomBytes(32), 'run-1', { id: randomUUID(), kind: 'org' }, '2026-10-07T08:02:00.000Z'), /signature/)
    await assert.rejects(recordUiCreationIntentFile(path, key, 'other', { id: randomUUID(), kind: 'org' }, '2026-10-07T08:02:00.000Z'), /identity/)
    assert.deepEqual(await readFile(path), before)

    const linked = join(directory, 'linked')
    await symlink(directory, linked, process.platform === 'win32' ? 'junction' : 'dir')
    await assert.rejects(recordUiCreationIntentFile(join(linked, 'registry.json'), key, 'run-1', { id: randomUUID(), kind: 'org' }, '2026-10-07T08:02:00.000Z'), /confined/)
    assert.deepEqual(await readFile(path), before)
  } finally { await rm(directory, { recursive: true, force: true }) }
})

test('persistent promotion refuses a source journal with unresolved creation intents', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'cronos-persistent-intents-'))
  try {
    const key = randomBytes(32), path = join(directory, 'persistent.json')
    await writeFile(path, JSON.stringify(signRegistry({ schema_version: 1, organizations: [], history_verified: false }, key)))
    const school = { local_id: 7, clerk_id: 'org_New', type: 'persistent', provenance: 'ui', creation_run_id: 'run-1' }
    const prepared = { schema_version: 1, status: 'prepared', run_id: 'run-1', organization: school, history_verified: false }
    const before = await readFile(path)
    const source = { schema_version: 1, run_id: 'run-1', started_at: '2026-10-07T08:00:00.000Z', finished_at: '2026-10-07T08:01:00.000Z',
      organizations: [school], intents: [{ id: randomUUID(), kind: 'org', attempted_at: '2026-10-07T08:00:30.000Z' }] }
    await assert.rejects(retainPersistentSchoolFile(path, key, prepared, source), /intent/i)
    assert.deepEqual(await readFile(path), before)
  } finally { await rm(directory, { recursive: true, force: true }) }
})

test('the campaign writes creation intents before the native UI effects they guard', () => {
  const campaign = readFileSync(join(ROOT, 'frontend/e2e/utils/ui-identity-campaign.js'), 'utf8')
  const founder = campaign.indexOf('beginActorCreation(email)')
  const founderContinue = campaign.indexOf("await page.getByRole('button', { name: 'Continuar', exact: true }).click()", campaign.indexOf("await page.goto('/register')"))
  assert.ok(founder > -1 && founderContinue > -1 && founder < founderContinue)
  const organization = campaign.indexOf('beginOrganizationCreation()')
  const foundationContinue = campaign.indexOf("await page.getByRole('button', { name: /^(continuar|continue)$/i }).click()")
  assert.ok(organization > -1 && organization < foundationContinue)
  assert.ok(campaign.indexOf('recordCreatedSchool(schoolType, page, organizationIntentId)') > foundationContinue)
  const teacher = campaign.indexOf('beginActorCreation(teacherEmail)')
  const teacherContinue = campaign.indexOf("await teacherPage.getByRole('button', { name: 'Continuar', exact: true }).click()")
  assert.ok(teacher > campaign.indexOf("'teacher-invitation'") && teacher < teacherContinue)
  const isolation = readFileSync(join(ROOT, 'frontend/e2e/utils/ui-isolation.js'), 'utf8')
  const secondOrganization = isolation.indexOf('beginOrganizationCreation()')
  const secondContinue = isolation.indexOf("await dialog.getByRole('button', { name: 'Criar organização', exact: true }).click()")
  assert.ok(secondOrganization > -1 && secondOrganization < secondContinue)
  assert.ok(isolation.indexOf("recordCreatedSchool('disposable', page, creationIntentId)") > secondContinue)
})
