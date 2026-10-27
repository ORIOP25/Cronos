import { expect, test } from '@playwright/test'
import {
  attachRuntimeGuards,
  clickSidebarRoute,
  expectNoAppCrash,
  expectRouteReady,
  goTo,
  loginAsAdminReal,
  loginAsTeacherReal,
} from '../utils/clerk-helpers.js'

async function ensureFoundationComplete(page) {
  await goTo(page, '/foundation')

  const startDate = page.locator('#school_start_date')
  if (await startDate.isVisible({ timeout: 5000 }).catch(() => false)) {
    await startDate.fill('2025-09-15')
    await page.locator('#school_hard_end_date').fill('2026-07-31')
    for (let step = 1; step < 8; step += 1) {
      await page.getByRole('button', { name: /seguinte/i }).click()
    }
    const automaticHolidays = page.getByRole('checkbox', { name: /feriados automáticos/i })
    const draftSaveResponse = page.waitForResponse((response) => (
      response.url().includes('/api/v1/foundation/draft') &&
      response.request().method() === 'PUT' &&
      response.status() === 200
    ))
    await automaticHolidays.check()
    await draftSaveResponse
    await page.getByRole('button', { name: /seguinte/i }).click()
    await page.getByRole('button', { name: /ignorar por agora/i }).click()
    await page.getByRole('button', { name: /^ativar escola$/i }).click()
    await page.waitForURL(/\/dashboard/, { timeout: 15000 })
  }
}

test.describe('Real stack smoke', () => {
  test('admin can complete Foundation and click every admin sidebar route', async ({ page }, testInfo) => {
    attachRuntimeGuards(page)
    await loginAsAdminReal(page)
    await ensureFoundationComplete(page)
    await goTo(page, '/dashboard')
    await expectRouteReady(page, '/dashboard')

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
      await expectNoAppCrash(page)
      await expect(page.locator('.app-main .spinner-border')).toHaveCount(0)
      for (const width of [375, 768, 1440]) {
        await page.setViewportSize({ width, height: 1000 })
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
        await page.screenshot({ path: testInfo.outputPath(`${path.slice(1)}-${width}.png`), fullPage: true })
      }
    }
  })

  test('teacher can click every teacher sidebar route', async ({ page }, testInfo) => {
    attachRuntimeGuards(page)
    await loginAsTeacherReal(page)
    await goTo(page, '/my-availability')
    await expectRouteReady(page, '/my-availability')

    for (const path of ['/my-availability', '/my-schedules', '/my-progress']) {
      await clickSidebarRoute(page, path)
      await expectNoAppCrash(page)
      await expect(page.locator('.app-main .spinner-border')).toHaveCount(0)
      for (const width of [375, 768, 1440]) {
        await page.setViewportSize({ width, height: 1000 })
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
        await page.screenshot({ path: testInfo.outputPath(`${path.slice(1)}-${width}.png`), fullPage: true })
      }
    }
  })
})
