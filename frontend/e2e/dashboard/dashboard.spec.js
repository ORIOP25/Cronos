import { test, expect } from '@playwright/test'
import { attachRuntimeGuards, expectRouteReady, goTo, loginAsAdminReal } from '../utils/clerk-helpers.js'

async function ensureOnboardingComplete(page) {
  await goTo(page, '/onboarding')
  const startDate = page.locator('input[type="date"]').first()
  if (await startDate.isVisible({ timeout: 5000 }).catch(() => false)) {
    await startDate.fill('2025-09-15')
    await page.locator('button[type="submit"]').click()
    await page.waitForURL(/\/dashboard/, { timeout: 15000 })
  }
}

test.describe('Dashboard real backend', () => {
  test.beforeEach(async ({ page }) => {
    attachRuntimeGuards(page)
    await loginAsAdminReal(page)
    await ensureOnboardingComplete(page)
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

    await expect(page.locator('[data-testid="resource-teachers"]')).toBeVisible({ timeout: 10000 })
    await expect(page.locator('[data-testid="resource-classes"]')).toBeVisible({ timeout: 10000 })
    await expect(page.locator('[data-testid="debt-summary"]')).toBeVisible({ timeout: 10000 })
    await expect(page.locator('[data-testid="schedule-health"]')).toBeVisible({ timeout: 10000 })
  })
})
