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
  || url.includes('/api/v1/foundation/status')
  || url.includes('/api/v1/foundation/draft')
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
    await expect(page.getByTestId('guide-landing')).toBeVisible()
    await page.getByRole('button', { name: /conhecer o guia/i }).click()
    await expect(page.getByTestId('tutorial-workspace')).toBeVisible()
    await page.getByTestId('tutorial-skip-all-button').click()
    await expect(page.getByTestId('tutorial-workspace')).toHaveCount(0)

    const operationalRequests = requests.filter((url) => !isAllowedTutorialRequest(url))
    expect(operationalRequests).toEqual([])
    await expectNoAppCrash(page)
  })
})
