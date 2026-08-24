import { expect, test } from '@playwright/test'
import {
  attachRuntimeGuards,
  expectNoAppCrash,
  goTo,
  loginAsAdminReal,
} from '../utils/clerk-helpers.js'

test.describe('Tutorial — 24 Steps Navigation & Skip Constraints', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      for (const key of Object.keys(localStorage)) {
        if (key.startsWith('cronos:tutorial:')) localStorage.removeItem(key)
      }
    })
    await loginAsAdminReal(page)
    await page.waitForLoadState('networkidle')
    attachRuntimeGuards(page)
  })

  test('navigates through 24-step interactive tutorial honoring mandatory and skippable steps', async ({ page }) => {
    await goTo(page, '/guide')
    await expect(page.getByTestId('tutorial-workspace')).toBeVisible()
    await expect(page.getByTestId('tutorial-step-counter')).toContainText('Passo 1 de 24')

    await page.getByTestId('tutorial-complete-step').click()
    await expect(page.getByTestId('tutorial-step-counter')).toContainText('Passo 2 de 24')
    await expect(page.getByTestId('tutorial-skip-step-button')).toBeVisible()

    await page.getByTestId('tutorial-skip-step-button').click()
    await expect(page.getByTestId('tutorial-step-counter')).toContainText('Passo 3 de 24')
    await page.getByTestId('tutorial-skip-all-button').click()
    await expect(page.getByTestId('tutorial-workspace')).toBeHidden()
    await expectNoAppCrash(page)
  })
})
