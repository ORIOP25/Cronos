const ABORTED_ERROR = 'net::ERR_ABORTED'
const CSP_FALLBACK_NOTE = /^\s*Note that 'script-src' was not explicitly set, so 'default-src' is used as a fallback\.\s*$/
// W03.7: the Cloudflare Web Analytics beacon is an optional, non-essential
// third-party script. Production CSP deliberately blocks it. Only this exact
// host, path and a CSP script violation on an observed script GET are optional.
const OPTIONAL_TELEMETRY_REASON = 'csp-blocked-optional-telemetry'
const OPTIONAL_TELEMETRY_SCRIPT_HOST = 'static.cloudflareinsights.com'
// Documented real URL only: the beacon carries a lowercase-hex build version.
const OPTIONAL_TELEMETRY_SCRIPT_PATH = /^\/beacon\.min\.js\/v[0-9a-f]{16,128}$/
// Exact Chrome CSP script-block grammar, anchored end to end. The trailing
// "The action has been blocked." suffix rejects a valid prefix with appended
// first-party/application error text.
const CSP_SCRIPT_BLOCK_MESSAGE = /^(?:Loading the script|Refused to load the script) '([^']+)'(?: violates the following| because it violates the following) Content Security Policy directive: "[^"]*"\.(?: Note that '[^']+' was not explicitly set, so '[^']+' is used as a fallback\.)? The action has been blocked\.$/
const CSP_ERROR_TEXTS = new Set(['csp', 'net::ERR_BLOCKED_BY_CSP'])
const ABORTABLE_PATH_PREFIXES = [
  '/api/',
  '/src/',
  '/@vite',
  '/@react-refresh',
  '/node_modules/',
  '/assets/',
]
const ABORTABLE_FILE_EXTENSIONS = new Set([
  '.css',
  '.gif',
  '.ico',
  '.jpeg',
  '.jpg',
  '.js',
  '.jsx',
  '.json',
  '.map',
  '.png',
  '.svg',
  '.ts',
  '.tsx',
  '.webp',
])

function parseUrl(url, baseUrl) {
  try {
    return new URL(url, baseUrl)
  } catch {
    return null
  }
}

function isDataLikeUrl(url) {
  return url.startsWith('data:') || url.startsWith('blob:')
}

function isSameOrigin(url, baseUrl) {
  const parsedUrl = parseUrl(url, baseUrl)
  const parsedBase = parseUrl(baseUrl, baseUrl)
  return Boolean(parsedUrl?.origin && parsedUrl.origin === parsedBase?.origin)
}

function hasAbortablePath(url, baseUrl) {
  const parsedUrl = parseUrl(url, baseUrl)
  if (!parsedUrl) return false
  const pathname = parsedUrl.pathname
  if (ABORTABLE_PATH_PREFIXES.some((prefix) => pathname.startsWith(prefix))) {
    return true
  }
  const extension = pathname.includes('.')
    ? pathname.slice(pathname.lastIndexOf('.')).toLowerCase()
    : ''
  return ABORTABLE_FILE_EXTENSIONS.has(extension)
}

function isClerkHostedUrl(parsedUrl) {
  return parsedUrl.hostname.endsWith('.accounts.dev') || parsedUrl.hostname === 'clerk.cronos.pt'
}

function isRuntimeOrigin(url, baseUrl) {
  const parsed = parseUrl(url, baseUrl)
  return isSameOrigin(url, baseUrl) || parsed?.origin === 'https://api.cronos.pt'
    || (parsed?.protocol === 'https:' && isClerkHostedUrl(parsed))
}

function isTelemetry(url, baseUrl) {
  const parsed = parseUrl(url, baseUrl)
  return parsed?.protocol === 'https:' && /^o\d+\.ingest\.(?:us\.)?sentry\.io$/.test(parsed.hostname)
    && /^\/api\/\d+\/envelope\/$/.test(parsed.pathname)
}

// Exact HTTPS host, default port, no userinfo and a version-bounded beacon path.
export function isOptionalTelemetryScriptUrl(url) {
  const parsed = parseUrl(url)
  if (!parsed || parsed.protocol !== 'https:') return false
  if (parsed.username || parsed.password || parsed.port) return false
  if (parsed.hostname !== OPTIONAL_TELEMETRY_SCRIPT_HOST) return false
  return OPTIONAL_TELEMETRY_SCRIPT_PATH.test(parsed.pathname)
}

// The blocked URL is quoted in the CSP console message. It must match the same
// request URL the observer already recorded as an actual script GET.
export function optionalTelemetryScriptFromConsoleText(text) {
  const match = CSP_SCRIPT_BLOCK_MESSAGE.exec(normalizedText(text))
  return match ? match[1] : null
}

// Safe signed-artifact snapshot: method, host, path and reason only. Never the
// full query, a token, a response body or the raw console/network text.
function optionalTelemetryDiagnostic(url, event) {
  const parsed = parseUrl(url)
  return {
    method: 'GET',
    host: parsed?.hostname ?? '',
    path: parsed?.pathname ?? '',
    reason: OPTIONAL_TELEMETRY_REASON,
    event,
  }
}

function isOptionalTelemetryScriptFailure(requestFailure, observedOptionalTelemetry) {
  if (!observedOptionalTelemetry?.has(normalizedText(requestFailure.url))) return false
  if (normalizedText(requestFailure.method || 'GET').toUpperCase() !== 'GET') return false
  if (normalizedText(requestFailure.resourceType) !== 'script') return false
  if (!CSP_ERROR_TEXTS.has(normalizedText(requestFailure.errorText))) return false
  return isOptionalTelemetryScriptUrl(requestFailure.url)
}

// A genuinely served beacon response is never an optional exemption. A 4xx/5xx
// must fail closed even when the browser emits no console message. Report the
// safe host, path and status only; never the full query or a response body.
export function getOptionalTelemetryResponseError({ url, status }, observedOptionalTelemetry) {
  if (!observedOptionalTelemetry?.has(url)) return null
  const parsed = parseUrl(url)
  if (!parsed || !isOptionalTelemetryScriptUrl(url)) return null
  if (!Number.isInteger(status) || status < 400) return null
  return `Optional telemetry beacon failed: ${status} ${parsed.hostname}${parsed.pathname}`
}

function isClerkImageUrl(parsedUrl) {
  return parsedUrl.hostname === 'img.clerk.com'
}

function isBenignAbortedRequest({ method, url }, { baseUrl }) {
  const parsedUrl = parseUrl(url, baseUrl)
  if (!parsedUrl) return false
  if (
    ['GET', 'HEAD'].includes(method.toUpperCase())
    && isSameOrigin(url, baseUrl)
    && (
      parsedUrl.pathname === '/'
      || hasAbortablePath(url, baseUrl)
      || parsedUrl.searchParams.has('__clerk_db_jwt')
    )
  ) {
    return true
  }
  if (method.toUpperCase() === 'GET' && isClerkImageUrl(parsedUrl)) {
    return true
  }
  // Clerk can cancel maintenance POSTs (for example sessions/*/touch) when
  // a test navigates or closes a context. This is the same benign abort as
  // its cancelled GETs; real Clerk network errors still surface below.
  return isClerkHostedUrl(parsedUrl) && (
    method.toUpperCase() === 'GET'
    || (method.toUpperCase() === 'POST' && /^\/v1\/client\/sessions\/[^/]+\/touch$/.test(parsedUrl.pathname))
  )
}

function normalizedText(value) {
  return String(value || '')
}

function allowedUrlMatches(allowedUrl, url) {
  if (!url) return true
  if (allowedUrl instanceof RegExp) {
    return allowedUrl.test(url)
  }
  return url.includes(String(allowedUrl))
}

function isAllowedApiFailure(allowedFailures, { status, url = '', method }, { baseUrl, action } = {}) {
  if (baseUrl === 'https://cronos.pt') {
    const parsed = parseUrl(url, baseUrl)
    return status < 500 && Boolean(method && action && parsed) && allowedFailures.some(allowed => (
      allowed.status === status && allowed.origin === parsed.origin && allowed.pathname === parsed.pathname
      && allowed.method === method && allowed.action === action
    ))
  }
  return allowedFailures.some((allowed) => (
    allowed.status === status && allowedUrlMatches(allowed.url, url)
  ))
}

export function getRequestFailureError(requestFailure, { baseUrl, observedOptionalTelemetry, onIgnoredOptionalTelemetry } = {}) {
  const url = normalizedText(requestFailure.url)
  if (isDataLikeUrl(url)) return null

  const method = normalizedText(requestFailure.method || 'GET')
  const errorText = normalizedText(requestFailure.errorText || 'unknown error')
  if (
    errorText.includes(ABORTED_ERROR)
    && isBenignAbortedRequest({ method, url }, { baseUrl })
  ) {
    return null
  }

  if (isOptionalTelemetryScriptFailure({
    url, method, resourceType: requestFailure.resourceType, errorText,
  }, observedOptionalTelemetry)) {
    onIgnoredOptionalTelemetry?.(optionalTelemetryDiagnostic(url, 'requestfailed'))
    return null
  }

  return `Network request failed: ${method} ${url} - ${errorText}`
}

function failedResourceStatus(text) {
  const failedResourcePattern = /Failed to load resource:.*(?:status of|status code)\s+(\d{3})/i
  const match = failedResourcePattern.exec(normalizedText(text))
  return match ? Number.parseInt(match[1], 10) : null
}

export function getConsoleError(consoleMessage, allowedFailures, { baseUrl, action, observedOptionalTelemetry, onIgnoredOptionalTelemetry } = {}) {
  if (consoleMessage.type !== 'error') return null

  const text = normalizedText(consoleMessage.text)
  if (CSP_FALLBACK_NOTE.test(text)) return null

  const optionalScriptUrl = optionalTelemetryScriptFromConsoleText(text)
  if (
    optionalScriptUrl
    && isOptionalTelemetryScriptUrl(optionalScriptUrl)
    && observedOptionalTelemetry?.has(optionalScriptUrl)
  ) {
    onIgnoredOptionalTelemetry?.(optionalTelemetryDiagnostic(optionalScriptUrl, 'console'))
    return null
  }

  const status = failedResourceStatus(text)
  if (status !== null) {
    const locationUrl = normalizedText(consoleMessage.locationUrl)
    if (baseUrl && isTelemetry(locationUrl, baseUrl)) return null
    if (isAllowedApiFailure(allowedFailures, { status, url: locationUrl, method: consoleMessage.method }, { baseUrl, action })) {
      return null
    }
  }

  return `Browser console error: ${text} at ${normalizedText(consoleMessage.locationUrl)}`
}

export function getApiResponseError(response, allowedFailures, { baseUrl, action } = {}) {
  const url = normalizedText(response.url)
  const status = Number(response.status)
  if (baseUrl && !isRuntimeOrigin(url, baseUrl)) return null
  if (
    (url.includes('/api/') || isClerkHostedUrl(parseUrl(url, baseUrl) || { hostname: '' }))
    && status >= 400
    && !isAllowedApiFailure(allowedFailures, { status, url, method: response.method }, { baseUrl, action })
  ) {
    return `API ${status}: ${url}`
  }
  return null
}
