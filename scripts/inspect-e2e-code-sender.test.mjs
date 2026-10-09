import assert from 'node:assert/strict'
import test from 'node:test'
import { spawnSync } from 'node:child_process'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { runInspection } from './inspect-e2e-code-sender.mjs'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const CLI = join(ROOT, 'scripts', 'inspect-e2e-code-sender.mjs')
const BASE_ENV = {
  PATH: process.env.PATH, SystemRoot: process.env.SystemRoot, SystemDrive: process.env.SystemDrive,
  TEMP: process.env.TEMP, TMP: process.env.TMP, PATHEXT: process.env.PATHEXT, COMSPEC: process.env.COMSPEC,
}

function runCli(overrides) {
  const env = { ...BASE_ENV, ...overrides }
  for (const key of Object.keys(env)) if (env[key] === undefined) delete env[key]
  return spawnSync(process.execPath, [CLI], { cwd: ROOT, encoding: 'utf8', windowsHide: true, env })
}

// Drive the real HTTP path with native Response objects so the CLI reads the
// body once and reports only safe metadata.
function gmailResponses(listing) {
  return async url => {
    const json = body => new Response(JSON.stringify(body), { status: 200, headers: { 'content-type': 'application/json' } })
    if (url.includes('/token')) return json({ access_token: 'private-token', scope: 'https://www.googleapis.com/auth/gmail.readonly' })
    if (url.endsWith('/profile')) return json({ emailAddress: MAILBOX })
    return listing
  }
}

const READONLY = 'https://www.googleapis.com/auth/gmail.readonly'
const MAILBOX = 'admincronos100@gmail.com'
const AFTER = Date.parse('2026-10-01T00:00:00.000Z')
const BEFORE = Date.parse('2026-10-08T00:00:00.000Z')
const DAY = 86_400_000

function environment(overrides = {}) {
  return {
    E2E_INSPECT_MAILBOX: 'admin',
    E2E_INSPECT_PURPOSE: 'verification',
    E2E_INSPECT_AFTER: new Date(AFTER).toISOString(),
    E2E_INSPECT_BEFORE: new Date(BEFORE).toISOString(),
    E2E_GMAIL_CLIENT_ID: 'client-id',
    E2E_GMAIL_CLIENT_SECRET: 'client-secret',
    E2E_GMAIL_ADMIN_REFRESH_TOKEN: 'admin-refresh',
    ...overrides,
  }
}

function headers({ from = 'Cronos <noreply@cronos.pt>', to = MAILBOX, subject = '123456 is your verification code' } = {}) {
  const list = []
  for (const value of [].concat(from)) if (value !== null) list.push({ name: 'From', value })
  for (const value of [].concat(to)) if (value !== null) list.push({ name: 'To', value })
  for (const value of [].concat(subject)) if (value !== null) list.push({ name: 'Subject', value })
  return list
}

function message({ id = 'm1', internalDate = AFTER + 1000, ...options } = {}) {
  return { id, internalDate: String(internalDate), payload: { headers: headers(options) } }
}

function server({ pages = [{ messages: [] }], bodies = {}, token = { access_token: 'private-token', scope: READONLY }, profile = { emailAddress: MAILBOX } } = {}) {
  const calls = []
  let page = 0
  const respond = (body, ok = true, status = 200) => ({ ok, status, json: async () => body })
  const fetchImpl = async (url, options = {}) => {
    calls.push({ url, method: options.method || 'GET', body: options.body ? String(options.body) : null })
    if (url.includes('oauth2.googleapis.com/token')) return respond(token)
    if (url.endsWith('/profile')) return respond(profile)
    if (url.includes('/messages?')) {
      const entry = pages[Math.min(page, pages.length - 1)]
      page += 1
      return respond(entry)
    }
    if (url.includes('/messages/')) {
      const id = decodeURIComponent(new URL(url).pathname.split('/messages/')[1])
      return respond(bodies[id] ?? message({ id }))
    }
    throw new Error('Unexpected request')
  }
  return { fetchImpl, calls }
}

test('observes the unique production sender with metadata-only requests', async () => {
  const { fetchImpl, calls } = server({
    pages: [{ messages: [{ id: 'm1' }, { id: 'm2' }] }],
    bodies: { m1: message({ id: 'm1', internalDate: AFTER + 1000 }), m2: message({ id: 'm2', internalDate: AFTER + 2000 }) },
  })
  const result = await runInspection(environment(), { fetchImpl })
  assert.equal(result.status, 'observed')
  assert.equal(result.certifies_production, false)
  assert.deepEqual(result.senders, ['noreply@cronos.pt'])
  assert.equal(result.sender_count, 1)
  assert.equal(result.message_count, 2)
  assert.equal(result.mailbox, 'admin')
  assert.equal(result.purpose, 'verification')
  assert.deepEqual(result.window, { after: new Date(AFTER).toISOString(), before: new Date(BEFORE).toISOString() })
  const metadata = calls.filter(call => call.url.includes('/messages/') && !call.url.includes('/messages?'))
  assert.ok(metadata.length)
  for (const call of metadata) {
    assert.equal(call.method, 'GET')
    const url = new URL(call.url)
    assert.equal(url.searchParams.get('format'), 'metadata')
    assert.equal(url.searchParams.get('fields'), 'internalDate,payload(headers(name,value))')
    assert.deepEqual(url.searchParams.getAll('metadataHeaders'), ['From', 'To', 'Subject'])
    assert.equal(url.searchParams.get('fields').includes('snippet'), false)
    assert.equal(url.searchParams.get('fields').includes('body'), false)
    assert.notEqual(url.searchParams.get('format'), 'full')
  }
  const listing = new URL(calls.find(call => call.url.includes('/messages?')).url)
  assert.equal(listing.searchParams.get('q'), `to:${MAILBOX} after:${AFTER / 1000} before:${BEFORE / 1000}`)
  assert.equal(listing.searchParams.get('maxResults'), '100')
  assert.equal(listing.searchParams.get('fields'), 'messages(id),nextPageToken,resultSizeEstimate')
  for (const forbidden of ['snippet', 'body', 'payload']) {
    assert.equal(listing.searchParams.get('fields').includes(forbidden), false, forbidden)
  }
  const serialized = JSON.stringify(result)
  for (const secret of ['private-token', 'admin-refresh', 'client-secret', '123456', 'is your verification code']) {
    assert.equal(serialized.includes(secret), false, secret)
  }
})

test('reports incomplete when the bounded window contains no matching message', async () => {
  const { fetchImpl } = server({ pages: [{ messages: [] }] })
  const result = await runInspection(environment(), { fetchImpl })
  assert.equal(result.status, 'incomplete')
  assert.equal(result.reason, 'no_messages')
  assert.deepEqual(result.senders, [])
  assert.equal(result.message_count, 0)
})

test('fails on ambiguous senders without dropping the observed list', async () => {
  const { fetchImpl } = server({
    pages: [{ messages: [{ id: 'm1' }, { id: 'm2' }] }],
    bodies: { m1: message({ id: 'm1' }), m2: message({ id: 'm2', from: 'Cronos <no-reply@cronos.pt>' }) },
  })
  const result = await runInspection(environment(), { fetchImpl })
  assert.equal(result.status, 'failed')
  assert.equal(result.reason, 'ambiguous_senders')
  assert.deepEqual(result.senders, ['no-reply@cronos.pt', 'noreply@cronos.pt'])
})

test('fails closed on missing, malformed or duplicate From headers', async () => {
  for (const from of [null, 'not an address', ['first@cronos.pt', 'second@cronos.pt']]) {
    const { fetchImpl } = server({ pages: [{ messages: [{ id: 'm1' }] }], bodies: { m1: message({ id: 'm1', from }) } })
    const result = await runInspection(environment(), { fetchImpl })
    assert.equal(result.status, 'failed', JSON.stringify(from))
    assert.equal(result.reason, 'malformed_headers')
  }
})

test('fails on a unique sender outside the exact cronos.pt rule', async () => {
  const { fetchImpl } = server({ pages: [{ messages: [{ id: 'm1' }] }], bodies: { m1: message({ id: 'm1', from: 'Clerk <noreply@example.com>' }) } })
  const result = await runInspection(environment(), { fetchImpl })
  assert.equal(result.status, 'failed')
  assert.equal(result.reason, 'incompatible_sender')
  assert.deepEqual(result.senders, ['noreply@example.com'])
})

test('ignores messages for another recipient, another subject or outside the window', async () => {
  for (const body of [
    message({ id: 'm1', to: 'professorcronos100@gmail.com' }),
    message({ id: 'm1', subject: '999999 is your reset password code' }),
    message({ id: 'm1', internalDate: BEFORE + 1 }),
    message({ id: 'm1', internalDate: AFTER - 1 }),
  ]) {
    const { fetchImpl } = server({ pages: [{ messages: [{ id: 'm1' }] }], bodies: { m1: body } })
    const result = await runInspection(environment(), { fetchImpl })
    assert.equal(result.status, 'incomplete', JSON.stringify(result))
  }
})

test('matches only the exact subject for the requested purpose', async () => {
  const reset = message({ id: 'm1', subject: '999999 is your reset password code' })
  const verification = await runInspection(environment(), { fetchImpl: server({ pages: [{ messages: [{ id: 'm1' }] }], bodies: { m1: reset } }).fetchImpl })
  assert.equal(verification.status, 'incomplete')
  const recovery = await runInspection(environment({ E2E_INSPECT_PURPOSE: 'reset' }), { fetchImpl: server({ pages: [{ messages: [{ id: 'm1' }] }], bodies: { m1: reset } }).fetchImpl })
  assert.equal(recovery.status, 'observed')
  assert.equal(recovery.purpose, 'reset')
})

test('stops discovery at the bounded page limit', async () => {
  const pages = Array.from({ length: 5 }, (_, index) => ({ messages: [{ id: `m${index}` }], nextPageToken: `p${index}` }))
  const bodies = Object.fromEntries(pages.map((_, index) => [`m${index}`, message({ id: `m${index}`, to: 'professorcronos100@gmail.com' })]))
  const { fetchImpl, calls } = server({ pages, bodies })
  const result = await runInspection(environment(), { fetchImpl })
  assert.equal(result.status, 'incomplete')
  assert.equal(result.reason, 'page_limit')
  assert.equal(calls.filter(call => call.url.includes('/messages?')).length, 3)
})

test('a truncated page window cannot report observed even when the read page matches', async () => {
  const base = server({
    pages: [{ messages: [{ id: 'm1' }], nextPageToken: 'p1' }, { messages: [{ id: 'm2' }] }],
    bodies: { m1: message({ id: 'm1' }), m2: message({ id: 'm2', from: 'Cronos <no-reply@cronos.pt>' }) },
  })
  const result = await runInspection(environment(), { fetchImpl: base.fetchImpl, maxPages: 1 })
  assert.equal(result.status, 'incomplete')
  assert.equal(result.reason, 'page_limit')
  assert.deepEqual(result.senders, ['noreply@cronos.pt'])
  assert.equal(base.calls.filter(call => call.url.includes('/messages?')).length, 1)
})

test('a deadline reached during the last fetch cannot report observed', async () => {
  const original = Date.now
  let now = 0
  try {
    Date.now = () => now
    const base = server({ pages: [{ messages: [{ id: 'm1' }] }], bodies: { m1: message({ id: 'm1' }) } })
    const fetchImpl = async (url, options) => { now += 40_000; return base.fetchImpl(url, options) }
    const result = await runInspection(environment(), { fetchImpl, deadlineMs: 30_000 })
    assert.equal(result.status, 'incomplete')
    assert.equal(result.reason, 'time_limit')
  } finally {
    Date.now = original
  }
})

test('uses the single runtime refresh token for the selected mailbox', async () => {
  const { fetchImpl, calls } = server({ pages: [{ messages: [] }] })
  const result = await runInspection(environment({ E2E_GMAIL_REFRESH_TOKEN: 'runtime-selected', E2E_GMAIL_ADMIN_REFRESH_TOKEN: 'legacy-admin' }), { fetchImpl })
  assert.equal(result.status, 'incomplete')
  const token = calls.find(call => call.url.includes('/token'))
  assert.equal(token.method, 'POST')
  assert.ok(token.body.includes('refresh_token=runtime-selected'))
  assert.equal(token.body.includes('legacy-admin'), false)
})

test('falls back to the mailbox-specific refresh token for local compatibility', async () => {
  const { fetchImpl, calls } = server({ pages: [{ messages: [] }] })
  await runInspection(environment(), { fetchImpl })
  const token = calls.find(call => call.url.includes('/token'))
  assert.ok(token.body.includes('refresh_token=admin-refresh'))
})

test('malformed listing and token responses stay sanitized dependency results', async () => {
  const malformedListing = async url => (url.includes('/token')
    ? { ok: true, json: async () => ({ access_token: 'private-token', scope: 'https://www.googleapis.com/auth/gmail.readonly' }) }
    : url.endsWith('/profile')
      ? { ok: true, json: async () => ({ emailAddress: MAILBOX }) }
      : { ok: true, json: async () => ({ messages: 'not-an-array' }) })
  const listingResult = await runInspection(environment(), { fetchImpl: malformedListing })
  assert.equal(listingResult.status, 'dependency_unavailable')
  assert.equal(listingResult.reason, 'gmail_unavailable')
  assert.equal(JSON.stringify(listingResult).includes('not-an-array'), false)

  const malformedToken = async () => ({ ok: true, json: async () => { throw new Error('raw token payload') } })
  const tokenResult = await runInspection(environment(), { fetchImpl: malformedToken })
  assert.equal(tokenResult.status, 'dependency_unavailable')
  assert.equal(tokenResult.reason, 'gmail_unavailable')
  assert.equal(JSON.stringify(tokenResult).includes('raw token payload'), false)
})

test('missing credentials are a dependency and start no external effect', async () => {
  let effects = 0
  const result = await runInspection(environment({ E2E_GMAIL_ADMIN_REFRESH_TOKEN: '' }), { fetchImpl: () => { effects += 1; throw new Error('no') } })
  assert.equal(result.status, 'dependency_unavailable')
  assert.equal(result.reason, 'missing_credentials')
  assert.equal(effects, 0)
})

test('provider, profile and scope failures stay sanitized dependency results', async () => {
  const failingToken = async url => (url.includes('/token')
    ? { ok: false, status: 401, json: async () => ({ error_description: 'raw provider detail' }) }
    : { ok: true, json: async () => ({ emailAddress: MAILBOX }) })
  const failure = await runInspection(environment(), { fetchImpl: failingToken })
  assert.equal(failure.status, 'dependency_unavailable')
  assert.equal(failure.reason, 'gmail_unavailable')
  assert.equal(JSON.stringify(failure).includes('raw provider detail'), false)

  const { fetchImpl: wrongProfile } = server({ profile: { emailAddress: 'other@gmail.com' } })
  assert.equal((await runInspection(environment(), { fetchImpl: wrongProfile })).status, 'dependency_unavailable')

  const { fetchImpl: wrongScope } = server({ token: { access_token: 'private-token', scope: 'https://mail.google.com/' } })
  assert.equal((await runInspection(environment(), { fetchImpl: wrongScope })).status, 'dependency_unavailable')
})

test('rejects an unlisted mailbox or an unauthorised recipient before any request', async () => {
  let effects = 0
  const fetchImpl = () => { effects += 1; throw new Error('no') }
  const badMailbox = await runInspection(environment({ E2E_INSPECT_MAILBOX: 'other' }), { fetchImpl })
  assert.equal(badMailbox.status, 'failed')
  assert.equal(badMailbox.reason, 'invalid_mailbox')
  const badPurpose = await runInspection(environment({ E2E_INSPECT_PURPOSE: 'other' }), { fetchImpl })
  assert.equal(badPurpose.status, 'failed')
  assert.equal(badPurpose.reason, 'invalid_purpose')
  const badRecipient = await runInspection(environment({ E2E_INSPECT_RECIPIENT: 'attacker@example.com' }), { fetchImpl })
  assert.equal(badRecipient.status, 'failed')
  assert.equal(badRecipient.reason, 'invalid_recipient')
  assert.equal(effects, 0)
})

test('bounds the UTC window and requires a reason beyond seven days', async () => {
  let effects = 0
  const fetchImpl = () => { effects += 1; throw new Error('no') }
  const tooLong = await runInspection(environment({ E2E_INSPECT_AFTER: new Date(BEFORE - 31 * DAY).toISOString() }), { fetchImpl })
  assert.equal(tooLong.status, 'failed')
  assert.equal(tooLong.reason, 'window_exceeds_limit')
  const eightDays = await runInspection(environment({ E2E_INSPECT_AFTER: new Date(BEFORE - 8 * DAY).toISOString() }), { fetchImpl })
  assert.equal(eightDays.status, 'failed')
  assert.equal(eightDays.reason, 'window_reason_required')
  const justified = await runInspection(environment({
    E2E_INSPECT_AFTER: new Date(BEFORE - 8 * DAY).toISOString(), E2E_INSPECT_WINDOW_REASON: 'scheduled maintenance',
  }), { fetchImpl: server({ pages: [{ messages: [] }] }).fetchImpl })
  assert.equal(justified.status, 'incomplete')
  const invalid = await runInspection(environment({ E2E_INSPECT_BEFORE: 'not-a-date' }), { fetchImpl })
  assert.equal(invalid.status, 'failed')
  assert.equal(invalid.reason, 'invalid_window')
  assert.equal(effects, 0)
})

test('reports the safe OAuth operation, code, status and reason without leaking the response', async () => {
  const fetchImpl = async url => (url.includes('/token')
    ? { ok: false, status: 400, json: async () => ({ error: 'invalid_grant', error_description: 'Token has been expired or revoked.', scope: 'openid email profile' }) }
    : { ok: true, status: 200, json: async () => ({ emailAddress: MAILBOX }) })
  const result = await runInspection(environment(), { fetchImpl })
  assert.equal(result.status, 'dependency_unavailable')
  assert.equal(result.reason, 'gmail_unavailable')
  assert.deepEqual(result.diagnostic, { operation: 'oauth_refresh', code: 'invalid_grant', http_status: 400, reason: 'oauth_error' })
  const serialized = JSON.stringify(result)
  for (const secret of ['Token has been expired', 'openid email profile', 'error_description']) assert.equal(serialized.includes(secret), false, secret)
})

test('reports the safe Gmail listing operation and status for the metadata integration', async () => {
  const fetchImpl = async url => {
    if (url.includes('/token')) return { ok: true, status: 200, json: async () => ({ access_token: 'private-token', scope: 'https://www.googleapis.com/auth/gmail.readonly' }) }
    if (url.endsWith('/profile')) return { ok: true, status: 200, json: async () => ({ emailAddress: MAILBOX }) }
    return { ok: false, status: 400, json: async () => ({ error: { code: 400, message: 'Invalid field selection payload(headers(name,value))' } }) }
  }
  const result = await runInspection(environment(), { fetchImpl })
  assert.equal(result.diagnostic.operation, 'message_listing')
  assert.equal(result.diagnostic.code, 'http_error')
  assert.equal(result.diagnostic.http_status, 400)
  assert.equal(result.diagnostic.reason, 'http')
  assert.equal(JSON.stringify(result).includes('Invalid field selection'), false)
})

test('reports a safe mailbox mismatch without exposing the profile address', async () => {
  const fetchImpl = async url => (url.includes('/token')
    ? { ok: true, status: 200, json: async () => ({ access_token: 'private-token', scope: 'https://www.googleapis.com/auth/gmail.readonly' }) }
    : { ok: true, status: 200, json: async () => ({ emailAddress: 'someone-else@gmail.com' }) })
  const result = await runInspection(environment(), { fetchImpl })
  assert.deepEqual(result.diagnostic, { operation: 'mailbox_profile', code: 'mailbox_mismatch', http_status: 200, reason: 'profile_mismatch' })
  assert.equal(JSON.stringify(result).includes('someone-else'), false)
})

test('reports a safe readonly scope diagnostic without exposing real scopes', async () => {
  const fetchImpl = async () => ({ ok: true, status: 200, json: async () => ({ access_token: 'private-token', scope: 'https://mail.google.com/ https://www.googleapis.com/auth/calendar' }) })
  const result = await runInspection(environment(), { fetchImpl })
  assert.deepEqual(result.diagnostic, { operation: 'oauth_refresh', code: 'invalid_readonly_scope', http_status: 200, reason: 'scope_mismatch' })
  assert.equal(JSON.stringify(result).includes('mail.google.com'), false)
})

test('classifies network and malformed JSON without echoing the original message', async () => {
  const network = await runInspection(environment(), { fetchImpl: async () => { throw new Error('getaddrinfo ENOTFOUND admincronos100@gmail.com') } })
  assert.deepEqual(network.diagnostic, { operation: 'oauth_refresh', code: 'network_error', http_status: null, reason: 'network' })
  assert.equal(JSON.stringify(network).includes('ENOTFOUND'), false)
  const malformed = await runInspection(environment(), { fetchImpl: async () => ({ ok: true, status: 200, json: async () => { throw new Error('raw body fragment') } }) })
  assert.deepEqual(malformed.diagnostic, { operation: 'oauth_refresh', code: 'invalid_json', http_status: 200, reason: 'invalid_json' })
  assert.equal(JSON.stringify(malformed).includes('raw body fragment'), false)
})

test('sanitizes arbitrary provider error text at every stage', async () => {
  const stages = [
    async url => (url.includes('/token')
      ? { ok: false, status: 403, json: async () => ({ error: 'quota_exceeded_secret', error_description: 'secret-oauth-detail' }) }
      : { ok: true, status: 200, json: async () => ({ emailAddress: MAILBOX }) }),
    async url => {
      if (url.includes('/token')) return { ok: true, status: 200, json: async () => ({ access_token: 'private-token', scope: 'https://www.googleapis.com/auth/gmail.readonly' }) }
      if (url.endsWith('/profile')) return { ok: false, status: 500, json: async () => ({ error: 'secret-profile-detail' }) }
      return { ok: true, status: 200, json: async () => ({ messages: [] }) }
    },
  ]
  for (const fetchImpl of stages) {
    const result = await runInspection(environment(), { fetchImpl })
    const serialized = JSON.stringify(result)
    for (const secret of ['quota_exceeded_secret', 'secret-oauth-detail', 'secret-profile-detail', 'error_description']) {
      assert.equal(serialized.includes(secret), false, secret)
    }
    assert.equal(['oauth_refresh', 'mailbox_profile', 'message_listing', 'message_metadata'].includes(result.diagnostic.operation), true)
  }
})

test('the CLI emits one parseable JSON line and never echoes injected control input', () => {
  const cli = runCli({
    E2E_INSPECT_MAILBOX: 'admin\nFORGED',
    E2E_INSPECT_PURPOSE: 'verification\r\nFORGED: injected',
    E2E_INSPECT_RECIPIENT: 'admincronos100@gmail.com\nFORGED',
  })
  assert.equal(cli.status, 1)
  assert.equal(cli.stderr, '')
  const records = cli.stdout.split('\n').filter(line => line.length)
  assert.equal(records.length, 1)
  const record = JSON.parse(records[0])
  assert.equal(record.status, 'failed')
  assert.equal(record.reason, 'invalid_mailbox')
  assert.equal(cli.stdout.includes('FORGED'), false)
  assert.equal(cli.stdout.includes('\r'), false)
})

test('the CLI emits one line for a missing-credential dependency without credential text', () => {
  const cli = runCli({ E2E_INSPECT_MAILBOX: 'admin', E2E_INSPECT_PURPOSE: 'verification' })
  assert.equal(cli.status, 3)
  assert.equal(cli.stderr, '')
  const records = cli.stdout.split('\n').filter(line => line.length)
  assert.equal(records.length, 1)
  const record = JSON.parse(records[0])
  assert.equal(record.status, 'dependency_unavailable')
  assert.equal(record.reason, 'missing_credentials')
  for (const text of ['secret', 'token', 'refresh', 'E2E_GMAIL']) assert.equal(cli.stdout.includes(text), false, text)
  assert.equal(cli.stdout.includes('\r'), false)
})

test('an empty selected listing result is a valid incomplete response', async () => {
  for (const body of [{ resultSizeEstimate: 0 }, {}]) {
    const listing = new Response(JSON.stringify(body), { status: 200, headers: { 'content-type': 'application/json' } })
    const result = await runInspection(environment(), { fetchImpl: gmailResponses(listing) })
    assert.equal(result.status, 'incomplete')
    assert.equal(result.reason, 'no_messages')
  }
})

test('a blank selected-field listing body fails closed with only safe body metadata', async () => {
  const listing = new Response('', { status: 200, headers: { 'content-type': 'application/json' } })
  const result = await runInspection(environment(), { fetchImpl: gmailResponses(listing) })
  assert.equal(result.status, 'dependency_unavailable')
  assert.equal(result.reason, 'gmail_unavailable')
  assert.deepEqual(result.diagnostic, {
    operation: 'message_listing', code: 'invalid_json', http_status: 200, reason: 'invalid_json',
    body_bytes: 0, empty_body: true, content_type: 'json',
  })
})

test('a non-JSON listing body fails closed without leaking the content', async () => {
  const html = '<html><body>FORGED_LISTING_SECRET</body></html>'
  const listing = new Response(html, { status: 200, headers: { 'content-type': 'text/html; charset=utf-8' } })
  const result = await runInspection(environment(), { fetchImpl: gmailResponses(listing) })
  assert.equal(result.diagnostic.code, 'invalid_json')
  assert.equal(result.diagnostic.http_status, 200)
  assert.equal(result.diagnostic.content_type, 'html')
  assert.equal(result.diagnostic.empty_body, false)
  assert.equal(result.diagnostic.body_bytes, Buffer.byteLength(html))
  assert.equal(JSON.stringify(result).includes('FORGED_LISTING_SECRET'), false)
})

test('a truncated listing payload retains its HTTP status and content type', async () => {
  const listing = new Response('{"messages":', { status: 200, headers: { 'content-type': 'application/json' } })
  const result = await runInspection(environment(), { fetchImpl: gmailResponses(listing) })
  assert.equal(result.diagnostic.code, 'invalid_json')
  assert.equal(result.diagnostic.http_status, 200)
  assert.equal(result.diagnostic.content_type, 'json')
  assert.equal(result.diagnostic.empty_body, false)
})

test('a non-success listing response retains its HTTP status without leaking the body', async () => {
  const listing = new Response('<html>FORGED_UNDERLYING</html>', { status: 400, headers: { 'content-type': 'text/html' } })
  const result = await runInspection(environment(), { fetchImpl: gmailResponses(listing) })
  assert.equal(result.diagnostic.operation, 'message_listing')
  assert.equal(result.diagnostic.code, 'http_error')
  assert.equal(result.diagnostic.http_status, 400)
  assert.equal(JSON.stringify(result).includes('FORGED_UNDERLYING'), false)
})
