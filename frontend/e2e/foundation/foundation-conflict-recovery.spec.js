import { expect, test } from '@playwright/test'
import {
  allowApiFailure,
  attachRuntimeGuards,
  expectNoAppCrash,
  expectRouteReady,
  goTo,
  loginAsAdminReal,
} from '../utils/clerk-helpers.js'

test.describe('Foundation — Conflict Resolution Modal', () => {
  test('handles 409 draft version conflict with reload and retry without data loss', async ({ browser }) => {
    const contextA = await browser.newContext()
    const contextB = await browser.newContext()
    const pageA = await contextA.newPage()
    const pageB = await contextB.newPage()
    for (const page of [pageA, pageB]) {
      attachRuntimeGuards(page)
      await loginAsAdminReal(page)
      await goTo(page, '/foundation')
      await expectRouteReady(page, '/foundation')
    }

    try {
      await pageA.locator('#school_start_date').fill('2025-09-15')
      await pageA.waitForResponse((response) => (
        response.url().includes('/api/v1/foundation/draft') &&
        response.request().method() === 'PUT' &&
        response.status() === 200
      ))

      await pageB.route('**/api/v1/foundation/draft', async (route) => {
        if (route.request().method() !== 'PUT') return route.continue()
        await route.fulfill({
          status: 409,
          contentType: 'application/json',
          body: JSON.stringify({ detail: { expected_version: 0, current_version: 1 } }),
        })
      })
      allowApiFailure(pageB, { status: 409, url: '/api/v1/foundation/draft' })
      await pageB.locator('#school_start_date').fill('2025-09-16')
      await expect(pageB.getByRole('heading', { name: /conflito de edição detetado/i })).toBeVisible()
      await expect(pageB.getByRole('button', { name: /seguinte/i })).toBeDisabled()
      await expect(pageB.locator('#school_start_date')).toBeDisabled()

      await pageB.unroute('**/api/v1/foundation/draft')
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
    } finally {
      await contextA.close()
      await contextB.close()
    }
  })
})
