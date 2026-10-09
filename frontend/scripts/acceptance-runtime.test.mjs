import assert from 'node:assert/strict'
import { EventEmitter } from 'node:events'
import test from 'node:test'
import { observeAcceptanceActivity, observeAcceptanceRuntime } from '../e2e/utils/acceptance-runtime.js'

function request(url, method = 'GET') {
  return { url: () => url, method: () => method, failure: () => ({ errorText: 'net::ERR_FAILED' }) }
}

const BEACON_URL = 'https://static.cloudflareinsights.com/beacon.min.js/v4bc70e2c01a94c73b74392e4234840661791215815920'
const BEACON_PATH = '/beacon.min.js/v4bc70e2c01a94c73b74392e4234840661791215815920'
const BEACON_REASON = 'csp-blocked-optional-telemetry'

function scriptRequest(url, method = 'GET', resourceType = 'script') {
  return { url: () => url, method: () => method, resourceType: () => resourceType, failure: () => null }
}

function failedScriptRequest(url, errorText = 'csp', resourceType = 'script', method = 'GET') {
  return { url: () => url, method: () => method, resourceType: () => resourceType, failure: () => ({ errorText }) }
}

function cspConsoleMessage(scriptUrl, locationUrl, { verb = 'Loading' } = {}) {
  const lead = verb === 'Refused' ? 'Refused to load the script' : 'Loading the script'
  const bridge = verb === 'Refused' ? 'because it ' : ''
  return {
    type: () => 'error',
    text: () => `${lead} '${scriptUrl}' ${bridge}violates the following Content Security Policy directive: "script-src 'self' https://clerk.cronos.pt https://challenges.cloudflare.com". The action has been blocked.`,
    location: () => ({ url: locationUrl }),
  }
}

test('a dynamic expected authentication failure is pinned to the observed request and action', async () => {
  const page = new EventEmitter()
  const observer = observeAcceptanceRuntime(page)
  const url = 'https://clerk.cronos.pt/v1/client/sign_ins/signin_owned/attempt_first_factor'
  await observer.action('old-password', [], async () => {
    const owned = request(url, 'POST')
    page.emit('request', owned)
    assert.equal(observer.allowRequestFailure(owned, 422), true)
    page.emit('response', { request: () => owned, url: owned.url, status: () => 422 })
    page.emit('console', { type: () => 'error', text: () => 'Failed to load resource: the server responded with a status of 422', location: () => ({ url }) })
    assert.deepEqual(observer.errors, [])
    const unrelated = request(url, 'POST')
    page.emit('request', unrelated)
    page.emit('response', { request: () => unrelated, url: unrelated.url, status: () => 422 })
    assert.equal(observer.errors.length, 1)
    const unavailable = request(url, 'POST')
    page.emit('request', unavailable)
    assert.equal(observer.allowRequestFailure(unavailable, 422), true)
    page.emit('response', { request: () => unavailable, url: unavailable.url, status: () => 503 })
    assert.equal(observer.errors.length, 2)
  })
  observer.dispose()
})

test('dynamic failure registration refuses unobserved requests, another action and server errors', async () => {
  const page = new EventEmitter()
  const observer = observeAcceptanceRuntime(page)
  const pending = request('https://clerk.cronos.pt/v1/client/sign_ins', 'POST')
  await observer.action('old-password', [], async () => {
    assert.equal(observer.allowRequestFailure(pending, 400), false)
    page.emit('request', pending)
    assert.equal(observer.allowRequestFailure(pending, 500), false)
    await observer.action('other', [], async () => assert.equal(observer.allowRequestFailure(pending, 400), false))
  })
  assert.equal(observer.allowRequestFailure(pending, 400), false)
  assert.equal(observer.errors.length, 4)
  observer.dispose()
})

test('runtime failures accumulate without throwing from browser event handlers', () => {
  const page = new EventEmitter()
  const observer = observeAcceptanceRuntime(page)
  assert.doesNotThrow(() => {
    page.emit('pageerror', new Error('render failed'))
    page.emit('requestfailed', request('https://api.cronos.pt/api/v1/rooms'))
    const apiRequest = request('https://api.cronos.pt/api/v1/schedules', 'POST')
    page.emit('request', apiRequest)
    page.emit('response', { request: () => apiRequest, url: apiRequest.url, status: () => 503 })
    page.emit('console', { type: () => 'error', text: () => 'unexpected client error', location: () => ({ url: '' }) })
  })
  assert.equal(observer.errors.length, 4)
  observer.dispose()
  assert.equal(page.listenerCount('pageerror'), 0)
  assert.equal(page.listenerCount('response'), 0)
})

test('expected HTTP failures are tied to the action that initiated the request', async () => {
  const page = new EventEmitter()
  const observer = observeAcceptanceRuntime(page)
  const allowed = { origin: 'https://api.cronos.pt', pathname: '/api/v1/rooms', method: 'POST', status: 409, action: 'duplicate-room' }
  await observer.action('duplicate-room', [allowed], async () => {
    const pending = request('https://api.cronos.pt/api/v1/rooms', 'POST')
    page.emit('request', pending)
    await observer.action('navigate', [], async () => {})
    page.emit('response', { request: () => pending, url: pending.url, status: () => 409 })
    page.emit('console', { type: () => 'error', text: () => 'Failed to load resource: the server responded with a status of 409', location: () => ({ url: pending.url() }) })
  })
  assert.deepEqual(observer.errors, [])
  const unrelated = request('https://api.cronos.pt/api/v1/rooms', 'POST')
  page.emit('request', unrelated)
  page.emit('response', { request: () => unrelated, url: unrelated.url, status: () => 409 })
  assert.equal(observer.errors.length, 1)
  observer.dispose()
})

test('console exceptions require an observed request, and 500 errors are never exempt', async () => {
  const page = new EventEmitter()
  const observer = observeAcceptanceRuntime(page)
  const allowed = { origin: 'https://api.cronos.pt', pathname: '/api/v1/rooms', method: 'POST', status: 500, action: 'submit' }
  await observer.action('submit', [allowed], async () => {
    page.emit('console', { type: () => 'error', text: () => 'Failed to load resource: the server responded with a status of 409', location: () => ({ url: 'https://api.cronos.pt/api/v1/rooms' }) })
    const pending = request('https://api.cronos.pt/api/v1/rooms', 'POST')
    page.emit('request', pending)
    page.emit('response', { request: () => pending, url: pending.url, status: () => 500 })
  })
  assert.equal(observer.errors.length, 2)
  observer.dispose()
})

test('acceptance activity is reported only for real page requests and navigations while subscribed', () => {
  const page = new EventEmitter()
  let seen = 0
  observeAcceptanceActivity(() => { seen += 1 })
  try {
    const observer = observeAcceptanceRuntime(page)
    page.emit('request', request('https://api.cronos.pt/api/v1/rooms'))
    page.emit('framenavigated')
    assert.equal(seen, 2)
    observeAcceptanceActivity(null)
    page.emit('request', request('https://api.cronos.pt/api/v1/rooms'))
    assert.equal(seen, 2)
    observer.dispose()
  } finally { observeAcceptanceActivity(null) }
})

test('a new request cannot reuse an old expected console failure at the same URL', async () => {
  const page = new EventEmitter()
  const observer = observeAcceptanceRuntime(page)
  const url = 'https://api.cronos.pt/api/v1/rooms'
  await observer.action('duplicate-room', [{ origin: 'https://api.cronos.pt', pathname: '/api/v1/rooms', method: 'POST', status: 409, action: 'duplicate-room' }], async () => {
    const previous = request(url, 'POST')
    page.emit('request', previous)
    page.emit('response', { request: () => previous, url: previous.url, status: () => 409 })
  })
  page.emit('request', request(url, 'POST'))
  page.emit('console', { type: () => 'error', text: () => 'Failed to load resource: the server responded with a status of 409', location: () => ({ url }) })
  assert.equal(observer.errors.length, 1)
  observer.dispose()
})

test('ignores the CSP-blocked optional Cloudflare beacon only after observing its script GET', () => {
  const page = new EventEmitter()
  const observer = observeAcceptanceRuntime(page)
  page.emit('request', scriptRequest(BEACON_URL))
  // The CSP console message references the first-party page URL and arrives
  // before the requestfailed event; both events must reuse the observation.
  page.emit('console', cspConsoleMessage(BEACON_URL, 'https://cronos.pt/contacto'))
  page.emit('requestfailed', failedScriptRequest(BEACON_URL))
  assert.deepEqual(observer.errors, [])
  assert.deepEqual(observer.ignoredOptionalTelemetry, [
    { method: 'GET', host: 'static.cloudflareinsights.com', path: BEACON_PATH, reason: BEACON_REASON, event: 'console' },
    { method: 'GET', host: 'static.cloudflareinsights.com', path: BEACON_PATH, reason: BEACON_REASON, event: 'requestfailed' },
  ])
  observer.dispose()
})

test('accepts the Refused-to-load CSP wording for the same observed beacon', () => {
  const page = new EventEmitter()
  const observer = observeAcceptanceRuntime(page)
  page.emit('request', scriptRequest(BEACON_URL))
  page.emit('console', cspConsoleMessage(BEACON_URL, 'https://cronos.pt/contacto', { verb: 'Refused' }))
  assert.deepEqual(observer.errors, [])
  assert.equal(observer.ignoredOptionalTelemetry.length, 1)
  observer.dispose()
})

test('an unobserved CSP block, a foreign host or a different URL stays fail-closed', () => {
  const page = new EventEmitter()
  const observer = observeAcceptanceRuntime(page)
  const foreign = 'https://static.cloudflareinsights.com.evil.test/beacon.min.js/v4bc70e2c01a94c73b74392e4234840661791215815920'
  const other = 'https://static.cloudflareinsights.com/beacon.min.js/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
  page.emit('console', cspConsoleMessage(BEACON_URL, 'https://cronos.pt/contacto'))
  page.emit('request', scriptRequest(foreign))
  page.emit('console', cspConsoleMessage(foreign, 'https://cronos.pt/contacto'))
  page.emit('requestfailed', failedScriptRequest(foreign))
  page.emit('request', scriptRequest(BEACON_URL))
  page.emit('console', cspConsoleMessage(other, 'https://cronos.pt/contacto'))
  assert.equal(observer.errors.length, 4)
  assert.deepEqual(observer.ignoredOptionalTelemetry, [])
  observer.dispose()
})

test('a new navigation invalidates a prior optional telemetry observation', () => {
  const page = new EventEmitter()
  const observer = observeAcceptanceRuntime(page)
  page.emit('request', scriptRequest(BEACON_URL))
  page.emit('framenavigated')
  page.emit('console', cspConsoleMessage(BEACON_URL, 'https://cronos.pt/contacto'))
  page.emit('requestfailed', failedScriptRequest(BEACON_URL))
  assert.equal(observer.errors.length, 2)
  assert.deepEqual(observer.ignoredOptionalTelemetry, [])
  observer.dispose()
})

test('a real network failure or a non-script request for the beacon stays fail-closed', () => {
  const page = new EventEmitter()
  const observer = observeAcceptanceRuntime(page)
  page.emit('request', scriptRequest(BEACON_URL))
  page.emit('requestfailed', failedScriptRequest(BEACON_URL, 'net::ERR_CONNECTION_REFUSED'))
  page.emit('request', scriptRequest(BEACON_URL, 'GET', 'fetch'))
  page.emit('console', cspConsoleMessage(BEACON_URL, 'https://cronos.pt/contacto'))
  page.emit('requestfailed', failedScriptRequest(BEACON_URL, 'csp', 'fetch'))
  assert.equal(observer.errors.length, 3)
  assert.deepEqual(observer.ignoredOptionalTelemetry, [])
  observer.dispose()
})

test('an HTTP 500 response never reuses the optional telemetry exception', async () => {
  const page = new EventEmitter()
  const observer = observeAcceptanceRuntime(page)
  page.emit('request', scriptRequest(BEACON_URL))
  await observer.action('submit', [], async () => {
    const pending = request('https://api.cronos.pt/api/v1/rooms', 'POST')
    page.emit('request', pending)
    page.emit('response', { request: () => pending, url: pending.url, status: () => 500 })
    page.emit('console', { type: () => 'error', text: () => 'Failed to load resource: the server responded with a status of 500', location: () => ({ url: pending.url() }) })
  })
  assert.equal(observer.errors.length, 2)
  observer.dispose()
})

test('a POST script request never registers an optional beacon observation', () => {
  const page = new EventEmitter()
  const observer = observeAcceptanceRuntime(page)
  page.emit('request', scriptRequest(BEACON_URL, 'POST'))
  page.emit('console', cspConsoleMessage(BEACON_URL, 'https://cronos.pt/contacto'))
  page.emit('requestfailed', failedScriptRequest(BEACON_URL, 'csp', 'script', 'POST'))
  assert.equal(observer.errors.length, 2)
  assert.deepEqual(observer.ignoredOptionalTelemetry, [])
  observer.dispose()
})

test('a real beacon response invalidates the observation so a later CSP-looking error persists', () => {
  const page = new EventEmitter()
  const observer = observeAcceptanceRuntime(page)
  const beacon = scriptRequest(BEACON_URL)
  page.emit('request', beacon)
  page.emit('response', { request: () => beacon, url: () => BEACON_URL, status: () => 500 })
  page.emit('console', cspConsoleMessage(BEACON_URL, 'https://cronos.pt/contacto'))
  page.emit('requestfailed', failedScriptRequest(BEACON_URL))
  // The served 500 itself is the first error; the later CSP-looking events add two.
  assert.equal(observer.errors.length, 3)
  assert.deepEqual(observer.ignoredOptionalTelemetry, [])
  observer.dispose()
})

test('a genuine beacon HTTP 500 without any console message fails', () => {
  const page = new EventEmitter()
  const observer = observeAcceptanceRuntime(page)
  const beacon = scriptRequest(BEACON_URL)
  page.emit('request', beacon)
  page.emit('response', { request: () => beacon, url: () => BEACON_URL, status: () => 500 })
  assert.equal(observer.errors.length, 1)
  assert.match(observer.errors[0], /Optional telemetry beacon failed: 500 static\.cloudflareinsights\.com\/beacon\.min\.js/)
  assert.deepEqual(observer.ignoredOptionalTelemetry, [])
  observer.dispose()
})

test('a served beacon 404 also fails without a console message', () => {
  const page = new EventEmitter()
  const observer = observeAcceptanceRuntime(page)
  const beacon = scriptRequest(BEACON_URL)
  page.emit('request', beacon)
  page.emit('response', { request: () => beacon, url: () => BEACON_URL, status: () => 404 })
  assert.equal(observer.errors.length, 1)
  assert.deepEqual(observer.ignoredOptionalTelemetry, [])
  observer.dispose()
})

test('a subframe navigation keeps the beacon while a main navigation discards it', () => {
  const mainFrame = { parentFrame: () => null }
  const subFrame = { parentFrame: () => mainFrame }
  const page = new EventEmitter()
  page.mainFrame = () => mainFrame
  const observer = observeAcceptanceRuntime(page)
  page.emit('request', scriptRequest(BEACON_URL))
  page.emit('framenavigated', subFrame)
  page.emit('console', cspConsoleMessage(BEACON_URL, 'https://cronos.pt/contacto'))
  assert.deepEqual(observer.errors, [])
  assert.equal(observer.ignoredOptionalTelemetry.length, 1)
  page.emit('framenavigated', mainFrame)
  page.emit('console', cspConsoleMessage(BEACON_URL, 'https://cronos.pt/contacto'))
  assert.equal(observer.errors.length, 1)
  assert.equal(observer.ignoredOptionalTelemetry.length, 1)
  observer.dispose()
})

test('a valid CSP prefix with appended first-party error text is not ignored', () => {
  const page = new EventEmitter()
  const observer = observeAcceptanceRuntime(page)
  page.emit('request', scriptRequest(BEACON_URL))
  page.emit('console', {
    type: () => 'error',
    text: () => `Loading the script '${BEACON_URL}' violates the following Content Security Policy directive: "script-src 'self'". The action has been blocked. Unauthorized`,
    location: () => ({ url: 'https://cronos.pt/contacto' }),
  })
  page.emit('requestfailed', failedScriptRequest(BEACON_URL))
  assert.equal(observer.errors.length, 1)
  assert.equal(observer.ignoredOptionalTelemetry.length, 1)
  observer.dispose()
})
