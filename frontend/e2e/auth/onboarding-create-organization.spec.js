import { createClerkClient } from '@clerk/backend'
import { setupClerkTestingToken } from '@clerk/testing/playwright'
import { createPageObjects } from '@clerk/testing/playwright/unstable'
import { expect, test } from '@playwright/test'
import {
  attachRuntimeGuards,
  CLERK_LEGAL_UNSAFE_METADATA,
  expectRouteReady,
} from '../utils/clerk-helpers.js'
import { createE2eRunKey, E2E_BASE_URL } from '../utils/e2e-config.js'

const OPERATION_TIMEOUT_MS = 30_000

function withTimeout(operation, label, timeoutMs = OPERATION_TIMEOUT_MS) {
  let timeoutId
  const timeout = new Promise((_, reject) => {
    timeoutId = setTimeout(() => reject(new Error(`${label} timed out after ${timeoutMs}ms`)), timeoutMs)
  })
  return Promise.race([Promise.resolve().then(operation), timeout]).finally(() => clearTimeout(timeoutId))
}

test('Clerk blocks registration until the legal consent checkbox is selected', async ({ page }) => {
  test.setTimeout(60_000)
  attachRuntimeGuards(page)
  await setupClerkTestingToken({ page })
  await page.goto(`${E2E_BASE_URL}/register`, { waitUntil: 'domcontentloaded' })

  const checkbox = page.getByRole('checkbox').first()
  await expect(checkbox).toBeVisible({ timeout: OPERATION_TIMEOUT_MS })
  await expect(checkbox).not.toBeChecked()

  const email = page.locator('input[name="emailAddress"]')
  const password = page.locator('input[name="password"]')
  await email.fill(`cronos-no-consent-${createE2eRunKey()}@example.com`)
  if (await password.isVisible()) await password.fill('NotARealPassword-123!')
  const continueButton = page.getByRole('button', { name: /continuar|criar conta|registar/i }).last()
  await expect(continueButton).toBeVisible()
  await continueButton.click()
  await expect(page).toHaveURL(/\/register(?:[/?#]|$)/)
  await expect(checkbox).not.toBeChecked()
})

test('founder onboarding creates and activates an organization directly at foundation', async ({ page }) => {
  test.setTimeout(120_000)
  const secretKey = process.env.CLERK_SECRET_KEY
  if (!secretKey) throw new Error('CLERK_SECRET_KEY is required for onboarding E2E.')

  const client = createClerkClient({ secretKey })
  const runKey = createE2eRunKey()
  const email = `cronos-onboarding-${runKey}+clerk_test@example.com`
  const schoolName = `Cronos Onboarding ${runKey}`
  let userId
  const organizationIds = new Set()
  const cleanupErrors = []
  let primaryError = null

  try {
    const user = await withTimeout(
      () => client.users.createUser({
        emailAddress: [email],
        firstName: 'Cronos',
        lastName: 'Onboarding',
        skipPasswordRequirement: true,
        legalAcceptedAt: new Date(),
        unsafeMetadata: CLERK_LEGAL_UNSAFE_METADATA,
        createOrganizationEnabled: true,
      }),
      'Clerk onboarding user creation',
    )
    userId = user.id

    attachRuntimeGuards(page)
    await setupClerkTestingToken({ page })
    const baseUrl = E2E_BASE_URL
    const ticket = await withTimeout(
      () => client.signInTokens.createSignInToken({ userId, expiresInSeconds: 300 }),
      'Clerk onboarding sign-in token creation',
    )
    const ticketUrl = new URL(ticket.url)
    const targetUrl = new URL('/foundation', baseUrl)
    ticketUrl.searchParams.set('redirect_url', targetUrl.toString())
    await page.goto(ticketUrl.toString(), { waitUntil: 'domcontentloaded' })

    await expect.poll(() => page.url(), { timeout: OPERATION_TIMEOUT_MS }).toMatch(
      /\/(?:foundation|tasks\/choose-organization)(?:[/?#]|$)/,
    )
    if (/\/tasks\/choose-organization(?:[/?#]|$)/.test(page.url())) {
      const clerkPages = createPageObjects({ page, baseURL: baseUrl })
      await withTimeout(
        () => clerkPages.sessionTask.resolveForceOrganizationSelectionTask({ name: schoolName }),
        'Clerk organization selection',
      )
    }
    await expect.poll(() => page.url(), { timeout: OPERATION_TIMEOUT_MS }).toMatch(
      /\/foundation(?:[/?#]|$)/,
    )
    await page.waitForFunction(() => window.Clerk?.user != null, null, {
      timeout: OPERATION_TIMEOUT_MS,
    })
    await page.waitForFunction(
      () => window.Clerk?.organization?.id?.startsWith('org_'),
      null,
      { timeout: OPERATION_TIMEOUT_MS },
    )
    await page.waitForURL('**/foundation', { timeout: OPERATION_TIMEOUT_MS })
    const organizationId = await page.evaluate(() => window.Clerk.organization.id)
    organizationIds.add(organizationId)
    await page.waitForURL('**/foundation', { timeout: OPERATION_TIMEOUT_MS })
    expect(organizationId).toMatch(/^org_/)
    await expectRouteReady(page, '/foundation')
    await expect(page.locator('#school_start_date')).toBeVisible()
  } catch (error) {
    primaryError = error
  } finally {
    for (const organizationId of organizationIds) {
      try {
        await withTimeout(
          () => client.organizations.deleteOrganization(organizationId),
          `Clerk onboarding organization cleanup ${organizationId}`,
        )
      } catch (error) {
        cleanupErrors.push(error)
      }
    }
    if (userId) {
      try {
        await withTimeout(
          () => client.users.deleteUser(userId),
          `Clerk onboarding user cleanup ${userId}`,
        )
      } catch (error) {
        cleanupErrors.push(error)
      }
    }
  }
  if (primaryError) throw primaryError
  if (cleanupErrors.length) throw new Error('Clerk onboarding cleanup failed')
})
