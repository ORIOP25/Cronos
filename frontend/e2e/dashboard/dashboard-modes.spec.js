import { expect, test } from '@playwright/test'
import {
  attachRuntimeGuards,
  expectNoAppCrash,
  goTo,
  loginAsAdminReal,
} from '../utils/clerk-helpers.js'

test.describe.configure({ mode: 'serial' })
test.use({ storageState: '.auth/admin.json' })

test.describe('Dashboard — canonical modes', () => {
  test('renders exactly one preparation or operational mode', async ({ page }) => {
    attachRuntimeGuards(page)
    await loginAsAdminReal(page)

    const dashboardResponse = page.waitForResponse((response) => (
      response.url().includes('/api/v1/dashboard') &&
      response.request().method() === 'GET'
    ))
    await goTo(page, '/dashboard')

    const payload = await (await dashboardResponse).json()
    expect(['PREPARATION', 'OPERATIONAL']).toContain(payload.mode)
    const preparation = page.getByTestId('preparation-dashboard')
    const operational = page.getByTestId('schedule-health')
    expect((await preparation.count()) + (await operational.count())).toBe(1)
    if (payload.mode === 'PREPARATION') {
      await expect(preparation).toBeVisible()
    } else {
      await expect(operational).toBeVisible()
    }
    await expectNoAppCrash(page)
  })
})
