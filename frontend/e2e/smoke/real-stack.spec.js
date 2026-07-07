import { test, expect } from '@playwright/test'
import {
  attachRuntimeGuards,
  clickSidebarRoute,
  goTo,
  loginAsAdminReal,
  loginAsTeacherReal,
} from '../utils/clerk-helpers.js'

async function ensureOnboardingComplete(page) {
  await goTo(page, '/onboarding')

  const startDate = page.locator('input[type="date"]').first()
  if (await startDate.isVisible({ timeout: 5000 }).catch(() => false)) {
    await startDate.fill('2025-09-15')
    await page.locator('button[type="submit"]').click()
    await page.waitForURL(/\/dashboard/, { timeout: 15000 })
  }
}

test.describe('Real stack smoke', () => {
  test('admin can complete onboarding and click every admin sidebar route', async ({ page }) => {
    attachRuntimeGuards(page)
    await loginAsAdminReal(page)
    await ensureOnboardingComplete(page)
    await goTo(page, '/dashboard')

    for (const path of [
      '/dashboard',
      '/schedules',
      '/absences',
      '/timesheets',
      '/courses',
      '/members',
      '/subjects',
      '/rooms',
      '/config',
    ]) {
      await clickSidebarRoute(page, path)
      await expect(page.locator('[data-testid="error-boundary"]')).toHaveCount(0)
    }
  })

  test('teacher can click every teacher sidebar route', async ({ page }) => {
    attachRuntimeGuards(page)
    await loginAsTeacherReal(page)
    await goTo(page, '/my-availability')

    for (const path of ['/my-availability', '/my-schedules', '/my-progress']) {
      await clickSidebarRoute(page, path)
      await expect(page.locator('[data-testid="error-boundary"]')).toHaveCount(0)
    }
  })
})
