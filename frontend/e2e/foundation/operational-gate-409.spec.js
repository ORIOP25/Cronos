import { createClerkClient } from '@clerk/backend'
import { expect, test } from '@playwright/test'
import {
  allowApiFailure,
  attachRuntimeGuards,
  expectNoAppCrash,
  goTo,
} from '../utils/clerk-helpers.js'
import { cleanupFreshFounder, createFreshFounder } from '../utils/fresh-founder.js'

test.describe('Foundation — Operational Gate 409', () => {
  test('blocks director from operational pages when foundation is not completed', async ({ page }) => {
    test.setTimeout(120_000)
    const secretKey = process.env.CLERK_SECRET_KEY
    if (!secretKey) throw new Error('CLERK_SECRET_KEY is required for foundation E2E.')
    const client = createClerkClient({ secretKey })
    let founder
    let primaryError = null
    let cleanupError = null
    attachRuntimeGuards(page)

    try {
      founder = await createFreshFounder(page, client, 'Operational Gate')
    // This test runs in the foundation-setup project, before the real activation test.
    // Both the route guard and the API response must come from the backend state.
      allowApiFailure(page, { status: 409, url: '/api/v1/classes' })

      // 1. Navigating to a real operational page redirects to /foundation.
      await goTo(page, '/courses')
      await expect(page).toHaveURL(/.*\/foundation/)
      await expect(page.locator('#school_start_date')).toBeVisible()

      // 2. The operational API also returns the real foundation gate response.
      const apiResponse = await page.evaluate(async () => {
        const token = await window.Clerk?.session?.getToken()
        const res = await fetch('/api/v1/classes/', {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        })
        return { status: res.status, body: await res.json() }
      })
      expect(apiResponse.status).toBe(409)
      expect(apiResponse.body.detail.code).toBe('FOUNDATION_REQUIRED')

      await expectNoAppCrash(page)
    } catch (error) {
      primaryError = error
    } finally {
      if (founder) {
        try {
          await cleanupFreshFounder(client, founder)
        } catch (error) {
          cleanupError = error
        }
      }
    }
    if (primaryError) throw primaryError
    if (cleanupError) throw cleanupError
  })
})
