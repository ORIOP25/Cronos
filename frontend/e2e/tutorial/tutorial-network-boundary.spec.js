import { expect, test } from '@playwright/test'
import {
  attachRuntimeGuards,
  expectNoAppCrash,
  goTo,
  loginAsAdminReal,
} from '../utils/clerk-helpers.js'

test.describe.configure({ mode: 'serial' })

const isAllowedTutorialRequest = (url) => (
  url.includes('/api/v1/tutorial/telemetry')
  || url.includes('/api/v1/members/me')
)

test.describe('Tutorial — network boundary', () => {
  test('uses local simulation only and sends telemetry without operational mutations', async ({ page }) => {
    await page.addInitScript(() => {
      for (const key of Object.keys(localStorage)) {
        if (key.startsWith('cronos:tutorial:')) localStorage.removeItem(key)
      }
    })
    await loginAsAdminReal(page)
    await page.waitForLoadState('networkidle')
    attachRuntimeGuards(page)

    const requests = []
    page.on('request', (request) => {
      if (request.url().includes('/api/v1/')) requests.push(request.url())
    })

    await goTo(page, '/guide')
    await expect(page.getByTestId('tutorial-workspace')).toBeVisible()

    for (let stepNumber = 1; stepNumber <= 24; stepNumber += 1) {
      await expect(page.getByTestId('tutorial-step-counter')).toHaveText(`Passo ${stepNumber} de 24`)
      const skipButton = page.getByTestId('tutorial-skip-step-button')
      if (await skipButton.isVisible()) await skipButton.click()
      else await page.getByTestId('tutorial-complete-step').click()

      const operationalRequests = requests.filter((url) => !isAllowedTutorialRequest(url))
      expect(operationalRequests).toEqual([])
    }

    await expect(page.getByTestId('tutorial-workspace')).toBeHidden()

    const operationalRequests = requests.filter((url) => !isAllowedTutorialRequest(url))
    expect(operationalRequests).toEqual([])
    await expectNoAppCrash(page)
  })
})
