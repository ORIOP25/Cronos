import assert from 'node:assert/strict'
import { mkdtemp, readFile, readdir, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import test from 'node:test'
import { assertRevisionSnapshot, deploymentConfig, readDeploymentSnapshot, recordGroupRevisionSnapshot } from '../e2e/utils/deployments.js'

const revision = 'a'.repeat(40)
const services = Object.fromEntries(['api', 'worker', 'supervisor', 'beat'].map(name => [name, `${name}-id`]))
function responses() {
  return {
    frontend: { schema_version: 1, revision, verifiable: true, source: 'cloudflare-pages' },
    pages: { success: true, result: [{ id: 'pages-id', environment: 'production', project_name: 'cronos', deployment_trigger: { metadata: { commit_hash: revision } }, latest_stage: { name: 'deploy', status: 'success' } }], result_info: { total_pages: 1 } },
    ready: { status: 'ok', revision, postgres: 'connected', redis: 'connected' },
    railway: { data: { serviceInstance: { latestDeployment: { id: 'deployment-id', status: 'SUCCESS', deploymentStopped: false, meta: { commitHash: revision } } }, deployments: { edges: [{ node: { id: 'deployment-id', status: 'SUCCESS', deploymentStopped: false, meta: { commitHash: revision } } }], pageInfo: { hasNextPage: false } } } },
  }
}
const config = { expectedRevision: revision, cloudflare: { token: 'secret', account: 'account-id', project: 'cronos' }, railway: { token: 'private', tokenType: 'account', project: 'project-id', environment: 'environment-id', services } }
const mockFetch = data => async (url) => ({ ok: true, status: 200, json: async () => url.includes('revision.json') ? data.frontend : url.includes('cloudflare.com') ? data.pages : url.includes('ready') ? data.ready : data.railway })

test('five components must have matching provider and public revisions', async () => {
  const snapshot = await readDeploymentSnapshot(config, { fetchImpl: mockFetch(responses()) })
  assertRevisionSnapshot(snapshot, revision)
  assert.deepEqual(Object.keys(snapshot.components).sort(), ['api', 'beat', 'frontend', 'supervisor', 'worker'])
  const changed = { ...snapshot, components: { ...snapshot.components, supervisor: 'b'.repeat(40) } }
  assert.throws(() => assertRevisionSnapshot(changed, revision), /supervisor/)
})

test('provider failure, preview, stale active worker and GraphQL errors are fatal', async () => {
  for (const mutate of [
    data => { data.pages.result[0].environment = 'preview' },
    data => { data.pages.success = false },
    data => { data.frontend.verifiable = false },
    data => { data.ready.redis = 'disconnected' },
    data => { data.railway.errors = [{ message: 'private error body' }] },
    data => { data.railway.data.serviceInstance.latestDeployment.status = 'BUILDING' },
    data => { data.railway.data.deployments.edges.push({ node: { id: 'old', deploymentStopped: false, status: 'SUCCESS', meta: { commitHash: 'b'.repeat(40) } } }) },
    data => { data.railway.data.deployments.pageInfo.hasNextPage = true },
  ]) {
    const data = responses(); mutate(data)
    await assert.rejects(readDeploymentSnapshot(config, { fetchImpl: mockFetch(data) }))
  }
  await assert.rejects(readDeploymentSnapshot(config, { fetchImpl: async () => ({ ok: false, status: 401 }) }), /401/)
})

test('all Railway pages are inspected so an older active process cannot hide beyond the first page', async () => {
  const data = responses()
  const cursors = []
  const pagedFetch = olderActive => async (url, options) => {
    if (!url.includes('railway.com')) return mockFetch(data)(url)
    const { variables } = JSON.parse(options.body)
    cursors.push(variables.after)
    const response = structuredClone(data.railway)
    if (!variables.after) {
      response.data.deployments.pageInfo = { hasNextPage: true, endCursor: 'older-page' }
    } else {
      assert.equal(variables.after, 'older-page')
      response.data.deployments.edges = [{ node: { id: 'old', deploymentStopped: !olderActive, status: 'SUCCESS', meta: { commitHash: 'b'.repeat(40) } } }]
    }
    return { ok: true, json: async () => response }
  }
  await readDeploymentSnapshot(config, { fetchImpl: pagedFetch(false) })
  assert.deepEqual(cursors, [null, 'older-page', null, 'older-page', null, 'older-page', null, 'older-page'])
  await assert.rejects(readDeploymentSnapshot(config, { fetchImpl: pagedFetch(true) }), /active deployment/)
})
test('Pages snapshot uses the accepted default pagination and never masks a provider rejection', async () => {
  const data = responses()
  let pagesReads = 0
  const fetchImpl = async (url, options) => {
    if (url.includes('cloudflare.com')) {
      pagesReads++
      const query = new URL(url).searchParams
      assert.equal(query.get('env'), 'production')
      if (query.get('per_page') === '100') return { ok: false, status: 400 }
      return mockFetch(data)(url, options)
    }
    return mockFetch(data)(url, options)
  }
  const snapshot = await readDeploymentSnapshot(config, { fetchImpl })
  assert.equal(pagesReads, 1)
  assertRevisionSnapshot(snapshot, revision)
})

function groupEnvironment() {
  return {
    E2E_EXPECTED_REVISION: revision,
    CLOUDFLARE_API_TOKEN: 'cloudflare-secret',
    E2E_CLOUDFLARE_ACCOUNT_ID: 'account-id',
    E2E_CLOUDFLARE_PROJECT: 'cronos',
    E2E_RAILWAY_TOKEN: 'railway-secret',
    E2E_RAILWAY_TOKEN_TYPE: 'account',
    E2E_RAILWAY_PROJECT_ID: 'project-id',
    E2E_RAILWAY_ENVIRONMENT_ID: 'environment-id',
    E2E_RAILWAY_API_SERVICE_ID: services.api,
    E2E_RAILWAY_WORKER_SERVICE_ID: services.worker,
    E2E_RAILWAY_SUPERVISOR_SERVICE_ID: services.supervisor,
    E2E_RAILWAY_BEAT_SERVICE_ID: services.beat,
  }
}

test('preflight and every acceptance group share one deployment provider configuration', () => {
  const built = deploymentConfig(groupEnvironment())
  assert.equal(built.expectedRevision, revision)
  assert.deepEqual(built.cloudflare, { token: 'cloudflare-secret', account: 'account-id', project: 'cronos' })
  assert.deepEqual(built.railway, { token: 'railway-secret', tokenType: 'account', project: 'project-id', environment: 'environment-id', services })
})

function withGroupTestInfo(run) {
  return mkdtemp(join(tmpdir(), 'cronos-group-')).then(async root => {
    const attachments = []
    const testInfo = {
      outputPath: (...parts) => join(root, ...parts),
      attach: async (name, options) => { attachments.push({ name, ...options }) },
    }
    try { return await run(testInfo, attachments, root) } finally { await rm(root, { recursive: true, force: true }) }
  })
}

test('a group records a safe live revision snapshot before its body runs', async () => {
  await withGroupTestInfo(async (testInfo, attachments, root) => {
    const snapshot = await recordGroupRevisionSnapshot(testInfo, groupEnvironment(), { fetchImpl: mockFetch(responses()) })
    assertRevisionSnapshot(snapshot, revision)
    assert.deepEqual(Object.keys(snapshot).sort(), ['checked_at', 'components', 'deployments'])
    assert.deepEqual(snapshot.components, Object.fromEntries(['frontend', 'api', 'worker', 'supervisor', 'beat'].map(name => [name, revision])))
    assert.deepEqual(snapshot.deployments, { frontend: 'pages-id', api: 'deployment-id', worker: 'deployment-id', supervisor: 'deployment-id', beat: 'deployment-id' })
    const serialized = JSON.stringify(snapshot)
    assert.equal(serialized.includes('cloudflare-secret') || serialized.includes('railway-secret'), false)
    assert.equal(attachments.length, 1)
    assert.equal(attachments[0].name, 'group-revision-snapshot')
    assert.equal(attachments[0].contentType, 'application/json')
    assert.equal(attachments[0].path, join(root, 'group-revision-snapshot.json'))
    assert.deepEqual(JSON.parse(await readFile(attachments[0].path, 'utf8')), snapshot)
  })
})

test('a changed worker or a new published revision fails the group without an attachment or body', async () => {
  for (const mutate of [
    data => { data.railway.data.serviceInstance.latestDeployment.meta.commitHash = 'b'.repeat(40) },
    data => { data.railway.data.deployments.edges[0].node.meta.commitHash = 'b'.repeat(40) },
    data => { data.frontend.revision = 'b'.repeat(40) },
    data => { data.pages.result[0].deployment_trigger.metadata.commit_hash = 'b'.repeat(40) },
    data => { data.ready.revision = 'b'.repeat(40) },
  ]) {
    await withGroupTestInfo(async (testInfo, attachments, root) => {
      const data = responses(); mutate(data)
      await assert.rejects(recordGroupRevisionSnapshot(testInfo, groupEnvironment(), { fetchImpl: mockFetch(data) }))
      assert.deepEqual(attachments, [])
      assert.deepEqual(await readdir(root), [])
    })
  }
})

test('unexpected provider failures fail the group without a green snapshot', async () => {
  for (const fetchImpl of [
    async () => { throw new Error('provider unreachable') },
    async () => ({ ok: false, status: 503 }),
    async () => ({ ok: true, status: 200, json: async () => ({ errors: [{ message: 'private body' }] }) }),
  ]) {
    await withGroupTestInfo(async (testInfo, attachments, root) => {
      await assert.rejects(recordGroupRevisionSnapshot(testInfo, groupEnvironment(), { fetchImpl }))
      assert.deepEqual(attachments, [])
      assert.deepEqual(await readdir(root), [])
    })
  }
})
