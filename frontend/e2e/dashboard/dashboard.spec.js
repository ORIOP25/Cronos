import { test, expect } from '@playwright/test'
import { attachRuntimeGuards, expectRouteReady, goTo, loginAsAdminReal } from '../utils/clerk-helpers.js'

async function ensureFoundationComplete(page) {
  await goTo(page, '/foundation')
  const startDate = page.locator('input[type="date"]').first()
  if (await startDate.isVisible({ timeout: 5000 }).catch(() => false)) {
    await startDate.fill('2025-09-15')
    await page.locator('#school_hard_end_date').fill('2026-07-31')
    for (let step = 1; step < 8; step += 1) {
      await page.getByRole('button', { name: /seguinte/i }).click()
    }
    const automaticHolidays = page.getByRole('checkbox', { name: /feriados automáticos/i })
    await expect(automaticHolidays).not.toBeChecked()
    const draftSaveResponse = page.waitForResponse((response) => (
      response.url().includes('/api/v1/foundation/draft') &&
      response.request().method() === 'PUT' &&
      response.status() === 200
    ))
    await automaticHolidays.check()
    await draftSaveResponse
    await page.getByRole('button', { name: /seguinte/i }).click()
    await page.getByRole('button', { name: /^ativar escola$/i }).click()
    await page.waitForURL(/\/dashboard/, { timeout: 15000 })
  }
}

test.describe('Dashboard real backend', () => {
  test.beforeEach(async ({ page }) => {
    attachRuntimeGuards(page)
    await loginAsAdminReal(page)
    await ensureFoundationComplete(page)
  })

  test('loads dashboard command center from the live API', async ({ page }) => {
    const dashboardResponse = page.waitForResponse(
      (response) => response.url().includes('/api/v1/dashboard') && response.status() === 200,
      { timeout: 15000 },
    )

    await goTo(page, '/dashboard')
    await dashboardResponse

    await expectRouteReady(page, '/dashboard')
  })

  test('renders dashboard resource and operational sections without API mocks', async ({ page }) => {
    await goTo(page, '/dashboard')
    await expectRouteReady(page, '/dashboard')

    const preparationDashboard = page.getByTestId('preparation-dashboard')
    if (await preparationDashboard.isVisible().catch(() => false)) {
      await expect(preparationDashboard).toBeVisible()
      return
    }

    await expect(page.locator('[data-testid="resource-teachers"]')).toBeVisible({ timeout: 10000 })
    await expect(page.locator('[data-testid="resource-classes"]')).toBeVisible({ timeout: 10000 })
    await expect(page.locator('[data-testid="debt-summary"]')).toBeVisible({ timeout: 10000 })
    await expect(page.locator('[data-testid="schedule-health"]')).toBeVisible({ timeout: 10000 })
  })
})
