import { expect, test } from '@playwright/test'
import {
  attachRuntimeGuards,
  expectNoAppCrash,
  goTo,
  loginAsAdminReal,
} from '../utils/clerk-helpers.js'

test.describe.configure({ mode: 'serial' })

const isAllowedTutorialRequest = (url) => (
  url.includes('/api/v1/members/me')
  || url.includes('/api/v1/foundation/status')
  || url.includes('/api/v1/foundation/draft')
)

test.describe('Tutorial — network boundary', () => {
  test('uses local simulation only without telemetry or operational mutations', async ({ page }) => {
    await page.addInitScript(() => {
      for (const key of Object.keys(localStorage)) {
        if (key.startsWith('cronos:tutorial:')) localStorage.removeItem(key)
      }
    })
    await loginAsAdminReal(page)
    await expect(page.locator('main.app-main')).toBeVisible({ timeout: 30_000 })
    attachRuntimeGuards(page)

    await goTo(page, '/guide')
    await expect(page.getByTestId('guide-landing')).toBeVisible()
    await page.getByRole('button', { name: /conhecer o guia/i }).click()
    await expect(page.getByTestId('tutorial-workspace')).toBeVisible()

    const requests = []
    const telemetryRequests = []
    page.on('request', (request) => {
      if (request.url().includes('/api/v1/tutorial/telemetry')) telemetryRequests.push(request.url())
      if (
        request.url().includes('/api/v1/')
        && !['GET', 'HEAD', 'OPTIONS'].includes(request.method())
      ) {
        requests.push(request.url())
      }
    })
    await page.getByTestId('tutorial-skip-all-button').click()
    await expect(page.getByTestId('tutorial-workspace')).toHaveCount(0)

    const operationalRequests = requests.filter((url) => !isAllowedTutorialRequest(url))
    expect(operationalRequests).toEqual([])
    expect(telemetryRequests).toEqual([])
    await expectNoAppCrash(page)
  })
})
