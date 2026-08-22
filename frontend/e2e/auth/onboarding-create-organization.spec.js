import { createClerkClient } from '@clerk/backend'
import { setupClerkTestingToken } from '@clerk/testing/playwright'
import { expect, test } from '@playwright/test'
import { attachRuntimeGuards, expectRouteReady } from '../utils/clerk-helpers.js'

const OPERATION_TIMEOUT_MS = 30_000

function withTimeout(operation, label, timeoutMs = OPERATION_TIMEOUT_MS) {
  let timeoutId
  const timeout = new Promise((_, reject) => {
    timeoutId = setTimeout(() => reject(new Error(`${label} timed out after ${timeoutMs}ms`)), timeoutMs)
  })
  return Promise.race([Promise.resolve().then(operation), timeout]).finally(() => clearTimeout(timeoutId))
}

test('manual founder onboarding creates and activates an organization', async ({ page }) => {
  test.setTimeout(120_000)
  const secretKey = process.env.CLERK_SECRET_KEY
  if (!secretKey) throw new Error('CLERK_SECRET_KEY is required for onboarding E2E.')

  const client = createClerkClient({ secretKey })
  const runKey = `${Date.now()}-${Math.random().toString(16).slice(2)}`
  const email = `cronos-onboarding-${runKey}+clerk_test@example.com`
  const schoolName = `Cronos Onboarding ${runKey}`
  let userId
  let organizationId
  const cleanupErrors = []
  let primaryError = null

  try {
    const user = await withTimeout(
      () => client.users.createUser({
        emailAddress: [email],
        firstName: 'Cronos',
        lastName: 'Onboarding',
        skipPasswordRequirement: true,
        skipLegalChecks: true,
        createOrganizationEnabled: true,
      }),
      'Clerk onboarding user creation',
    )
    userId = user.id

    attachRuntimeGuards(page)
    await setupClerkTestingToken({ page })
    const baseUrl = process.env.BASE_URL || 'http://localhost:5173'
    const ticket = await withTimeout(
      () => client.signInTokens.createSignInToken({ userId, expiresInSeconds: 300 }),
      'Clerk onboarding sign-in token creation',
    )
    const ticketUrl = new URL(ticket.url)
    ticketUrl.searchParams.set('redirect_url', new URL('/create-org', baseUrl).toString())
    await page.goto(ticketUrl.toString(), { waitUntil: 'domcontentloaded' })
    await page.waitForURL('**/create-org', { timeout: OPERATION_TIMEOUT_MS })
    await page.waitForFunction(() => window.Clerk?.user != null, null, {
      timeout: OPERATION_TIMEOUT_MS,
    })

    await page.getByLabel('Nome da escola').fill(schoolName)
    await page.getByRole('button', { name: 'Criar organização' }).click()
    await page.waitForFunction(
      () => window.Clerk?.organization?.id?.startsWith('org_'),
      null,
      { timeout: OPERATION_TIMEOUT_MS },
    )
    organizationId = await page.evaluate(() => window.Clerk.organization.id)
    await page.waitForURL('**/foundation', { timeout: OPERATION_TIMEOUT_MS })
    expect(organizationId).toMatch(/^org_/)
    await expectRouteReady(page, '/foundation')
    await expect(page.locator('#school_start_date')).toBeVisible()
  } catch (error) {
    primaryError = error
  } finally {
    if (organizationId) {
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
