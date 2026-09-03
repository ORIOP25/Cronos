import { createClerkClient } from '@clerk/backend'
import { expect, test } from '@playwright/test'
import {
  allowApiFailure,
  attachRuntimeGuards,
  expectNoAppCrash,
  expectRouteReady,
} from '../utils/clerk-helpers.js'
import {
  cleanupFreshFounder,
  createFreshFounder,
  signInFreshFounder,
} from '../utils/fresh-founder.js'

test.describe('Foundation — Conflict Resolution Modal', () => {
  test('handles 409 draft version conflict with reload and retry without data loss', async ({ browser }) => {
    test.setTimeout(120_000)
    const secretKey = process.env.CLERK_SECRET_KEY
    if (!secretKey) throw new Error('CLERK_SECRET_KEY is required for foundation E2E.')
    const client = createClerkClient({ secretKey })
    const contextA = await browser.newContext()
    const contextB = await browser.newContext()
    const pageA = await contextA.newPage()
    const pageB = await contextB.newPage()
    attachRuntimeGuards(pageA)
    attachRuntimeGuards(pageB)
    let founder
    let primaryError = null
    let cleanupError = null

    try {
      founder = await createFreshFounder(pageA, client, 'Foundation Conflict')
      await expectRouteReady(pageA, '/foundation')
      await signInFreshFounder(pageB, client, founder)
      await expectRouteReady(pageB, '/foundation')
      const pageASave = pageA.waitForResponse((response) => (
        response.url().includes('/api/v1/foundation/draft') &&
        response.request().method() === 'PUT' &&
        response.status() === 200
      ))
      await pageA.locator('#school_start_date').fill('2025-09-15')
      await pageASave

      allowApiFailure(pageB, { status: 409, url: '/api/v1/foundation/draft' })
      const pageBConflict = pageB.waitForResponse((response) => (
        response.url().includes('/api/v1/foundation/draft') &&
        response.request().method() === 'PUT' &&
        response.status() === 409
      ))
      await pageB.locator('#school_start_date').fill('2025-09-16')
      await pageBConflict
      await expect(pageB.getByRole('heading', { name: /conflito de edição detetado/i })).toBeVisible()
      await expect(pageB.getByText(/Versão esperada:/i)).toBeVisible()
      await expect(pageB.getByRole('button', { name: /seguinte/i })).toBeDisabled()

      await pageB.getByRole('button', { name: /recarregar dados mais recentes/i }).click()
      await expect(pageB.getByRole('heading', { name: /conflito de edição detetado/i })).toBeHidden()

      await pageB.locator('#school_hard_end_date').fill('2026-07-31')
      await pageB.waitForResponse((response) => (
        response.url().includes('/api/v1/foundation/draft') &&
        response.request().method() === 'PUT' &&
        response.status() === 200
      ))
      await expectNoAppCrash(pageA)
      await expectNoAppCrash(pageB)
    } catch (error) {
      primaryError = error
    } finally {
      await contextA.close()
      await contextB.close()
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
