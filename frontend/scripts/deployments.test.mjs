import assert from 'node:assert/strict'
import test from 'node:test'
import { assertRevisionSnapshot, readDeploymentSnapshot } from '../e2e/utils/deployments.js'

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
