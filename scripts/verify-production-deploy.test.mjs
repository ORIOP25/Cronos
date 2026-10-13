import assert from 'node:assert/strict'
import test from 'node:test'
import { observeDeployment } from './verify-production-deploy.mjs'

const SHA = 'a'.repeat(40)
const OLD = 'b'.repeat(40)
const PAGE = '<html><head><title>Cronos | Gestão</title></head><body><div id="root"></div></body></html>'

function production({ site = SHA, api = SHA, health = { status: 'ok', postgres: 'connected', redis: 'connected' }, pages = {} } = {}) {
  return async (url) => {
    const { origin, pathname } = new URL(url)
    if (origin === 'https://cronos.pt' && pathname === '/revision.json') return Response.json({ revision: site })
    if (origin === 'https://api.cronos.pt' && pathname === '/health/ready') return Response.json({ ...health, revision: api })
    if (origin === 'https://cronos.pt') {
      const page = pages[pathname] ?? { status: 200, body: PAGE }
      return new Response(page.body, { status: page.status, headers: { 'content-type': 'text/html; charset=utf-8' } })
    }
    throw new Error(`unexpected request ${url}`)
  }
}

test('a deployment serving the commit with healthy dependencies is ready', async () => {
  assert.deepEqual(await observeDeployment(SHA, { fetchImpl: production() }), { ready: true, failures: [] })
})

test('a frontend still serving the previous build is not ready', async () => {
  const result = await observeDeployment(SHA, { fetchImpl: production({ site: OLD }) })
  assert.equal(result.ready, false)
  assert.deepEqual(result.failures, [`Frontend serves ${OLD}`])
})

test('the API revision is required only when the commit changed the backend', async () => {
  const fetchImpl = production({ api: OLD })
  assert.deepEqual((await observeDeployment(SHA, { fetchImpl, backendChanged: true })).failures, [`API serves ${OLD}`])
  assert.equal((await observeDeployment(SHA, { fetchImpl, backendChanged: false })).ready, true)
})

test('an unhealthy API dependency is a failure even on the expected revision', async () => {
  const fetchImpl = production({ health: { status: 'degraded', postgres: 'connected', redis: 'disconnected' } })
  assert.deepEqual((await observeDeployment(SHA, { fetchImpl })).failures, ['API health is degraded (postgres connected, redis disconnected)'])
})

test('a public page that does not render the application shell is a failure', async () => {
  const fetchImpl = production({ pages: { '/login': { status: 503, body: 'down' } } })
  assert.deepEqual((await observeDeployment(SHA, { fetchImpl })).failures, ['/login answered 503'])
})

test('an unreachable endpoint becomes a failure instead of an exception', async () => {
  const fetchImpl = async () => { throw new Error('getaddrinfo ENOTFOUND') }
  const result = await observeDeployment(SHA, { fetchImpl })
  assert.equal(result.ready, false)
  assert.ok(result.failures.every((failure) => failure.endsWith('unreachable: getaddrinfo ENOTFOUND')))
})
