import { createClerkClient } from '@clerk/backend'
import { expect, test } from '@playwright/test'
import {
  attachRuntimeGuards,
  expectNoAppCrash,
  expectRouteReady,
} from '../utils/clerk-helpers.js'
import { cleanupFreshFounder, createFreshFounder } from '../utils/fresh-founder.js'

test.use({ locale: 'en-US' })

test.describe('Foundation — 24h time inputs', () => {
  test('renders editable hours without AM/PM under a US-English locale', async ({ page }) => {
    test.setTimeout(120_000)
    const secretKey = process.env.CLERK_SECRET_KEY
    if (!secretKey) throw new Error('CLERK_SECRET_KEY is required for foundation E2E.')
    const client = createClerkClient({ secretKey })
    let founder
    let primaryError = null
    let cleanupError = null
    attachRuntimeGuards(page)

    try {
      founder = await createFreshFounder(page, client, 'Foundation 24h')
      await expectRouteReady(page, '/foundation')
      await expect(page.getByText('1. Período do Ano Letivo')).toBeVisible()

      await page.locator('#school_start_date').fill('2025-09-15')
      await page.locator('#school_hard_end_date').fill('2026-07-31')
      await page.getByRole('button', { name: /Seguinte/i }).click()

      for (const day of [0, 1, 2, 3, 4]) {
        const checkbox = page.locator(`#day-${day}`)
        if (!await checkbox.isChecked()) await checkbox.check()
      }
      await page.getByRole('button', { name: /Seguinte/i }).click()

      const opening = page.locator('#opening_time')
      await expect(opening).toHaveAttribute('type', 'text')
      await expect(opening).toHaveAttribute('inputmode', 'numeric')
      await opening.fill('8:30')
      await expect(opening).toHaveValue('8:30')
      await expect(page.locator('#opening_time-unit')).toHaveText('h')
      await expect(page.locator('input[type="time"]')).toHaveCount(0)
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
