import assert from 'node:assert/strict'
import test from 'node:test'
import { randomBytes } from 'node:crypto'
import { signRegistry, verifyRegistry } from './e2e-run-registry.mjs'

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
