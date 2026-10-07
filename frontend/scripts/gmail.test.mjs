import assert from 'node:assert/strict'
import test from 'node:test'
import { createGmailReader, extractMessage, validateDeliveredLink } from '../e2e/utils/gmail.js'
import { createAuthorization, validateCallback } from '../../scripts/authorize-e2e-gmail.mjs'

const criteria = { recipient: 'admincronos100+run1@gmail.com', after: 1791360000000, before: 1791363600000, senders: ['noreply@cronos.pt'], subject: /^Verify your email$/, purpose: 'code' }
function message(body = 'Your verification code is 123456') {
  return { id: 'mail-1', internalDate: String(criteria.after + 1000), payload: { headers: [
    { name: 'To', value: criteria.recipient }, { name: 'From', value: 'Cronos <noreply@cronos.pt>' }, { name: 'Subject', value: 'Verify your email' },
  ], parts: [{ mimeType: 'multipart/alternative', parts: [{ mimeType: 'text/plain', body: { data: Buffer.from(body).toString('base64url') } }] }] } }
}

test('message matching checks recipient, sender, purpose and internal delivery time', () => {
  assert.equal(extractMessage(message(), criteria).code, '123456')
  for (const change of [
    item => { item.internalDate = String(criteria.after - 1) },
    item => { item.internalDate = String(criteria.before + 1) },
    item => { item.payload.headers[0].value = 'customer@gmail.com' },
    item => { item.payload.headers[1].value = 'noreply@cronos.pt.attacker.test' },
    item => { item.payload.headers[2].value = 'Other purpose' },
  ]) { const item = message(); change(item); assert.equal(extractMessage(item, criteria), null) }
  assert.throws(() => extractMessage(message('123456 or 654321'), criteria), /ambiguous/i)
})

test('delivered links require exact https hosts and no embedded credentials', () => {
  assert.equal(validateDeliveredLink('https://cronos.pt/invitation?ticket=received', ['cronos.pt']).hostname, 'cronos.pt')
  for (const url of ['http://cronos.pt/a', 'https://cronos.pt.evil.test/a', 'https://user@cronos.pt/a', 'javascript:alert(1)']) {
    assert.throws(() => validateDeliveredLink(url, ['cronos.pt']), /link/i)
  }
})

test('Gmail reader verifies mailbox before any message read and uses only readonly requests', async () => {
  const calls = []
  const fetchImpl = async (url, options) => {
    calls.push({ url, options })
    const body = url.includes('/token') ? { access_token: 'private-token', scope: 'https://www.googleapis.com/auth/gmail.readonly' }
      : url.endsWith('/profile') ? { emailAddress: 'admincronos100@gmail.com' }
        : url.includes('format=full') ? message() : { messages: [{ id: 'mail-1' }] }
    return { ok: true, status: 200, json: async () => body }
  }
  const reader = await createGmailReader({ clientId: 'client', clientSecret: 'secret', refreshToken: 'refresh', mailbox: 'admincronos100@gmail.com' }, { fetchImpl })
  assert.equal((await reader.poll(criteria, { timeoutMs: 1000, intervalMs: 100 })).code, '123456')
  assert.equal(calls.filter(item => item.options.method === 'POST').length, 1)
  assert.ok(calls.filter(item => item.url.includes('/gmail/')).every(item => item.options.method === 'GET'))
  await assert.rejects(createGmailReader({ clientId: 'client', clientSecret: 'secret', refreshToken: 'refresh', mailbox: 'professorcronos100@gmail.com' }, { fetchImpl }), /mailbox/i)
  const errorFetch = async () => ({ ok: false, status: 401, json: async () => ({ error: 'do not expose body' }) })
  await assert.rejects(createGmailReader({ clientId: 'client', clientSecret: 'secret', refreshToken: 'refresh', mailbox: 'admincronos100@gmail.com' }, { fetchImpl: errorFetch }), /Gmail.*401/)
})

test('OAuth uses PKCE, readonly offline consent and validates callback state and path', () => {
  const auth = createAuthorization('client', 'http://127.0.0.1:12345/callback', 'admincronos100@gmail.com')
  const url = new URL(auth.url)
  assert.equal(url.searchParams.get('scope'), 'https://www.googleapis.com/auth/gmail.readonly')
  assert.equal(url.searchParams.get('code_challenge_method'), 'S256')
  assert.equal(url.searchParams.get('access_type'), 'offline')
  assert.equal(validateCallback(`/callback?state=${auth.state}&code=received`, auth.state), 'received')
  for (const callback of [
    '/callback?state=wrong&code=received', `/callback?state=${auth.state}`, `/other?state=${auth.state}&code=received`,
    `/callback?state=${auth.state}&state=wrong&code=received`, `/callback?state=${auth.state}&code=received&code=other`,
    `https://outside.test/callback?state=${auth.state}&code=received`, `/callback?state=${auth.state}&code=received#error`,
  ]) {
    assert.throws(() => validateCallback(callback, auth.state), /callback/i)
  }
})

test('a refreshed Gmail token must explicitly confirm only readonly scope before reading the profile', async () => {
  for (const scope of [undefined, 'https://mail.google.com/', 'https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.modify']) {
    const calls = []
    const fetchImpl = async url => {
      calls.push(url)
      return { ok: true, json: async () => url.includes('/token') ? { access_token: 'private-token', scope } : { emailAddress: 'admincronos100@gmail.com' } }
    }
    await assert.rejects(createGmailReader({ clientId: 'client', clientSecret: 'secret', refreshToken: 'refresh', mailbox: 'admincronos100@gmail.com' }, { fetchImpl }), /readonly/)
    assert.equal(calls.length, 1)
  }
})
