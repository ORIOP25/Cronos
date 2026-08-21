import { expect, test } from '@playwright/test'
import {
  attachRuntimeGuards,
  expectNoAppCrash,
  goTo,
  loginAsAdminReal,
} from '../utils/clerk-helpers.js'

test.describe.configure({ mode: 'serial' })

test.describe('Tutorial — network boundary', () => {
  test('uses local simulation only and sends telemetry without operational mutations', async ({ page }) => {
    attachRuntimeGuards(page)
    await loginAsAdminReal(page)
    await page.evaluate(() => {
      for (const key of Object.keys(localStorage)) {
        if (key.startsWith('cronos:tutorial:')) localStorage.removeItem(key)
      }
    })
    await goTo(page, '/guide')
    await expect(page.getByTestId('tutorial-modal')).toBeVisible()

    const requests = []
    page.on('request', (request) => {
      if (request.url().includes('/api/v1/')) requests.push(request.url())
    })

    await page.getByTestId('tutorial-next-button').click()
    await page.getByTestId('tutorial-skip-all-button').click()
    await expect(page.getByTestId('tutorial-modal')).toBeHidden()

    const operationalRequests = requests.filter((url) => !url.includes('/tutorial/telemetry'))
    expect(operationalRequests).toEqual([])
    await expectNoAppCrash(page)
  })
})
