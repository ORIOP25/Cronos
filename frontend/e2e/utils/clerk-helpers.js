import { clerk, setupClerkTestingToken } from '@clerk/testing/playwright'
import { expect } from '@playwright/test'
import {
  getApiResponseError,
  getConsoleError,
  getRequestFailureError,
} from './runtime-guards.js'
import { observeClerkSignIn } from './clerk-rate-limit.js'
import { E2E_BASE_URL } from './e2e-config.js'

export const CLERK_LEGAL_UNSAFE_METADATA = Object.freeze({
  cronos_legal_versions: Object.freeze({
    terms_version: '2026-01',
    dpa_version: '2026-01',
    privacy_version: '2026-01',
  }),
})

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

function runtimeApiFailures(page) {
  const failures = allowedApiFailures(page)
  let pathname = ''
  try {
    pathname = new URL(page.url()).pathname
  } catch {
    pathname = ''
  }
  // A new Clerk organization can briefly return 403 for /members/me until the
  // background bootstrap creates the local member. The hosted organization
  // list can also return 403 while Clerk settles a testing session; it is a
  // background read and does not block the active organization or Cronos API.
  // The route gate owns the local transition; all other API failures remain
  // fatal in E2E.
  const allowed = [{
    status: 403,
    url: /\.clerk\.accounts\.dev\/v1\/organizations(?:\?|$)/,
  }]
  if (pathname !== '/foundation') return [...failures, ...allowed]
  return [
    ...failures,
    ...allowed,
    { status: 403, url: '/api/v1/members/me' },
  ]
}

export function allowApiFailure(page, { status, url = '/api/' }) {
  allowedApiFailures(page).push({ status, url })
}

export function attachRuntimeGuards(page) {
  page.on('pageerror', (error) => {
    throw error
  })
  page.on('console', (message) => {
    const error = getConsoleError({
      type: message.type(),
      text: message.text(),
      locationUrl: message.location()?.url,
    }, runtimeApiFailures(page), { baseUrl: E2E_BASE_URL })
    if (error) {
      throw new Error(error)
    }
  })
  page.on('requestfailed', (request) => {
    const error = getRequestFailureError({
      method: request.method(),
      url: request.url(),
      errorText: request.failure()?.errorText,
    }, { baseUrl: E2E_BASE_URL })
    if (error) {
      throw new Error(error)
    }
  })
  page.on('response', (response) => {
    const error = getApiResponseError({
      url: response.url(),
      status: response.status(),
    }, runtimeApiFailures(page), { baseUrl: E2E_BASE_URL })
    if (error) {
      throw new Error(error)
    }
  })
}

async function loginReal(page, emailEnvironmentVariable) {
  const emailAddress = requiredEnv(emailEnvironmentVariable)
  const organizationId = process.env.E2E_CLERK_ORG_ID
  await expect.poll(
    () => observeClerkSignIn(async () => {
      await setupClerkTestingToken({ page })
      // This public route stays public for signed-in users while the test selects its organization.
      await page.goto(`${E2E_BASE_URL}/privacidade`)
      await page.waitForFunction(() => window.Clerk?.loaded)
      const active = await page.evaluate(() => ({
        email: window.Clerk?.user?.primaryEmailAddress?.emailAddress,
        organizationId: window.Clerk?.organization?.id,
      }))
      if (active.email !== emailAddress) {
        await clerk.signIn({ page, emailAddress })
        await page.waitForFunction(
          (email) => window.Clerk?.loaded && window.Clerk?.session
            && window.Clerk?.user?.primaryEmailAddress?.emailAddress === email,
          emailAddress,
        )
      }
      if (organizationId && (active.email !== emailAddress || active.organizationId !== organizationId)) {
        await page.evaluate(async (id) => {
          await window.Clerk.setActive({ organization: id })
        }, organizationId)
        await page.waitForFunction(
          (id) => window.Clerk?.organization?.id === id,
          organizationId,
        )
      }
    }),
    {
      message: `Clerk sign-in should succeed for ${emailEnvironmentVariable}`,
      intervals: [5_000, 10_000],
      timeout: 30_000,
    },
  ).toBe(true)
}

export async function loginAsAdminReal(page) {
  await loginReal(page, 'E2E_CLERK_ADMIN_EMAIL')
  await page.goto(`${E2E_BASE_URL}/dashboard`, { waitUntil: 'domcontentloaded' })
}

export async function loginAsTeacherReal(page) {
  await loginReal(page, 'E2E_CLERK_TEACHER_EMAIL')
}

export async function goTo(page, path) {
  await setupClerkTestingToken({ page })
  await page.goto(`${E2E_BASE_URL}${path}`, { waitUntil: 'domcontentloaded' })
  await expectNoAppCrash(page)
}

export async function expectFoundationReady(page) {
  await expect(page).toHaveURL(/\/foundation(?:[/?#]|$)/, { timeout: 30_000 })
  await expect(page.locator('#school_start_date')).toBeVisible({ timeout: 30_000 })
}

export async function clickSidebarRoute(page, path) {
  const sidebarLink = page.locator('aside').locator(`a[href="${path}"]`).first()
  await expect(sidebarLink).toBeVisible({ timeout: 10000 })
  await sidebarLink.click()
  await expectRouteReady(page, path)
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function readyMarker(page, path) {
  if (path === '/dashboard') {
    return page.locator('[data-testid="preparation-dashboard"], [data-testid="resource-counts"]').first()
  }
  const exactMarkers = new Map([
    ['/members', /Equipa/i],
    ['/courses', /Cursos/i],
    ['/rooms', /Salas/i],
    ['/subjects', /Disciplinas/i],
    ['/config', /Configuração/i],
    ['/schedules', /Horarios escolares|Horários escolares/i],
    ['/absences', /Faltas e\s+Ocorrencias|Faltas e\s+Ocorrências/i],
    ['/timesheets', /Fecho\s+Semanal/i],
    ['/my-availability', /Minha\s+Disponibilidade/i],
    ['/my-schedules', /Meus\s+Horarios|Meus\s+Horários/i],
    ['/my-progress', /Meu\s+Progresso/i],
  ])
  const heading = exactMarkers.get(path)
  if (!heading) return null
  if (path === '/config') {
    return page.locator('.page-header__pretitle', { hasText: heading }).first()
  }
  return page.getByRole('heading', { name: heading }).first()
}

export async function expectNoAppCrash(page) {
  await expect(page.getByText(/Algo correu mal|Ocorreu um erro inesperado/i)).toHaveCount(0)
}

export async function expectRouteReady(page, path) {
  await expect(page).toHaveURL(new RegExp(`${escapeRegExp(path)}(?:[?#].*)?$`), { timeout: 10000 })
  await expectNoAppCrash(page)
  const marker = readyMarker(page, path)
  if (marker) {
    await expect(marker).toBeVisible({ timeout: 10000 })
  }
}
