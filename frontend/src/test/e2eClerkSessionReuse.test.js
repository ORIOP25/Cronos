import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const clerkSignIn = vi.hoisted(() => vi.fn())
const setupClerkTestingToken = vi.hoisted(() => vi.fn())

vi.mock('@clerk/testing/playwright', () => ({
  clerk: { signIn: clerkSignIn },
  setupClerkTestingToken,
}))

import { loginAsAdminReal } from '../../e2e/utils/clerk-helpers.js'

function pageWithSession(email, organizationId) {
  const page = {
    goto: vi.fn(),
    waitForFunction: vi.fn(),
    evaluate: vi.fn(async (_, nextOrganizationId) => {
      if (nextOrganizationId) return
      return { email, organizationId }
    }),
  }
  return page
}

describe('E2E Clerk session reuse', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubEnv('E2E_CLERK_ADMIN_EMAIL', 'admin+clerk_test@example.com')
    vi.stubEnv('E2E_CLERK_ORG_ID', 'org_test')
  })

  afterEach(() => vi.unstubAllEnvs())

  it('uses the isolated saved session without signing in or switching organizations again', async () => {
    const page = pageWithSession('admin+clerk_test@example.com', 'org_test')

    await loginAsAdminReal(page)

    expect(clerkSignIn).not.toHaveBeenCalled()
    expect(page.evaluate).toHaveBeenCalledTimes(1)
    expect(page.goto).toHaveBeenCalledTimes(2)
  })

  it('signs in when the page has a different identity', async () => {
    const page = pageWithSession('other+clerk_test@example.com', 'org_test')

    await loginAsAdminReal(page)

    expect(clerkSignIn).toHaveBeenCalledWith({ page, emailAddress: 'admin+clerk_test@example.com' })
    expect(page.evaluate).toHaveBeenCalledTimes(2)
  })

  it('restores the expected organization without signing in again', async () => {
    const page = pageWithSession('admin+clerk_test@example.com', 'org_other')

    await loginAsAdminReal(page)

    expect(clerkSignIn).not.toHaveBeenCalled()
    expect(page.evaluate).toHaveBeenCalledTimes(2)
    expect(page.evaluate.mock.calls[1][1]).toBe('org_test')
  })
})
