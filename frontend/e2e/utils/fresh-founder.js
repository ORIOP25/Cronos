import { createPageObjects } from '@clerk/testing/playwright/unstable'
import { setupClerkTestingToken } from '@clerk/testing/playwright'
import { expect } from '@playwright/test'
import { createE2eRunKey, E2E_BASE_URL } from './e2e-config.js'
import {
  acceptLegalDocumentsInApp,
} from './clerk-helpers.js'

export function withTimeout(operation, label, timeoutMs = 30_000) {
  let timeoutId
  const timeout = new Promise((_, reject) => {
    timeoutId = setTimeout(() => reject(new Error(`${label} timed out after ${timeoutMs}ms`)), timeoutMs)
  })
  return Promise.race([Promise.resolve().then(operation), timeout]).finally(() => clearTimeout(timeoutId))
}

async function signInWithTicket(page, client, userId, organizationName) {
  const ticket = await withTimeout(
    () => client.signInTokens.createSignInToken({ userId, expiresInSeconds: 300 }),
    'Clerk E2E sign-in token creation',
  )
  const ticketUrl = new URL(ticket.url)
  ticketUrl.searchParams.set('redirect_url', new URL('/create-org', E2E_BASE_URL).toString())
  await setupClerkTestingToken({ page })
  await page.goto(ticketUrl.toString(), { waitUntil: 'domcontentloaded' })
  await expect.poll(() => page.url(), { timeout: 30_000 }).toMatch(
    /\/(?:create-org|tasks\/choose-organization)(?:[/?#]|$)/,
  )
  if (/\/tasks\/choose-organization(?:[/?#]|$)/.test(page.url())) {
    const clerkPages = createPageObjects({ page, baseURL: E2E_BASE_URL })
    await withTimeout(
      () => clerkPages.sessionTask.resolveForceOrganizationSelectionTask({ name: organizationName }),
      'Clerk E2E organization selection',
    )
  }
  await expect.poll(() => page.url(), { timeout: 30_000 }).toMatch(
    /\/(?:create-org|foundation)(?:[/?#]|$)/,
  )
  await page.waitForFunction(() => window.Clerk?.user != null, null, { timeout: 30_000 })
}

export async function createFreshFounder(page, client, label) {
  const runKey = createE2eRunKey()
  const emailLabel = label.toLowerCase().replace(/[^a-z0-9]+/g, '-')
  const email = `cronos-${emailLabel.slice(0, 12)}-${runKey}+clerk_test@example.com`
  const organizationName = `Cronos ${label} ${runKey}`
  const user = await withTimeout(
    () => client.users.createUser({
      emailAddress: [email],
      firstName: 'Cronos',
      lastName: 'E2E',
      skipPasswordRequirement: true,
      skipLegalChecks: true,
      createOrganizationEnabled: true,
    }),
    'Clerk E2E user creation',
  )

  let organizationId
  try {
    await signInWithTicket(page, client, user.id, organizationName)
    await acceptLegalDocumentsInApp(page)
    await page.waitForURL('**/foundation', { timeout: 30_000 })
    await page.waitForFunction(() => window.Clerk?.organization?.id?.startsWith('org_'), null, {
      timeout: 30_000,
    })
    organizationId = await page.evaluate(() => window.Clerk.organization.id)
    await expect(page.locator('#school_start_date')).toBeEnabled({ timeout: 30_000 })
    return { email, userId: user.id, organizationId, organizationName }
  } catch (error) {
    if (organizationId) {
      try { await client.organizations.deleteOrganization(organizationId) } catch { /* best effort */ }
    }
    try { await client.users.deleteUser(user.id) } catch { /* best effort */ }
    throw error
  }
}

export async function signInFreshFounder(page, client, founder) {
  await signInWithTicket(page, client, founder.userId, founder.organizationName)
  await page.evaluate(async (organizationId) => {
    await window.Clerk.setActive({ organization: organizationId })
  }, founder.organizationId)
  await page.waitForFunction(
    (organizationId) => window.Clerk?.organization?.id === organizationId,
    founder.organizationId,
    { timeout: 30_000 },
  )
  await page.goto(`${E2E_BASE_URL}/foundation`, { waitUntil: 'domcontentloaded' })
  await acceptLegalDocumentsInApp(page)
  await page.waitForURL('**/foundation', { timeout: 30_000 })
  await expect(page.locator('#school_start_date')).toBeEnabled({ timeout: 30_000 })
}

export async function cleanupFreshFounder(client, founder) {
  const errors = []
  if (founder?.organizationId) {
    try {
      await withTimeout(
        () => client.organizations.deleteOrganization(founder.organizationId),
        `Clerk E2E organization cleanup ${founder.organizationId}`,
      )
    } catch (error) {
      errors.push(error)
    }
  }
  if (founder?.userId) {
    try {
      await withTimeout(
        () => client.users.deleteUser(founder.userId),
        `Clerk E2E user cleanup ${founder.userId}`,
      )
    } catch (error) {
      errors.push(error)
    }
  }
  if (errors.length) throw new Error(`Clerk E2E cleanup failed (${errors.length} operation(s))`)
}
