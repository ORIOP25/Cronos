/* global process */
import { clerk } from '@clerk/testing/playwright'
import { expect } from '@playwright/test'

const BASE_URL = process.env.BASE_URL || 'http://localhost:5173'
const AUTH_FAILURE_STATUSES = new Set([401, 403])

function requiredEnv(name) {
  const value = process.env[name]
  if (!value) {
    throw new Error(`${name} is required for real Clerk E2E tests.`)
  }
  return value
}

function allowedApiFailures(page) {
  if (!page.__allowedApiFailures) {
    page.__allowedApiFailures = []
  }
  return page.__allowedApiFailures
}

function isAllowedApiFailure(page, response) {
  return allowedApiFailures(page).some((allowed) => {
    const statusMatches = allowed.status === response.status()
    const url = response.url()
    const urlMatches = allowed.url instanceof RegExp
      ? allowed.url.test(url)
      : url.includes(allowed.url)
    return statusMatches && urlMatches
  })
}

export function allowApiFailure(page, { status, url = '/api/' }) {
  allowedApiFailures(page).push({ status, url })
}

export function attachRuntimeGuards(page) {
  page.on('pageerror', (error) => {
    throw error
  })
  page.on('console', (message) => {
    if (message.type() === 'error') {
      throw new Error(`Browser console error: ${message.text()}`)
    }
  })
  page.on('requestfailed', (request) => {
    const url = request.url()
    if (url.startsWith('data:') || url.startsWith('blob:')) {
      return
    }
    throw new Error(`Network request failed: ${request.method()} ${url} - ${request.failure()?.errorText || 'unknown error'}`)
  })
  page.on('response', (response) => {
    const url = response.url()
    const status = response.status()
    if (
      url.includes('/api/')
      && (status >= 500 || AUTH_FAILURE_STATUSES.has(status))
      && !isAllowedApiFailure(page, response)
    ) {
      throw new Error(`API ${status}: ${url}`)
    }
  })
}

export async function loginAsAdminReal(page) {
  await page.goto(BASE_URL)
  await clerk.signIn({
    page,
    emailAddress: requiredEnv('E2E_CLERK_ADMIN_EMAIL'),
  })
}

export async function loginAsTeacherReal(page) {
  await page.goto(BASE_URL)
  await clerk.signIn({
    page,
    emailAddress: requiredEnv('E2E_CLERK_TEACHER_EMAIL'),
  })
}

export async function goTo(page, path) {
  await page.goto(`${BASE_URL}${path}`, { waitUntil: 'networkidle' })
}

export async function clickSidebarRoute(page, path) {
  const sidebarLink = page.locator('aside').locator(`a[href="${path}"]`).first()
  await expect(sidebarLink).toBeVisible({ timeout: 10000 })
  await sidebarLink.click()
  await expect(page).toHaveURL(new RegExp(`${path.replace('/', '\\/')}$`))
}

export async function expectText(page, text) {
  await expect(page.getByText(text).first()).toBeVisible({ timeout: 10000 })
}

export async function expectNoRuntimeFailure(page) {
  await expect(page.locator('[role="alert"]').filter({ hasText: /erro|error/i })).toHaveCount(0)
}

export async function expectApiOk(page, urlPattern) {
  return await page.waitForResponse(
    (res) => res.url().includes(urlPattern) && res.status() === 200,
    { timeout: 10000 }
  )
}
