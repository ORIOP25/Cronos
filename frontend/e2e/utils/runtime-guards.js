const ABORTED_ERROR = 'net::ERR_ABORTED'
const CSP_FALLBACK_NOTE = /^\s*Note that 'script-src' was not explicitly set, so 'default-src' is used as a fallback\.\s*$/
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
  return Boolean(parsedUrl && parsedBase && parsedUrl.origin === parsedBase.origin)
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

function isGoogleFontsUrl(parsedUrl) {
  return parsedUrl.hostname === 'fonts.googleapis.com'
    || parsedUrl.hostname === 'fonts.gstatic.com'
}

function isClerkHostedUrl(parsedUrl) {
  return parsedUrl.hostname.endsWith('.accounts.dev')
}

function isBenignAbortedRequest({ method, url }, { baseUrl }) {
  const parsedUrl = parseUrl(url, baseUrl)
  if (!parsedUrl) return false
  if (
    ['GET', 'HEAD'].includes(method.toUpperCase())
    && isSameOrigin(url, baseUrl)
    && (parsedUrl.pathname === '/' || hasAbortablePath(url, baseUrl))
  ) {
    return true
  }
  if (isGoogleFontsUrl(parsedUrl)) {
    return true
  }
  return ['GET', 'HEAD'].includes(method.toUpperCase())
    && isClerkHostedUrl(parsedUrl)
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

function isAllowedApiFailure(allowedFailures, { status, url = '' }) {
  return allowedFailures.some((allowed) => (
    allowed.status === status && allowedUrlMatches(allowed.url, url)
  ))
}

export function getRequestFailureError(requestFailure, { baseUrl }) {
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

  return `Network request failed: ${method} ${url} - ${errorText}`
}

function failedResourceStatus(text) {
  const match = normalizedText(text).match(
    /Failed to load resource:.*(?:status of|status code)\s+(\d{3})/i,
  )
  return match ? Number.parseInt(match[1], 10) : null
}

function isBenignGoogleFont404(status, url) {
  const parsedUrl = parseUrl(url, 'http://localhost')
  return status === 404 && parsedUrl?.hostname === 'fonts.gstatic.com'
}

export function getConsoleError(consoleMessage, allowedFailures) {
  if (consoleMessage.type !== 'error') return null

  const text = normalizedText(consoleMessage.text)
  if (CSP_FALLBACK_NOTE.test(text)) return null

  const status = failedResourceStatus(text)
  if (
    status !== null
    && (
      isBenignGoogleFont404(status, normalizedText(consoleMessage.locationUrl))
      || isAllowedApiFailure(allowedFailures, {
        status,
        url: normalizedText(consoleMessage.locationUrl),
      })
    )
  ) {
    return null
  }

  return `Browser console error: ${text} at ${normalizedText(consoleMessage.locationUrl)}`
}

export function getApiResponseError(response, allowedFailures) {
  const url = normalizedText(response.url)
  const status = Number(response.status)
  if (
    url.includes('/api/')
    && status >= 400
    && !isAllowedApiFailure(allowedFailures, { status, url })
  ) {
    return `API ${status}: ${url}`
  }
  return null
}
