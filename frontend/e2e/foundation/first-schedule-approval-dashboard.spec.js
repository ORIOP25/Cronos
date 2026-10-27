import { createClerkClient } from '@clerk/backend'
import { createPageObjects } from '@clerk/testing/playwright/unstable'
import { setupClerkTestingToken } from '@clerk/testing/playwright'
import { expect, test } from '@playwright/test'
import {
  allowApiFailure,
  attachRuntimeGuards,
  CLERK_LEGAL_UNSAFE_METADATA,
  expectNoAppCrash,
  expectRouteReady,
} from '../utils/clerk-helpers.js'
import { generateAndApproveThroughUi, seedMinimalSchedulerInputs } from '../utils/scheduler-fixtures.js'
import { createE2eRunKey, E2E_BASE_URL } from '../utils/e2e-config.js'
import { cleanupOrganizationByName } from '../utils/fresh-founder.js'

function withTimeout(operation, label, timeoutMs = 30_000) {
  let timeoutId
  const timeout = new Promise((_, reject) => {
    timeoutId = setTimeout(() => reject(new Error(`${label} timed out after ${timeoutMs}ms`)), timeoutMs)
  })
  return Promise.race([Promise.resolve().then(operation), timeout]).finally(() => clearTimeout(timeoutId))
}

async function signInFreshFounder(client, page, userId, organizationName) {
  const ticket = await withTimeout(
    () => client.signInTokens.createSignInToken({ userId, expiresInSeconds: 300 }),
    'dashboard E2E sign-in token creation',
  )
  const baseUrl = E2E_BASE_URL
  const ticketUrl = new URL(ticket.url)
  ticketUrl.searchParams.set('redirect_url', new URL('/foundation', baseUrl).toString())
  await setupClerkTestingToken({ page })
  await page.goto(ticketUrl.toString(), { waitUntil: 'domcontentloaded' })
  await expect.poll(() => page.url(), { timeout: 30_000 }).toMatch(
    /\/(?:foundation|tasks\/choose-organization)(?:[/?#]|$)/,
  )
  if (/\/tasks\/choose-organization(?:[/?#]|$)/.test(page.url())) {
    const clerkPages = createPageObjects({ page, baseURL: baseUrl })
    await withTimeout(
      () => clerkPages.sessionTask.resolveForceOrganizationSelectionTask({ name: organizationName }),
      'dashboard E2E organization selection',
    )
  }
  await expect.poll(() => page.url(), { timeout: 30_000 }).toMatch(
    /\/foundation(?:[/?#]|$)/,
  )
  await page.waitForFunction(() => window.Clerk?.user != null, null, { timeout: 30_000 })
  await page.waitForFunction(() => window.Clerk?.organization?.id?.startsWith('org_'), null, { timeout: 30_000 })
  await page.waitForURL('**/foundation', { timeout: 30_000 })
  return page.evaluate(() => window.Clerk.organization.id)
}

async function completeFreshFoundation(page) {
  await page.waitForURL('**/foundation', { timeout: 30_000 })
  await expectRouteReady(page, '/foundation')
  await expect(page.locator('#school_start_date')).toBeEnabled({ timeout: 30_000 })
  await page.locator('#school_start_date').fill('2025-09-15')
  await page.locator('#school_hard_end_date').fill('2026-07-31')
  for (let step = 1; step < 8; step += 1) {
    await page.getByRole('button', { name: /seguinte/i }).click()
  }
  const automaticHolidays = page.getByRole('checkbox', { name: /feriados automáticos/i })
  await expect(automaticHolidays).not.toBeChecked()
  const save = page.waitForResponse((response) => (
    response.url().includes('/api/v1/foundation/draft') &&
    response.request().method() === 'PUT' && response.status() === 200
  ))
  await automaticHolidays.check()
  await save
  await page.getByRole('button', { name: /seguinte/i }).click()
  await page.getByRole('button', { name: /ignorar por agora/i }).click()
  await page.getByRole('checkbox', { name: /confirmo que revi/i }).check()
  const activate = page.waitForResponse((response) => (
    response.url().includes('/api/v1/foundation/complete') &&
    response.request().method() === 'POST'
  ))
  await page.getByRole('button', { name: /^ativar escola$/i }).click()
  expect((await activate).status()).toBe(200)
  await expectRouteReady(page, '/dashboard')
}

test.describe('Dashboard — First Real Schedule Approval & Discrimination', () => {
  test('displays PREPARATION mode before first schedule approval and OPERATIONAL mode afterwards', async ({ page }) => {
    test.setTimeout(300_000)
    const secretKey = process.env.CLERK_SECRET_KEY
    if (!secretKey) throw new Error('CLERK_SECRET_KEY is required for dashboard E2E.')
    const client = createClerkClient({ secretKey })
    const runKey = createE2eRunKey()
    const email = `cronos-dashboard-${runKey}+clerk_test@example.com`
    const organizationName = `Cronos Dashboard ${runKey}`
    let userId
    let organizationId
    let primaryError = null
    let cleanupError = null

    try {
      const user = await withTimeout(
        () => client.users.createUser({
          emailAddress: [email],
          firstName: 'Cronos',
          lastName: 'Dashboard',
          skipPasswordRequirement: true,
          legalAcceptedAt: new Date(),
          unsafeMetadata: CLERK_LEGAL_UNSAFE_METADATA,
          createOrganizationEnabled: true,
        }),
        'dashboard E2E user creation',
      )
      userId = user.id
      allowApiFailure(page, { status: 404, url: '/api/v1/scheduler/drafts/current' })
      attachRuntimeGuards(page)
      organizationId = await signInFreshFounder(client, page, userId, organizationName)
      await completeFreshFoundation(page)
      await seedMinimalSchedulerInputs(page, email)

      // 1. PREPARATION mode: read the real dashboard response before approval.
      const preparationResponse = page.waitForResponse((response) => (
        response.url().includes('/api/v1/dashboard') && response.request().method() === 'GET'
      ))
      await page.goto(`${E2E_BASE_URL}/dashboard`, { waitUntil: 'domcontentloaded' })
      const preparationPayload = await (await preparationResponse).json()
      expect(preparationPayload.mode).toBe('PREPARATION')
      await expect(page.getByTestId('preparation-dashboard')).toBeVisible()
      await expect(page.getByRole('heading', { name: /Passos de preparação/i })).toBeVisible()
      await expect(page.getByTestId('schedule-health')).toHaveCount(0)

      // 2. Generate and approve a real draft, then read the real operational dashboard.
      await generateAndApproveThroughUi(page)
      const operationalResponse = page.waitForResponse((response) => (
        response.url().includes('/api/v1/dashboard') && response.request().method() === 'GET'
      ))
      await page.goto(`${E2E_BASE_URL}/dashboard`, { waitUntil: 'domcontentloaded' })
      const operationalPayload = await (await operationalResponse).json()
      expect(operationalPayload.mode).toBe('OPERATIONAL')
      await expect(page.getByTestId('schedule-health')).toBeVisible()
      await expect(page.getByTestId('preparation-dashboard')).toHaveCount(0)
      await expectRouteReady(page, '/dashboard')
      await expectNoAppCrash(page)
    } catch (error) {
      primaryError = error
    } finally {
      try {
        if (organizationId) {
          await withTimeout(() => client.organizations.deleteOrganization(organizationId), 'dashboard E2E organization cleanup')
        }
      } catch (error) {
        cleanupError = error
      }
      try {
        await cleanupOrganizationByName(client, organizationName)
      } catch (error) {
        cleanupError ||= error
      }
      try {
        if (userId) await withTimeout(() => client.users.deleteUser(userId), 'dashboard E2E user cleanup')
      } catch (error) {
        cleanupError ||= error
      }
    }
    if (primaryError) throw primaryError
    if (cleanupError) throw cleanupError
  })
})
