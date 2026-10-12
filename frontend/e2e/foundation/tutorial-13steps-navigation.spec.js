import { expect, test } from '@playwright/test'
import {
  attachRuntimeGuards,
  expectNoAppCrash,
  goTo,
  loginAsAdminReal,
} from '../utils/clerk-helpers.js'

test.use({ storageState: '.auth/admin.json' })

test.describe('Tutorial — 13 passos por funcionalidade', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      for (const key of Object.keys(localStorage)) {
        if (key.startsWith('cronos:tutorial:')) localStorage.removeItem(key)
      }
    })
    await loginAsAdminReal(page)
    await expect(page.locator('main.app-main')).toBeVisible({ timeout: 30_000 })
    attachRuntimeGuards(page)
  })

  test('permite saltar o guia de forma integral', async ({ page }) => {
    await goTo(page, '/guide')
    await expect(page.getByTestId('guide-landing')).toBeVisible()
    await page.getByRole('button', { name: /conhecer o guia/i }).click()
    await expect(page.getByTestId('tutorial-skip-all-button')).toBeVisible()
    await page.getByTestId('tutorial-skip-all-button').click()
    await expect(page.getByTestId('tutorial-workspace')).toHaveCount(0)
    await expectNoAppCrash(page)
  })
})
