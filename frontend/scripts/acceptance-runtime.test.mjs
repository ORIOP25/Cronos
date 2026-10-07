import assert from 'node:assert/strict'
import { EventEmitter } from 'node:events'
import test from 'node:test'
import { observeAcceptanceRuntime } from '../e2e/utils/acceptance-runtime.js'

function request(url, method = 'GET') {
  return { url: () => url, method: () => method, failure: () => ({ errorText: 'net::ERR_FAILED' }) }
}

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
