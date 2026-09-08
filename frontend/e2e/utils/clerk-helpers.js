import { clerk, setupClerkTestingToken } from '@clerk/testing/playwright'
import { expect } from '@playwright/test'
import {
  getApiResponseError,
  getConsoleError,
  getRequestFailureError,
} from './runtime-guards.js'
import { observeClerkSignIn } from './clerk-rate-limit.js'
import { E2E_BASE_URL } from './e2e-config.js'

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
    }, { baseUrl: E2E_BASE_URL })
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
      await page.goto(E2E_BASE_URL)
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

export async function acceptCurrentLegalDocuments(page) {
  // A newly-created Clerk organization can take a few seconds to appear in
  // the local mirror. Keep those temporary auth responses visible in traces
  // without failing the page before the mirror can converge.
  allowApiFailure(page, { status: 403, url: '/api/v1/members/me' })
  allowApiFailure(page, { status: 403, url: '/api/v1/legal/status' })

  for (let attempt = 0; attempt < 5; attempt += 1) {
    // Navigate explicitly to the legal route. This removes the race where the
    // previous protected route is briefly visible before the legal redirect.
    await page.goto(`${E2E_BASE_URL}/legal/aceitar`, { waitUntil: 'domcontentloaded' })
    let legalState = null
    try {
      await expect.poll(
        async () => {
          legalState = await page.evaluate(async () => {
            let token = null
            const organizationId = window.Clerk?.organization?.id ?? null
            const tokenOptions = organizationId
              ? { organizationId, skipCache: true }
              : undefined
            try {
              token = await window.Clerk?.session?.getToken?.(tokenOptions)
            } catch {
              token = null
            }
            if (!token) {
              try {
                const activeSession = window.Clerk?.client?.sessions?.find(
                  (session) => session.status === 'active',
                ) || window.Clerk?.client?.sessions?.[0]
                token = await activeSession?.getToken?.(tokenOptions)
              } catch {
                token = null
              }
            }
            if (!token) return null
            const response = await fetch('/api/v1/legal/status', {
              headers: { Authorization: `Bearer ${token}` },
            })
            if (!response.ok) return null
            const status = await response.json()
            if (status.requires_acceptance) return 'required'
            if (status.accepted) return 'accepted'
            return null
          })
          return legalState
        },
        { timeout: 10_000, intervals: [250, 500, 1_000] },
      ).toMatch(/^(?:required|accepted)$/)
    } catch {
      if (attempt < 4) {
        await page.waitForTimeout(1_000)
        continue
      }
      throw new Error('Legal status did not become available for the E2E organization.')
    }

    if (legalState === 'accepted') {
      await expect(page).toHaveURL(/\/(?:foundation|dashboard)(?:[/?#]|$)/, { timeout: 30_000 })
      return
    }

    const legalHeading = page.getByRole('heading', { name: 'Antes de configurar a escola' })
    await expect(legalHeading).toBeVisible({ timeout: 10_000 })
    await page.getByLabel('Nome legal da entidade').fill('Entidade E2E, ENI')
    await page.getByLabel('NIF/NIPC').fill('999999990')
    await page.getByLabel('Morada registada').fill('Rua E2E, 1, 1000-000 Lisboa')
    await page.getByLabel('Email de contacto').fill('e2e-legal@example.com')
    await page.getByLabel('Nome do representante').fill('Representante E2E')
    await page.getByLabel('Cargo do representante').fill('Administrador')
    for (const checkbox of await page.getByRole('checkbox').all()) await checkbox.check()
    await page.getByRole('button', { name: 'Aceitar e continuar' }).click()
    await expect(page).toHaveURL(/\/(?:foundation|dashboard)(?:[/?#]|$)/, { timeout: 30_000 })
    return
  }
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
    ['/my-availability', /Minhas\s+Preferencias|Minhas\s+Preferências/i],
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
