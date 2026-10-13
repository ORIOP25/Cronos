import assert from 'node:assert/strict'
import test from 'node:test'
import { applicationFailure } from './verify-production-browser.mjs'

test('a failed or erroring application resource is a failure', () => {
  assert.equal(applicationFailure({ url: 'https://cronos.pt/assets/index-abc.js', status: 404 }), 'https://cronos.pt/assets/index-abc.js answered 404')
  assert.equal(applicationFailure({ url: 'https://cronos.pt/assets/index-abc.js', errorText: 'net::ERR_BLOCKED_BY_CSP' }), 'https://cronos.pt/assets/index-abc.js failed: net::ERR_BLOCKED_BY_CSP')
})

test('third-party resources and cancelled navigations are not application failures', () => {
  assert.equal(applicationFailure({ url: 'https://static.cloudflareinsights.com/beacon.min.js', errorText: 'csp' }), null)
  assert.equal(applicationFailure({ url: 'https://clerk.cronos.pt/v1/client', status: 401 }), null)
  assert.equal(applicationFailure({ url: 'https://cronos.pt/assets/index-abc.js', errorText: 'net::ERR_ABORTED' }), null)
  assert.equal(applicationFailure({ url: 'https://cronos.pt/login', status: 200 }), null)
})
