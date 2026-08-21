import { expect, test } from '@playwright/test'
import {
  attachRuntimeGuards,
  expectNoAppCrash,
  goTo,
  loginAsAdminReal,
} from '../utils/clerk-helpers.js'

test.describe.configure({ mode: 'serial' })

test.describe('Year reset — no legacy onboarding', () => {
  test('does not redirect to the removed onboarding contract or auto-open the guide', async ({ page }) => {
    attachRuntimeGuards(page)
    await loginAsAdminReal(page)
    await page.evaluate(() => {
      for (const key of Object.keys(localStorage)) {
        if (key.startsWith('cronos:tutorial:')) localStorage.removeItem(key)
      }
    })

    await goTo(page, '/dashboard')
    await expect(page).not.toHaveURL(/\/onboarding/)
    await expect(page).not.toHaveURL(/\/guide/)
    await expectNoAppCrash(page)

    await goTo(page, '/onboarding')
    await expect(page).toHaveURL(/\/onboarding$/)
    await expect(page.getByText(/página não encontrada|não encontrada/i)).toBeVisible()
  })
})
