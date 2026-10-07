import { setTimeout as sleep } from 'node:timers/promises'

const READONLY_SCOPE = 'https://www.googleapis.com/auth/gmail.readonly'
const DEDICATED_MAILBOXES = new Set(['admincronos100@gmail.com', 'professorcronos100@gmail.com'])

function addresses(value) {
  return String(value || '').match(/[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi)?.map(item => item.toLowerCase()) || []
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

function validateCriteria(criteria) {
  const recipient = criteria.recipient?.toLowerCase()
  if (!/^admincronos100\+[a-z0-9-]+@gmail\.com$|^professorcronos100\+[a-z0-9-]+@gmail\.com$/.test(recipient || '')) throw new Error('Message recipient must identify a dedicated run alias')
  if (!Number.isSafeInteger(criteria.after) || !Number.isSafeInteger(criteria.before) || criteria.before <= criteria.after) throw new Error('Message interval must have bounded epoch timestamps')
  if (!Array.isArray(criteria.senders) || !criteria.senders.length || !(criteria.subject instanceof RegExp) || !['code', 'invitation'].includes(criteria.purpose)) throw new Error('Message sender and purpose criteria are required')
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
  if (criteria.purpose === 'code') {
    const codes = [...new Set(text.match(/(?<!\d)\d{6}(?!\d)/g) || [])]
    if (!codes.length) return null
    if (codes.length !== 1) throw new Error('Ambiguous verification codes in delivered message')
    return { id: message.id, delivered_at: new Date(delivered).toISOString(), code: codes[0] }
  }
  const links = [...new Set(text.match(/https?:\/\/[^\s<>"']+/g) || [])]
    .filter(value => new URL(value).pathname === criteria.linkPath)
    .map(value => validateDeliveredLink(value, criteria.linkHosts).href)
  if (!links.length) return null
  if (links.length !== 1) throw new Error('Ambiguous invitation links in delivered message')
  return { id: message.id, delivered_at: new Date(delivered).toISOString(), link: links[0] }
}

async function requestJson(fetchImpl, url, options) {
  const response = await fetchImpl(url, { ...options, redirect: 'error', signal: AbortSignal.timeout(15_000) })
  if (!response.ok) throw new Error(`Gmail dependency unavailable: HTTP ${response.status}`)
  try { return await response.json() } catch { throw new Error('Gmail dependency returned invalid JSON') }
}

export async function createGmailReader(credentials, { fetchImpl = fetch } = {}) {
  const { clientId, clientSecret, refreshToken, mailbox } = credentials
  if (!clientId || !clientSecret || !refreshToken || !DEDICATED_MAILBOXES.has(mailbox)) throw new Error('Gmail dedicated mailbox credentials are required')
  let token
  let expiresAt = 0
  async function renew() {
    const result = await requestJson(fetchImpl, 'https://oauth2.googleapis.com/token', {
      method: 'POST', body: new URLSearchParams({ client_id: clientId, client_secret: clientSecret, refresh_token: refreshToken, grant_type: 'refresh_token' }),
    })
    if (!result.access_token || result.scope !== READONLY_SCOPE) throw new Error('Gmail token must grant only readonly scope')
    token = result.access_token
    expiresAt = Date.now() + Math.max(0, Number(result.expires_in || 3600) - 60) * 1000
    const profile = await requestJson(fetchImpl, 'https://gmail.googleapis.com/gmail/v1/users/me/profile', { method: 'GET', headers: { Authorization: `Bearer ${token}` } })
    if (profile.emailAddress?.toLowerCase() !== mailbox) throw new Error('Gmail token belongs to a different mailbox')
  }
  await renew()
  async function get(path) {
    if (Date.now() >= expiresAt) await renew()
    return requestJson(fetchImpl, `https://gmail.googleapis.com/gmail/v1/users/me/${path}`, { method: 'GET', headers: { Authorization: `Bearer ${token}` } })
  }
  return {
    mailbox,
    async poll(criteria, { timeoutMs = 120_000, intervalMs = 2000 } = {}) {
      validateCriteria(criteria)
      if (!Number.isFinite(timeoutMs) || timeoutMs <= 0 || timeoutMs > 300_000 || !Number.isFinite(intervalMs) || intervalMs < 100 || intervalMs > timeoutMs) throw new Error('Gmail polling bounds are invalid')
      const deadline = Date.now() + timeoutMs
      const query = new URLSearchParams({ q: `to:${criteria.recipient} after:${Math.floor(criteria.after / 1000)} before:${Math.ceil(criteria.before / 1000)}`, maxResults: '100' })
      do {
        const matches = []
        let pageToken
        do {
          if (Date.now() > deadline) throw new Error('Gmail delivery deadline exceeded')
          const params = new URLSearchParams(query)
          if (pageToken) params.set('pageToken', pageToken)
          const listing = await get(`messages?${params}`)
          for (const item of listing.messages || []) {
            if (Date.now() > deadline) throw new Error('Gmail delivery deadline exceeded')
            const delivered = extractMessage(await get(`messages/${encodeURIComponent(item.id)}?format=full`), criteria)
            if (delivered) matches.push(delivered)
          }
          pageToken = listing.nextPageToken
        } while (pageToken)
        if (matches.length > 1) throw new Error('Ambiguous matching Gmail messages')
        if (matches.length === 1) return matches[0]
        await sleep(Math.min(intervalMs, Math.max(0, deadline - Date.now())))
      } while (Date.now() < deadline)
      throw new Error('Gmail delivery deadline exceeded')
    },
  }
}
