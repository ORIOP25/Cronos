import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createGmailReader, isDedicatedRecipient } from '../frontend/e2e/utils/gmail.js'

const MAILBOXES = { admin: 'admincronos100@gmail.com', teacher: 'professorcronos100@gmail.com' }
const PURPOSES = new Set(['verification', 'reset'])
const DEFAULT_WINDOW_MS = 7 * 24 * 60 * 60 * 1000
const MAX_WINDOW_MS = 30 * 24 * 60 * 60 * 1000

// Compose the bounded, dedicated inspection from the operator environment.
// Credentials stay local to the caller and are never written to the result.
export function inspectionConfig(environment, now = Date.now()) {
  const role = environment.E2E_INSPECT_MAILBOX || 'admin'
  if (!Object.hasOwn(MAILBOXES, role)) return { status: 'failed', reason: 'invalid_mailbox' }
  const purpose = environment.E2E_INSPECT_PURPOSE || 'verification'
  if (!PURPOSES.has(purpose)) return { status: 'failed', reason: 'invalid_purpose' }
  const mailbox = MAILBOXES[role]
  const recipient = String(environment.E2E_INSPECT_RECIPIENT || mailbox).toLowerCase()
  if (!isDedicatedRecipient(mailbox, recipient)) return { status: 'failed', reason: 'invalid_recipient' }
  // The workflow materializes only the selected mailbox token into the generic
  // variable. The role-specific variable remains a local compatibility fallback.
  const credentials = {
    clientId: environment.E2E_GMAIL_CLIENT_ID,
    clientSecret: environment.E2E_GMAIL_CLIENT_SECRET,
    refreshToken: environment.E2E_GMAIL_REFRESH_TOKEN || environment[`E2E_GMAIL_${role.toUpperCase()}_REFRESH_TOKEN`],
    mailbox,
  }
  if (!credentials.clientId || !credentials.clientSecret || !credentials.refreshToken) {
    return { status: 'dependency_unavailable', reason: 'missing_credentials' }
  }
  const before = environment.E2E_INSPECT_BEFORE ? Date.parse(environment.E2E_INSPECT_BEFORE) : now
  const after = environment.E2E_INSPECT_AFTER ? Date.parse(environment.E2E_INSPECT_AFTER) : before - DEFAULT_WINDOW_MS
  if (!Number.isSafeInteger(after) || !Number.isSafeInteger(before) || before <= after) return { status: 'failed', reason: 'invalid_window' }
  const span = before - after
  if (span > MAX_WINDOW_MS) return { status: 'failed', reason: 'window_exceeds_limit' }
  if (span > DEFAULT_WINDOW_MS && !String(environment.E2E_INSPECT_WINDOW_REASON || '').trim()) {
    return { status: 'failed', reason: 'window_reason_required' }
  }
  return { role, purpose, mailbox, recipient, credentials, after, before }
}

export async function inspectCodeSender(config, { fetchImpl = fetch, maxPages, deadlineMs } = {}) {
  const reader = await createGmailReader(config.credentials, { fetchImpl })
  const discovered = await reader.discoverSender(
    { recipient: config.recipient, purpose: config.purpose, after: config.after, before: config.before },
    { ...(maxPages === undefined ? {} : { maxPages }), ...(deadlineMs === undefined ? {} : { deadlineMs }) },
  )
  return {
    status: discovered.status,
    reason: discovered.reason,
    certifies_production: false,
    mailbox: config.role,
    purpose: config.purpose,
    senders: discovered.senders,
    sender_count: discovered.senders.length,
    message_count: discovered.message_count,
    window: { after: new Date(config.after).toISOString(), before: new Date(config.before).toISOString() },
  }
}

const SAFE_OPERATIONS = new Set(['oauth_refresh', 'mailbox_profile', 'message_listing', 'message_metadata'])
const SAFE_CODES = new Set([
  'invalid_grant', 'invalid_client', 'unauthorized_client', 'access_denied',
  'invalid_readonly_scope', 'mailbox_mismatch', 'http_error', 'network_error', 'invalid_json',
])
const SAFE_REASONS = new Set(['oauth_error', 'http', 'network', 'invalid_json', 'scope_mismatch', 'profile_mismatch'])
const SAFE_CONTENT_TYPES = new Set(['json', 'html', 'text', 'other', 'missing'])

// Keep only known enums and a bounded status. An unknown error never exposes
// its message, body, scopes, URLs or identifiers.
function safeDiagnostic(error) {
  const httpStatus = Number.isInteger(error?.httpStatus) && error.httpStatus >= 100 && error.httpStatus <= 599 ? error.httpStatus : null
  const diagnostic = {
    operation: SAFE_OPERATIONS.has(error?.operation) ? error.operation : null,
    code: SAFE_CODES.has(error?.code) ? error.code : 'unknown_error',
    http_status: httpStatus,
    reason: SAFE_REASONS.has(error?.reason) ? error.reason : null,
  }
  if (error?.code === 'invalid_json' && error.bodyBytes !== undefined) {
    diagnostic.body_bytes = Number.isSafeInteger(error.bodyBytes) && error.bodyBytes >= 0 ? error.bodyBytes : null
    diagnostic.empty_body = typeof error.emptyBody === 'boolean' ? error.emptyBody : null
    diagnostic.content_type = SAFE_CONTENT_TYPES.has(error.contentType) ? error.contentType : 'missing'
  }
  return diagnostic
}

// A safe, secret-free result. Provider and credential failures collapse to a
// fixed status with a structured, enum-only diagnostic.
export async function runInspection(environment, options = {}) {
  const base = { certifies_production: false }
  const config = inspectionConfig(environment, options.now)
  if (config.status) return { ...base, status: config.status, reason: config.reason }
  try {
    return await inspectCodeSender(config, options)
  } catch (error) {
    return { ...base, status: 'dependency_unavailable', reason: 'gmail_unavailable', mailbox: config.role, purpose: config.purpose, diagnostic: safeDiagnostic(error) }
  }
}

export function inspectionExitCode(status) {
  if (status === 'observed') return 0
  if (status === 'dependency_unavailable') return 3
  return 1
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const result = await runInspection(process.env)
  // One JSON record per invocation on a single line. Any control newline that
  // could forge a log line is removed before the sink.
  process.stdout.write(`${JSON.stringify(result).replace(/[\r\n]/g, '')}\n`)
  process.exitCode = inspectionExitCode(result.status)
}
