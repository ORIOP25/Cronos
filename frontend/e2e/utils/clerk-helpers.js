import { clerk, setupClerkTestingToken } from '@clerk/testing/playwright'
import { expect } from '@playwright/test'
import {
  getApiResponseError,
  getConsoleError,
  getRequestFailureError,
} from './runtime-guards.js'
import { observeClerkSignIn } from './clerk-rate-limit.js'

const BASE_URL = process.env.BASE_URL || 'http://localhost:5173'

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
    }, allowedApiFailures(page))
    if (error) {
      throw new Error(error)
    }
  })
  page.on('requestfailed', (request) => {
    const error = getRequestFailureError({
      method: request.method(),
      url: request.url(),
      errorText: request.failure()?.errorText,
    }, { baseUrl: BASE_URL })
    if (error) {
      throw new Error(error)
    }
  })
  page.on('response', (response) => {
    const error = getApiResponseError({
      url: response.url(),
      status: response.status(),
    }, allowedApiFailures(page))
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
      await page.goto(BASE_URL)
      await clerk.signIn({ page, emailAddress })
      if (organizationId) {
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
}

export async function loginAsTeacherReal(page) {
  await loginReal(page, 'E2E_CLERK_TEACHER_EMAIL')
}

export async function goTo(page, path) {
  await setupClerkTestingToken({ page })
  await page.goto(`${BASE_URL}${path}`, { waitUntil: 'domcontentloaded' })
  await expectNoAppCrash(page)
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
  const exactMarkers = new Map([
    ['/dashboard', /Painel de Controlo/i],
    ['/members', /Equipa/i],
    ['/courses', /Cursos/i],
    ['/rooms', /Salas/i],
    ['/subjects', /Disciplinas/i],
    ['/config', /Escola/i],
    ['/schedules', /Horarios escolares|Horários escolares/i],
    ['/absences', /Faltas e\s+Ocorrencias|Faltas e\s+Ocorrências/i],
    ['/timesheets', /Fecho\s+Semanal/i],
    ['/my-availability', /Minhas\s+Preferencias|Minhas\s+Preferências/i],
    ['/my-schedules', /Meus\s+Horarios|Meus\s+Horários/i],
    ['/my-progress', /Meu\s+Progresso/i],
  ])
  const heading = exactMarkers.get(path)
  return heading ? page.getByRole('heading', { name: heading }).first() : null
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
