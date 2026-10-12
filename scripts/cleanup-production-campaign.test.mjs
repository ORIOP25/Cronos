import assert from 'node:assert/strict'
import { randomBytes, randomUUID } from 'node:crypto'
import { mkdir, mkdtemp, readFile, readdir, rm, symlink, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import test from 'node:test'
import { classifyTransportFailure, cleanupProductionCampaign, mintClerkTestingToken, sshIdentityFile } from './cleanup-production-campaign.mjs'
import { createUiRegistry, recordUiActor, recordUiCreationIntent, recordUiSchool, signRegistry, verifyRegistry } from './e2e-run-registry.mjs'
import { protectEvidence, recoverEvidence } from './protect-test-evidence.mjs'

async function fixture() {
  const root = await mkdtemp(join(tmpdir(), 'cronos-cleanup-adapter-'))
  const signingKey = randomBytes(32), artifactKey = randomBytes(32)
  let registry = createUiRegistry('run-1', '2026-10-08T09:00:00.000Z')
  registry = recordUiActor(registry, { id: 'user_Founder', email: 'admincronos100+run-1@gmail.com', created_at: '2026-10-08T09:01:00.000Z' }, '2026-10-08T09:02:00.000Z')
  registry = recordUiSchool(registry, { local_id: 7, clerk_id: 'org_School', creator_id: 'user_Founder', created_at: '2026-10-08T09:02:00.000Z', actors: registry.actors }, 'disposable', '2026-10-08T09:03:00.000Z')
  const registryPath = join(root, 'registry.json')
  await writeFile(registryPath, JSON.stringify(signRegistry(registry, signingKey)))
  const environment = { E2E_REGISTRY_HMAC_KEY: signingKey.toString('base64'), E2E_ARTIFACT_KEY: artifactKey.toString('base64'),
    E2E_ADMIN_SSH_KEY: 'private-key-test-value', E2E_RAILWAY_TOKEN: 'railway-test-value', E2E_RAILWAY_TOKEN_TYPE: 'account',
    E2E_RAILWAY_PROJECT_ID: 'project', E2E_RAILWAY_ENVIRONMENT_ID: 'production', E2E_RAILWAY_API_SERVICE_ID: 'api' }
  const options = { runId: 'run-1', expectedRevision: 'a'.repeat(40), registryPath, artifactRoot: join(root, 'evidence') }
  const result = { run_id: 'run-1', status: 'completed', completed: [7], removed_actors: ['user_Founder'], pending: [], pending_actors: [] }
  const encrypted = protectEvidence(Buffer.from('classified administrative export'), artifactKey, { run_id: 'run-1', path: 'organization-7.zip' })
  const response = { result, exports: [{ name: 'organization-7.zip.enc', content: encrypted.toString('base64') }] }
  return { root, options, environment, response, artifactKey }
}

test('cleanup authenticates ownership before transport and never transmits the SSH key in stdin', async () => {
  const f = await fixture()
  try {
    const result = await cleanupProductionCampaign(f.options, f.environment, { execute: async payload => {
      assert.equal(payload.run_id, 'run-1')
      assert.equal(payload.expected_revision, f.options.expectedRevision)
      assert.equal(JSON.stringify(payload).includes(f.environment.E2E_ADMIN_SSH_KEY), false)
      return f.response
    } })
    assert.equal(result.status, 'completed')
    const file = await readFile(join(f.options.artifactRoot, 'organization-7.zip.enc'))
    assert.equal(recoverEvidence(file, f.artifactKey, { run_id: 'run-1', path: 'organization-7.zip' }).toString(), 'classified administrative export')
  } finally { await rm(f.root, { recursive: true, force: true }) }
})

test('reconciliation authenticates prior backups before transport and preserves their exact existing bytes', async () => {
  const f = await fixture()
  try {
    await mkdir(f.options.artifactRoot)
    const path = join(f.options.artifactRoot, 'organization-7.zip.enc')
    const original = Buffer.from(f.response.exports[0].content, 'base64')
    await writeFile(path, original)
    const result = await cleanupProductionCampaign(f.options, f.environment, { usePriorExports: true, execute: async packet => {
      assert.deepEqual(packet.prior_exports, [{ local_id: 7, content: original.toString('base64') }])
      return f.response
    } })
    assert.equal(result.status, 'completed')
    assert.deepEqual(await readFile(path), original)
  } finally { await rm(f.root, { recursive: true, force: true }) }
})

test('a corrupt prior backup prevents remote effects and a changed returned backup cannot overwrite the original', async () => {
  const f = await fixture()
  try {
    await mkdir(f.options.artifactRoot)
    const path = join(f.options.artifactRoot, 'organization-7.zip.enc')
    await writeFile(path, 'corrupted envelope')
    let effects = 0
    const invalid = await cleanupProductionCampaign(f.options, f.environment, { usePriorExports: true,
      execute: async () => { effects++; return f.response } })
    assert.equal(invalid.status, 'failed')
    assert.equal(effects, 0)
    const original = Buffer.from(f.response.exports[0].content, 'base64')
    await writeFile(path, original)
    const changed = protectEvidence(Buffer.from('replacement content'), f.artifactKey, { run_id: 'run-1', path: 'organization-7.zip' })
    const result = await cleanupProductionCampaign(f.options, f.environment, { usePriorExports: true,
      execute: async () => ({ ...f.response, exports: [{ name: 'organization-7.zip.enc', content: changed.toString('base64') }] }) })
    assert.equal(result.status, 'failed')
    assert.deepEqual(result.completed, [7])
    assert.deepEqual(await readFile(path), original)
  } finally { await rm(f.root, { recursive: true, force: true }) }
})

test('export-only authenticates every target backup without certifying or requesting deletion', async () => {
  const f = await fixture()
  try {
    const exported = { ...f.response.result, status: 'exported', completed: [], removed_actors: [],
      pending: [7], pending_actors: ['user_Founder'], exported: [7] }
    const result = await cleanupProductionCampaign(f.options, f.environment, { exportOnly: true, execute: async packet => {
      assert.equal(packet.mode, 'export')
      return { ...f.response, result: exported }
    } })
    assert.equal(result.status, 'exported')
    assert.deepEqual(result.completed, [])
    assert.deepEqual(result.removed_actors, [])
    assert.deepEqual(result.pending, [7])
    assert.deepEqual(result.exported, [7])
    assert.ok((await readFile(join(f.options.artifactRoot, 'organization-7.zip.enc'))).length > 0)
  } finally { await rm(f.root, { recursive: true, force: true }) }
})

test('export-only rejects deletion outcomes, missing backups and cross-mode success', async () => {
  const f = await fixture()
  try {
    const exported = { ...f.response.result, status: 'exported', completed: [], removed_actors: [],
      pending: [7], pending_actors: ['user_Founder'], exported: [7] }
    for (const result of [f.response.result, { ...exported, completed: [7] },
      { ...exported, removed_actors: ['user_Founder'] }, { ...exported, exported: [] }]) {
      const outcome = await cleanupProductionCampaign(f.options, f.environment, { exportOnly: true,
        execute: async () => ({ ...f.response, result }) })
      assert.equal(outcome.status, 'failed')
    }
    const missing = await cleanupProductionCampaign(f.options, f.environment, { exportOnly: true,
      execute: async () => ({ result: exported, exports: [] }) })
    assert.equal(missing.status, 'failed')
    const wrongMode = await cleanupProductionCampaign(f.options, f.environment, {
      execute: async () => ({ ...f.response, result: exported }) })
    assert.equal(wrongMode.status, 'failed')
    assert.deepEqual(await readdir(f.options.artifactRoot).catch(() => []), [])
  } finally { await rm(f.root, { recursive: true, force: true }) }
})

test('foreign campaigns and missing credentials prevent all remote effects', async () => {
  const f = await fixture()
  try {
    let effects = 0
    const execute = async () => { effects++; return f.response }
    const foreign = await cleanupProductionCampaign({ ...f.options, runId: 'foreign' }, f.environment, { execute })
    assert.equal(foreign.status, 'failed')
    const missing = await cleanupProductionCampaign(f.options, { ...f.environment, E2E_ADMIN_SSH_KEY: '' }, { execute })
    assert.equal(missing.status, 'failed')
    assert.equal(effects, 0)
  } finally { await rm(f.root, { recursive: true, force: true }) }
})

test('unowned exports and missing authenticated export never certify deletion', async () => {
  const f = await fixture()
  try {
    for (const exports of [[], [{ ...f.response.exports[0], name: '../organization-7.zip.enc' }], [{ ...f.response.exports[0], name: 'organization-8.zip.enc' }], [{ ...f.response.exports[0], content: Buffer.from('plaintext').toString('base64') }]]) {
      const result = await cleanupProductionCampaign(f.options, f.environment, { execute: async () => ({ ...f.response, exports }) })
      assert.equal(result.status, 'failed')
    }
    assert.deepEqual(await readdir(f.options.artifactRoot).catch(() => []), [])
  } finally { await rm(f.root, { recursive: true, force: true }) }
})

test('transport failures remain pending without exposing provider error text', async () => {
  const f = await fixture()
  try {
    const result = await cleanupProductionCampaign(f.options, f.environment, { execute: async () => { throw new Error('secret provider response') } })
    assert.equal(result.status, 'failed')
    assert.deepEqual(result.pending, [7])
    assert.deepEqual(result.pending_actors, ['user_Founder'])
    assert.equal(JSON.stringify(result).includes('secret provider response'), false)
  } finally { await rm(f.root, { recursive: true, force: true }) }
})

test('local export failure preserves authenticated deletion outcomes for reconciliation', async () => {
  const f = await fixture()
  try {
    await mkdir(f.options.artifactRoot)
    const destination = join(f.options.artifactRoot, 'organization-7.zip.enc')
    await writeFile(destination, 'existing evidence must remain intact')
    const result = await cleanupProductionCampaign(f.options, f.environment, { execute: async () => ({
      ...f.response, export_directory: '/tmp/cronos-e2e-run-1-backup',
    }) })
    assert.equal(result.status, 'failed')
    assert.deepEqual(result.completed, [7])
    assert.deepEqual(result.removed_actors, ['user_Founder'])
    assert.deepEqual(result.pending, [])
    assert.deepEqual(result.pending_actors, [])
    assert.deepEqual(result.exports, [])
    assert.equal(result.remote_export_directory, '/tmp/cronos-e2e-run-1-backup')
    assert.equal(await readFile(destination, 'utf8'), 'existing evidence must remain intact')
  } finally { await rm(f.root, { recursive: true, force: true }) }
})

test('a response cannot remove the founder of a persistent school', async () => {
  const f = await fixture()
  try {
    const key = Buffer.from(f.environment.E2E_REGISTRY_HMAC_KEY, 'base64')
    const registry = verifyRegistry(JSON.parse(await readFile(f.options.registryPath, 'utf8')), key)
    registry.organizations[0].type = 'persistent'
    await writeFile(f.options.registryPath, JSON.stringify(signRegistry(registry, key)))
    const result = await cleanupProductionCampaign(f.options, f.environment, { execute: async () => ({
      result: { ...f.response.result, completed: [] }, exports: [],
    }) })
    assert.equal(result.status, 'failed')
    assert.deepEqual(await readdir(f.options.artifactRoot).catch(() => []), [])
  } finally { await rm(f.root, { recursive: true, force: true }) }
})

test('artifact directory aliases are rejected before any administrative transport', async () => {
  const f = await fixture()
  try {
    await mkdir(join(f.root, 'real-directory'))
    await symlink(join(f.root, 'real-directory'), join(f.root, 'alias'), process.platform === 'win32' ? 'junction' : 'dir')
    let effects = 0
    const result = await cleanupProductionCampaign({ ...f.options, artifactRoot: join(f.root, 'alias', 'evidence') }, f.environment, { execute: async () => { effects++; return f.response } })
    assert.equal(result.status, 'failed')
    assert.equal(effects, 0)
    assert.deepEqual(await readdir(join(f.root, 'real-directory')), [])
  } finally { await rm(f.root, { recursive: true, force: true }) }
})
test('conflicting removed and pending actor outcomes cannot certify remote effects', async () => {
  const f = await fixture()
  try {
    const result = await cleanupProductionCampaign(f.options, f.environment, { execute: async () => ({
      ...f.response, result: { ...f.response.result, status: 'failed', pending_actors: ['user_Founder'] },
    }) })
    assert.equal(result.status, 'failed')
    assert.deepEqual(result.removed_actors, [])
    assert.deepEqual(result.pending_actors, ['user_Founder'])
    assert.deepEqual(result.completed, [])
    assert.deepEqual(await readdir(f.options.artifactRoot).catch(() => []), [])
  } finally { await rm(f.root, { recursive: true, force: true }) }
})

test('an unresolved write-ahead intent fails the campaign while confirmed removals and backups are preserved', async () => {
  const f = await fixture()
  try {
    const key = Buffer.from(f.environment.E2E_REGISTRY_HMAC_KEY, 'base64')
    const registry = verifyRegistry(JSON.parse(await readFile(f.options.registryPath, 'utf8')), key)
    const intentId = randomUUID(), attemptedAt = '2026-10-08T09:04:00.000Z'
    const withIntent = recordUiCreationIntent(registry, { id: intentId, kind: 'actor', alias: 'professorcronos100+run-1@gmail.com' }, attemptedAt)
    await writeFile(f.options.registryPath, JSON.stringify(signRegistry(withIntent, key)))
    const result = await cleanupProductionCampaign(f.options, f.environment, { execute: async () => f.response })
    assert.equal(result.status, 'failed')
    assert.equal(result.failure_type, 'UnresolvedUiCreation')
    assert.deepEqual(result.completed, [7])
    assert.deepEqual(result.removed_actors, ['user_Founder'])
    assert.deepEqual(result.pending, [])
    assert.deepEqual(result.exports, ['organization-7.zip.enc'])
    assert.deepEqual(result.unresolved_intents, [{ id: intentId, kind: 'actor', attempted_at: attemptedAt }])
    assert.ok((await readFile(join(f.options.artifactRoot, 'organization-7.zip.enc'))).length > 0)
  } finally { await rm(f.root, { recursive: true, force: true }) }
})

test('an unresolved write-ahead intent without known targets fails closed without transport', async () => {
  const f = await fixture()
  try {
    const key = Buffer.from(f.environment.E2E_REGISTRY_HMAC_KEY, 'base64')
    const intentId = randomUUID(), attemptedAt = '2026-10-08T09:01:00.000Z'
    const registry = recordUiCreationIntent(createUiRegistry('run-1', '2026-10-08T09:00:00.000Z'), { id: intentId, kind: 'org' }, attemptedAt)
    await writeFile(f.options.registryPath, JSON.stringify(signRegistry(registry, key)))
    let effects = 0
    const result = await cleanupProductionCampaign(f.options, f.environment, { execute: async () => { effects++; return f.response } })
    assert.equal(result.status, 'failed')
    assert.equal(result.failure_type, 'UnresolvedUiCreation')
    assert.equal(effects, 0)
    assert.deepEqual(result.completed, [])
    assert.deepEqual(result.unresolved_intents, [{ id: intentId, kind: 'org', attempted_at: attemptedAt }])
  } finally { await rm(f.root, { recursive: true, force: true }) }
})

test('testing token is minted through the administrative transport without protection keys', async () => {
  const f = await fixture()
  try {
    let sent
    const token = await mintClerkTestingToken({ expectedRevision: f.options.expectedRevision }, f.environment, {
      execute: async (packet, environment, code) => { sent = { packet, code }; return { testing_token: 'tok_' + 'a'.repeat(40) } } })
    assert.equal(token, 'tok_' + 'a'.repeat(40))
    assert.deepEqual(sent.packet, { mode: 'testing_token', expected_revision: f.options.expectedRevision })
    assert.match(sent.code, /testing_tokens/)
    assert.doesNotMatch(JSON.stringify(sent.packet), /private-key|railway-test/)
  } finally { await rm(f.root, { recursive: true, force: true }) }
})

test('testing token minting fails closed on configuration and malformed responses', async () => {
  const f = await fixture()
  try {
    let calls = 0
    const execute = async () => { calls++; return { testing_token: 'bad token' } }
    await assert.rejects(mintClerkTestingToken({ expectedRevision: 'short' }, f.environment, { execute }), /Invalid campaign identity/)
    await assert.rejects(mintClerkTestingToken({ expectedRevision: f.options.expectedRevision }, { ...f.environment, E2E_ADMIN_SSH_KEY: '' }, { execute }), /Administrative dependency unavailable/)
    assert.equal(calls, 0)
    for (const response of [{ testing_token: 'bad token' }, {}, null]) {
      await assert.rejects(mintClerkTestingToken({ expectedRevision: f.options.expectedRevision }, f.environment, { execute: async () => response }), /Testing token unavailable/)
    }
  } finally { await rm(f.root, { recursive: true, force: true }) }
})

test('administrative transport failures are reported only as fixed classes', () => {
  assert.equal(classifyTransportFailure('Host key verification failed.\r\n'), 'ssh_host_key')
  assert.equal(classifyTransportFailure('git@ssh: Permission denied (publickey).'), 'ssh_key_rejected')
  assert.equal(classifyTransportFailure('Unauthorized. Please login with `railway login`'), 'railway_auth')
  assert.equal(classifyTransportFailure('Service not found'), 'target_not_found')
  assert.equal(classifyTransportFailure('sk_live_secret leaked text'), 'unknown')
  assert.equal(classifyTransportFailure(''), 'unknown')
})

test('the administrative SSH identity is written in the format OpenSSH loads', () => {
  const key = '-----BEGIN OPENSSH PRIVATE KEY-----\nAAAA\n-----END OPENSSH PRIVATE KEY-----'
  assert.equal(sshIdentityFile(key), `${key}\n`)
  assert.equal(sshIdentityFile(`${key.replaceAll('\n', '\r\n')}\r\n\r\n`), `${key}\n`)
  assert.equal(classifyTransportFailure('Load key "/tmp/identity": error in libcrypto'), 'ssh_key_unreadable')
  assert.equal(classifyTransportFailure('{"status":"no_ssh_key"}'), 'ssh_key_unreadable')
})
