import { setTimeout as sleep } from 'node:timers/promises'
import { CODE_SENDER_PATTERN } from './acceptance-policy.js'

const READONLY_SCOPE = 'https://www.googleapis.com/auth/gmail.readonly'
const DEDICATED_MAILBOXES = new Set(['admincronos100@gmail.com', 'professorcronos100@gmail.com'])
const DEDICATED_ALIAS = /^(?:admincronos100|professorcronos100)\+[a-z0-9-]+@gmail\.com$/
const DISCOVERY_SUBJECTS = {
  verification: /^\d{6} is your verification code$/,
  reset: /^\d{6} is your reset password code$/,
}
const DISCOVERY_MAX_WINDOW_MS = 30 * 24 * 60 * 60 * 1000
const DISCOVERY_LISTING_FIELDS = 'messages(id),nextPageToken,resultSizeEstimate'
const DISCOVERY_METADATA_FIELDS = 'internalDate,payload(headers(name,value))'
const DISCOVERY_METADATA_HEADERS = `format=metadata&fields=${DISCOVERY_METADATA_FIELDS}&metadataHeaders=From&metadataHeaders=To&metadataHeaders=Subject`

// A discovery recipient is the dedicated mailbox itself or one of its own
// plus-aliases. The rule keeps the search inside the two dedicated mailboxes.
export function isDedicatedRecipient(mailbox, value) {
  const base = String(mailbox || '').toLowerCase()
  const recipient = String(value || '').toLowerCase()
  if (!DEDICATED_MAILBOXES.has(base)) return false
  if (recipient === base) return true
  return DEDICATED_ALIAS.test(recipient) && recipient.startsWith(`${base.slice(0, base.indexOf('@'))}+`)
}

function validateDiscoveryCriteria(criteria, mailbox) {
  if (!Object.hasOwn(DISCOVERY_SUBJECTS, criteria.purpose)) throw new Error('Discovery purpose must be verification or reset')
  if (!isDedicatedRecipient(mailbox, criteria.recipient)) throw new Error('Discovery recipient must identify the dedicated mailbox or one of its aliases')
  if (!Number.isSafeInteger(criteria.after) || !Number.isSafeInteger(criteria.before) || criteria.before <= criteria.after) throw new Error('Discovery window must have bounded epoch timestamps')
  if (criteria.before - criteria.after > DISCOVERY_MAX_WINDOW_MS) throw new Error('Discovery window exceeds the maximum of 30 days')
}

// Apply the same strict To/subject/time filters used for delivered codes, then
// read only the From header. The subject is tested in memory and never returned.
function metadataSender(message, criteria, subject) {
  const delivered = Number(message.internalDate)
  if (!Number.isSafeInteger(delivered) || delivered < criteria.after || delivered > criteria.before) return null
  const headers = message.payload?.headers || []
  const values = name => headers.filter(item => item.name.toLowerCase() === name).map(item => item.value)
  if (!addresses(values('to').join(', ')).includes(criteria.recipient.toLowerCase())) return null
  const subjects = values('subject')
  subject.lastIndex = 0
  if (subjects.length !== 1 || !subject.test(subjects[0])) return null
  const senders = addresses(values('from').join(', '))
  return senders.length === 1 ? { sender: senders[0] } : { malformed: true }
}

function addresses(value) {
  return String(value || '').split(/[\s<>(),;:"]+/)
    .filter(item => /^[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Z0-9.-]+\.[A-Z]{2,}$/i.test(item))
    .map(item => item.toLowerCase())
}

const DEADLINE_ERROR = 'Gmail delivery deadline exceeded'

function compareStrings(a, b) {
  if (a === b) return 0
  return a < b ? -1 : 1
}

function listingQuery({ recipient, marker = '', after, before, fields }) {
  const params = new URLSearchParams({
    q: [`to:${recipient}`, marker && `"${marker}"`, `after:${Math.floor(after / 1000)}`, `before:${Math.ceil(before / 1000)}`].filter(Boolean).join(' '),
    maxResults: '100',
  })
  if (fields) params.set('fields', fields)
  return params
}

function listingItems(listing) {
  const items = listing.messages ?? []
  if (!Array.isArray(items)) throw new Error('Gmail listing returned malformed entries')
  return items
}

function messageId(item) {
  if (typeof item?.id !== 'string' || !item.id) throw new Error('Gmail listing returned malformed entries')
  return item.id
}

function validatePollBounds(timeoutMs, intervalMs) {
  if (!Number.isFinite(timeoutMs) || timeoutMs <= 0 || timeoutMs > 300_000
    || !Number.isFinite(intervalMs) || intervalMs < 100 || intervalMs > timeoutMs) {
    throw new Error('Gmail polling bounds are invalid')
  }
}

function recordObservation(found, observed) {
  if (!observed) return
  if (observed.malformed) { found.malformedCount += 1; return }
  found.messageCount += 1
  found.senders.add(observed.sender)
}

function discoveryOutcome(found) {
  if (found.malformedCount > 0) return { status: 'failed', reason: 'malformed_headers' }
  if (found.messageCount === 0) return { status: 'incomplete', reason: 'no_messages' }
  const distinct = [...found.senders]
  if (distinct.length !== 1) return { status: 'failed', reason: 'ambiguous_senders' }
  if (!CODE_SENDER_PATTERN.test(distinct[0])) return { status: 'failed', reason: 'incompatible_sender' }
  return { status: 'observed', reason: 'unique_sender' }
}

function discoveryResult(found, outcome) {
  return { ...outcome, senders: [...found.senders].sort(compareStrings), message_count: found.messageCount }
}

function textParts(payload) {
  const own = ['text/plain', 'text/html'].includes(payload?.mimeType) && payload.body?.data
    ? [Buffer.from(payload.body.data, 'base64url').toString('utf8')] : []
  return [...own, ...(payload?.parts || []).flatMap(textParts)]
}

export function validateDeliveredLink(value, hosts) {
  let url
  try { url = new URL(value) } catch { throw new Error('Invalid delivered link') }
  if (url.protocol !== 'https:' || url.username || url.password || url.port || !hosts.includes(url.hostname)) throw new Error('Unexpected delivered link destination')
  return url
}

export function deliveredMessageSecrets(message) {
  if (message.code) return [message.code]
  if (!message.link) throw new Error('Delivered message contains no credential')
  const values = [...new URL(message.link).searchParams.values()].filter(Boolean)
  return [...new Set([message.link, ...values, ...values.map(value => encodeURIComponent(value))])]
}

function validateCriteria(criteria) {
  const recipient = criteria.recipient?.toLowerCase()
  if (criteria.purpose === 'contact') {
    const fields = criteria.fields
    const labels = ['Nome', 'Email', 'Telefone', 'Assunto', 'Cursos', 'Professores', 'Mensagem']
    if (recipient !== 'contacto@cronos.pt' || !DEDICATED_MAILBOXES.has(criteria.forwardedMailbox)
      || !DEDICATED_ALIAS.test(criteria.replyTo || '') || !/^e2e-contact-[a-z0-9-]{1,100}$/.test(criteria.marker || '')
      || !fields || Object.keys(fields).length !== labels.length
      || labels.some(label => typeof fields[label] !== 'string' || !fields[label] || /[\r\n]/.test(fields[label]))
      || fields.Email !== criteria.replyTo || fields.Mensagem !== criteria.marker) {
      throw new Error('Contact delivery requires its original recipient, dedicated forward and complete run-specific answers')
    }
  } else if (!DEDICATED_ALIAS.test(recipient || '')) throw new Error('Message recipient must identify a dedicated run alias')
  if (!Number.isSafeInteger(criteria.after) || !Number.isSafeInteger(criteria.before) || criteria.before <= criteria.after) throw new Error('Message interval must have bounded epoch timestamps')
  if (!Array.isArray(criteria.senders) || !criteria.senders.length || !(criteria.subject instanceof RegExp) || !['code', 'invitation', 'contact'].includes(criteria.purpose)) throw new Error('Message sender and purpose criteria are required')
  if (criteria.purpose === 'invitation' && (!Array.isArray(criteria.linkHosts) || !criteria.linkHosts.length)) throw new Error('Invitation link hosts are required')
}

export function extractMessage(message, criteria) {
  validateCriteria(criteria)
  const delivered = Number(message.internalDate)
  if (!Number.isSafeInteger(delivered) || delivered < criteria.after || delivered > criteria.before) return null
  const headers = message.payload?.headers || []
  const header = name => headers.filter(item => item.name.toLowerCase() === name).map(item => item.value).join(', ')
  if (!addresses(header('to')).includes(criteria.recipient.toLowerCase())) return null
  const senders = addresses(header('from'))
  if (senders.length !== 1 || !criteria.senders.includes(senders[0])) return null
  criteria.subject.lastIndex = 0
  if (!criteria.subject.test(header('subject'))) return null
  const text = textParts(message.payload).join('\n').replaceAll('&amp;', '&')
  const found = { id: message.id, delivered_at: new Date(delivered).toISOString() }
  if (criteria.purpose === 'contact') return contactFields(header, text, criteria, found)
  if (criteria.purpose === 'code') return deliveredCode(header('subject'), text, found)
  return invitationLink(text, criteria, found)
}

function contactFields(header, text, criteria, found) {
  const recipients = addresses(header('to')), reply = addresses(header('reply-to'))
  const lines = new Set(text.split(/\r?\n/))
  if (recipients.length !== 1 || reply.length !== 1 || reply[0] !== criteria.replyTo
    || !addresses(header('delivered-to')).includes(criteria.forwardedMailbox)
    || Object.entries(criteria.fields).some(([label, value]) => !lines.has(`${label}: ${value}`))) return null
  return { ...found, recipient: recipients[0], reply_to: reply[0], marker: criteria.marker }
}

function deliveredCode(subject, text, found) {
  // Clerk puts the code first in the subject; its HTML also holds six-digit colours.
  const subjectCode = /^(\d{6}) /.exec(subject)?.[1]
  if (subjectCode) return new RegExp(String.raw`(?<!\d)${subjectCode}(?!\d)`).test(text) ? { ...found, code: subjectCode } : null
  const codes = [...new Set(text.match(/(?<!\d)\d{6}(?!\d)/g) || [])]
  if (!codes.length) return null
  if (codes.length !== 1) throw new Error('Ambiguous verification codes in delivered message')
  return { ...found, code: codes[0] }
}

function invitationLink(text, criteria, found) {
  const links = [...new Set(text.match(/https?:\/\/[^\s<>"']+/g) || [])]
    .filter(value => new URL(value).pathname === criteria.linkPath)
    .map(value => validateDeliveredLink(value, criteria.linkHosts).href)
  if (!links.length) return null
  if (links.length !== 1) throw new Error('Ambiguous invitation links in delivered message')
  return { ...found, link: links[0] }
}

const OAUTH_ERRORS = new Set(['invalid_grant', 'invalid_client', 'unauthorized_client', 'access_denied'])

function safeHttpStatus(value) {
  return Number.isInteger(value) && value >= 100 && value <= 599 ? value : null
}

const SAFE_CONTENT_TYPES = new Set(['json', 'html', 'text', 'other', 'missing'])

function safeContentType(value) {
  const type = String(value || '').toLowerCase()
  if (!type) return 'missing'
  if (type.includes('json')) return 'json'
  if (type.includes('html')) return 'html'
  if (type.startsWith('text/')) return 'text'
  return 'other'
}

// A dependency error carries only an operation enum, a safe code, a bounded
// HTTP status and a reason enum. Provider bodies, descriptions, scopes and
// messages never reach it.
function gmailError(code, { operation, httpStatus = null, reason, message, bodyBytes, emptyBody, contentType }) {
  const status = safeHttpStatus(httpStatus)
  const suffix = status ? `: HTTP ${status}` : ''
  const error = new Error(message || `Gmail ${operation} failed${suffix}`)
  error.name = 'GmailDependencyError'
  error.code = code
  error.operation = operation
  error.httpStatus = status
  error.reason = reason
  if (code === 'invalid_json' && (bodyBytes !== undefined || emptyBody !== undefined || contentType !== undefined)) {
    error.bodyBytes = Number.isSafeInteger(bodyBytes) && bodyBytes >= 0 ? bodyBytes : null
    error.emptyBody = typeof emptyBody === 'boolean' ? emptyBody : null
    error.contentType = SAFE_CONTENT_TYPES.has(contentType) ? contentType : 'missing'
  }
  return error
}

// Parse the provider response only in memory and keep an allowlisted OAuth code.
async function providerErrorCode(response, operation) {
  if (operation !== 'oauth_refresh') return null
  try {
    const payload = await response.json()
    return typeof payload?.error === 'string' && OAUTH_ERRORS.has(payload.error) ? payload.error : null
  } catch {
    return null
  }
}

// Read a successful body once and parse it in memory. A blank or malformed body
// is a fail-closed invalid_json error carrying only size and type metadata.
async function parseJsonBody(response, operation) {
  const httpStatus = response.status
  const contentType = safeContentType(response.headers?.get?.('content-type'))
  if (typeof response.text === 'function') {
    let text
    try {
      text = await response.text()
    } catch {
      throw gmailError('invalid_json', { operation, httpStatus, reason: 'invalid_json', contentType })
    }
    try {
      return JSON.parse(text)
    } catch {
      throw gmailError('invalid_json', { operation, httpStatus, reason: 'invalid_json', bodyBytes: Buffer.byteLength(text), emptyBody: text.length === 0, contentType })
    }
  }
  try {
    return await response.json()
  } catch {
    throw gmailError('invalid_json', { operation, httpStatus, reason: 'invalid_json' })
  }
}

async function requestJson(fetchImpl, url, { operation, ...options }) {
  let response
  try {
    response = await fetchImpl(url, { ...options, redirect: 'error', signal: AbortSignal.timeout(15_000) })
  } catch {
    throw gmailError('network_error', { operation, reason: 'network' })
  }
  if (!response.ok) {
    const providerCode = await providerErrorCode(response, operation)
    throw gmailError(providerCode || 'http_error', { operation, httpStatus: response.status, reason: providerCode ? 'oauth_error' : 'http' })
  }
  return parseJsonBody(response, operation)
}

export async function createGmailReader(credentials, { fetchImpl = fetch } = {}) {
  const { clientId, clientSecret, refreshToken, mailbox } = credentials
  if (!clientId || !clientSecret || !refreshToken || !DEDICATED_MAILBOXES.has(mailbox)) throw new Error('Gmail dedicated mailbox credentials are required')
  let token
  let expiresAt = 0
  async function renew() {
    const result = await requestJson(fetchImpl, 'https://oauth2.googleapis.com/token', {
      operation: 'oauth_refresh',
      method: 'POST', body: new URLSearchParams({ client_id: clientId, client_secret: clientSecret, refresh_token: refreshToken, grant_type: 'refresh_token' }),
    })
    if (!result.access_token || result.scope !== READONLY_SCOPE) {
      throw gmailError('invalid_readonly_scope', { operation: 'oauth_refresh', httpStatus: 200, reason: 'scope_mismatch', message: 'Gmail token must grant only readonly scope' })
    }
    token = result.access_token
    expiresAt = Date.now() + Math.max(0, Number(result.expires_in || 3600) - 60) * 1000
    const profile = await requestJson(fetchImpl, 'https://gmail.googleapis.com/gmail/v1/users/me/profile', { operation: 'mailbox_profile', method: 'GET', headers: { Authorization: `Bearer ${token}` } })
    if (profile.emailAddress?.toLowerCase() !== mailbox) {
      throw gmailError('mailbox_mismatch', { operation: 'mailbox_profile', httpStatus: 200, reason: 'profile_mismatch', message: 'Gmail token belongs to a different mailbox' })
    }
  }
  await renew()
  async function get(path, operation) {
    if (Date.now() >= expiresAt) await renew()
    return requestJson(fetchImpl, `https://gmail.googleapis.com/gmail/v1/users/me/${path}`, { operation, method: 'GET', headers: { Authorization: `Bearer ${token}` } })
  }
  // Shared bounded pagination for delivery polling and sender discovery. It
  // stops on the deadline or the page cap and reports both explicitly.
  async function scanPages(query, { deadline, maxPages = Number.POSITIVE_INFINITY }, visit) {
    const expired = () => Date.now() > deadline
    let pageToken
    let pages = 0
    while (true) {
      if (expired()) return { truncated: Boolean(pageToken), expired: true }
      const params = new URLSearchParams(query)
      if (pageToken) params.set('pageToken', pageToken)
      const listing = await get(`messages?${params}`, 'message_listing')
      for (const item of listingItems(listing)) {
        if (expired()) return { truncated: Boolean(pageToken), expired: true }
        await visit(item)
      }
      pageToken = listing.nextPageToken
      pages += 1
      if (expired()) return { truncated: Boolean(pageToken), expired: true }
      if (!pageToken || pages >= maxPages) return { truncated: Boolean(pageToken), expired: false }
    }
  }
  return {
    mailbox,
    // Metadata-only discovery of the code sender. It reads From/To/Subject
    // headers, never the body, and reports only a fixed, secret-free summary.
    async discoverSender(criteria, { maxPages = 3, deadlineMs = 30_000 } = {}) {
      validateDiscoveryCriteria(criteria, mailbox)
      if (!Number.isSafeInteger(maxPages) || maxPages < 1 || maxPages > 10) throw new Error('Discovery page bound is invalid')
      if (!Number.isFinite(deadlineMs) || deadlineMs <= 0 || deadlineMs > 300_000) throw new Error('Discovery time bound is invalid')
      const subject = DISCOVERY_SUBJECTS[criteria.purpose]
      const found = { senders: new Set(), messageCount: 0, malformedCount: 0 }
      const query = listingQuery({ recipient: criteria.recipient, after: criteria.after, before: criteria.before, fields: DISCOVERY_LISTING_FIELDS })
      const { truncated, expired } = await scanPages(query, { deadline: Date.now() + deadlineMs, maxPages }, async item => {
        const message = await get(`messages/${encodeURIComponent(messageId(item))}?${DISCOVERY_METADATA_HEADERS}`, 'message_metadata')
        recordObservation(found, metadataSender(message, criteria, subject))
      })
      // A remaining page token means the bounded scan was truncated; a unique
      // sender is never reported from a partial scan.
      if (truncated) return discoveryResult(found, { status: 'incomplete', reason: 'page_limit' })
      if (expired) return discoveryResult(found, { status: 'incomplete', reason: 'time_limit' })
      return discoveryResult(found, discoveryOutcome(found))
    },
    async poll(criteria, { timeoutMs = 120_000, intervalMs = 2000 } = {}) {
      validateCriteria(criteria)
      if (criteria.purpose === 'contact' && criteria.forwardedMailbox !== mailbox) throw new Error('Contact forward belongs to a different mailbox')
      validatePollBounds(timeoutMs, intervalMs)
      const deadline = Date.now() + timeoutMs
      const query = listingQuery({
        recipient: criteria.recipient,
        marker: criteria.purpose === 'contact' ? criteria.marker : '',
        after: criteria.after,
        before: criteria.before,
      })
      let previous = -1
      do {
        const matches = []
        const { expired } = await scanPages(query, { deadline }, async item => {
          const delivered = extractMessage(await get(`messages/${encodeURIComponent(messageId(item))}?format=full`, 'message_metadata'), criteria)
          if (delivered) matches.push(delivered)
        })
        if (expired) throw new Error(DEADLINE_ERROR)
        // A re-sent code (e.g. Clerk's new-device check) invalidates the earlier one:
        // with `latest`, take the newest code once two scans agree on the set.
        if (criteria.latest === true && criteria.purpose === 'code' && matches.length) {
          if (matches.length === previous) return matches.reduce((a, b) => (b.delivered_at > a.delivered_at ? b : a))
          previous = matches.length
        } else {
          if (matches.length > 1) throw new Error('Ambiguous matching Gmail messages')
          if (matches.length === 1) return matches[0]
        }
        await sleep(Math.min(intervalMs, Math.max(0, deadline - Date.now())))
      } while (Date.now() < deadline)
      throw new Error(DEADLINE_ERROR)
    },
  }
}
