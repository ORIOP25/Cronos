// @vitest-environment node
import { describe, expect, it } from 'vitest'
import {
  getApiResponseError,
  getConsoleError,
  getOptionalTelemetryResponseError,
  getRequestFailureError,
  isOptionalTelemetryScriptUrl,
  optionalTelemetryScriptFromConsoleText,
} from '../../e2e/utils/runtime-guards.js'

const baseUrl = 'http://localhost:5173'
const BEACON_URL = 'https://static.cloudflareinsights.com/beacon.min.js/v4bc70e2c01a94c73b74392e4234840661791215815920'
const BEACON_PATH = '/beacon.min.js/v4bc70e2c01a94c73b74392e4234840661791215815920'
const cspConsole = url => ({
  type: 'error',
  text: `Loading the script '${url}' violates the following Content Security Policy directive: "script-src 'self'". The action has been blocked.`,
  locationUrl: 'https://cronos.pt/contacto',
})

describe('E2E runtime guard classifiers', () => {
  it.each([
    ['app root navigation', `${baseUrl}/`],
    ['API request', `${baseUrl}/api/v1/members/me`],
    ['Vite module', `${baseUrl}/src/pages/Dashboard.jsx?t=123`],
    ['lazy component', `${baseUrl}/src/components/dashboard/ScheduleHealthCard.jsx?t=123`],
    ['static asset', `${baseUrl}/logo.png`],
  ])('ignores same-origin browser-cancelled %s during navigation', (_label, url) => {
    expect(getRequestFailureError({
      method: 'GET',
      url,
      errorText: 'net::ERR_ABORTED',
    }, { baseUrl })).toBeNull()
  })

  it.each([
    ['Clerk browser bundle', 'https://welcome-cat-83.clerk.accounts.dev/npm/@clerk/clerk-js@5/dist/clerk.browser.js'],
    ['Clerk organization memberships read', 'https://welcomed-cat-83.clerk.accounts.dev/v1/me/organization_memberships?limit=10'],
    ['Clerk hosted sign-in navigation', 'https://welcomed-cat-83.accounts.dev/sign-in?__clerk_db_jwt=test-token'],
    ['Clerk image asset', 'https://img.clerk.com/eyJ0eXBlIjoicHJveHkiLCJzcmMiOiJodHRwczovL2ltYWdlcy5jbGVyay5kZXYvdXBsb2FkZWQvaW1nXzF9?width=200'],
  ])('ignores benign external browser-cancelled %s', (_label, url) => {
    expect(getRequestFailureError({
      method: 'GET',
      url,
      errorText: 'net::ERR_ABORTED',
    }, { baseUrl })).toBeNull()
  })

  it('ignores a Clerk development CDN UI chunk blocked by ORB', () => {
    expect(getRequestFailureError({
      method: 'GET',
      url: 'https://welcomed-cat-83.clerk.accounts.dev/npm/@clerk/ui@1.40.0/dist/3736_ui_96623b_1.40.0.js',
      errorText: 'net::ERR_BLOCKED_BY_ORB',
    }, { baseUrl })).toBeNull()
  })

  it.each([
    ['an application asset', 'http://localhost:5173/assets/index.js'],
    ['a Clerk API read', 'https://welcomed-cat-83.clerk.accounts.dev/v1/client'],
  ])('still fails %s blocked by ORB', (_label, url) => {
    expect(getRequestFailureError({
      method: 'GET',
      url,
      errorText: 'net::ERR_BLOCKED_BY_ORB',
    }, { baseUrl })).toContain('Network request failed')
  })

  it('fails an aborted Clerk organization write because its outcome is unknown', () => {
    expect(getRequestFailureError({
      method: 'POST',
      url: 'https://welcomed-cat-83.accounts.dev/v1/organizations',
      errorText: 'net::ERR_ABORTED',
    }, { baseUrl })).toContain('Network request failed')
  })

  it.each(['https://api.cronos.pt/api/v1/members', 'https://clerk.cronos.pt/v1/client'])('observes production API and authentication outside the frontend origin: %s', url => {
    expect(getApiResponseError({ status: 500, url }, [], { baseUrl: 'https://cronos.pt' })).toContain('500')
    expect(getConsoleError({ type: 'error', text: 'Failed to load resource: status of 500', locationUrl: url }, [], { baseUrl: 'https://cronos.pt' })).toContain('500')
  })

  it('only ignores explicitly classified telemetry, not an unknown external console failure', () => {
    expect(getConsoleError({ type: 'error', text: 'Failed to load resource: status of 500', locationUrl: 'https://unknown.test/api/a' }, [], { baseUrl })).toContain('500')
  })

  it('production exceptions require exact origin, method, path, status and current action', () => {
    const response = { status: 403, method: 'GET', url: 'https://api.cronos.pt/api/v1/members' }
    const allowed = [{ status: 403, method: 'GET', origin: 'https://api.cronos.pt', pathname: '/api/v1/members', action: 'teacher-denied' }]
    const options = { baseUrl: 'https://cronos.pt', action: 'teacher-denied' }
    expect(getApiResponseError(response, allowed, options)).toBeNull()
    for (const changed of [
      { ...response, method: 'DELETE' }, { ...response, status: 500 },
      { ...response, url: 'https://api.cronos.pt/api/v1/members/17' },
      { ...response, url: 'https://clerk.cronos.pt/api/v1/members' },
    ]) expect(getApiResponseError(changed, allowed, options)).not.toBeNull()
    expect(getApiResponseError(response, allowed, { ...options, action: 'import' })).not.toBeNull()
    expect(getApiResponseError(response, [{ status: 403, url: '/api/v1/members' }], options)).not.toBeNull()
    expect(getConsoleError({ type: 'error', text: 'Failed to load resource: status of 403', locationUrl: response.url }, allowed, options)).not.toBeNull()
    expect(getConsoleError({ type: 'error', text: 'Failed to load resource: status of 403', locationUrl: response.url, method: 'GET' }, allowed, options)).toBeNull()
  })

  it.each([
    ['connection refused', `${baseUrl}/api/v1/dashboard`, 'net::ERR_CONNECTION_REFUSED'],
    ['DNS failure', 'https://missing.invalid/api/v1/dashboard', 'net::ERR_NAME_NOT_RESOLVED'],
    ['SSL failure', 'https://example.test/api/v1/dashboard', 'net::ERR_CERT_AUTHORITY_INVALID'],
    ['aborted third-party script', 'https://cdn.example.test/widget.js', 'net::ERR_ABORTED'],
  ])('still fails real network errors: %s', (_label, url, errorText) => {
    expect(getRequestFailureError({
      method: 'GET',
      url,
      errorText,
    }, { baseUrl })).toContain(errorText)
  })

  it('ignores failed-resource console noise for an explicitly allowed API failure', () => {
    const error = getConsoleError({
      type: 'error',
      text: 'Failed to load resource: the server responded with a status of 403 (Forbidden)',
      locationUrl: `${baseUrl}/api/v1/members`,
    }, [{ status: 403, url: '/api/v1/members' }])

    expect(error).toBeNull()
  })

  it('allows Clerk organization detail settling during foundation onboarding', () => {
    const error = getConsoleError({
      type: 'error',
      text: 'Failed to load resource: the server responded with a status of 403 (Forbidden)',
      locationUrl: 'https://welcomed-cat-83.clerk.accounts.dev/v1/organizations?session=test',
    }, [
      { status: 403, url: /\.clerk\.accounts\.dev\/v1\/organizations(?:\?|$)/ },
    ])

    expect(error).toBeNull()
  })

  it('keeps unexpected asset failures visible', () => {
    const font404 = getConsoleError({
      type: 'error',
      text: 'Failed to load resource: the server responded with a status of 404 ()',
      locationUrl: 'https://cdn.example.test/font.woff2',
    }, [])
    const font500 = getConsoleError({
      type: 'error',
      text: 'Failed to load resource: the server responded with a status of 500 ()',
      locationUrl: 'https://cdn.example.test/font.woff2',
    }, [])
    const other404 = getConsoleError({
      type: 'error',
      text: 'Failed to load resource: the server responded with a status of 404 ()',
      locationUrl: 'https://cdn.example.test/font.woff2',
    }, [])

    expect(font404).toContain('Browser console error')
    expect(font500).toContain('Browser console error')
    expect(other404).toContain('Browser console error')
  })

  it('keeps throwing for unexpected browser console errors', () => {
    const error = getConsoleError({
      type: 'error',
      text: 'Uncaught TypeError: cannot read properties of undefined',
      locationUrl: `${baseUrl}/src/pages/Dashboard.jsx`,
    }, [])

    expect(error).toContain('Browser console error')
  })

  it('includes the location URL when throwing an unexpected failed-resource console error', () => {
    const error = getConsoleError({
      type: 'error',
      text: 'Failed to load resource: the server responded with a status of 403 (Forbidden)',
      locationUrl: `${baseUrl}/api/v1/members`,
    }, [])

    expect(error).toContain('Browser console error: Failed to load resource: the server responded with a status of 403 (Forbidden) at http://localhost:5173/api/v1/members')
  })

  it('ignores the browser CSP fallback note emitted by Clerk hosted sign-in', () => {
    const error = getConsoleError({
      type: 'error',
      text: " Note that 'script-src' was not explicitly set, so 'default-src' is used as a fallback.",
      locationUrl: '',
    }, [])

    expect(error).toBeNull()
  })

  it('ignores allowed API auth failures and fails unexpected API failures', () => {
    expect(getApiResponseError({
      status: 403,
      url: `${baseUrl}/api/v1/members`,
    }, [{ status: 403, url: '/api/v1/members' }])).toBeNull()

    expect(getApiResponseError({
      status: 500,
      url: `${baseUrl}/api/v1/dashboard`,
    }, [])).toBe(`API 500: ${baseUrl}/api/v1/dashboard`)
  })

  it('fails an unexpected API 404 unless it is explicitly allowlisted', () => {
    const response = {
      status: 404,
      url: `${baseUrl}/api/v1/schedule/active-blocks/42/log`,
    }

    expect(getApiResponseError(response, [])).toBe(
      `API 404: ${baseUrl}/api/v1/schedule/active-blocks/42/log`,
    )
    expect(getApiResponseError(response, [{
      status: 404,
      url: '/api/v1/schedule/active-blocks/',
    }])).toBeNull()
  })

  it('ignores external telemetry failures when the base URL is provided', () => {
    const sentryUrl = 'https://o449981.ingest.us.sentry.io/api/4508852298842113/envelope/'

    expect(getApiResponseError(
      { status: 429, url: sentryUrl },
      [],
      { baseUrl },
    )).toBeNull()

    expect(getConsoleError({
      type: 'error',
      text: 'Failed to load resource: the server responded with a status of 429 ()',
      locationUrl: sentryUrl,
    }, [], { baseUrl })).toBeNull()
  })

  it('classifies only the exact observed Cloudflare beacon CSP block as optional', () => {
    const observed = new Set([BEACON_URL])
    const ignored = []
    const options = {
      baseUrl: 'https://cronos.pt',
      observedOptionalTelemetry: observed,
      onIgnoredOptionalTelemetry: event => ignored.push(event),
    }

    expect(getConsoleError(cspConsole(BEACON_URL), [], options)).toBeNull()
    expect(getRequestFailureError({
      url: BEACON_URL, method: 'GET', resourceType: 'script', errorText: 'csp',
    }, options)).toBeNull()
    expect(ignored).toEqual([
      { method: 'GET', host: 'static.cloudflareinsights.com', path: BEACON_PATH, reason: 'csp-blocked-optional-telemetry', event: 'console' },
      { method: 'GET', host: 'static.cloudflareinsights.com', path: BEACON_PATH, reason: 'csp-blocked-optional-telemetry', event: 'requestfailed' },
    ])
  })

  it('keeps an unobserved, malformed or non-CSP beacon failure', () => {
    expect(getConsoleError(cspConsole(BEACON_URL), [], { baseUrl: 'https://cronos.pt' })).toContain('Browser console error')
    expect(getRequestFailureError({
      url: BEACON_URL, method: 'GET', resourceType: 'script', errorText: 'csp',
    }, { baseUrl: 'https://cronos.pt' })).toContain('Network request failed')

    const observed = new Set([BEACON_URL])
    const options = { baseUrl: 'https://cronos.pt', observedOptionalTelemetry: observed }
    expect(getRequestFailureError({
      url: BEACON_URL, method: 'GET', resourceType: 'script', errorText: 'net::ERR_FAILED',
    }, options)).toContain('Network request failed')
    expect(getRequestFailureError({
      url: BEACON_URL, method: 'GET', resourceType: 'fetch', errorText: 'csp',
    }, options)).toContain('Network request failed')
    expect(getConsoleError({
      type: 'error', text: 'Failed to load resource: status of 500', locationUrl: BEACON_URL,
    }, [], options)).toContain('Browser console error')

    for (const url of [
      'https://static.cloudflareinsights.com.evil.test/beacon.min.js/v4bc70e2c01a94c73b74392e4234840661791215815920',
      'https://user:pass@static.cloudflareinsights.com/beacon.min.js/v4bc70e2c01a94c73b74392e4234840661791215815920',
      'https://static.cloudflareinsights.com:8443/beacon.min.js/v4bc70e2c01a94c73b74392e4234840661791215815920',
      'http://static.cloudflareinsights.com/beacon.min.js/v4bc70e2c01a94c73b74392e4234840661791215815920',
      'https://static.cloudflareinsights.com/other.js/v4bc70e2c01a94c73b74392e4234840661791215815920',
      'https://static.cloudflareinsights.com/beacon.min.js/vshort',
      'https://static.cloudflareinsights.com/beacon.min.js/4bc70e2c01a94c73b74392e4234840661791215815920',
      'https://static.cloudflareinsights.com/beacon.min.js/v4bc70e2c01a94c73b74392e423484066179121581Z0',
    ]) {
      expect(isOptionalTelemetryScriptUrl(url)).toBe(false)
    }
  })

  it('accepts the Chrome fallback-note variant but rejects appended error text', () => {
    const observed = new Set([BEACON_URL])
    const options = { baseUrl: 'https://cronos.pt', observedOptionalTelemetry: observed }
    const fallback = {
      type: 'error',
      text: `Loading the script '${BEACON_URL}' violates the following Content Security Policy directive: "script-src 'self'". Note that 'script-src-elem' was not explicitly set, so 'script-src' is used as a fallback. The action has been blocked.`,
      locationUrl: 'https://cronos.pt/contacto',
    }
    expect(getConsoleError(fallback, [], options)).toBeNull()
    expect(getConsoleError({
      type: 'error', text: `${fallback.text} Unauthorized`, locationUrl: 'https://cronos.pt/contacto',
    }, [], options)).toContain('Browser console error')
  })

  it('extracts the quoted CSP script URL from the console message only', () => {
    expect(optionalTelemetryScriptFromConsoleText(cspConsole(BEACON_URL).text)).toBe(BEACON_URL)
    expect(optionalTelemetryScriptFromConsoleText('Uncaught TypeError: boom')).toBeNull()
  })

  it('matches the exact Chrome message recorded on production run 37935721500', () => {
    const text = `Loading the script '${BEACON_URL}' violates the following Content Security Policy directive: "script-src 'self' https://clerk.cronos.pt https://challenges.cloudflare.com https://*.protect.clerk.com". Note that 'script-src-elem' was not explicitly set, so 'script-src' is used as a fallback. The action has been blocked.`
    expect(optionalTelemetryScriptFromConsoleText(text)).toBe(BEACON_URL)
  })

  it('reports a served beacon 4xx/5xx as a fail-closed error without a console message', () => {
    const observed = new Set([BEACON_URL])
    expect(getOptionalTelemetryResponseError({ url: BEACON_URL, status: 500 }, observed))
      .toBe(`Optional telemetry beacon failed: 500 static.cloudflareinsights.com${BEACON_PATH}`)
    expect(getOptionalTelemetryResponseError({ url: BEACON_URL, status: 404 }, observed)).toContain('404')
    expect(getOptionalTelemetryResponseError({ url: BEACON_URL, status: 200 }, observed)).toBeNull()
    expect(getOptionalTelemetryResponseError({ url: BEACON_URL, status: 500 }, new Set())).toBeNull()
    const apiUrl = 'https://api.cronos.pt/api/v1/rooms'
    expect(getOptionalTelemetryResponseError({ url: apiUrl, status: 500 }, new Set([apiUrl]))).toBeNull()
  })
})
