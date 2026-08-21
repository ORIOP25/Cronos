import { expect, test } from '@playwright/test'
import {
  attachRuntimeGuards,
  expectNoAppCrash,
  goTo,
  loginAsAdminReal,
} from '../utils/clerk-helpers.js'

test.describe('Tutorial — 24 Steps Navigation & Skip Constraints', () => {
  test.beforeEach(async ({ page }) => {
    attachRuntimeGuards(page)
    await loginAsAdminReal(page)
  })

  test('navigates through 24-step interactive tutorial honoring mandatory and skippable steps', async ({ page }) => {
    await goTo(page, '/guide')
    await expect(page.getByTestId('tutorial-modal')).toBeVisible()
    await expect(page.getByTestId('tutorial-step-counter')).toContainText('Passo 1 de 24')

    await page.getByTestId('tutorial-next-button').click()
    await expect(page.getByTestId('tutorial-step-counter')).toContainText('Passo 2 de 24')
    await expect(page.getByTestId('tutorial-skip-button')).toBeVisible()

    await page.getByTestId('tutorial-skip-button').click()
    await expect(page.getByTestId('tutorial-step-counter')).toContainText('Passo 3 de 24')
    await page.getByTestId('tutorial-skip-all-button').click()
    await expect(page.getByTestId('tutorial-modal')).toBeHidden()
    await expectNoAppCrash(page)
  })
})
