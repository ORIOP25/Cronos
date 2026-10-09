import assert from 'node:assert/strict'
import test from 'node:test'
import { createGmailReader, deliveredMessageSecrets, extractMessage, validateDeliveredLink } from '../e2e/utils/gmail.js'
import { createAuthorization, validateCallback } from '../../scripts/authorize-e2e-gmail.mjs'

const criteria = { recipient: 'admincronos100+run1@gmail.com', after: 1791360000000, before: 1791363600000, senders: ['noreply@cronos.pt'], subject: /^Verify your email$/, purpose: 'code' }
function message(body = 'Your verification code is 123456') {
  return { id: 'mail-1', internalDate: String(criteria.after + 1000), payload: { headers: [
    { name: 'To', value: criteria.recipient }, { name: 'From', value: 'Cronos <noreply@cronos.pt>' }, { name: 'Subject', value: 'Verify your email' },
  ], parts: [{ mimeType: 'multipart/alternative', parts: [{ mimeType: 'text/plain', body: { data: Buffer.from(body).toString('base64url') } }] }] } }
}

test('mail headers reject an address with a trailing path instead of accepting a matching substring', () => {
  const malformed = message()
  malformed.payload.headers[0].value = `<${criteria.recipient}/not-an-email>`
  assert.equal(extractMessage(malformed, criteria), null)
  const longHeader = message()
  longHeader.payload.headers[0].value = `${'x'.repeat(50_000)} <${criteria.recipient}>`
  assert.equal(extractMessage(longHeader, criteria).code, '123456')
})

const contactCriteria = { ...criteria, recipient: 'contacto@cronos.pt', purpose: 'contact',
  forwardedMailbox: 'admincronos100@gmail.com', replyTo: criteria.recipient, marker: 'e2e-contact-run1',
  senders: ['website@forms.cronos.pt'], subject: /^\[Cronos\] Novo contacto — Criar horários do zero sem conflitos$/,
  fields: { Nome: 'Cronos Aceitação run1', Email: criteria.recipient, Telefone: 'Não indicado',
    Assunto: 'Criar horários do zero sem conflitos', Cursos: 'Entre 1 e 5', Professores: 'Entre 1 e 15', Mensagem: 'e2e-contact-run1' },
}
function contactMessage() {
  const result = message('Novo contacto do website Cronos\n\n' + Object.entries(contactCriteria.fields).map(([key, value]) => `${key}: ${value}`).join('\n'))
  result.payload.headers = [
    { name: 'To', value: contactCriteria.recipient }, { name: 'From', value: contactCriteria.senders[0] },
    { name: 'Subject', value: '[Cronos] Novo contacto — Criar horários do zero sem conflitos' },
    { name: 'Reply-To', value: contactCriteria.replyTo }, { name: 'Delivered-To', value: contactCriteria.forwardedMailbox },
  ]
  return result
}

test('contact delivery requires the original recipient, authorized forward, reply address and every submitted answer', () => {
  assert.deepEqual(extractMessage(contactMessage(), contactCriteria), { id: 'mail-1',
    delivered_at: new Date(criteria.after + 1000).toISOString(), recipient: 'contacto@cronos.pt',
    reply_to: criteria.recipient, marker: 'e2e-contact-run1' })
  for (const change of [
    item => { item.payload.headers[0].value = criteria.recipient },
    item => { item.payload.headers[1].value = 'attacker@example.test' },
    item => { item.payload.headers[3].value = 'other@gmail.com' },
    item => { item.payload.headers[4].value = 'professorcronos100@gmail.com' },
    item => { item.payload.parts[0].parts[0].body.data = Buffer.from('e2e-contact-run1').toString('base64url') },
    item => { item.internalDate = String(criteria.after - 1) },
  ]) { const item = contactMessage(); change(item); assert.equal(extractMessage(item, contactCriteria), null) }
  for (const fields of Object.keys(contactCriteria.fields)) {
    const item = contactMessage()
    const part = item.payload.parts[0].parts[0].body
    part.data = Buffer.from(Buffer.from(part.data, 'base64url').toString().replace(`${fields}: ${contactCriteria.fields[fields]}`, `${fields}: changed`)).toString('base64url')
    assert.equal(extractMessage(item, contactCriteria), null)
  }
  for (const change of [{ recipient: criteria.recipient }, { forwardedMailbox: 'customer@gmail.com' },
    { replyTo: 'customer@gmail.com' }, { marker: '' }, { fields: {} }]) {
    assert.throws(() => extractMessage(contactMessage(), { ...contactCriteria, ...change }), /contact/i)
  }
})

test('contact polling reads only the configured forward mailbox and narrows discovery to the unique run marker', async () => {
  const calls = []
  const fetchImpl = async url => {
    calls.push(url)
    const body = url.includes('/token') ? { access_token: 'private-token', scope: 'https://www.googleapis.com/auth/gmail.readonly' }
      : url.endsWith('/profile') ? { emailAddress: 'admincronos100@gmail.com' }
        : url.includes('format=full') ? contactMessage() : { messages: [{ id: 'mail-1' }] }
    return { ok: true, status: 200, json: async () => body }
  }
  const reader = await createGmailReader({ clientId: 'client', clientSecret: 'secret', refreshToken: 'refresh', mailbox: 'admincronos100@gmail.com' }, { fetchImpl })
  assert.equal((await reader.poll(contactCriteria, { timeoutMs: 1000, intervalMs: 100 })).marker, contactCriteria.marker)
  const listing = new URL(calls.find(url => url.includes('messages?')))
  assert.equal(listing.searchParams.get('q'), `to:contacto@cronos.pt "e2e-contact-run1" after:${Math.floor(criteria.after / 1000)} before:${Math.ceil(criteria.before / 1000)}`)
  const previous = calls.length
  await assert.rejects(reader.poll({ ...contactCriteria, forwardedMailbox: 'professorcronos100@gmail.com' }), /different mailbox/)
  assert.equal(calls.length, previous)
})

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

test('delivered invitation credentials are protected even when the browser rewrites their URL', () => {
  const link = 'https://clerk.cronos.pt/v1/tickets/accept?ticket=actual%2Bticket%2Fvalue&redirect_url=https%3A%2F%2Fcronos.pt%2Flogin'
  const secrets = deliveredMessageSecrets({ link })
  for (const value of [link, 'actual+ticket/value', 'actual%2Bticket%2Fvalue']) assert.ok(secrets.includes(value))
  assert.deepEqual(deliveredMessageSecrets({ code: '135790' }), ['135790'])
  assert.throws(() => deliveredMessageSecrets({}), /credential/)
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

test('metadata discovery constrains the request to From, To and Subject and rejects unsafe criteria', async () => {
  const calls = []
  const body = { id: 'mail-9', internalDate: String(criteria.after + 1000), payload: { headers: [
    { name: 'From', value: 'Cronos <noreply@cronos.pt>' },
    { name: 'To', value: criteria.recipient },
    { name: 'Subject', value: '123456 is your verification code' },
  ] } }
  const fetchImpl = async (url, options) => {
    calls.push({ url, method: options.method })
    const payload = url.includes('/token') ? { access_token: 'private-token', scope: 'https://www.googleapis.com/auth/gmail.readonly' }
      : url.endsWith('/profile') ? { emailAddress: 'admincronos100@gmail.com' }
        : url.includes('/messages/') ? body : { messages: [{ id: 'mail-9' }] }
    return { ok: true, status: 200, json: async () => payload }
  }
  const reader = await createGmailReader({ clientId: 'client', clientSecret: 'secret', refreshToken: 'refresh', mailbox: 'admincronos100@gmail.com' }, { fetchImpl })
  const discovered = await reader.discoverSender({ recipient: criteria.recipient, purpose: 'verification', after: criteria.after, before: criteria.before })
  assert.equal(discovered.status, 'observed')
  assert.deepEqual(discovered.senders, ['noreply@cronos.pt'])
  const metadata = new URL(calls.find(call => call.url.includes('/messages/') && !call.url.includes('/messages?')).url)
  assert.equal(metadata.searchParams.get('format'), 'metadata')
  assert.equal(metadata.searchParams.get('fields'), 'internalDate,payload(headers(name,value))')
  assert.deepEqual(metadata.searchParams.getAll('metadataHeaders'), ['From', 'To', 'Subject'])
  assert.equal(metadata.searchParams.get('fields').includes('snippet'), false)
  assert.equal(metadata.searchParams.get('fields').includes('body'), false)
  const listing = new URL(calls.find(call => call.url.includes('/messages?')).url)
  assert.equal(listing.searchParams.get('fields'), 'messages(id),nextPageToken')
  for (const forbidden of ['snippet', 'body', 'payload']) {
    assert.equal(listing.searchParams.get('fields').includes(forbidden), false, forbidden)
  }
  await assert.rejects(reader.discoverSender({ recipient: 'attacker@example.com', purpose: 'verification', after: criteria.after, before: criteria.before }), /recipient/i)
  await assert.rejects(reader.discoverSender({ recipient: criteria.recipient, purpose: 'other', after: criteria.after, before: criteria.before }), /purpose/i)
  await assert.rejects(reader.discoverSender({ recipient: criteria.recipient, purpose: 'verification', after: criteria.before, before: criteria.after }), /window/i)
  await assert.rejects(reader.discoverSender({ recipient: criteria.recipient, purpose: 'verification', after: 0, before: 31 * 86_400_000 }), /window/i)
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

test('Gmail dependency errors expose only a safe operation, code, status and reason', async () => {
  const errorFetch = async () => ({ ok: false, status: 400, json: async () => ({ error: 'invalid_grant', error_description: 'do not leak this body' }) })
  const error = await createGmailReader({ clientId: 'client', clientSecret: 'secret', refreshToken: 'refresh', mailbox: 'admincronos100@gmail.com' }, { fetchImpl: errorFetch }).then(() => null, value => value)
  assert.equal(error.code, 'invalid_grant')
  assert.equal(error.operation, 'oauth_refresh')
  assert.equal(error.httpStatus, 400)
  assert.equal(error.reason, 'oauth_error')
  assert.equal(error.message.includes('do not leak this body'), false)
})
