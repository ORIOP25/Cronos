import { describe, expect, it } from 'vitest'
import {
  getApiResponseError,
  getConsoleError,
  getRequestFailureError,
} from '../../e2e/utils/runtime-guards.js'

const baseUrl = 'http://localhost:5173'

describe('E2E runtime guard classifiers', () => {
  it.each([
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
    ['Google Fonts stylesheet', 'https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap'],
    ['Google Fonts file', 'https://fonts.gstatic.com/s/inter/v18/UcCO3FwrK3iLTcviYwYZ8UA3.woff2'],
    ['Clerk browser bundle', 'https://welcome-cat-83.clerk.accounts.dev/npm/@clerk/clerk-js@5/dist/clerk.browser.js'],
  ])('ignores benign external browser-cancelled %s', (_label, url) => {
    expect(getRequestFailureError({
      method: 'GET',
      url,
      errorText: 'net::ERR_ABORTED',
    }, { baseUrl })).toBeNull()
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

  it('keeps throwing for unexpected browser console errors', () => {
    const error = getConsoleError({
      type: 'error',
      text: 'Uncaught TypeError: cannot read properties of undefined',
      locationUrl: `${baseUrl}/src/pages/Dashboard.jsx`,
    }, [])

    expect(error).toContain('Browser console error')
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
})
